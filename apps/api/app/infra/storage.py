"""Abstracción de almacenamiento de adjuntos.

- LocalStorage (dev): archivos bajo STORAGE_LOCAL_PATH.
- GcsStorage (prod, P5): bucket privado + URLs firmadas de 15 min.

Los binarios NUNCA van a PostgreSQL: la DB guarda solo metadatos + path.
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import Settings


class Storage(ABC):
    @abstractmethod
    async def save(self, path: str, data: bytes, content_type: str) -> str:
        """Guarda el binario y devuelve el path/URI persistible en DB."""

    @abstractmethod
    async def load(self, path: str) -> bytes:
        """Lee el binario guardado (para servirlo al panel)."""


class LocalStorage(Storage):
    def __init__(self, base_path: Path) -> None:
        self._base = base_path
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        target = (self._base / path).resolve()
        if not str(target).startswith(str(self._base.resolve())):
            raise ValueError("Path fuera del directorio de storage")
        return target

    async def save(self, path: str, data: bytes, content_type: str) -> str:
        target = self._resolve(path)
        await asyncio.to_thread(self._write, target, data)
        return path

    async def load(self, path: str) -> bytes:
        target = self._resolve(path)
        return await asyncio.to_thread(target.read_bytes)

    @staticmethod
    def _write(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


_storage: Storage | None = None


def init_storage(settings: Settings) -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_driver == "local":
            _storage = LocalStorage(settings.storage_local_path)
        else:
            raise NotImplementedError(
                "GcsStorage se implementa en la fase de despliegue GCP (P5); "
                "usar STORAGE_DRIVER=local"
            )
    return _storage


def get_storage() -> Storage:
    if _storage is None:
        raise RuntimeError("Storage no inicializado: llamar init_storage() en el lifespan")
    return _storage
