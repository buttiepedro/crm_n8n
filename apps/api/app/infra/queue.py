"""Abstracción de cola de tareas.

- InlineTaskQueue (dev): ejecuta el handler en el mismo proceso, async, con
  reintentos exponenciales para RetryableTaskError.
- CloudTasksQueue (prod, P5): encola HTTP tasks hacia endpoints /internal/**
  autenticados por OIDC. Pendiente de implementar en la fase de despliegue.

Regla de reintentos: los handlers lanzan RetryableTaskError para causas
transitorias (5xx, red, rate limit); cualquier otra excepción es permanente
(se loguea y no se reintenta).
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import structlog

from app.core.config import Settings
from app.core.errors import RetryableTaskError

log = structlog.get_logger()

Handler = Callable[[dict], Awaitable[None]]

# Nombres de tareas (contrato entre productores y handlers)
TASK_INGEST_META = "ingest_meta_event"
TASK_SEND_MESSAGE = "send_whatsapp_message"
TASK_DISPATCH_N8N = "dispatch_n8n_event"
TASK_DOWNLOAD_MEDIA = "download_media"
TASK_MARK_READ = "mark_message_read"


class TaskQueue(ABC):
    @abstractmethod
    def register(self, task: str, handler: Handler) -> None: ...

    @abstractmethod
    async def enqueue(self, task: str, payload: dict) -> None: ...

    async def drain(self) -> None:
        """Espera a que terminen las tareas en vuelo (shutdown graceful/tests)."""


class InlineTaskQueue(TaskQueue):
    def __init__(self, *, max_attempts: int = 3, base_delay: float = 1.0) -> None:
        self._handlers: dict[str, Handler] = {}
        self._tasks: set[asyncio.Task] = set()
        self._max_attempts = max_attempts
        self._base_delay = base_delay

    def register(self, task: str, handler: Handler) -> None:
        self._handlers[task] = handler

    async def enqueue(self, task: str, payload: dict) -> None:
        if task not in self._handlers:
            raise ValueError(f"Tarea sin handler registrado: {task}")
        t = asyncio.create_task(self._run(task, payload))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _run(self, task: str, payload: dict) -> None:
        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._handlers[task](payload)
                return
            except RetryableTaskError as exc:
                if attempt == self._max_attempts:
                    log.error("task_retries_exhausted", task=task, attempts=attempt, error=str(exc))
                    return
                delay = self._base_delay * 2 ** (attempt - 1)
                log.warning("task_retry", task=task, attempt=attempt, retry_in_s=delay, error=str(exc))
                await asyncio.sleep(delay)
            except Exception:
                log.exception("task_failed_permanent", task=task, attempt=attempt)
                return

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


_queue: TaskQueue | None = None


def init_queue(settings: Settings) -> TaskQueue:
    global _queue
    if _queue is None:
        if settings.queue_driver == "inline":
            _queue = InlineTaskQueue()
        else:
            raise NotImplementedError(
                "CloudTasksQueue se implementa en la fase de despliegue GCP (P5); "
                "usar QUEUE_DRIVER=inline"
            )
    return _queue


def get_queue() -> TaskQueue:
    if _queue is None:
        raise RuntimeError("Cola no inicializada: llamar init_queue() en el lifespan")
    return _queue


def reset_queue() -> None:
    """Solo para tests."""
    global _queue
    _queue = None
