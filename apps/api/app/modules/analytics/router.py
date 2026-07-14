"""Analytics de atención comercial.

KPIs elegidos por impacto en canal conversacional (WhatsApp):
- Velocidad: primera respuesta (mediana), % respondidas <1h, cola esperando.
  En WhatsApp la velocidad de respuesta es el principal driver de conversión.
- Demanda: conversaciones/contactos nuevos, mensajes in/out, distribución
  horaria de entrantes (staffing).
- Resultado: leads creados/ganados, tasa de cierre (won/(won+lost)), valor.
- Equipo: mensajes enviados, asignadas y ganados por agente.

Cada métrica de período se calcula también para el período anterior
(mismo largo) para mostrar la variación.
"""

import statistics
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import (
    Contact,
    Conversation,
    Lead,
    LeadStageEvent,
    Message,
    Pipeline,
    PipelineStage,
    User,
)
from app.db.models.enums import ConversationStatus, MessageDirection
from app.db.session import get_db
from app.modules.auth import permissions as perms
from app.modules.auth.deps import AuthContext, require_permissions

router = APIRouter(prefix="/analytics", tags=["analytics"])

_IN = MessageDirection.inbound
_OUT = MessageDirection.outbound


async def _count(db: AsyncSession, stmt) -> int:
    return (await db.execute(stmt)).scalar_one() or 0


def _since(now: datetime, days: int) -> datetime | None:
    """days=0 es el sentinel de "Histórico": sin cota inferior de tiempo."""
    return None if days == 0 else now - timedelta(days=days)


def _current_stage_entered_at():
    """Subquery: por lead, cuándo entró a su etapa actual (última transición).
    Todo lead tiene ≥1 evento por construcción (create_lead siempre inserta uno)."""
    return (
        sa.select(LeadStageEvent.lead_id,
                  sa.func.max(LeadStageEvent.created_at).label("entered_at"))
        .group_by(LeadStageEvent.lead_id)
        .subquery()
    )


def _leads_currently_outcome(start: datetime | None, end: datetime, outcome: str):
    """Leads cuya etapa ACTUAL tiene este outcome (won/lost), cohorteados por
    cuándo entraron a ella — mismo criterio que funnel.currentCount. A
    diferencia de contar transiciones (evento histórico), esto excluye leads
    borrados y leads que ya no están en esa etapa (por ejemplo, si se
    reabrieron)."""
    entered_at = _current_stage_entered_at()
    conds = [Lead.deleted_at.is_(None), PipelineStage.outcome == outcome,
             entered_at.c.entered_at < end]
    if start is not None:
        conds.append(entered_at.c.entered_at >= start)
    return (
        sa.select(Lead.id.label("lead_id"))
        .select_from(Lead)
        .join(PipelineStage, Lead.stage_id == PipelineStage.id)
        .join(entered_at, entered_at.c.lead_id == Lead.id)
        .where(*conds)
    )


