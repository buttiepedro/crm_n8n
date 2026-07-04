"""Registro de todos los modelos (necesario para Alembic y generate_ddl)."""

from app.db.models.accounts import WhatsAppAccount
from app.db.models.crm import Lead, LeadStageEvent, Note, Pipeline, PipelineStage
from app.db.models.identity import ApiKey, AuthSession, User, UserPermission
from app.db.models.messaging import (
    Attachment,
    Contact,
    Conversation,
    Message,
    MessageStatusEvent,
)
from app.db.models.ops import EventLog, Setting, WebhookDelivery

__all__ = [
    "ApiKey",
    "Attachment",
    "AuthSession",
    "Contact",
    "Conversation",
    "EventLog",
    "Lead",
    "LeadStageEvent",
    "Message",
    "MessageStatusEvent",
    "Note",
    "Pipeline",
    "PipelineStage",
    "Setting",
    "User",
    "UserPermission",
    "WebhookDelivery",
    "WhatsAppAccount",
]
