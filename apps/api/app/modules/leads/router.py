"""API de leads y embudo configurable (pipelines/etapas) del CRM."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Contact,
    Conversation,
    Lead,
    LeadStageEvent,
    Note,
    Pipeline,
    PipelineStage,
)
from app.db.models.enums import LeadSource
from app.db.session import get_db
from app.modules.audit.service import log_event
from app.modules.auth import permissions as perms
from app.modules.auth.deps import AuthContext, require_permissions
from app.schemas.hooks import CamelModel

router = APIRouter(tags=["leads"])


def _stage_row(s: PipelineStage, count: int | None = None, value: Decimal | None = None) -> dict:
    data = {
        "id": str(s.id), "name": s.name, "position": s.position, "color": s.color,
        "isTerminal": s.is_terminal, "outcome": s.outcome,
    }
    if count is not None:
        data["leadCount"] = count
        data["totalValue"] = float(value or 0)
    return data


def _lead_row(lead: Lead, contact: Contact | None = None) -> dict:
    return {
        "id": str(lead.id),
        "title": lead.title,
        "value": float(lead.value) if lead.value is not None else None,
        "currency": lead.currency,
        "source": lead.source.value,
        "externalKey": lead.external_key,
        "pipelineId": str(lead.pipeline_id),
        "stageId": str(lead.stage_id),
        "conversationId": str(lead.conversation_id) if lead.conversation_id else None,
        "ownerUserId": str(lead.owner_user_id) if lead.owner_user_id else None,
        "attributes": lead.attributes,
        "contact": (
            {"id": str(contact.id), "waId": contact.wa_id, "profileName": contact.profile_name}
            if contact else None
        ),
        "createdAt": lead.created_at.isoformat(),
        "updatedAt": lead.updated_at.isoformat(),
    }


async def _renumber_stages(db: AsyncSession, pipeline_id: uuid.UUID) -> None:
    stages = (await db.execute(
        sa.select(PipelineStage).where(PipelineStage.pipeline_id == pipeline_id)
        .order_by(PipelineStage.position)
    )).scalars().all()
    for i, stage in enumerate(stages, start=1):
        stage.position = i


# ── Pipelines y etapas ─────────────────────────────────────────────────────

@router.get("/pipelines")
async def list_pipelines(
    auth: AuthContext = Depends(require_permissions(perms.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    pipelines = (await db.execute(sa.select(Pipeline).order_by(Pipeline.created_at))).scalars().all()
    counts = dict()
    values = dict()
    rows = (await db.execute(
        sa.select(Lead.stage_id, sa.func.count(), sa.func.coalesce(sa.func.sum(Lead.value), 0))
        .where(Lead.deleted_at.is_(None)).group_by(Lead.stage_id)
    )).all()
    for stage_id, count, total in rows:
        counts[stage_id] = count
        values[stage_id] = total

    items = []
    for p in pipelines:
        stages = (await db.execute(
            sa.select(PipelineStage).where(PipelineStage.pipeline_id == p.id)
            .order_by(PipelineStage.position)
        )).scalars().all()
        items.append({
            "id": str(p.id), "name": p.name, "isDefault": p.is_default,
            "stages": [_stage_row(s, counts.get(s.id, 0), values.get(s.id)) for s in stages],
        })
    return {"items": items}


class PipelineIn(CamelModel):
    name: str
    is_default: bool = False


@router.post("/pipelines")
async def create_pipeline(
    body: PipelineIn,
    auth: AuthContext = Depends(require_permissions(perms.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    pipeline = Pipeline(name=body.name, is_default=body.is_default)
    if body.is_default:
        await db.execute(sa.update(Pipeline).values(is_default=False))
    db.add(pipeline)
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="pipeline.created", entity_type="pipeline")
    await db.commit()
    return {"id": str(pipeline.id)}


class StageIn(CamelModel):
    name: str
    color: str | None = None
    position: int | None = None
    is_terminal: bool = False
    outcome: str | None = None  # 'won' | 'lost'


@router.post("/pipelines/{pipeline_id}/stages")
async def create_stage(
    pipeline_id: uuid.UUID,
    body: StageIn,
    auth: AuthContext = Depends(require_permissions(perms.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await db.get(Pipeline, pipeline_id) is None:
        raise NotFoundError("Pipeline inexistente")
    max_pos = (await db.execute(
        sa.select(sa.func.coalesce(sa.func.max(PipelineStage.position), 0))
        .where(PipelineStage.pipeline_id == pipeline_id)
    )).scalar_one()
    stage = PipelineStage(
        pipeline_id=pipeline_id, name=body.name, color=body.color,
        position=body.position or max_pos + 1,
        is_terminal=body.is_terminal, outcome=body.outcome,
    )
    db.add(stage)
    await db.flush()
    if body.position is not None:
        # Insertar en el medio: correr las demás y renumerar
        await db.execute(
            sa.update(PipelineStage)
            .where(PipelineStage.pipeline_id == pipeline_id, PipelineStage.id != stage.id,
                   PipelineStage.position >= body.position)
            .values(position=PipelineStage.position + 1)
        )
        await _renumber_stages(db, pipeline_id)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="stage.created",
                    entity_type="pipeline_stage", entity_id=stage.id,
                    metadata={"name": body.name})
    await db.commit()
    return {"id": str(stage.id)}


@router.patch("/stages/{stage_id}")
async def update_stage(
    stage_id: uuid.UUID,
    body: StageIn,
    auth: AuthContext = Depends(require_permissions(perms.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise NotFoundError("Etapa inexistente")
    stage.name = body.name
    stage.color = body.color
    stage.is_terminal = body.is_terminal
    stage.outcome = body.outcome
    if body.position is not None and body.position != stage.position:
        old, new = stage.position, body.position
        if new < old:
            await db.execute(
                sa.update(PipelineStage)
                .where(PipelineStage.pipeline_id == stage.pipeline_id,
                       PipelineStage.position >= new, PipelineStage.position < old,
                       PipelineStage.id != stage.id)
                .values(position=PipelineStage.position + 1)
            )
        else:
            await db.execute(
                sa.update(PipelineStage)
                .where(PipelineStage.pipeline_id == stage.pipeline_id,
                       PipelineStage.position <= new, PipelineStage.position > old,
                       PipelineStage.id != stage.id)
                .values(position=PipelineStage.position - 1)
            )
        stage.position = new
        await _renumber_stages(db, stage.pipeline_id)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="stage.updated",
                    entity_type="pipeline_stage", entity_id=stage.id)
    await db.commit()
    return {"ok": True}


@router.delete("/stages/{stage_id}")
async def delete_stage(
    stage_id: uuid.UUID,
    move_leads_to_stage_id: uuid.UUID | None = Query(None, alias="moveLeadsToStageId"),
    auth: AuthContext = Depends(require_permissions(perms.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise NotFoundError("Etapa inexistente")
    lead_count = (await db.execute(
        sa.select(sa.func.count()).where(Lead.stage_id == stage_id, Lead.deleted_at.is_(None))
    )).scalar_one()
    if lead_count:
        if move_leads_to_stage_id is None:
            raise ConflictError(
                f"La etapa tiene {lead_count} leads: indicar moveLeadsToStageId")
        target = await db.get(PipelineStage, move_leads_to_stage_id)
        if target is None or target.pipeline_id != stage.pipeline_id:
            raise NotFoundError("Etapa destino inválida")
        await db.execute(sa.update(Lead).where(Lead.stage_id == stage_id)
                         .values(stage_id=target.id))
    await db.delete(stage)
    await _renumber_stages(db, stage.pipeline_id)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="stage.deleted",
                    entity_type="pipeline_stage", entity_id=stage_id,
                    metadata={"movedLeads": lead_count})
    await db.commit()
    return {"ok": True}


# ── Leads ──────────────────────────────────────────────────────────────────

@router.get("/leads")
async def list_leads(
    pipeline_id: uuid.UUID | None = Query(None, alias="pipelineId"),
    stage_id: uuid.UUID | None = Query(None, alias="stageId"),
    q: str | None = None,
    limit: int = Query(100, le=500),
    auth: AuthContext = Depends(require_permissions(perms.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        sa.select(Lead, Contact).join(Contact, Lead.contact_id == Contact.id)
        .where(Lead.deleted_at.is_(None)).order_by(Lead.created_at.desc()).limit(limit)
    )
    if pipeline_id:
        stmt = stmt.where(Lead.pipeline_id == pipeline_id)
    if stage_id:
        stmt = stmt.where(Lead.stage_id == stage_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(sa.or_(Lead.title.ilike(like), Contact.profile_name.ilike(like),
                                 Contact.wa_id.like(like)))
    rows = (await db.execute(stmt)).all()
    return {"items": [_lead_row(lead, contact) for lead, contact in rows]}


class LeadCreateIn(CamelModel):
    conversation_id: uuid.UUID
    title: str | None = None
    value: Decimal | None = None
    currency: str | None = None
    stage_id: uuid.UUID | None = None


@router.post("/leads", status_code=201)
async def create_lead(
    body: LeadCreateIn,
    auth: AuthContext = Depends(require_permissions(perms.LEADS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await db.get(Conversation, body.conversation_id)
    if conversation is None:
        raise NotFoundError("Conversación inexistente")
    existing = (await db.execute(
        sa.select(Lead.id).join(PipelineStage, Lead.stage_id == PipelineStage.id)
        .where(Lead.conversation_id == conversation.id, Lead.deleted_at.is_(None),
               PipelineStage.is_terminal.is_(False))
    )).scalar_one_or_none()
    if existing:
        raise ConflictError("La conversación ya tiene un lead activo")

    pipeline = (await db.execute(
        sa.select(Pipeline).where(Pipeline.is_default.is_(True)))).scalar_one_or_none()
    if pipeline is None:
        raise NotFoundError("No hay pipeline por defecto")
    if body.stage_id:
        stage = await db.get(PipelineStage, body.stage_id)
        if stage is None:
            raise NotFoundError("Etapa inexistente")
        pipeline_id = stage.pipeline_id
    else:
        stage = (await db.execute(
            sa.select(PipelineStage).where(PipelineStage.pipeline_id == pipeline.id)
            .order_by(PipelineStage.position).limit(1))).scalar_one()
        pipeline_id = pipeline.id

    contact = await db.get(Contact, conversation.contact_id)
    lead = Lead(
        contact_id=conversation.contact_id, conversation_id=conversation.id,
        pipeline_id=pipeline_id, stage_id=stage.id,
        title=body.title or f"Lead {contact.profile_name or contact.wa_id}",
        value=body.value, currency=body.currency or "ARS", source=LeadSource.manual,
        owner_user_id=auth.user.id,
    )
    db.add(lead)
    await db.flush()
    db.add(LeadStageEvent(lead_id=lead.id, from_stage_id=None, to_stage_id=stage.id,
                          moved_by=f"user:{auth.user.id}"))
    # Notas huérfanas del chat → se asocian al lead recién creado
    await db.execute(
        sa.update(Note).where(Note.conversation_id == conversation.id, Note.lead_id.is_(None))
        .values(lead_id=lead.id)
    )
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="lead.created",
                    entity_type="lead", entity_id=lead.id)
    await db.commit()
    return _lead_row(lead, contact)


@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.deleted_at is not None:
        raise NotFoundError("Lead inexistente")
    contact = await db.get(Contact, lead.contact_id)
    data = _lead_row(lead, contact)
    events = (await db.execute(
        sa.select(LeadStageEvent).where(LeadStageEvent.lead_id == lead.id)
        .order_by(LeadStageEvent.created_at)
    )).scalars().all()
    data["history"] = [
        {"fromStageId": str(e.from_stage_id) if e.from_stage_id else None,
         "toStageId": str(e.to_stage_id), "movedBy": e.moved_by,
         "at": e.created_at.isoformat()}
        for e in events
    ]
    notes = (await db.execute(
        sa.select(Note).where(Note.lead_id == lead.id, Note.deleted_at.is_(None))
        .order_by(Note.created_at)
    )).scalars().all()
    data["notes"] = [
        {"id": str(n.id), "body": n.body, "authorSource": n.author_source.value,
         "updatedAt": n.updated_at.isoformat()}
        for n in notes
    ]
    return data


class LeadPatch(CamelModel):
    title: str | None = None
    value: Decimal | None = None
    currency: str | None = None
    owner_user_id: uuid.UUID | None = None


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadPatch,
    auth: AuthContext = Depends(require_permissions(perms.LEADS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.deleted_at is not None:
        raise NotFoundError("Lead inexistente")
    provided = body.model_fields_set
    if "title" in provided and body.title:
        lead.title = body.title
    if "value" in provided:
        lead.value = body.value
    if "currency" in provided and body.currency:
        lead.currency = body.currency
    if "owner_user_id" in provided:
        lead.owner_user_id = body.owner_user_id
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="lead.updated",
                    entity_type="lead", entity_id=lead.id)
    await db.commit()
    return {"ok": True}


class MoveStageIn(CamelModel):
    stage_id: uuid.UUID


@router.patch("/leads/{lead_id}/stage")
async def move_lead_stage(
    lead_id: uuid.UUID,
    body: MoveStageIn,
    auth: AuthContext = Depends(require_permissions(perms.LEADS_MOVE_STAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.deleted_at is not None:
        raise NotFoundError("Lead inexistente")
    stage = await db.get(PipelineStage, body.stage_id)
    if stage is None or stage.pipeline_id != lead.pipeline_id:
        raise NotFoundError("Etapa inexistente o de otro pipeline")
    if stage.id == lead.stage_id:
        return {"ok": True}
    db.add(LeadStageEvent(lead_id=lead.id, from_stage_id=lead.stage_id,
                          to_stage_id=stage.id, moved_by=f"user:{auth.user.id}"))
    lead.stage_id = stage.id
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="lead.stage_changed", entity_type="lead", entity_id=lead.id,
                    metadata={"toStage": stage.name})
    await db.commit()
    return {"ok": True}


@router.delete("/leads/{lead_id}")
async def delete_lead(
    lead_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.LEADS_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.deleted_at is not None:
        raise NotFoundError("Lead inexistente")
    lead.deleted_at = datetime.now(UTC)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="lead.deleted",
                    entity_type="lead", entity_id=lead.id)
    await db.commit()
    return {"ok": True}
