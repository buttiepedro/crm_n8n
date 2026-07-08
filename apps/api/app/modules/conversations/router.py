"""API del CRM: conversaciones, mensajes, notas internas y adjuntos.

Permite leer y ENVIAR mensajes directamente desde la plataforma, sin pasar
por n8n. Tiempo real v1: polling del frontend (WebSockets quedan para una
iteración posterior).
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models import (
    Attachment,
    Contact,
    Conversation,
    Lead,
    Message,
    Note,
    PipelineStage,
    User,
    WhatsAppAccount,
)
from app.db.models.enums import ConversationStatus, MessageOrigin, NoteAuthorSource
from app.db.session import get_db
from app.modules.audit.service import log_event
from app.modules.auth import permissions as perms
from app.modules.auth.deps import AuthContext, get_auth, require_permissions
from app.modules.conversations.service import build_attachment_response
from app.modules.messages.outbound import is_window_open, queue_outbound_message
from app.schemas.hooks import CamelModel, OutboundMessageContent

router = APIRouter(tags=["crm"])


# ── Serializadores ─────────────────────────────────────────────────────────

def _conversation_row(c: Conversation, contact: Contact, account: WhatsAppAccount,
                      last_body: str | None, lead_id: uuid.UUID | None) -> dict:
    return {
        "id": str(c.id),
        "status": c.status.value,
        "contact": {"id": str(contact.id), "waId": contact.wa_id,
                    "profileName": contact.profile_name},
        "account": {"id": str(account.id), "name": account.name, "isTest": account.is_test},
        "assignedUserId": str(c.assigned_user_id) if c.assigned_user_id else None,
        "lastMessageAt": c.last_message_at.isoformat() if c.last_message_at else None,
        "lastMessagePreview": (last_body or "")[:120],
        "unreadCount": c.unread_count,
        "windowOpen": is_window_open(c.last_inbound_at),
        "botPaused": c.bot_paused,
        "leadId": str(lead_id) if lead_id else None,
    }


def _message_row(m: Message, attachments: list[Attachment]) -> dict:
    return {
        "id": str(m.id),
        "direction": m.direction.value,
        "origin": m.origin.value,
        "type": m.type.value,
        "body": m.body,
        "status": m.status.value,
        "errorDetail": m.error_detail,
        "sentByUserId": str(m.sent_by_user_id) if m.sent_by_user_id else None,
        "createdAt": m.created_at.isoformat(),
        "waTimestamp": m.wa_timestamp.isoformat() if m.wa_timestamp else None,
        "attachments": [
            {"id": str(a.id), "mimeType": a.mime_type, "fileName": a.file_name,
             "downloadStatus": a.download_status.value, "transcript": a.transcript}
            for a in attachments
        ],
    }


def _note_row(n: Note) -> dict:
    return {
        "id": str(n.id),
        "body": n.body,
        "externalKey": n.external_key,
        "authorSource": n.author_source.value,
        "authorUserId": str(n.author_user_id) if n.author_user_id else None,
        "leadId": str(n.lead_id) if n.lead_id else None,
        "createdAt": n.created_at.isoformat(),
        "updatedAt": n.updated_at.isoformat(),
    }


async def _active_lead_id(db: AsyncSession, conversation_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        sa.select(Lead.id)
        .join(PipelineStage, Lead.stage_id == PipelineStage.id)
        .where(Lead.conversation_id == conversation_id, Lead.deleted_at.is_(None),
               PipelineStage.is_terminal.is_(False))
        .order_by(Lead.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


# ── Conversaciones ─────────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    account_id: uuid.UUID | None = Query(None, alias="accountId"),
    status: ConversationStatus | None = None,
    assigned_user_id: uuid.UUID | None = Query(None, alias="assignedUserId"),
    unread: bool = False,
    q: str | None = None,
    before: datetime | None = None,
    limit: int = Query(50, le=100),
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    last_body = (
        sa.select(Message.body).where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc()).limit(1).scalar_subquery()
    )
    stmt = (
        sa.select(Conversation, Contact, WhatsAppAccount, last_body)
        .join(Contact, Conversation.contact_id == Contact.id)
        .join(WhatsAppAccount, Conversation.whatsapp_account_id == WhatsAppAccount.id)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(limit)
    )
    if account_id:
        stmt = stmt.where(Conversation.whatsapp_account_id == account_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    if assigned_user_id:
        stmt = stmt.where(Conversation.assigned_user_id == assigned_user_id)
    if unread:
        stmt = stmt.where(Conversation.unread_count > 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(sa.or_(Contact.profile_name.ilike(like), Contact.wa_id.like(like)))
    if before:
        stmt = stmt.where(Conversation.last_message_at < before)

    rows = (await db.execute(stmt)).all()
    items = []
    for conv, contact, account, body in rows:
        lead_id = await _active_lead_id(db, conv.id)
        items.append(_conversation_row(conv, contact, account, body, lead_id))
    return {"items": items}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversación no encontrada")
    contact = await db.get(Contact, conv.contact_id)
    account = await db.get(WhatsAppAccount, conv.whatsapp_account_id)
    lead_id = await _active_lead_id(db, conv.id)
    data = _conversation_row(conv, contact, account, None, lead_id)
    data["lastInboundAt"] = conv.last_inbound_at.isoformat() if conv.last_inbound_at else None
    return data


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    before: datetime | None = None,
    limit: int = Query(50, le=200),
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        sa.select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc()).limit(limit)
    )
    if before:
        stmt = stmt.where(Message.created_at < before)
    messages = list((await db.execute(stmt)).scalars().all())

    att_map: dict[uuid.UUID, list[Attachment]] = {}
    if messages:
        atts = (await db.execute(
            sa.select(Attachment).where(Attachment.message_id.in_([m.id for m in messages]))
        )).scalars().all()
        for a in atts:
            att_map.setdefault(a.message_id, []).append(a)

    return {"items": [_message_row(m, att_map.get(m.id, [])) for m in reversed(messages)]}


@router.post("/conversations/{conversation_id}/messages", status_code=202)
async def send_message(
    conversation_id: uuid.UUID,
    body: OutboundMessageContent,
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_SEND)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    message = await queue_outbound_message(
        db, conversation_id=conversation_id, content=body,
        origin=MessageOrigin.crm_user, sent_by_user_id=auth.user.id,
    )
    return {"messageId": str(message.id), "status": message.status.value}


@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversación no encontrada")
    conv.unread_count = 0
    await db.commit()
    return {"ok": True}


class ConversationPatch(CamelModel):
    status: ConversationStatus | None = None
    assigned_user_id: uuid.UUID | None = None
    unassign: bool = False
    bot_paused: bool | None = None


@router.patch("/conversations/{conversation_id}")
async def patch_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversación no encontrada")

    if body.status is not None:
        if body.status == ConversationStatus.closed and not auth.has(perms.CONVERSATIONS_CLOSE):
            raise ForbiddenError("Sin permiso para cerrar conversaciones")
        conv.status = body.status
    if body.assigned_user_id is not None or body.unassign:
        if not auth.has(perms.CONVERSATIONS_ASSIGN):
            raise ForbiddenError("Sin permiso para asignar conversaciones")
        conv.assigned_user_id = None if body.unassign else body.assigned_user_id
    if body.bot_paused is not None:
        # Mismo permiso que responder manualmente: quien puede tomar la
        # conversación puede silenciar al bot para hacerlo.
        if not auth.has(perms.CONVERSATIONS_SEND):
            raise ForbiddenError("Sin permiso para silenciar el bot")
        conv.bot_paused = body.bot_paused

    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="conversation.updated", entity_type="conversation",
                    entity_id=conv.id,
                    metadata=body.model_dump(mode="json", exclude_none=True))
    await db.commit()
    return {"ok": True}


# ── Notas internas ─────────────────────────────────────────────────────────

@router.get("/conversations/{conversation_id}/notes")
async def list_notes(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lead_id = await _active_lead_id(db, conversation_id)
    where = [Note.deleted_at.is_(None)]
    if lead_id:
        where.append(sa.or_(Note.conversation_id == conversation_id, Note.lead_id == lead_id))
    else:
        where.append(Note.conversation_id == conversation_id)
    notes = (await db.execute(
        sa.select(Note).where(*where).order_by(Note.created_at)
    )).scalars().all()
    return {"items": [_note_row(n) for n in notes]}


class NoteIn(CamelModel):
    body: str


@router.post("/conversations/{conversation_id}/notes")
async def create_note(
    conversation_id: uuid.UUID,
    body: NoteIn,
    auth: AuthContext = Depends(require_permissions(perms.NOTES_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversación no encontrada")
    note = Note(
        conversation_id=conversation_id,
        lead_id=await _active_lead_id(db, conversation_id),
        body=body.body,
        author_user_id=auth.user.id,
        author_source=NoteAuthorSource.user,
    )
    db.add(note)
    await db.commit()
    return _note_row(note)


@router.patch("/notes/{note_id}")
async def edit_note(
    note_id: uuid.UUID,
    body: NoteIn,
    auth: AuthContext = Depends(require_permissions(perms.NOTES_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    note = await db.get(Note, note_id)
    if note is None or note.deleted_at is not None:
        raise NotFoundError("Nota no encontrada")
    own = note.author_user_id == auth.user.id
    if not own and not auth.has(perms.NOTES_EDIT_ANY):
        raise ForbiddenError("Solo podés editar tus propias notas")
    note.body = body.body
    note.updated_at = datetime.now(UTC)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="note.edited",
                    entity_type="note", entity_id=note.id)
    await db.commit()
    return _note_row(note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.NOTES_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    note = await db.get(Note, note_id)
    if note is None or note.deleted_at is not None:
        raise NotFoundError("Nota no encontrada")
    own = note.author_user_id == auth.user.id
    if not own and not auth.has(perms.NOTES_EDIT_ANY):
        raise ForbiddenError("Solo podés borrar tus propias notas")
    note.deleted_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}


# ── Adjuntos ───────────────────────────────────────────────────────────────

@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    att = await db.get(Attachment, attachment_id)
    return await build_attachment_response(att)


# ── Usuarios (para selects de asignación) ──────────────────────────────────

@router.get("/users")
async def list_users_lite(
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    users = (await db.execute(
        sa.select(User).where(User.is_active.is_(True)).order_by(User.name)
    )).scalars().all()
    return {"items": [{"id": str(u.id), "name": u.name, "role": u.role.value} for u in users]}
