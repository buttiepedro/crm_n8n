"""Registro de todos los modelos (necesario para Alembic y generate_ddl)."""

from app.db.models.accounts import WhatsAppAccount
from app.db.models.crm import (
    Lead,
    LeadFieldDefinition,
    LeadStageEvent,
    Note,
    Pipeline,
    PipelineStage,
)
from app.db.models.identity import ApiKey, AuthSession, User, UserPermission
from app.db.models.messaging import (
    Attachment,
    Contact,
    Conversation,
    Message,
    MessageStatusEvent,
)
from app.db.models.ops import EventLog, Setting, WebhookDelivery
from app.db.models.tags import ConversationTag, Tag

__all__ = [
    "ApiKey",
    "Attachment",
    "AuthSession",
    "Contact",
    "Conversation",
    "ConversationTag",
    "EventLog",
    "Lead",
    "LeadFieldDefinition",
    "LeadStageEvent",
    "Message",
    "MessageStatusEvent",
    "Note",
    "Pipeline",
    "PipelineStage",
    "Setting",
    "Tag",
    "User",
    "UserPermission",
    "WebhookDelivery",
    "WhatsAppAccount",
]
