"""Descarga de media entrante: Meta → storage (local en dev, GCS en prod).

La URL de descarga de Meta expira en ~5 minutos: la tarea corre inmediata
tras la ingesta, con reintentos para fallos transitorios.
"""

import hashlib

import structlog

from app.core.config import get_settings
from app.core.errors import RetryableTaskError
from app.db.models import Attachment, Message
from app.db.models.enums import AttachmentDownloadStatus
from app.db.session import get_sessionmaker
from app.infra.storage import get_storage
from app.modules.accounts.service import decrypt_access_token, get_account
from app.modules.settings.service import KEY_GRAPH_VERSION, get_setting_cached
from app.modules.whatsapp.graph_client import GraphApiError, WhatsAppGraphClient

log = structlog.get_logger()

MAX_MEDIA_BYTES = 100 * 1024 * 1024  # límite configurable vía settings en P4


async def handle_download_media(payload: dict) -> None:
    """Handler de la tarea TASK_DOWNLOAD_MEDIA."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        attachment = await session.get(Attachment, payload["attachment_id"])
        if attachment is None or attachment.download_status == AttachmentDownloadStatus.done:
            return
        message = await session.get(Message, attachment.message_id)
        account = await get_account(session, message.whatsapp_account_id)

        client = WhatsAppGraphClient(
            access_token=decrypt_access_token(settings, account),
            phone_number_id=account.phone_number_id,
            api_version=await get_setting_cached(KEY_GRAPH_VERSION, "v21.0"),
        )

        try:
            info = await client.get_media_info(attachment.media_id)
            data = await client.download_media(info["url"])
        except GraphApiError as exc:
            if exc.retryable:
                raise RetryableTaskError(str(exc)) from exc
            attachment.download_status = AttachmentDownloadStatus.failed
            await session.commit()
            log.error("media_download_failed", attachment_id=str(attachment.id),
                      status=exc.status, detail=exc.detail)
            return

        if len(data) > MAX_MEDIA_BYTES:
            attachment.download_status = AttachmentDownloadStatus.failed
            await session.commit()
            log.error("media_too_large", attachment_id=str(attachment.id), size=len(data))
            return

        path = (
            f"accounts/{account.id}/{message.created_at:%Y/%m}/{message.id}/"
            f"{attachment.file_name or attachment.media_id}"
        )
        stored_path = await get_storage().save(path, data, attachment.mime_type)

        attachment.gcs_path = stored_path
        attachment.size_bytes = len(data)
        attachment.sha256 = hashlib.sha256(data).hexdigest()
        attachment.download_status = AttachmentDownloadStatus.done
        await session.commit()
        log.info("media_downloaded", attachment_id=str(attachment.id), size=len(data))