async def _window_metrics(db: AsyncSession, start: datetime | None, end: datetime) -> dict:
    if start is None:
        in_window = lambda col: col < end  # noqa: E731
    else:
        in_window = lambda col: sa.and_(col >= start, col < end)  # noqa: E731

    new_conversations = await _count(
        db, sa.select(sa.func.count()).where(in_window(Conversation.created_at)))
    new_contacts = await _count(
        db, sa.select(sa.func.count()).where(in_window(Contact.created_at)))
    inbound = await _count(
        db, sa.select(sa.func.count()).where(
            Message.direction == _IN, in_window(Message.created_at)))
    outbound = await _count(
        db, sa.select(sa.func.count()).where(
            Message.direction == _OUT, in_window(Message.created_at)))
    leads_created = await _count(
        db, sa.select(sa.func.count()).where(
            in_window(Lead.created_at), Lead.deleted_at.is_(None)))

    won_ids = _leads_currently_outcome(start, end, "won").subquery()
    lost_ids = _leads_currently_outcome(start, end, "lost").subquery()
    leads_won = await _count(db, sa.select(sa.func.count()).select_from(won_ids))
    leads_lost = await _count(db, sa.select(sa.func.count()).select_from(lost_ids))
    won_value = (await db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(Lead.value), 0))
        .where(Lead.id.in_(sa.select(won_ids.c.lead_id)))
    )).scalar_one()

    # Primera respuesta: por conversación creada en la ventana,
    # min(entrante) → min(saliente posterior)
    since_conds = [Message.created_at >= start] if start is not None else []
    fi = (
        sa.select(Message.conversation_id.label("cid"),
                  sa.func.min(Message.created_at).label("t"))
        .where(Message.direction == _IN, *since_conds)
        .group_by(Message.conversation_id)
    ).subquery()
    fo = (
        sa.select(Message.conversation_id.label("cid"),
                  sa.func.min(Message.created_at).label("t"))
        .where(Message.direction == _OUT, *since_conds)
        .group_by(Message.conversation_id)
    ).subquery()
    rows = (await db.execute(
        sa.select(fi.c.t, fo.c.t)
        .select_from(Conversation)
        .join(fi, fi.c.cid == Conversation.id)
        .outerjoin(fo, fo.c.cid == Conversation.id)
        .where(in_window(Conversation.created_at))
    )).all()

    deltas = [
        (t_out - t_in).total_seconds()
        for t_in, t_out in rows
        if t_out is not None and t_out > t_in
    ]
    with_inbound = len(rows)
    responded = len(deltas)
    within_1h = sum(1 for d in deltas if d <= 3600)

    closed = leads_won + leads_lost
    return {
        "newConversations": new_conversations,
        "newContacts": new_contacts,
        "inbound": inbound,
        "outbound": outbound,
        "leadsCreated": leads_created,
        "leadsWon": leads_won,
        "leadsLost": leads_lost,
        "wonValue": float(won_value or 0),
        "winRate": round(leads_won / closed * 100, 1) if closed else None,
        "medianFirstResponseMin": round(statistics.median(deltas) / 60, 1) if deltas else None,
        "pctWithin1h": round(within_1h / responded * 100, 1) if responded else None,
        "respondedRate": round(responded / with_inbound * 100, 1) if with_inbound else None,
    }


