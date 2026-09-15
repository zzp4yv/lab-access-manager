"""Regras de ciclo de vida automático do acesso:

  1. Quando `now >= expires_at` e o usuário está ACTIVE (ou FAILED),
     revoga o acesso em todos os ambientes e marca REVOKED, definindo
     `purge_after = revoked_at + DATA_RETENTION_DAYS_AFTER_REVOKE`.
  2. Quando `now >= purge_after` e o usuário está REVOKED, remove os
     dados nos ambientes e marca PURGED, além de anonimizar os campos
     pessoais no próprio banco de dados (LGPD).

Este módulo é chamado periodicamente pelo scheduler (`scheduler.py`) e
também pode ser invocado manualmente por um administrador via endpoint
(`/api/users/{id}/revoke-now`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LabUser, UserStatus
from app.provisioning.orchestrator import provision_user, purge_user, revoke_user, sync_last_access
from app.services.audit import log_action

logger = logging.getLogger("services.lifecycle")
settings = get_settings()


def provision_pending_users(db: Session) -> int:
    """Provisiona usuários recém-cadastrados (status PENDING) em todos os
    ambientes. Retorna quantos foram processados."""
    pending = db.query(LabUser).filter(LabUser.status == UserStatus.PENDING).all()
    count = 0
    for user in pending:
        ok = provision_user(db, user)
        user.status = UserStatus.ACTIVE if ok else UserStatus.FAILED
        db.commit()
        log_action(
            db,
            actor="system",
            action="provision_completed" if ok else "provision_failed",
            target_type="lab_user",
            target_id=user.id,
        )
        count += 1
    return count


def revoke_expired_users(db: Session) -> int:
    """Revoga automaticamente usuários cujo prazo de acesso expirou."""
    now = datetime.utcnow()
    expired = (
        db.query(LabUser)
        .filter(LabUser.status.in_([UserStatus.ACTIVE, UserStatus.FAILED]))
        .filter(LabUser.expires_at <= now)
        .all()
    )
    count = 0
    for user in expired:
        ok = revoke_user(db, user)
        user.status = UserStatus.REVOKED
        user.revoked_at = now
        user.purge_after = now + timedelta(days=settings.DATA_RETENTION_DAYS_AFTER_REVOKE)
        db.commit()
        log_action(
            db,
            actor="system",
            action="access_revoked_expired" if ok else "access_revoked_with_errors",
            target_type="lab_user",
            target_id=user.id,
            details={"expires_at": str(user.expires_at)},
        )
        count += 1
    return count


def purge_retained_users(db: Session) -> int:
    """Remove dados de usuários revogados há mais de
    DATA_RETENTION_DAYS_AFTER_REVOKE dias, e anonimiza o registro no
    banco (mantendo apenas o necessário para auditoria)."""
    now = datetime.utcnow()
    to_purge = (
        db.query(LabUser)
        .filter(LabUser.status == UserStatus.REVOKED)
        .filter(LabUser.purge_after.isnot(None))
        .filter(LabUser.purge_after <= now)
        .all()
    )
    count = 0
    for user in to_purge:
        ok = purge_user(db, user)
        if ok:
            user.status = UserStatus.PURGED
            user.purged_at = now
            # Anonimização de PII, mantendo trilha de auditoria (matrícula
            # e datas) conforme política de retenção de 30 dias.
            user.full_name = "Dados removidos (LGPD)"
            user.personal_email = "removido@removido.invalid"
            user.phone = "-"
            user.test_description = "-"
            if user.document_path:
                _delete_local_file(user.document_path)
                user.document_path = None
                user.document_filename = None
            db.commit()
            log_action(
                db, actor="system", action="user_data_purged", target_type="lab_user", target_id=user.id
            )
            count += 1
        else:
            log_action(
                db,
                actor="system",
                action="user_purge_failed",
                target_type="lab_user",
                target_id=user.id,
            )
    return count


def _delete_local_file(path: str) -> None:
    import os

    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:  # pragma: no cover
        logger.warning("Falha ao remover arquivo local %s: %s", path, exc)


def sync_all_last_access(db: Session) -> None:
    active_users = db.query(LabUser).filter(LabUser.status == UserStatus.ACTIVE).all()
    for user in active_users:
        sync_last_access(db, user)


def run_lifecycle_cycle(db: Session) -> dict:
    """Executa um ciclo completo: provisiona pendentes, revoga expirados,
    purga retidos e sincroniza último acesso. Usado tanto pelo scheduler
    quanto por um endpoint administrativo de execução manual."""
    provisioned = provision_pending_users(db)
    revoked = revoke_expired_users(db)
    purged = purge_retained_users(db)
    sync_all_last_access(db)
    result = {"provisioned": provisioned, "revoked": revoked, "purged": purged}
    logger.info("Ciclo de vida executado: %s", result)
    return result
