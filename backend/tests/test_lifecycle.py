from __future__ import annotations

from datetime import datetime, timedelta

from app.models import LabUser, UserStatus
from app.services.lifecycle import (
    provision_pending_users,
    purge_retained_users,
    revoke_expired_users,
    run_lifecycle_cycle,
)


def _make_user(db_session, **overrides) -> LabUser:
    now = datetime.utcnow()
    defaults = dict(
        full_name="Usuário Lifecycle",
        matricula=f"LC-{overrides.get('matricula_suffix', '0001')}",
        personal_email="lifecycle@example.com",
        phone="11900000000",
        test_description="Teste automatizado de ciclo de vida",
        access_days=1,
        starts_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),  # já expirado
        status=UserStatus.ACTIVE,
    )
    defaults.update({k: v for k, v in overrides.items() if k != "matricula_suffix"})
    user = LabUser(**defaults)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_revoke_expired_users_marks_revoked_and_sets_purge_after(db_session):
    user = _make_user(db_session, matricula_suffix="0001")

    count = revoke_expired_users(db_session)

    db_session.refresh(user)
    assert count == 1
    assert user.status == UserStatus.REVOKED
    assert user.revoked_at is not None
    assert user.purge_after is not None
    assert user.purge_after > user.revoked_at


def test_purge_retained_users_anonymizes_pii_after_retention(db_session):
    now = datetime.utcnow()
    user = _make_user(
        db_session,
        matricula_suffix="0002",
        status=UserStatus.REVOKED,
        revoked_at=now - timedelta(days=31),
        purge_after=now - timedelta(days=1),  # janela de retenção já passou
    )

    count = purge_retained_users(db_session)

    db_session.refresh(user)
    assert count == 1
    assert user.status == UserStatus.PURGED
    assert user.purged_at is not None
    assert user.full_name != "Usuário Lifecycle"
    assert user.personal_email == "removido@removido.invalid"


def test_provision_pending_users_marks_active_on_success(db_session):
    now = datetime.utcnow()
    user = _make_user(
        db_session,
        matricula_suffix="0004",
        status=UserStatus.PENDING,
        starts_at=now,
        expires_at=now + timedelta(days=5),
    )

    count = provision_pending_users(db_session)

    db_session.refresh(user)
    assert count == 1
    assert user.status == UserStatus.ACTIVE
    assert len(user.provisioning_records) == 4


def test_provision_pending_users_marks_failed_when_adapter_fails(db_session, monkeypatch):
    from app.services import lifecycle as lifecycle_module

    now = datetime.utcnow()
    _make_user(
        db_session,
        matricula_suffix="0005",
        status=UserStatus.PENDING,
        starts_at=now,
        expires_at=now + timedelta(days=5),
    )

    monkeypatch.setattr(lifecycle_module, "provision_user", lambda db, user: False)

    provision_pending_users(db_session)

    user = db_session.query(LabUser).filter(LabUser.matricula == "LC-0005").first()
    assert user.status == UserStatus.FAILED


def test_run_lifecycle_cycle_returns_summary(db_session):
    result = run_lifecycle_cycle(db_session)
    assert set(result.keys()) == {"provisioned", "revoked", "purged"}


def test_purge_does_not_touch_users_within_retention_window(db_session):
    now = datetime.utcnow()
    user = _make_user(
        db_session,
        matricula_suffix="0003",
        status=UserStatus.REVOKED,
        revoked_at=now - timedelta(days=5),
        purge_after=now + timedelta(days=25),  # ainda dentro da janela de 30 dias
    )

    count = purge_retained_users(db_session)

    db_session.refresh(user)
    assert count == 0
    assert user.status == UserStatus.REVOKED
