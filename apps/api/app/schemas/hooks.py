"""Contratos Pydantic de los webhooks entrantes de n8n.

Fuente única de verdad: validan en runtime y generan la documentación OpenAPI
(/api/docs) para quien arma los workflows de n8n. Aceptan camelCase (alias)
y snake_case; responden en camelCase.
"""

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class TemplateContent(CamelModel):
    name: str
    language: str = "es_AR"
    components: list[dict[str, Any]] = Field(default_factory=list)


class OutboundMessageContent(CamelModel):
    type: Literal["text", "image", "document", "audio", "video", "template"]
    body: str | None = None  # texto del mensaje o caption de la media
    media_url: str | None = None  # URL descargable si type es media
    file_name: str | None = None  # para documents
    template: TemplateContent | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "OutboundMessageContent":
        if self.type == "text" and not self.body:
            raise ValueError("type=text requiere body")
        if self.type == "template" and self.template is None:
            raise ValueError("type=template requiere template")
        if self.type in {"image", "document", "audio", "video"} and not self.media_url:
            raise ValueError(f"type={self.type} requiere mediaUrl")
        return self


class N8nMessageIn(CamelModel):
    """POST /api/v1/hooks/n8n/messages — n8n responde a una conversación."""

    conversation_id: UUID | None = None  # opción A: id interno (viene en el webhook saliente)
    account_id: UUID | None = None  # opción B: cuenta + destinatario
    to: str | None = None  # wa_id E.164 sin '+'
    message: OutboundMessageContent

    @model_validator(mode="after")
    def _check_target(self) -> "N8nMessageIn":
        if self.conversation_id is None and not (self.account_id and self.to):
            raise ValueError("Se requiere conversationId, o bien accountId + to")
        return self


class N8nMessageOut(CamelModel):
    message_id: UUID
    status: str


class N8nNoteIn(CamelModel):
    """Nota interna: con externalKey hace upsert (crea si no existe, EDITA si
    existe); sin externalKey siempre crea una nueva."""

    external_key: str | None = None
    body: str = Field(min_length=1)


class N8nLeadIn(CamelModel):
    """POST /api/v1/hooks/n8n/leads — upsert de lead + notas desde n8n."""

    external_key: str | None = None  # idempotencia: mismo key → mismo lead
    conversation_id: UUID
    title: str | None = None
    value: Decimal | None = None
    currency: str | None = Field(None, min_length=3, max_length=3)
    pipeline_id: UUID | None = None  # null → pipeline por defecto
    stage_id: UUID | None = None
    stage_name: str | None = None  # alternativa amigable a stageId
    owner_user_email: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    notes: list[N8nNoteIn] = Field(default_factory=list)


class StageOut(CamelModel):
    id: UUID
    name: str


class NoteResultOut(CamelModel):
    id: UUID
    external_key: str | None
    created: bool


class N8nLeadOut(CamelModel):
    lead_id: UUID
    created: bool
    stage: StageOut
    notes: list[NoteResultOut]
