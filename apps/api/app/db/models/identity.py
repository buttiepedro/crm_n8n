"""Identidad y acceso: usuarios, permisos, sesiones y API keys de n8n."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPkMixin
from app.db.models.enums import UserRole, UserRoleType


class User(UUIDPkMixin, TimestampedMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)  # lowercase en app
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)  # argon2id
    role: Mapped[UserRole] = mapped_column(UserRoleType, nullable=False, default=UserRole.agent)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class UserPermission(Base):
    __tablename__ = "user_permissions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(sa.Text, primary_key=True)


class AuthSession(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)  # sha256
    # Step-up del panel de configuración: vigente hasta este instante
    config_panel_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(sa.Text)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ApiKey(UUIDPkMixin, CreatedAtMixin, Base):
    """API keys para los webhooks entrantes de n8n. El valor completo solo se
    muestra al crearla; acá vive el sha256 + un prefijo identificable."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
