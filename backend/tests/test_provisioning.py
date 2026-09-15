from __future__ import annotations

from datetime import datetime, timedelta

from app.models import LabUser, ProvisioningStatus, UserStatus
from app.provisioning.orchestrator import get_all_adapters, provision_user, purge_user, revoke_user


def _make_user() -> LabUser:
    now = datetime.utcnow()
    return LabUser(
        full_name="Ada Lovelace",
        matricula="ADA-0001",
        personal_email="ada@example.com",
        phone="11911112222",
        test_description="Testar pipeline de fine-tuning",
        access_days=7,
        starts_at=now,
        expires_at=now + timedelta(days=7),
        status=UserStatus.PENDING,
    )


def test_all_adapters_registered_for_required_environments():
    envs = {a.environment.value for a in get_all_adapters()}
    assert envs == {"linux_tars", "linux_case", "pangolin_vpn", "next_term"}


def test_provision_user_creates_one_record_per_environment(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    ok = provision_user(db_session, user)

    db_session.refresh(user)
    assert ok is True
    assert len(user.provisioning_records) == 4
    assert all(r.status == ProvisioningStatus.SUCCESS for r in user.provisioning_records)
    assert all(r.external_identifier for r in user.provisioning_records)


def test_revoke_then_purge_updates_all_records(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    provision_user(db_session, user)
    revoke_user(db_session, user)
    db_session.refresh(user)
    assert all(r.status == ProvisioningStatus.REVOKED for r in user.provisioning_records)

    purge_user(db_session, user)
    db_session.refresh(user)
    assert all(r.status == ProvisioningStatus.PURGED for r in user.provisioning_records)
