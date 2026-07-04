"""Webhook saliente hacia n8n: cada mensaje entrante se reenvía al workflow
configurado por cuenta, firmado con HMAC-SHA256 del secreto de la cuenta.

Cada intento queda registrado en webhook_deliveries (visible en el panel,
re-entregable manualmente). La entrega es asíncrona: la persistencia del
mensaje nunca depende de que n8n esté vivo.
"""

import json
from datetime import UTC, datetime

import httpx
import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import RetryableTaskError
from app.core.ids import uuid7
from app.core.security import sign_payload
from app.db.models import (
    Attachment,
    Contact,
    Conversation,
    Lead,
    Message,
    PipelineStage,
    WebhookDelivery,
    WhatsAppAccount,
)
from app.db.session import get_sessionmaker
from app.modules.accounts.service import decrypt_webhook_secret
from app.modules.settings.service import (
    KEY_N8N_WEBHOOK_SECRET,
    KEY_N8N_WEBHOOK_URL,
    get_setting,
    get_setting_cached,
)

log = structlog.get_logger()

EVENT_MESSAGE_RECEIVED = "message.received"
_TIMEOUT = httpx.Timeout(15.0)
_MAX_RESPONSE_BODY = 4096


async def create_message_received_delivery(
    session: AsyncSession,
    *,
    settings: Settings,
    account: WhatsAppAccount,
    conversation: Conversation,
    contact: Contact,
    message: Message,
    attachment: Attachment | None,
) -> WebhookDelivery | None:
    """Crea la fila de entrega (misma transacción que el mensaje).

    URL destino: la de la cuenta si tiene una propia; si no, el webhook
    GLOBAL de n8n (panel técnico). Sin ninguno de los dos → no se reenvía
    (el mensaje igual queda persistido)."""
    target_url = account.n8n_inbound_webhook_url or await get_setting(
        session, KEY_N8N_WEBHOOK_URL
    )
    if not target_url:
        return None

    lead = await _find_active_lead(session, conversation.id)

    payload = {
        "event": EVENT_MESSAGE_RECEIVED,
        "eventId": str(uuid7()),
        "occurredAt": datetime.now(UTC).isoformat(),
        "account": {
            "id": str(account.id),
            "name": account.name,
            "phoneNumberId": account.phone_number_id,
            "displayPhoneNumber": account.display_phone_number,
        },
        "conversation": {
            "id": str(conversation.id),
            "status": conversation.status.value,
            "assignedUserId": (
                str(conversation.assigned_user_id) if conversation.assigned_user_id else None
            ),
        },
        "contact": {
            "id": str(contact.id),
            "waId": contact.wa_id,
            "profileName": contact.profile_name,
        },
        "lead": (
            {
                "id": str(lead.id),
                "stageId": str(lead.stage_id),
                "externalKey": lead.external_key,
            }
            if lead
            else None
        ),
        "message": {
            "id": str(message.id),
            "wamid": message.wamid,
            "type": message.type.value,
            "body": message.body,
            # Payload crudo de WhatsApp, tal cual llegó de Meta
            "raw": message.raw_payload,
            "waTimestamp": message.wa_timestamp.isoformat() if message.wa_timestamp else None,
            "attachments": (
                [
                    {
                        "id": str(attachment.id),
                        "mimeType": attachment.mime_type,
                        "fileName": attachment.file_name,
                        # TODO(P5): URL firmada de GCS (15 min). Con storage local
                        # n8n puede pedir el binario a la API cuando exista el endpoint.
                        "storagePath": attachment.gcs_path,
                    }
                ]
                if attachment
                else []
            ),
        },
    }

    delivery = WebhookDelivery(
        whatsapp_account_id=account.id,
        target_url=target_url,
        event_type=EVENT_MESSAGE_RECEIVED,
        payload=payload,
    )
    session.add(delivery)
    await session.flush()
    return delivery


async def _find_active_lead(session: AsyncSession, conversation_id) -> Lead | None:
    result = await session.execute(
        sa.select(Lead)
        .join(PipelineStage, Lead.stage_id == PipelineStage.id)
        .where(
            Lead.conversation_id == conversation_id,
            Lead.deleted_at.is_(None),
            PipelineStage.is_terminal.is_(False),
        )
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def handle_dispatch_n8n_event(payload: dict) -> None:
    """Handler de la tarea TASK_DISPATCH_N8N: un intento de entrega."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        delivery = await session.get(WebhookDelivery, payload["delivery_id"])
        if delivery is None or delivery.succeeded:
            return
        account = await session.get(WhatsAppAccount, delivery.whatsapp_account_id)

        delivery.attempt += 1
        body = json.dumps(delivery.payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Event-Id": delivery.payload.get("eventId", str(delivery.id)),
            "X-Event-Type": delivery.event_type,
        }
        # Firma: secreto de la cuenta si tiene uno propio; si no, el global
        secret = decrypt_webhook_secret(settings, account) or await get_setting_cached(
            KEY_N8N_WEBHOOK_SECRET
        )
        if secret:
            headers["X-Signature-256"] = sign_payload(secret, body)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(delivery.target_url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            delivery.response_status = None
            delivery.response_body = str(exc)[:_MAX_RESPONSE_BODY]
            await session.commit()
            raise RetryableTaskError(f"n8n inalcanzable: {exc}") from exc

        delivery.response_status = resp.status_code
        delivery.response_body = resp.text[:_MAX_RESPONSE_BODY]
        if 200 <= resp.status_code < 300:
            delivery.succeeded = True
            await session.commit()
            log.info("n8n_delivery_ok", delivery_id=str(delivery.id), attempt=delivery.attempt)
        else:
            await session.commit()
            raise RetryableTaskError(f"n8n respondió {resp.status_code}")
