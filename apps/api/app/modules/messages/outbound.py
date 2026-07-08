"""Servicio único de envío de mensajes salientes.

Todos los orígenes convergen acá (agente del CRM, hook de n8n): misma
validación de ventana de 24h, misma cola, mismo pipeline de estados.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AccountPausedError,
    ConflictError,
    NotFoundError,
    RetryableTaskError,
    WindowExpiredError,
)
from app.db.models import Contact, Conversation, Message, WhatsAppAccount
from app.db.models.enums import (
    MessageDirection,
    MessageOrigin,
    MessageStatus,
    MessageType,
    WaAccountStatus,
)
from app.db.session import get_sessionmaker
from app.infra.queue import TASK_SEND_MESSAGE, get_queue
from app.modules.accounts.service import decrypt_access_token, has_token
from app.modules.conversations.service import get_or_create_contact, get_or_create_conversation
from app.modules.settings.service import KEY_GRAPH_VERSION, get_setting_cached
from app.modules.whatsapp.graph_client import GraphApiError, WhatsAppGraphClient
from app.schemas.hooks import OutboundMessageContent

log = structlog.get_logger()

WINDOW_HOURS = 24


def is_window_open(last_inbound_at: datetime | None, now: datetime | None = None) -> bool:
    """Ventana de 24h de WhatsApp: solo abierta si el cliente escribió hace
    menos de 24h. Fuera de ventana solo se permiten plantillas aprobadas."""
    if last_inbound_at is None:
        return False
    now = now or datetime.now(UTC)
    return now - last_inbound_at < timedelta(hours=WINDOW_HOURS)


async def queue_outbound_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    to_wa_id: str | None = None,
    content: OutboundMessageContent,
    origin: MessageOrigin,
    sent_by_user_id: uuid.UUID | None = None,
    reply_to_message_id: uuid.UUID | None = None,
) -> Message:
    conversation, account = await _resolve_target(session, conversation_id, account_id, to_wa_id)

    if account.status == WaAccountStatus.paused:
        raise AccountPausedError(f"La cuenta '{account.name}' está pausada")
    if not account.is_test and not has_token(account):
        raise ConflictError(
            f"La cuenta '{account.name}' no tiene access token cargado: "
            "pegalo en el panel técnico → Cuentas para poder enviar",
            code="ACCOUNT_TOKEN_MISSING",
        )
    if content.type != "template" and not is_window_open(conversation.last_inbound_at):
        raise WindowExpiredError(
            "Ventana de 24h cerrada: solo se pueden enviar plantillas aprobadas"
        )

    message = Message(
        conversation_id=conversation.id,
        whatsapp_account_id=account.id,
        direction=MessageDirection.outbound,
        origin=origin,
        sent_by_user_id=sent_by_user_id,
        type=MessageType(content.type),
        body=content.body,
        status=MessageStatus.queued,
        raw_payload={"request": content.model_dump(mode="json", by_alias=True)},
        reply_to_message_id=reply_to_message_id,
    )
    session.add(message)
    conversation.last_message_at = datetime.now(UTC)
    await session.commit()

    await get_queue().enqueue(TASK_SEND_MESSAGE, {"message_id": str(message.id)})
    log.info("outbound_queued", message_id=str(message.id), origin=origin.value)
    return message


async def _resolve_target(
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
    to_wa_id: str | None,
) -> tuple[Conversation, WhatsAppAccount]:
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversación no encontrada")
        account = await session.get(WhatsAppAccount, conversation.whatsapp_account_id)
        return conversation, account

    account = await session.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta WhatsApp no encontrada")
    contact = await get_or_create_contact(session, to_wa_id)
    conversation = await get_or_create_conversation(session, account.id, contact.id)
    return conversation, account


async def handle_send_message(payload: dict) -> None:
    """Handler de la tarea TASK_SEND_MESSAGE: envía vía Graph API."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        message = await session.get(Message, payload["message_id"])
        if message is None or message.status != MessageStatus.queued:
            return  # ya procesado (idempotencia del worker)

        conversation = await session.get(Conversation, message.conversation_id)
        contact = await session.get(Contact, conversation.contact_id)
        account = await session.get(WhatsAppAccount, message.whatsapp_account_id)

        if account.is_test:
            # Canal de prueba: nunca se llama a la Graph API de Meta, se
            # simula la entrega para poder ver la respuesta de n8n en el CRM.
            message.wamid = f"test.{uuid.uuid4()}"
            message.status = MessageStatus.sent
            await session.commit()
            log.info("outbound_sent_test", message_id=str(message.id))
            return

        try:
            access_token = decrypt_access_token(settings, account)
        except ConflictError as exc:
            # Token faltante o cifrado con otra clave: fallo claro, no colgado
            message.status = MessageStatus.failed
            message.error_detail = {"code": exc.code, "detail": exc.message}
            await session.commit()
            log.error("outbound_failed_credentials", message_id=str(message.id),
                      code=exc.code)
            return

        client = WhatsAppGraphClient(
            access_token=access_token,
            phone_number_id=account.phone_number_id,
            api_version=await get_setting_cached(KEY_GRAPH_VERSION, "v21.0"),
        )

        reply_to_wamid = None
        if message.reply_to_message_id is not None:
            quoted = await session.get(Message, message.reply_to_message_id)
            reply_to_wamid = quoted.wamid if quoted else None

        graph_payload = build_graph_payload(message, contact.wa_id, reply_to_wamid)

        try:
            wamid = await client.send_message(graph_payload)
        except GraphApiError as exc:
            if exc.retryable:
                raise RetryableTaskError(str(exc)) from exc
            message.status = MessageStatus.failed
            message.error_detail = {"status": exc.status, "detail": exc.detail}
            await session.commit()
            log.error("outbound_failed", message_id=str(message.id),
                      status=exc.status, detail=exc.detail)
            return

        message.wamid = wamid
        message.status = MessageStatus.sent
        await session.commit()
        log.info("outbound_sent", message_id=str(message.id), wamid=wamid)


def build_graph_payload(
    message: Message, to_wa_id: str, reply_to_wamid: str | None = None
) -> dict:
    """Construye el payload de la Graph API desde el request original."""
    request: dict = (message.raw_payload or {}).get("request", {})
    msg_type = message.type.value
    payload: dict = {"messaging_product": "whatsapp", "to": to_wa_id, "type": msg_type}
    if reply_to_wamid:
        payload["context"] = {"message_id": reply_to_wamid}

    if msg_type == "text":
        payload["text"] = {"body": message.body, "preview_url": True}
    elif msg_type == "template":
        tpl = request.get("template") or {}
        payload["template"] = {
            "name": tpl.get("name"),
            "language": {"code": tpl.get("language", "es_AR")},
            "components": tpl.get("components", []),
        }
    else:  # image | document | audio | video — media por link
        media: dict = {"link": request.get("mediaUrl")}
        if message.body:
            media["caption"] = message.body
        if msg_type == "document" and request.get("fileName"):
            media["filename"] = request["fileName"]
        payload[msg_type] = media

    return payload
