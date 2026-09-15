"""Testes dos adaptadores de provisionamento em modo `live`, usando
dependências externas (httpx, paramiko) mockadas — sem nenhuma chamada
de rede real. Cobrem tanto o caminho de sucesso quanto o de falha."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models import LabUser, UserStatus
from app.provisioning.next_term import NextTermProvisioner
from app.provisioning.orchestrator import sync_last_access
from app.provisioning.pangolin import PangolinProvisioner


def _make_user() -> LabUser:
    now = datetime.utcnow()
    return LabUser(
        full_name="Grace Hopper",
        matricula="GH-0001",
        personal_email="grace@example.com",
        phone="11900001111",
        test_description="Testar compilador",
        access_days=3,
        starts_at=now,
        expires_at=now + timedelta(days=3),
        status=UserStatus.PENDING,
    )


class _FakeResponse:
    def __init__(self, json_data=None, ok=True):
        self._json = json_data or {}
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("HTTP error simulado")

    def json(self):
        return self._json


class _FakeHttpxClient:
    """Substitui httpx.Client como context manager, permitindo
    configurar respostas de sucesso/falha por teste."""

    def __init__(self, *, ok=True, external_id="ext-123", **kwargs):
        self._ok = ok
        self._external_id = external_id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _respond(self):
        if not self._ok:
            raise RuntimeError("Falha de conexão simulada")
        return _FakeResponse({"id": self._external_id, "occurredAt": "2026-09-10T12:00:00"})

    def post(self, *args, **kwargs):
        return self._respond()

    def get(self, *args, **kwargs):
        return self._respond()

    def delete(self, *args, **kwargs):
        return self._respond()


@pytest.fixture()
def live_mode(monkeypatch):
    monkeypatch.setenv("PROVISIONING_MODE", "live")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_pangolin_provision_success(monkeypatch, live_mode):
    adapter = PangolinProvisioner()
    monkeypatch.setattr(adapter, "_client", lambda: _FakeHttpxClient(ok=True, external_id="peer-1"))

    result = adapter.provision(_make_user())

    assert result.success is True
    assert result.external_identifier == "peer-1"


def test_pangolin_provision_failure_is_captured(monkeypatch, live_mode):
    adapter = PangolinProvisioner()
    monkeypatch.setattr(adapter, "_client", lambda: _FakeHttpxClient(ok=False))

    result = adapter.provision(_make_user())

    assert result.success is False
    assert "simulada" in result.message


def test_pangolin_revoke_and_purge_without_identifier_are_noop(live_mode):
    adapter = PangolinProvisioner()
    user = _make_user()

    assert adapter.revoke(user, None).success is True
    assert adapter.purge(user, None).success is True


def test_next_term_full_cycle_success(monkeypatch, live_mode):
    adapter = NextTermProvisioner()
    monkeypatch.setattr(adapter, "_client", lambda: _FakeHttpxClient(ok=True, external_id="grant-1"))

    user = _make_user()
    provisioned = adapter.provision(user)
    assert provisioned.success is True

    revoked = adapter.revoke(user, provisioned.external_identifier)
    assert revoked.success is True

    purged = adapter.purge(user, provisioned.external_identifier)
    assert purged.success is True

    last_access = adapter.check_last_access(user, provisioned.external_identifier)
    assert last_access == "2026-09-10T12:00:00"


def test_next_term_revoke_failure_is_captured(monkeypatch, live_mode):
    adapter = NextTermProvisioner()
    monkeypatch.setattr(adapter, "_client", lambda: _FakeHttpxClient(ok=False))

    result = adapter.revoke(_make_user(), "grant-1")
    assert result.success is False


def test_sync_last_access_updates_user_from_adapters(db_session, monkeypatch, live_mode):
    from app.provisioning import orchestrator as orch_module

    user = _make_user()
    user.status = UserStatus.ACTIVE
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    fake_adapter = MagicMock()
    fake_adapter.environment = list(orch_module.get_all_adapters())[0].environment
    fake_adapter.check_last_access.return_value = "2026-09-12T08:30:00"

    from app.models import ProvisioningRecord, ProvisioningStatus

    record = ProvisioningRecord(
        user_id=user.id,
        environment=fake_adapter.environment,
        status=ProvisioningStatus.SUCCESS,
        external_identifier="whatever",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setattr(orch_module, "get_all_adapters", lambda: [fake_adapter])

    sync_last_access(db_session, user)

    db_session.refresh(user)
    assert user.last_access_at == datetime(2026, 9, 12, 8, 30, 0)


def test_linux_ssh_provision_live_without_paramiko_fails_gracefully(monkeypatch, live_mode):
    """Em modo live, sem a lib paramiko instalada/mocada, o adaptador
    deve reportar falha de forma controlada (não deve lançar exceção)."""
    from app.provisioning.linux_ssh import LinuxSSHProvisioner
    from app.models import ProvisioningEnvironment

    # Garante que `import paramiko` falhe dentro do adaptador, simulando
    # um ambiente onde a dependência opcional não está instalada.
    monkeypatch.setitem(sys.modules, "paramiko", None)

    adapter = LinuxSSHProvisioner(host="tars", environment=ProvisioningEnvironment.LINUX_TARS)
    result = adapter.provision(_make_user())

    assert result.success is False
    assert "paramiko" in result.message.lower()


def test_linux_ssh_provision_live_with_mocked_paramiko_success(monkeypatch, live_mode):
    from app.provisioning.linux_ssh import LinuxSSHProvisioner
    from app.models import ProvisioningEnvironment

    fake_paramiko = types.ModuleType("paramiko")

    class _FakeChannel:
        def recv_exit_status(self):
            return 0

    class _FakeStream:
        def __init__(self, text=""):
            self.channel = _FakeChannel()
            self._text = text

        def read(self):
            return self._text.encode()

    class _FakeSSHClient:
        def set_missing_host_key_policy(self, policy):
            pass

        def connect(self, **kwargs):
            pass

        def exec_command(self, command, timeout=60):
            return None, _FakeStream("ok"), _FakeStream("")

        def close(self):
            pass

    fake_paramiko.SSHClient = _FakeSSHClient
    fake_paramiko.RejectPolicy = MagicMock
    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)

    adapter = LinuxSSHProvisioner(host="case", environment=ProvisioningEnvironment.LINUX_CASE)
    result = adapter.provision(_make_user())

    assert result.success is True
