"""Operación: configuración, auditoría de negocio y entregas de webhooks."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPkMixin


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(),
        nullable=False,
    )


class EventLog(UUIDPkMixin, CreatedAtMixin, Base):
    """Auditoría de negocio (quién hizo qué). Inmutable: sin UPDATE/DELETE."""

    __tablename__ = "event_logs"
    __table_args__ = (
        sa.Index("idx_event_logs_entity", "entity_type", "entity_id", "created_at"),
        sa.Index("idx_event_logs_created", "created_at"),
    )

    actor_type: Mapped[str] = mapped_column(sa.Text, nullable=False)  # user|api_key|system|meta
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 'lead.stage_changed', …
    entity_type: Mapped[str | None] = mapped_column(sa.Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    trace_id: Mapped[str | None] = mapped_column(sa.Text)  # correlación con Cloud Logging


class WebhookDelivery(UUIDPkMixin, CreatedAtMixin, Base):
    """Trazabilidad de cada entrega (con reintentos) hacia n8n."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        sa.Index(
            "idx_webhook_deliveries_pending",
            "next_retry_at",
            postgresql_where=sa.text("succeeded = false"),
        ),
    )

    whatsapp_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("whatsapp_accounts.id"), nullable=False
    )
    target_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 'message.received'
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    response_status: Mapped[int | None] = mapped_column(sa.Integer)
    response_body: Mapped[str | None] = mapped_column(sa.Text)  # truncado a 4KB
    succeeded: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
