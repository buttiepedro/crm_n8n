"""Enums del dominio, mapeados a tipos ENUM nativos de PostgreSQL."""

import enum

import sqlalchemy as sa


class UserRole(str, enum.Enum):
    admin = "admin"
    supervisor = "supervisor"
    agent = "agent"


class WaAccountStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    error = "error"


class ConversationStatus(str, enum.Enum):
    open = "open"
    pending = "pending"
    closed = "closed"


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"
    received = "received"


# Orden de progresión de estados de entrega: nunca retroceder
# (Meta puede entregar `read` antes que `delivered` en reintentos).
MESSAGE_STATUS_ORDER: dict[MessageStatus, int] = {
    MessageStatus.queued: 0,
    MessageStatus.sent: 1,
    MessageStatus.delivered: 2,
    MessageStatus.read: 3,
}


class MessageOrigin(str, enum.Enum):
    whatsapp = "whatsapp"
    crm_user = "crm_user"
    n8n = "n8n"


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    sticker = "sticker"
    location = "location"
    contacts = "contacts"
    template = "template"
    interactive = "interactive"
    reaction = "reaction"
    unknown = "unknown"


class AttachmentDownloadStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class NoteAuthorSource(str, enum.Enum):
    user = "user"
    n8n_webhook = "n8n_webhook"


class LeadSource(str, enum.Enum):
    manual = "manual"
    n8n_webhook = "n8n_webhook"


def _pg_enum(py_enum: type[enum.Enum], name: str) -> sa.Enum:
    return sa.Enum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


UserRoleType = _pg_enum(UserRole, "user_role")
WaAccountStatusType = _pg_enum(WaAccountStatus, "wa_account_status")
ConversationStatusType = _pg_enum(ConversationStatus, "conversation_status")
MessageDirectionType = _pg_enum(MessageDirection, "message_direction")
MessageStatusType = _pg_enum(MessageStatus, "message_status")
MessageOriginType = _pg_enum(MessageOrigin, "message_origin")
MessageTypeType = _pg_enum(MessageType, "message_type")
AttachmentDownloadStatusType = _pg_enum(AttachmentDownloadStatus, "attachment_download_status")
NoteAuthorSourceType = _pg_enum(NoteAuthorSource, "note_author_source")
LeadSourceType = _pg_enum(LeadSource, "lead_source")
