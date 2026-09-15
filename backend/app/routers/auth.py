from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Admin
from app.schemas import AdminOut, LoginRequest, TokenResponse
from app.security import create_access_token, verify_password
from app.services.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == payload.email.lower()).first()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos"
        )
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrador inativo")

    admin.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(admin)

    log_action(db, actor=admin.email, action="admin_login", target_type="admin", target_id=admin.id)

    token = create_access_token(subject=admin.email)
    return TokenResponse(access_token=token, admin=AdminOut.model_validate(admin))


@router.get("/me", response_model=AdminOut)
def me(current_admin: Admin = Depends(get_current_admin)):
    return current_admin
