"""Contactos, conversaciones, mensajes, estados de entrega y adjuntos."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPkMixin
from app.db.models.enums import (
    AttachmentDownloadStatus,
    AttachmentDownloadStatusType,
    ConversationStatus,
    ConversationStatusType,
    MessageDirection,
    MessageDirectionType,
    MessageOrigin,
    MessageOriginType,
    MessageStatus,
    MessageStatusType,
    MessageType,
    MessageTypeType,
)


class Contact(UUIDPkMixin, TimestampedMixin, Base):
    __tablename__ = "contacts"

    wa_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)  # E.164 sin '+'
    profile_name: Mapped[str | None] = mapped_column(sa.Text)
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )


class Conversation(UUIDPkMixin, TimestampedMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        sa.UniqueConstraint("whatsapp_account_id", "contact_id", name="uq_conversation_account_contact"),
        sa.Index("idx_conversations_inbox", "whatsapp_account_id", "status", "last_message_at"),
        sa.Index(
            "idx_conversations_assigned",
            "assigned_user_id",
            postgresql_where=sa.text("status <> 'closed'"),
        ),
    )

    whatsapp_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("whatsapp_accounts.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        ConversationStatusType, nullable=False, default=ConversationStatus.open
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Último mensaje ENTRANTE: define la ventana de 24h de WhatsApp
    last_inbound_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unread_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    # Silencia el bot (n8n) para esta conversación: el mensaje entrante se
    # persiste igual pero no se reenvía al webhook, así el bot no autorresponde
    # mientras un agente toma el control manual.
    bot_paused: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.text("false")
    )


class Message(UUIDPkMixin, CreatedAtMixin, Base):
    """Inmutable: los mensajes nunca se editan ni borran. El payload crudo de
    Meta se conserva íntegro en raw_payload (JSONB)."""

    __tablename__ = "messages"
    __table_args__ = (
        sa.Index("idx_messages_conversation", "conversation_id", "created_at"),
        sa.Index("idx_messages_account_created", "whatsapp_account_id", "created_at"),
        # Búsqueda full-text en español sobre body: índice GIN por migración manual
        # (expresión to_tsvector, no expresable en el modelo). Ver roadmap/base_de_datos.
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False
    )
    whatsapp_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("whatsapp_accounts.id"), nullable=False
    )
    wamid: Mapped[str | None] = mapped_column(sa.Text, unique=True)  # NULL hasta enviar
    direction: Mapped[MessageDirection] = mapped_column(MessageDirectionType, nullable=False)
    origin: Mapped[MessageOrigin] = mapped_column(MessageOriginType, nullable=False)
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id")
    )
    type: Mapped[MessageType] = mapped_column(MessageTypeType, nullable=False)
    body: Mapped[str | None] = mapped_column(sa.Text)  # texto o caption
    status: Mapped[MessageStatus] = mapped_column(MessageStatusType, nullable=False)
    error_detail: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("messages.id")
    )
    wa_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class MessageStatusEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Historial de estados de entrega (Meta manda sent/delivered/read como
    eventos separados). Inmutable."""

    __tablename__ = "message_status_events"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MessageStatus] = mapped_column(MessageStatusType, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Attachment(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[str | None] = mapped_column(sa.Text)  # id de media en Meta
    gcs_path: Mapped[str | None] = mapped_column(sa.Text)  # NULL hasta completar descarga
    mime_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(sa.Text)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    sha256: Mapped[str | None] = mapped_column(sa.Text)
    download_status: Mapped[AttachmentDownloadStatus] = mapped_column(
        AttachmentDownloadStatusType,
        nullable=False,
        default=AttachmentDownloadStatus.pending,
    )
