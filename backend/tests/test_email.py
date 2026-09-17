"""Testes do serviço de e-mail de instruções de acesso."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models import LabUser, ProvisioningEnvironment, ProvisioningRecord, ProvisioningStatus, UserStatus
from app.services.email import _build_body, send_access_instructions


def _make_user_with_records() -> LabUser:
    now = datetime.utcnow()
    user = LabUser(
        full_name="Grace Hopper",
        matricula="F0001",
        personal_email="grace@example.com",
        phone="11900001111",
        test_description="Testar compilador",
        access_days=3,
        starts_at=now,
        expires_at=now + timedelta(days=3),
        status=UserStatus.ACTIVE,
    )
    user.provisioning_records = [
        ProvisioningRecord(
            environment=ProvisioningEnvironment.NEXT_TERM,
            status=ProvisioningStatus.SUCCESS,
            external_identifier="graceF0001",
            last_message="criado — usuário: graceF0001 / senha inicial: AbC123XyZ (comunicar por canal seguro)",
        ),
        ProvisioningRecord(
            environment=ProvisioningEnvironment.PANGOLIN_VPN,
            status=ProvisioningStatus.SUCCESS,
            external_identifier="grace@example.com",
            last_message="convite criado — compartilhar com o visitante: https://pangolin.oxigenio.online/invite?token=abc",
        ),
        ProvisioningRecord(
            environment=ProvisioningEnvironment.LINUX_TARS,
            status=ProvisioningStatus.SUCCESS,
            external_identifier="lab-grace-f0001",
            last_message="ok",
        ),
        ProvisioningRecord(
            environment=ProvisioningEnvironment.LINUX_CASE,
            status=ProvisioningStatus.SUCCESS,
            external_identifier="lab-grace-f0001",
            last_message="ok",
        ),
    ]
    return user


def test_build_body_includes_nexterm_credentials_and_pangolin_link():
    body = _build_body(_make_user_with_records())

    assert "graceF0001" in body
    assert "AbC123XyZ" in body
    assert "https://pangolin.oxigenio.online/invite?token=abc" in body
    assert "lab-grace-f0001" in body


def test_send_access_instructions_skips_when_smtp_not_configured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    assert send_access_instructions(_make_user_with_records()) is True


def test_send_access_instructions_sends_via_smtp_when_configured(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "no-reply@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    from app.config import get_settings

    get_settings.cache_clear()

    fake_server = MagicMock()
    fake_smtp_cm = MagicMock()
    fake_smtp_cm.__enter__.return_value = fake_server
    fake_smtp_cm.__exit__.return_value = False

    import app.services.email as email_module

    monkeypatch.setattr(email_module.smtplib, "SMTP", lambda *a, **k: fake_smtp_cm)

    result = send_access_instructions(_make_user_with_records())

    assert result is True
    fake_server.starttls.assert_called_once()
    fake_server.login.assert_called_once_with("no-reply@example.com", "secret")
    fake_server.send_message.assert_called_once()

    get_settings.cache_clear()


def test_send_access_instructions_returns_false_on_smtp_error(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    from app.config import get_settings

    get_settings.cache_clear()

    import app.services.email as email_module

    def _raise(*args, **kwargs):
        raise RuntimeError("conexão recusada")

    monkeypatch.setattr(email_module.smtplib, "SMTP", _raise)

    assert send_access_instructions(_make_user_with_records()) is False

    get_settings.cache_clear()
