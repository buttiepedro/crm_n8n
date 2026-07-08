"""Descarga de media entrante: Meta → storage (local en dev, GCS en prod).

La URL de descarga de Meta expira en ~5 minutos: la tarea corre inmediata
tras la ingesta, con reintentos para fallos transitorios.
"""

import hashlib

import structlog

from app.core.config import get_settings
from app.core.errors import ConflictError, RetryableTaskError
from app.db.models import Attachment, Message
from app.db.models.enums import AttachmentDownloadStatus
from app.db.session import get_sessionmaker
from app.infra.storage import get_storage
from app.modules.accounts.service import decrypt_access_token, get_account
from app.modules.settings.service import KEY_GRAPH_VERSION, get_setting_cached
from app.modules.whatsapp.graph_client import GraphApiError, WhatsAppGraphClient
from app.modules.whatsapp.transcription import transcribe_audio

log = structlog.get_logger()

MAX_MEDIA_BYTES = 100 * 1024 * 1024  # límite configurable vía settings en P4


async def _perform_download(attachment: Attachment, message: Message, account, settings) -> None:
    """Baja el media de Meta y lo guarda en storage (deja el commit al caller).

    Lanza RetryableTaskError para fallos transitorios (5xx, red, rate limit);
    cualquier otro fallo marca el adjunto como failed y retorna sin excepción.
    """
    try:
        access_token = decrypt_access_token(settings, account)
    except ConflictError as exc:
        attachment.download_status = AttachmentDownloadStatus.failed
        log.error("media_download_failed_credentials",
                  attachment_id=str(attachment.id), code=exc.code)
        return

    client = WhatsAppGraphClient(
        access_token=access_token,
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
        log.error("media_download_failed", attachment_id=str(attachment.id),
                  status=exc.status, detail=exc.detail)
        return

    if len(data) > MAX_MEDIA_BYTES:
        attachment.download_status = AttachmentDownloadStatus.failed
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
    log.info("media_downloaded", attachment_id=str(attachment.id), size=len(data))

    if attachment.mime_type.startswith("audio/"):
        attachment.transcript = await transcribe_audio(
            data, attachment.mime_type, attachment.file_name
        )


async def handle_download_media(payload: dict) -> None:
    """Handler de la tarea TASK_DOWNLOAD_MEDIA (red de respaldo: reintenta lo
    que no se pudo bajar en línea, o baja los tipos que no se bajan en línea)."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        attachment = await session.get(Attachment, payload["attachment_id"])
        if attachment is None or attachment.download_status == AttachmentDownloadStatus.done:
            return
        message = await session.get(Message, attachment.message_id)
        account = await get_account(session, message.whatsapp_account_id)
        await _perform_download(attachment, message, account, settings)
        await session.commit()


async def download_audio_inline(attachment: Attachment, message: Message, account, settings) -> None:
    """Baja el audio en línea, durante la ingesta, para que el webhook a n8n
    ya salga con el path del archivo resuelto (n8n no tiene que pedirlo aparte).

    Best-effort: cualquier fallo se traga acá (el mensaje no puede depender de
    que Meta responda rápido); TASK_DOWNLOAD_MEDIA queda como red de respaldo.
    """
    try:
        await _perform_download(attachment, message, account, settings)
    except RetryableTaskError as exc:
        log.warning("audio_inline_download_deferred",
                    attachment_id=str(attachment.id), error=str(exc))
