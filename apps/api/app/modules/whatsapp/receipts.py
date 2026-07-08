"""Read receipt + indicador de 'escribiendo...' para mensajes entrantes.

Cosmético: si falla, no se reintenta (el indicador dura ~25s, reintentar
tarde no tiene sentido).
"""

import structlog

from app.core.config import get_settings
from app.db.models import Message
from app.db.session import get_sessionmaker
from app.modules.accounts.service import decrypt_access_token, get_account
from app.modules.settings.service import KEY_GRAPH_VERSION, get_setting_cached
from app.modules.whatsapp.graph_client import GraphApiError, WhatsAppGraphClient

log = structlog.get_logger()


async def handle_mark_read(payload: dict) -> None:
    """Handler de la tarea TASK_MARK_READ."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        message = await session.get(Message, payload["message_id"])
        if message is None or not message.wamid:
            return
        account = await get_account(session, message.whatsapp_account_id)

        try:
            access_token = decrypt_access_token(settings, account)
        except Exception:
            log.warning("mark_read_no_token", account_id=str(account.id))
            return

        client = WhatsAppGraphClient(
            access_token=access_token,
            phone_number_id=account.phone_number_id,
            api_version=await get_setting_cached(KEY_GRAPH_VERSION, "v21.0"),
        )
        try:
            await client.mark_read_with_typing(message.wamid)
        except GraphApiError as exc:
            log.warning("mark_read_failed", message_id=str(message.id),
                        status=exc.status, detail=exc.detail)
