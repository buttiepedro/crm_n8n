"""Settings de plataforma en DB (tabla `settings`), editables desde el panel.

Los valores secretos (verify token, app secret de Meta) se guardan cifrados
con AES-256-GCM: en JSONB va {"enc": "<base64>"}; los no secretos, {"v": ...}.
Cache en memoria con TTL para no golpear la DB en cada webhook.
"""

import base64
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import CredentialsCipher
from app.db.models import Setting
from app.db.session import get_sessionmaker

# Claves conocidas
KEY_WA_VERIFY_TOKEN = "whatsapp.verify_token"
KEY_WA_APP_SECRET = "whatsapp.app_secret"
KEY_GRAPH_VERSION = "whatsapp.graph_api_version"
# Webhook GLOBAL hacia n8n: todas las cuentas lo usan salvo que definan uno propio
KEY_N8N_WEBHOOK_URL = "n8n.webhook_url"
KEY_N8N_WEBHOOK_SECRET = "n8n.webhook_secret"

SECRET_KEYS = {KEY_WA_VERIFY_TOKEN, KEY_WA_APP_SECRET, KEY_N8N_WEBHOOK_SECRET}
DEFAULTS: dict[str, Any] = {KEY_GRAPH_VERSION: "v21.0"}

_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, Any]] = {}


def _cipher() -> CredentialsCipher:
    return CredentialsCipher(get_settings().encryption_key_bytes)


def _decode(key: str, stored: Any) -> Any:
    if isinstance(stored, dict) and "enc" in stored:
        blob = base64.b64decode(stored["enc"])
        return _cipher().decrypt(blob, aad=f"setting:{key}")
    if isinstance(stored, dict) and "v" in stored:
        return stored["v"]
    return stored


def _encode(key: str, value: Any) -> dict:
    if key in SECRET_KEYS and value is not None:
        blob = _cipher().encrypt(str(value), aad=f"setting:{key}")
        return {"enc": base64.b64encode(blob).decode()}
    return {"v": value}


async def get_setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key, default)
    return _decode(key, row.value)


async def set_setting(
    session: AsyncSession, key: str, value: Any, *, updated_by: uuid.UUID | None = None
) -> None:
    row = await session.get(Setting, key)
    encoded = _encode(key, value)
    if row is None:
        session.add(Setting(key=key, value=encoded, updated_by=updated_by))
    else:
        row.value = encoded
        row.updated_by = updated_by
    invalidate_cache(key)


async def get_setting_cached(key: str, default: Any = None) -> Any:
    """Para rutas calientes (webhooks): DB con cache TTL de 60 s."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    async with get_sessionmaker()() as session:
        value = await get_setting(session, key, default)
    _cache[key] = (now + _TTL_SECONDS, value)
    return value


def invalidate_cache(key: str | None = None) -> None:
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


def prime_cache(key: str, value: Any, ttl: float = 3600.0) -> None:
    """Solo para tests: inyecta un valor sin tocar la DB."""
    _cache[key] = (time.monotonic() + ttl, value)
