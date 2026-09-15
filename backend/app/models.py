from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class UserStatus(str, enum.Enum):
    PENDING = "pending"        # cadastrado, aguardando provisionamento
    ACTIVE = "active"          # provisionado e com acesso válido
    REVOKED = "revoked"        # acesso expirado/revogado, dados ainda retidos
    PURGED = "purged"          # dados removidos dos ambientes (pós 30 dias)
    FAILED = "failed"          # provisionamento falhou em algum ambiente


class ProvisioningEnvironment(str, enum.Enum):
    LINUX_TARS = "linux_tars"
    LINUX_CASE = "linux_case"
    PANGOLIN_VPN = "pangolin_vpn"
    NEXT_TERM = "next_term"


class ProvisioningStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REVOKED = "revoked"
    PURGED = "purged"


class LabUser(Base):
    """Usuário externo/visitante com acesso temporário ao laboratório."""

    __tablename__ = "lab_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- Dados obrigatórios (cf. requisitos) ---------------------------
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    matricula: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    personal_email: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    test_description: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Descrição do que o usuário deseja testar no laboratório"
    )
    document_filename: Mapped[str] = mapped_column(String(300), nullable=True)
    document_path: Mapped[str] = mapped_column(String(500), nullable=True)

    # --- Controle de tempo de acesso ------------------------------------
    access_days: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # --- Estado ------------------------------------------------------
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.PENDING
    )
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    purged_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_access_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # --- Metadados -----------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_by_admin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admins.id"), nullable=True
    )

    created_by = relationship("Admin", back_populates="created_users")
    provisioning_records = relationship(
        "ProvisioningRecord", back_populates="user", cascade="all, delete-orphan"
    )

    def compute_expiration(self) -> None:
        self.expires_at = self.starts_at + timedelta(days=self.access_days)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return now >= self.expires_at


class ProvisioningRecord(Base):
    """Registro do estado de provisionamento de um usuário em um ambiente
    específico (uma linha por ambiente: linux_tars, linux_case,
    pangolin_vpn, next_term)."""

    __tablename__ = "provisioning_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("lab_users.id"), nullable=False)
    environment: Mapped[ProvisioningEnvironment] = mapped_column(
        Enum(ProvisioningEnvironment), nullable=False
    )
    status: Mapped[ProvisioningStatus] = mapped_column(
        Enum(ProvisioningStatus), nullable=False, default=ProvisioningStatus.PENDING
    )
    external_identifier: Mapped[str] = mapped_column(String(200), nullable=True)
    last_message: Mapped[str] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provisioned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    purged_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("LabUser", back_populates="provisioning_records")


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_users = relationship("LabUser", back_populates="created_by")


class AuditLog(Base):
    """Trilha de auditoria de ações administrativas e de ciclo de vida
    automático (criação, provisionamento, revogação, purga)."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(200), nullable=False, doc="admin email ou 'system'")
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str] = mapped_column(String(36), nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
