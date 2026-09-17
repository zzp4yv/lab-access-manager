from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_admin
from app.models import Admin, LabUser, UserStatus
from app.provisioning.orchestrator import provision_user, purge_user, revoke_user
from app.schemas import LabUserOut, LabUserSummary, LabUserUpdate
from app.services.audit import log_action
from app.services.email import send_access_instructions

router = APIRouter(prefix="/api/users", tags=["users"])
settings = get_settings()


def _validate_upload(upload: UploadFile) -> None:
    ext = (upload.filename or "").rsplit(".", 1)[-1].lower() if "." in (upload.filename or "") else ""
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensão de arquivo não permitida: .{ext}",
        )


def _save_upload(upload: UploadFile, user_id: str) -> tuple[str, str]:
    _validate_upload(upload)
    user_dir = os.path.join(settings.UPLOAD_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{upload.filename}"
    dest_path = os.path.join(user_dir, safe_name)

    size = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    with open(dest_path, "wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(dest_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            f.write(chunk)
    return upload.filename, dest_path


@router.post("", response_model=LabUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    full_name: str = Form(...),
    matricula: str = Form(...),
    personal_email: str = Form(...),
    phone: str = Form(...),
    test_description: str = Form(...),
    access_days: int = Form(...),
    document: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Cadastro de novo usuário com atrito mínimo: um único formulário
    multipart contendo todos os campos obrigatórios + o documento
    anexado. O provisionamento nos ambientes é disparado imediatamente
    após a criação (síncrono aqui para feedback rápido ao admin; o
    scheduler também cobre qualquer pendência residual)."""

    if access_days <= 0 or access_days > settings.MAX_ACCESS_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"access_days deve estar entre 1 e {settings.MAX_ACCESS_DAYS}",
        )

    if db.query(LabUser).filter(LabUser.matricula == matricula).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Matrícula já cadastrada")

    now = datetime.utcnow()
    user = LabUser(
        full_name=full_name,
        matricula=matricula,
        personal_email=personal_email,
        phone=phone,
        test_description=test_description,
        access_days=access_days,
        starts_at=now,
        expires_at=now + timedelta(days=access_days),
        status=UserStatus.PENDING,
        created_by_admin_id=current_admin.id,
    )
    db.add(user)
    db.flush()

    if document is not None and document.filename:
        filename, path = _save_upload(document, user.id)
        user.document_filename = filename
        user.document_path = path

    db.commit()
    db.refresh(user)

    log_action(
        db,
        actor=current_admin.email,
        action="user_created",
        target_type="lab_user",
        target_id=user.id,
        details={"matricula": user.matricula, "access_days": access_days},
    )

    ok = provision_user(db, user)
    user.status = UserStatus.ACTIVE if ok else UserStatus.FAILED
    db.commit()
    db.refresh(user)

    log_action(
        db,
        actor="system",
        action="provision_completed" if ok else "provision_failed",
        target_type="lab_user",
        target_id=user.id,
    )

    if ok:
        send_access_instructions(user)

    return user


@router.get("", response_model=list[LabUserSummary])
def list_users(
    status_filter: UserStatus | None = None,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    query = db.query(LabUser)
    if status_filter:
        query = query.filter(LabUser.status == status_filter)
    return query.order_by(LabUser.created_at.desc()).all()


@router.get("/{user_id}", response_model=LabUserOut)
def get_user(
    user_id: str, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    user = db.get(LabUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    return user


@router.patch("/{user_id}", response_model=LabUserOut)
def update_user(
    user_id: str,
    payload: LabUserUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    user = db.get(LabUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    if user.status in (UserStatus.PURGED,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário com dados já purgados não pode ser editado"
        )

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)

    if "access_days" in changes:
        user.expires_at = user.starts_at + timedelta(days=user.access_days)

    db.commit()
    db.refresh(user)

    log_action(
        db,
        actor=current_admin.email,
        action="user_updated",
        target_type="lab_user",
        target_id=user.id,
        details=changes,
    )
    return user


@router.post("/{user_id}/retry-provisioning", response_model=LabUserOut)
def retry_provisioning(
    user_id: str, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    user = db.get(LabUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    was_active = user.status == UserStatus.ACTIVE
    ok = provision_user(db, user)
    user.status = UserStatus.ACTIVE if ok else UserStatus.FAILED
    db.commit()
    db.refresh(user)

    if ok and not was_active:
        send_access_instructions(user)

    log_action(
        db,
        actor=current_admin.email,
        action="provisioning_retried",
        target_type="lab_user",
        target_id=user.id,
        details={"success": ok},
    )
    return user


@router.post("/{user_id}/revoke-now", response_model=LabUserOut)
def revoke_now(
    user_id: str, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    """Revogação manual antecipada (antes do prazo expirar), solicitada
    por um administrador."""
    user = db.get(LabUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    if user.status in (UserStatus.REVOKED, UserStatus.PURGED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário já revogado/purgado")

    now = datetime.utcnow()
    ok = revoke_user(db, user)
    user.status = UserStatus.REVOKED
    user.revoked_at = now
    user.purge_after = now + timedelta(days=settings.DATA_RETENTION_DAYS_AFTER_REVOKE)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        actor=current_admin.email,
        action="user_revoked_manually",
        target_type="lab_user",
        target_id=user.id,
        details={"success": ok},
    )
    return user


@router.delete("/{user_id}")
def delete_user_permanently(
    user_id: str, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    """Exclusão definitiva e imediata: purga o usuário em todos os
    ambientes de provisionamento (sem esperar o prazo de retenção) e
    remove o registro do banco de dados. Ação irreversível."""
    user = db.get(LabUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    matricula = user.matricula
    ok = purge_user(db, user)

    log_action(
        db,
        actor=current_admin.email,
        action="user_deleted_permanently",
        target_type="lab_user",
        target_id=user.id,
        details={"matricula": matricula, "provisioning_purge_ok": ok},
    )

    db.delete(user)
    db.commit()
    return {"success": True, "provisioning_purge_ok": ok}


@router.post("/run-lifecycle-now")
def run_lifecycle_now(
    db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    """Dispara manualmente o ciclo de revogação/purga (útil para testes
    e para forçar a aplicação imediata de mudanças de política)."""
    from app.services.lifecycle import run_lifecycle_cycle

    result = run_lifecycle_cycle(db)
    log_action(
        db,
        actor=current_admin.email,
        action="lifecycle_run_manual",
        details=result,
    )
    return result