@router.get("/summary")
async def summary(
    days: int = Query(0, ge=0, le=3650),
    auth: AuthContext = Depends(require_permissions(perms.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    since = _since(now, days)

    current = await _window_metrics(db, since, now)
    # Sin cota inferior (Histórico) no existe un "período anterior" válido.
    previous = await _window_metrics(db, since - timedelta(days=days), since) if since else {}

    # Snapshot operativo: conversaciones esperando respuesta AHORA
    later_outbound = sa.select(Message.id).where(
        Message.conversation_id == Conversation.id,
        Message.direction == _OUT,
        Message.created_at > Conversation.last_inbound_at,
    )
    awaiting = await _count(db, sa.select(sa.func.count()).where(
        Conversation.last_inbound_at.is_not(None),
        Conversation.status != ConversationStatus.closed,
        ~sa.exists(later_outbound),
    ))

    # Leads actualmente en una etapa no terminal, cohorteados por cuándo
    # entraron a esa etapa (regla consistente con funnel.currentCount).
    entered_at = _current_stage_entered_at()
    open_leads_stmt = (
        sa.select(sa.func.count())
        .select_from(Lead)
        .join(PipelineStage, Lead.stage_id == PipelineStage.id)
        .join(entered_at, entered_at.c.lead_id == Lead.id)
        .where(Lead.deleted_at.is_(None), PipelineStage.is_terminal.is_(False))
    )
    if since is not None:
        open_leads_stmt = open_leads_stmt.where(entered_at.c.entered_at >= since)
    open_leads = await _count(db, open_leads_stmt)

    return {"days": days, "current": current, "previous": previous,
            "awaitingReply": awaiting, "openLeads": open_leads}


@router.get("/timeseries")
async def timeseries(
    days: int = Query(0, ge=0, le=3650),
    auth: AuthContext = Depends(require_permissions(perms.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    if days == 0:
        # Histórico: el piso real es el mensaje más antiguo (o "ahora" si no hay ninguno).
        floor = (await db.execute(sa.select(sa.func.min(Message.created_at)))).scalar_one_or_none() or now
        start = floor.replace(hour=0, minute=0, second=0, microsecond=0)
        n_days = (now.date() - start.date()).days + 1
    else:
        since = now - timedelta(days=days - 1)
        start = since.replace(hour=0, minute=0, second=0, microsecond=0)
        n_days = days
    day_col = sa.func.date_trunc("day", Message.created_at)

    by_day: dict[str, dict] = {}
    for i in range(n_days):
        key = (start + timedelta(days=i)).date().isoformat()
        by_day[key] = {"date": key, "inbound": 0, "outbound": 0,
                       "newConversations": 0, "leadsCreated": 0}

    msg_rows = (await db.execute(
        sa.select(day_col, Message.direction, sa.func.count())
        .where(Message.created_at >= start)
        .group_by(day_col, Message.direction)
    )).all()
    for day, direction, count in msg_rows:
        key = day.date().isoformat()
        if key in by_day:
            by_day[key]["inbound" if direction == _IN else "outbound"] = count

    conv_day = sa.func.date_trunc("day", Conversation.created_at)
    for day, count in (await db.execute(
        sa.select(conv_day, sa.func.count())
        .where(Conversation.created_at >= start).group_by(conv_day)
    )).all():
        key = day.date().isoformat()
        if key in by_day:
            by_day[key]["newConversations"] = count

    lead_day = sa.func.date_trunc("day", Lead.created_at)
    for day, count in (await db.execute(
        sa.select(lead_day, sa.func.count())
        .where(Lead.created_at >= start, Lead.deleted_at.is_(None)).group_by(lead_day)
    )).all():
        key = day.date().isoformat()
        if key in by_day:
            by_day[key]["leadsCreated"] = count

    return {"items": list(by_day.values())}


@router.get("/hourly")
async def hourly(
    days: int = Query(0, ge=0, le=3650),
    auth: AuthContext = Depends(require_permissions(perms.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mensajes ENTRANTES por hora del día (horas UTC; el frontend las
    desplaza a la zona horaria local)."""
    since = _since(datetime.now(UTC), days)
    hour_col = sa.func.extract("hour", Message.created_at)
    since_conds = [Message.created_at >= since] if since is not None else []
    rows = (await db.execute(
        sa.select(hour_col, sa.func.count())
        .where(Message.direction == _IN, *since_conds)
        .group_by(hour_col)
    )).all()
    counts = {int(h): c for h, c in rows}
    return {"items": [{"hourUtc": h, "count": counts.get(h, 0)} for h in range(24)]}


@router.get("/agents")
async def agents(
    days: int = Query(0, ge=0, le=3650),
    auth: AuthContext = Depends(require_permissions(perms.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    since = _since(now, days)
    data: dict[uuid.UUID, dict] = {}

    def entry(user_id: uuid.UUID) -> dict:
        return data.setdefault(user_id, {
            "outboundMessages": 0, "conversationsAssigned": 0,
            "leadsWon": 0, "wonValue": 0.0,
        })

    since_conds = [Message.created_at >= since] if since is not None else []
    for user_id, count in (await db.execute(
        sa.select(Message.sent_by_user_id, sa.func.count())
        .where(Message.sent_by_user_id.is_not(None), *since_conds)
        .group_by(Message.sent_by_user_id)
    )).all():
        entry(user_id)["outboundMessages"] = count

    for user_id, count in (await db.execute(
        sa.select(Conversation.assigned_user_id, sa.func.count())
        .where(Conversation.assigned_user_id.is_not(None),
               Conversation.status != ConversationStatus.closed)
        .group_by(Conversation.assigned_user_id)
    )).all():
        entry(user_id)["conversationsAssigned"] = count

    won_ids = _leads_currently_outcome(since, now, "won").subquery()
    for user_id, count, value in (await db.execute(
        sa.select(Lead.owner_user_id, sa.func.count(),
                  sa.func.coalesce(sa.func.sum(Lead.value), 0))
        .where(Lead.id.in_(sa.select(won_ids.c.lead_id)),
               Lead.owner_user_id.is_not(None))
        .group_by(Lead.owner_user_id)
    )).all():
        e = entry(user_id)
        e["leadsWon"] = count
        e["wonValue"] = float(value or 0)

    users = (await db.execute(
        sa.select(User).where(User.id.in_(list(data.keys()))))).scalars().all() if data else []
    names = {u.id: u.name for u in users}

    items = [
        {"userId": str(uid), "name": names.get(uid, "—"), **metrics}
        for uid, metrics in data.items()
    ]
    items.sort(key=lambda x: (-x["outboundMessages"], -x["leadsWon"]))
    return {"items": items}


@router.get("/funnel")
async def funnel(
    days: int = Query(0, ge=0, le=3650),
    pipeline_id: uuid.UUID | None = Query(None, alias="pipelineId"),
    auth: AuthContext = Depends(require_permissions(perms.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    since = _since(now, days)

    if pipeline_id is None:
        pipeline = (await db.execute(
            sa.select(Pipeline).where(Pipeline.is_default.is_(True)))).scalar_one_or_none()
    else:
        pipeline = await db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise NotFoundError("Pipeline inexistente")

    stages = (await db.execute(
        sa.select(PipelineStage).where(PipelineStage.pipeline_id == pipeline.id)
        .order_by(PipelineStage.position)
    )).scalars().all()

    # currentCount: leads cuya etapa actual coincide con s.id, cohorteados por
    # cuándo entraron a ella (misma regla que summary.openLeads).
    entered_at = _current_stage_entered_at()
    current_stmt = (
        sa.select(Lead.stage_id, sa.func.count())
        .select_from(Lead)
        .join(entered_at, entered_at.c.lead_id == Lead.id)
        .where(Lead.pipeline_id == pipeline.id, Lead.deleted_at.is_(None))
    )
    if since is not None:
        current_stmt = current_stmt.where(entered_at.c.entered_at >= since)
    current = {sid: c for sid, c in (await db.execute(
        current_stmt.group_by(Lead.stage_id)
    )).all()}

    entered_conds = [LeadStageEvent.created_at >= since] if since is not None else []
    entered = {sid: c for sid, c in (await db.execute(
        sa.select(LeadStageEvent.to_stage_id,
                  sa.func.count(sa.func.distinct(LeadStageEvent.lead_id)))
        .join(PipelineStage, LeadStageEvent.to_stage_id == PipelineStage.id)
        .where(PipelineStage.pipeline_id == pipeline.id, *entered_conds)
        .group_by(LeadStageEvent.to_stage_id)
    )).all()}

    # % = participación de la etapa sobre el TOTAL de leads del período,
    # calculado con el mismo número que se muestra (currentCount).
    total = sum(current.get(s.id, 0) for s in stages)
    items = []
    for s in stages:
        stage_count = current.get(s.id, 0)
        items.append({
            "id": str(s.id), "name": s.name, "isTerminal": s.is_terminal,
            "outcome": s.outcome, "color": s.color, "currentCount": stage_count,
            "enteredInPeriod": entered.get(s.id, 0),
            "pctOfTotal": round(stage_count / total * 100, 1) if total else None,
        })
    return {"pipeline": {"id": str(pipeline.id), "name": pipeline.name},
            "days": days, "items": items}
