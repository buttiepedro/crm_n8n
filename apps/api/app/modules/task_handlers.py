"""Registro central de handlers de tareas asíncronas.

Módulo separado para evitar ciclos de import entre la cola y los módulos.
"""

from app.infra.queue import (
    TASK_DISPATCH_N8N,
    TASK_DOWNLOAD_MEDIA,
    TASK_INGEST_META,
    TASK_MARK_READ,
    TASK_SEND_MESSAGE,
    TaskQueue,
)
from app.modules.messages.outbound import handle_send_message
from app.modules.n8n_dispatch.service import handle_dispatch_n8n_event
from app.modules.whatsapp.ingest import handle_ingest_meta_event
from app.modules.whatsapp.media import handle_download_media
from app.modules.whatsapp.receipts import handle_mark_read


def register_task_handlers(queue: TaskQueue) -> None:
    queue.register(TASK_INGEST_META, handle_ingest_meta_event)
    queue.register(TASK_SEND_MESSAGE, handle_send_message)
    queue.register(TASK_DISPATCH_N8N, handle_dispatch_n8n_event)
    queue.register(TASK_DOWNLOAD_MEDIA, handle_download_media)
    queue.register(TASK_MARK_READ, handle_mark_read)
