"""Orquestra o provisionamento/revogação/purga de um LabUser em todos os
ambientes configurados (Linux tars/case, Pangolin VPN, Next Term).

Cada ambiente é independente: uma falha em um ambiente não impede a
tentativa nos demais, e o estado de cada um fica registrado em sua
própria linha de `ProvisioningRecord`. Se qualquer ambiente falhar, o
usuário fica com status `FAILED` para chamar atenção do administrador
(ver `routers/users.py`), mas os ambientes que tiveram sucesso
permanecem provisionados — retry é feito reexecutando a mesma operação
(idempotente) via endpoint `/api/users/{id}/retry-provisioning`.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import LabUser, ProvisioningRecord, ProvisioningStatus
from app.provisioning.base import ProvisioningAdapter
from app.provisioning.linux_ssh import build_linux_provisioners
from app.provisioning.next_term import NextTermProvisioner
from app.provisioning.pangolin import PangolinProvisioner

logger = logging.getLogger("provisioning.orchestrator")


def get_all_adapters() -> list[ProvisioningAdapter]:
    adapters: list[ProvisioningAdapter] = []
    adapters.extend(build_linux_provisioners())
    adapters.append(PangolinProvisioner())
    adapters.append(NextTermProvisioner())
    return adapters


def _get_or_create_record(db: Session, user: LabUser, adapter: ProvisioningAdapter) -> ProvisioningRecord:
    record = next(
        (r for r in user.provisioning_records if r.environment == adapter.environment), None
    )
    if record is None:
        record = ProvisioningRecord(user_id=user.id, environment=adapter.environment)
        db.add(record)
        db.flush()
    return record


def provision_user(db: Session, user: LabUser) -> bool:
    """Provisiona o usuário em todos os ambientes. Retorna True se todos
    os ambientes tiveram sucesso."""
    all_ok = True
    for adapter in get_all_adapters():
        record = _get_or_create_record(db, user, adapter)
        record.attempts += 1
        result = adapter.provision(user)
        record.last_message = result.message
        record.updated_at = datetime.utcnow()
        if result.success:
            record.status = ProvisioningStatus.SUCCESS
            record.external_identifier = result.external_identifier
            record.provisioned_at = datetime.utcnow()
        else:
            record.status = ProvisioningStatus.FAILED
            all_ok = False
            logger.error(
                "Falha ao provisionar usuário %s em %s: %s",
                user.matricula,
                adapter.environment,
                result.message,
            )
    db.commit()
    return all_ok


def revoke_user(db: Session, user: LabUser) -> bool:
    """Revoga o acesso do usuário em todos os ambientes onde havia sido
    provisionado (mantém os dados até a purga)."""
    all_ok = True
    for adapter in get_all_adapters():
        record = _get_or_create_record(db, user, adapter)
        if record.status not in (ProvisioningStatus.SUCCESS, ProvisioningStatus.FAILED):
            continue
        result = adapter.revoke(user, record.external_identifier)
        record.last_message = result.message
        record.updated_at = datetime.utcnow()
        if result.success:
            record.status = ProvisioningStatus.REVOKED
            record.revoked_at = datetime.utcnow()
        else:
            all_ok = False
            logger.error(
                "Falha ao revogar usuário %s em %s: %s", user.matricula, adapter.environment, result.message
            )
    db.commit()
    return all_ok


def purge_user(db: Session, user: LabUser) -> bool:
    """Remove definitivamente os dados do usuário em todos os ambientes
    (chamado 30 dias após a revogação)."""
    all_ok = True
    for adapter in get_all_adapters():
        record = _get_or_create_record(db, user, adapter)
        if record.status == ProvisioningStatus.PURGED:
            continue
        result = adapter.purge(user, record.external_identifier)
        record.last_message = result.message
        record.updated_at = datetime.utcnow()
        if result.success:
            record.status = ProvisioningStatus.PURGED
            record.purged_at = datetime.utcnow()
        else:
            all_ok = False
            logger.error(
                "Falha ao purgar usuário %s em %s: %s", user.matricula, adapter.environment, result.message
            )
    db.commit()
    return all_ok


def sync_last_access(db: Session, user: LabUser) -> None:
    """Consulta os adaptadores que suportam `check_last_access` e
    atualiza `last_access_at` com o timestamp mais recente encontrado."""
    latest: datetime | None = None
    for adapter in get_all_adapters():
        record = next(
            (r for r in user.provisioning_records if r.environment == adapter.environment), None
        )
        if not record or record.status != ProvisioningStatus.SUCCESS:
            continue
        raw = adapter.check_last_access(user, record.external_identifier)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        if latest is None or ts > latest:
            latest = ts

    if latest and (user.last_access_at is None or latest > user.last_access_at):
        user.last_access_at = latest
        db.commit()
