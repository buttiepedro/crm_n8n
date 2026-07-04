"""Servicio de leads: upsert transaccional usado por el webhook de n8n
(y por la API del CRM en P3 — una sola implementación de reglas).

Semántica del upsert (ver roadmap/next_steps_webhooks_n8n.md):
1. Lead: por external_key → si no, lead activo de la conversación → si no, crear.
   Merge parcial: solo se actualizan los campos presentes en el payload.
2. Etapa: cambio registrado en lead_stage_events con el actor.
3. Notas: upsert por (lead_id, external_key) — crea si no existe, EDITA si
   existe. Sin external_key siempre crea.
4. Notas huérfanas de la conversación se re-asocian al lead.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, StageAmbiguousError
from app.db.models import (
    Contact,
    Conversation,
    Lead,
    LeadStageEvent,
    Note,
    Pipeline,
    PipelineStage,
    User,
)
from app.db.models.enums import LeadSource, NoteAuthorSource
from app.modules.audit.service import log_event
from app.schemas.hooks import N8nLeadIn, N8nLeadOut, NoteResultOut, StageOut

log = structlog.get_logger()


async def upsert_lead_from_webhook(
    session: AsyncSession, data: N8nLeadIn, *, api_key_id: uuid.UUID
) -> N8nLeadOut:
    conversation = await session.get(Conversation, data.conversation_id)
    if conversation is None:
        raise NotFoundError("conversationId no corresponde a una conversación existente")

    lead, created = await _find_or_create_lead(session, data, conversation, api_key_id)

    if not created:
        await _merge_lead_fields(session, lead, data)
        target_stage = await _resolve_stage(session, lead.pipeline_id, data)
        if target_stage is not None and target_stage.id != lead.stage_id:
            session.add(
                LeadStageEvent(
                    lead_id=lead.id,
                    from_stage_id=lead.stage_id,
                    to_stage_id=target_stage.id,
                    moved_by=f"webhook:{api_key_id}",
                )
            )
            lead.stage_id = target_stage.id

    note_results = await _upsert_notes(session, lead, conversation, data)

    await log_event(
        session,
        actor_type="api_key",
        actor_id=api_key_id,
        action="lead.upserted_via_webhook",
        entity_type="lead",
        entity_id=lead.id,
        metadata={"created": created, "externalKey": data.external_key,
                  "notes": len(data.notes)},
    )
    await session.commit()

    stage = await session.get(PipelineStage, lead.stage_id)
    return N8nLeadOut(
        lead_id=lead.id,
        created=created,
        stage=StageOut(id=stage.id, name=stage.name),
        notes=note_results,
    )


async def _find_or_create_lead(
    session: AsyncSession, data: N8nLeadIn, conversation: Conversation, api_key_id: uuid.UUID
) -> tuple[Lead, bool]:
    lead: Lead | None = None

    if data.external_key:
        result = await session.execute(
            sa.select(Lead).where(Lead.external_key == data.external_key)
        )
        lead = result.scalar_one_or_none()

    if lead is None:
        result = await session.execute(
            sa.select(Lead)
            .join(PipelineStage, Lead.stage_id == PipelineStage.id)
            .where(
                Lead.conversation_id == conversation.id,
                Lead.deleted_at.is_(None),
                PipelineStage.is_terminal.is_(False),
            )
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        lead = result.scalar_one_or_none()
        if lead is not None and data.external_key and lead.external_key is None:
            lead.external_key = data.external_key  # adopta la clave para futuros upserts

    if lead is not None:
        return lead, False

    # Crear lead nuevo
    pipeline = await _resolve_pipeline(session, data.pipeline_id)
    stage = await _resolve_stage(session, pipeline.id, data)
    if stage is None:
        stage = await _first_stage(session, pipeline.id)

    contact = await session.get(Contact, conversation.contact_id)
    title = data.title or f"Lead {contact.profile_name or contact.wa_id}"

    lead = Lead(
        contact_id=conversation.contact_id,
        conversation_id=conversation.id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        external_key=data.external_key,
        title=title,
        value=data.value,
        currency=data.currency or "ARS",
        source=LeadSource.n8n_webhook,
        attributes=data.attributes or {},
        owner_user_id=await _resolve_owner(session, data.owner_user_email),
    )
    session.add(lead)
    await session.flush()

    session.add(
        LeadStageEvent(
            lead_id=lead.id, from_stage_id=None, to_stage_id=stage.id,
            moved_by=f"webhook:{api_key_id}",
        )
    )
    # Re-asociar notas huérfanas de la conversación (creadas antes que el lead)
    await session.execute(
        sa.update(Note)
        .where(Note.conversation_id == conversation.id, Note.lead_id.is_(None))
        .values(lead_id=lead.id)
    )
    return lead, True


async def _merge_lead_fields(session: AsyncSession, lead: Lead, data: N8nLeadIn) -> None:
    """Merge parcial: el upsert de n8n no pisa campos que no envía."""
    provided = data.model_fields_set
    if "title" in provided and data.title:
        lead.title = data.title
    if "value" in provided:
        lead.value = data.value
    if "currency" in provided and data.currency:
        lead.currency = data.currency
    if "attributes" in provided and data.attributes:
        lead.attributes = {**lead.attributes, **data.attributes}
    if "owner_user_email" in provided and data.owner_user_email:
        owner_id = await _resolve_owner(session, data.owner_user_email)
        if owner_id is not None:
            lead.owner_user_id = owner_id


async def _resolve_pipeline(session: AsyncSession, pipeline_id: uuid.UUID | None) -> Pipeline:
    if pipeline_id is not None:
        pipeline = await session.get(Pipeline, pipeline_id)
        if pipeline is None:
            raise NotFoundError("pipelineId inexistente")
        return pipeline
    result = await session.execute(sa.select(Pipeline).where(Pipeline.is_default.is_(True)))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise NotFoundError("No hay pipeline por defecto configurado (correr el seed)")
    return pipeline


async def _resolve_stage(
    session: AsyncSession, pipeline_id: uuid.UUID, data: N8nLeadIn
) -> PipelineStage | None:
    if data.stage_id is not None:
        stage = await session.get(PipelineStage, data.stage_id)
        if stage is None or stage.pipeline_id != pipeline_id:
            raise NotFoundError("stageId inexistente o de otro pipeline")
        return stage
    if data.stage_name:
        result = await session.execute(
            sa.select(PipelineStage).where(
                PipelineStage.pipeline_id == pipeline_id,
                sa.func.lower(PipelineStage.name) == data.stage_name.lower(),
            )
        )
        stages = result.scalars().all()
        if not stages:
            raise NotFoundError(f"No existe la etapa '{data.stage_name}' en el pipeline")
        if len(stages) > 1:
            raise StageAmbiguousError(f"Etapa '{data.stage_name}' ambigua; usar stageId")
        return stages[0]
    return None


async def _first_stage(session: AsyncSession, pipeline_id: uuid.UUID) -> PipelineStage:
    result = await session.execute(
        sa.select(PipelineStage)
        .where(PipelineStage.pipeline_id == pipeline_id)
        .order_by(PipelineStage.position)
        .limit(1)
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise NotFoundError("El pipeline no tiene etapas")
    return stage


async def _resolve_owner(session: AsyncSession, email: str | None) -> uuid.UUID | None:
    if not email:
        return None
    result = await session.execute(
        sa.select(User.id).where(User.email == email.lower(), User.is_active.is_(True))
    )
    owner_id = result.scalar_one_or_none()
    if owner_id is None:
        log.warning("lead_owner_email_not_found", email=email)
    return owner_id


async def _upsert_notes(
    session: AsyncSession, lead: Lead, conversation: Conversation, data: N8nLeadIn
) -> list[NoteResultOut]:
    results: list[NoteResultOut] = []
    for note_in in data.notes:
        existing: Note | None = None
        if note_in.external_key:
            result = await session.execute(
                sa.select(Note).where(
                    Note.lead_id == lead.id, Note.external_key == note_in.external_key
                )
            )
            existing = result.scalar_one_or_none()

        if existing is not None:
            existing.body = note_in.body
            existing.updated_at = datetime.now(UTC)
            results.append(
                NoteResultOut(id=existing.id, external_key=note_in.external_key, created=False)
            )
        else:
            note = Note(
                lead_id=lead.id,
                conversation_id=conversation.id,
                external_key=note_in.external_key,
                body=note_in.body,
                author_source=NoteAuthorSource.n8n_webhook,
            )
            session.add(note)
            await session.flush()
            results.append(
                NoteResultOut(id=note.id, external_key=note_in.external_key, created=True)
            )
    return results
