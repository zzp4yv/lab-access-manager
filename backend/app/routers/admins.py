from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Admin
from app.schemas import AdminCreate, AdminOut, AdminUpdate
from app.security import hash_password
from app.services.audit import log_action

router = APIRouter(prefix="/api/admins", tags=["admins"])

# Nota de requisito: "Administrador listado na mesma interface de
# usuários" / "Administrador não precisa ser provisionado nos
# ambientes" — por isso este router não chama o orquestrador de
# provisionamento em nenhum momento. O frontend (users.html) exibe
# uma aba/seção "Administradores" ao lado da lista de usuários,
# consumindo estes mesmos endpoints.


@router.get("", response_model=list[AdminOut])
def list_admins(db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    return db.query(Admin).order_by(Admin.created_at.desc()).all()


@router.post("", response_model=AdminOut, status_code=status.HTTP_201_CREATED)
def create_admin(
    payload: AdminCreate, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)
):
    email = payload.email.lower()
    if db.query(Admin).filter(Admin.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado")

    admin = Admin(full_name=payload.full_name, email=email, hashed_password=hash_password(payload.password))
    db.add(admin)
    db.commit()
    db.refresh(admin)

    log_action(
        db,
        actor=current_admin.email,
        action="admin_created",
        target_type="admin",
        target_id=admin.id,
        details={"email": email},
    )
    return admin


@router.patch("/{admin_id}", response_model=AdminOut)
def update_admin(
    admin_id: str,
    payload: AdminUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    admin = db.get(Admin, admin_id)
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Administrador não encontrado")

    if admin.id == current_admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível desativar a própria conta"
        )

    changes = payload.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(admin, field, value)
    if payload.password:
        admin.hashed_password = hash_password(payload.password)
        changes["password"] = "***alterada***"

    db.commit()
    db.refresh(admin)

    log_action(
        db,
        actor=current_admin.email,
        action="admin_updated",
        target_type="admin",
        target_id=admin.id,
        details=changes,
    )
    return admin
