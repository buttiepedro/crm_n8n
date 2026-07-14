"""CRM: pipelines (embudo configurable), leads, historial y notas internas."""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPkMixin
from app.db.models.enums import (
    LeadSource,
    LeadSourceType,
    NoteAuthorSource,
    NoteAuthorSourceType,
)


class Pipeline(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "pipelines"

    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class PipelineStage(UUIDPkMixin, Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        # Deferrable: permite reordenar posiciones dentro de una transacción
        sa.UniqueConstraint(
            "pipeline_id", "position", name="uq_stage_position",
            deferrable=True, initially="DEFERRED",
        ),
        sa.CheckConstraint("outcome IN ('won', 'lost')", name="ck_stage_outcome"),
    )

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(sa.Text)
    is_terminal: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    outcome: Mapped[str | None] = mapped_column(sa.Text)  # 'won' | 'lost'


class Lead(UUIDPkMixin, TimestampedMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        sa.Index("idx_leads_stage", "pipeline_id", "stage_id",
                 postgresql_where=sa.text("deleted_at IS NULL")),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("conversations.id")
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pipelines.id"), nullable=False
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pipeline_stages.id"), nullable=False
    )
    # Clave idempotente para upsert desde el webhook de n8n
    external_key: Mapped[str | None] = mapped_column(sa.Text, unique=True)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(sa.CHAR(3), default="ARS")
    source: Mapped[LeadSource] = mapped_column(
        LeadSourceType, nullable=False, default=LeadSource.manual
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class LeadStageEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Historial de movimientos en el embudo (hechos inmutables, base de las
    métricas de conversión)."""

    __tablename__ = "lead_stage_events"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pipeline_stages.id")
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pipeline_stages.id"), nullable=False
    )
    moved_by: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 'user:<id>'|'webhook:<id>'


class Note(UUIDPkMixin, TimestampedMixin, Base):
    """Notas internas: viven en el chat y se asocian al lead de esa
    conversación. Creables/editables también desde el webhook de leads de n8n
    vía external_key (upsert por (lead_id, external_key))."""

    __tablename__ = "notes"
    __table_args__ = (
        sa.UniqueConstraint("lead_id", "external_key", name="uq_note_lead_external_key"),
        sa.CheckConstraint(
            "lead_id IS NOT NULL OR conversation_id IS NOT NULL",
            name="ck_note_lead_or_conversation",
        ),
        sa.Index("idx_notes_lead", "lead_id", postgresql_where=sa.text("deleted_at IS NULL")),
    )

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("conversations.id")
    )
    external_key: Mapped[str | None] = mapped_column(sa.Text)
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    author_source: Mapped[NoteAuthorSource] = mapped_column(
        NoteAuthorSourceType, nullable=False, default=NoteAuthorSource.user
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class LeadFieldDefinition(UUIDPkMixin, CreatedAtMixin, Base):
    """Campo custom definido por un admin y renderizado en el form de leads.
    El valor vive en Lead.attributes[key] — esta tabla solo define el esquema."""

    __tablename__ = "lead_field_definitions"
    __table_args__ = (
        sa.CheckConstraint("type IN ('text', 'number', 'date', 'select')", name="ck_field_def_type"),
    )

    key: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(sa.Text, nullable=False)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB)  # solo si type == "select"
