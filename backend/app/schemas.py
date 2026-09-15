from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import ProvisioningEnvironment, ProvisioningStatus, UserStatus


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminOut


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
class AdminCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AdminUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class AdminOut(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------
class ProvisioningRecordOut(BaseModel):
    environment: ProvisioningEnvironment
    status: ProvisioningStatus
    external_identifier: str | None = None
    last_message: str | None = None
    attempts: int
    provisioned_at: datetime | None = None
    revoked_at: datetime | None = None
    purged_at: datetime | None = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Lab User
# ---------------------------------------------------------------------------
class LabUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    matricula: str = Field(min_length=1, max_length=50)
    personal_email: EmailStr
    phone: str = Field(min_length=8, max_length=30)
    test_description: str = Field(
        min_length=5,
        max_length=4000,
        description="O que o usuário deseja testar no laboratório",
    )
    access_days: int = Field(gt=0, le=365)

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, v: str) -> str:
        return v.strip()


class LabUserUpdate(BaseModel):
    full_name: str | None = None
    personal_email: EmailStr | None = None
    phone: str | None = None
    test_description: str | None = None
    access_days: int | None = Field(default=None, gt=0, le=365)


class LabUserOut(BaseModel):
    id: str
    full_name: str
    matricula: str
    personal_email: EmailStr
    phone: str
    test_description: str
    document_filename: str | None = None
    access_days: int
    starts_at: datetime
    expires_at: datetime
    status: UserStatus
    revoked_at: datetime | None = None
    purge_after: datetime | None = None
    purged_at: datetime | None = None
    last_access_at: datetime | None = None
    created_at: datetime
    provisioning_records: list[ProvisioningRecordOut] = []

    class Config:
        from_attributes = True


class LabUserSummary(BaseModel):
    """Versão resumida usada na listagem/tabela principal."""

    id: str
    full_name: str
    matricula: str
    status: UserStatus
    expires_at: datetime
    last_access_at: datetime | None = None

    class Config:
        from_attributes = True


class AccessEvent(BaseModel):
    """Payload aceito no webhook de registro de acesso (chamado pelos
    ambientes provisionados, ou por um job de sincronização, para
    reportar o último login de um usuário)."""

    matricula: str
    environment: ProvisioningEnvironment
    occurred_at: datetime | None = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    pending_users: int
    revoked_users: int
    purged_users: int
    failed_users: int
    expiring_in_7_days: int
    users_by_environment_status: dict
