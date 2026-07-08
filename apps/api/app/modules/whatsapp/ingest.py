"""Ingesta de eventos del webhook de Meta (procesamiento asíncrono).

Garantías:
- Idempotencia por wamid: reprocesar el mismo evento no duplica mensajes.
- Todo el payload crudo se conserva (raw_payload JSONB).
- La caída de n8n nunca bloquea la persistencia (dispatch en cola aparte).
"""

from datetime import datetime

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ids import uuid7
from app.db.models import Attachment, Conversation, Message, MessageStatusEvent
from app.db.models.enums import (
    MESSAGE_STATUS_ORDER,
    AttachmentDownloadStatus,
    ConversationStatus,
    MessageDirection,
    MessageOrigin,
    MessageStatus,
    MessageType,
)
from app.db.models import WhatsAppAccount
from app.db.session import get_sessionmaker
from app.infra.queue import TASK_DISPATCH_N8N, TASK_DOWNLOAD_MEDIA, TASK_MARK_READ, get_queue
from app.modules.accounts.service import TOKEN_PENDING, get_account_by_phone_number_id
from app.modules.conversations.service import get_or_create_contact, get_or_create_conversation
from app.modules.n8n_dispatch.service import create_message_received_delivery
from app.modules.whatsapp.media import download_audio_inline
from app.modules.whatsapp.parser import (
    ParsedInboundMessage,
    ParsedStatusEvent,
    parse_meta_event,
)

log = structlog.get_logger()


async def handle_ingest_meta_event(payload: dict) -> None:
    """Handler de la tarea TASK_INGEST_META."""
    async with get_sessionmaker()() as session:
        await ingest_meta_event(session, payload["event"])


async def ingest_meta_event(session: AsyncSession, event: dict) -> None:
    inbound, statuses = parse_meta_event(event)
    for parsed in inbound:
        await _ingest_message(session, parsed)
    for status_event in statuses:
        await _apply_status(session, status_event)


async def _ingest_message(session: AsyncSession, parsed: ParsedInboundMessage) -> None:
    account = await get_account_by_phone_number_id(session, parsed.phone_number_id)
    if account is None:
        # Auto-registro: recibir nunca requiere configuración previa. El mensaje
        # se guarda y se reenvía a n8n; el token se carga después en el panel
        # (solo hace falta para RESPONDER y descargar media).
        account = WhatsAppAccount(
            name=f"Auto: {parsed.display_phone_number or parsed.phone_number_id}",
            waba_id="",
            phone_number_id=parsed.phone_number_id,
            display_phone_number=parsed.display_phone_number or parsed.phone_number_id,
            access_token_ciphertext=TOKEN_PENDING,
        )
        session.add(account)
        await session.flush()
        log.info("account_auto_registered", phone_number_id=parsed.phone_number_id,
                 account_id=str(account.id))

    contact = await get_or_create_contact(session, parsed.wa_from, parsed.profile_name)
    conversation = await get_or_create_conversation(session, account.id, contact.id)

    # Idempotencia: Meta reenvía eventos → ON CONFLICT (wamid) DO NOTHING
    message_id = uuid7()
    stmt = (
        pg_insert(Message)
        .values(
            id=message_id,
            conversation_id=conversation.id,
            whatsapp_account_id=account.id,
            wamid=parsed.wamid,
            direction=MessageDirection.inbound,
            origin=MessageOrigin.whatsapp,
            type=parsed.type,
            body=parsed.body,
            status=MessageStatus.received,
            raw_payload=parsed.raw,
            wa_timestamp=parsed.wa_timestamp,
        )
        .on_conflict_do_nothing(index_elements=[Message.wamid])
        .returning(Message.id)
    )
    inserted_id = (await session.execute(stmt)).scalar_one_or_none()
    if inserted_id is None:
        log.info("meta_event_duplicate", wamid=parsed.wamid)
        await session.commit()
        return

    _touch_conversation_inbound(conversation, parsed.wa_timestamp)

    attachment: Attachment | None = None
    if parsed.media is not None:
        attachment = Attachment(
            message_id=message_id,
            media_id=parsed.media.media_id,
            mime_type=parsed.media.mime_type,
            file_name=parsed.media.file_name,
            sha256=parsed.media.sha256,
            download_status=AttachmentDownloadStatus.pending,
        )
        session.add(attachment)
        await session.flush()

    message = await session.get(Message, message_id)

    # Audio: bajarlo ANTES de armar el webhook a n8n. El payload se congela acá
    # (delivery.payload es JSON fijo) — si no está bajado ya, storagePath queda
    # null para siempre y n8n no tiene forma de pedirlo después.
    if (
        attachment is not None
        and parsed.type == MessageType.audio
        and account.access_token_ciphertext != TOKEN_PENDING
    ):
        await download_audio_inline(attachment, message, account, get_settings())

    delivery = await create_message_received_delivery(
        session,
        settings=get_settings(),
        account=account,
        conversation=conversation,
        contact=contact,
        message=message,
        attachment=attachment,
    )
    await session.commit()

    log.info(
        "message_persisted",
        message_id=str(message_id),
        wamid=parsed.wamid,
        account_id=str(account.id),
        conversation_id=str(conversation.id),
        type=parsed.type.value,
    )

    queue = get_queue()
    if (
        attachment is not None
        and attachment.download_status != AttachmentDownloadStatus.done
        and account.access_token_ciphertext != TOKEN_PENDING
    ):
        # Descargar media requiere el token de la cuenta. Si ya se bajó en
        # línea (audio) no hace falta reencolar.
        await queue.enqueue(TASK_DOWNLOAD_MEDIA, {"attachment_id": str(attachment.id)})
    if delivery is not None:
        await queue.enqueue(TASK_DISPATCH_N8N, {"delivery_id": str(delivery.id)})
    if (
        parsed.type in (MessageType.text, MessageType.audio)
        and account.access_token_ciphertext != TOKEN_PENDING
    ):
        # Doble check azul + indicador "escribiendo..." solo en texto/audio
        # (requiere token propio)
        await queue.enqueue(TASK_MARK_READ, {"message_id": str(message_id)})


def _touch_conversation_inbound(conversation: Conversation, occurred_at: datetime) -> None:
    conversation.last_message_at = occurred_at
    conversation.last_inbound_at = occurred_at
    conversation.unread_count += 1
    if conversation.status == ConversationStatus.closed:
        conversation.status = ConversationStatus.open


async def _apply_status(session: AsyncSession, event: ParsedStatusEvent) -> None:
    import sqlalchemy as sa

    result = await session.execute(sa.select(Message).where(Message.wamid == event.wamid))
    message = result.scalar_one_or_none()
    if message is None:
        log.warning("status_for_unknown_message", wamid=event.wamid, status=event.status.value)
        return

    session.add(
        MessageStatusEvent(
            message_id=message.id,
            status=event.status,
            raw_payload=event.raw,
            occurred_at=event.occurred_at,
        )
    )

    if event.status == MessageStatus.failed:
        message.status = MessageStatus.failed
        message.error_detail = {"errors": event.errors}
    else:
        # Solo hacia adelante: nunca pisar 'read' con 'delivered'
        current = MESSAGE_STATUS_ORDER.get(message.status, -1)
        incoming = MESSAGE_STATUS_ORDER.get(event.status, -1)
        if incoming > current:
            message.status = event.status

    await session.commit()
