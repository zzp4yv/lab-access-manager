from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_admin(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    email = decode_access_token(token)
    if not email:
        raise credentials_exception

    admin = db.query(Admin).filter(Admin.email == email).first()
    if not admin or not admin.is_active:
        raise credentials_exception
    return admin
