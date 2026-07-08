"""Autenticación por API key de los webhooks entrantes de n8n.

Las keys se crean en el panel de configuración con scopes; en DB solo vive
sha256(key). La autorización la define la key, nunca el payload.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import hash_api_key
from app.db.models import ApiKey
from app.db.session import get_db

SCOPE_HOOKS_MESSAGES = "hooks:messages"
SCOPE_HOOKS_LEADS = "hooks:leads"
SCOPE_HOOKS_MEDIA = "hooks:media"


def require_api_key(*required_scopes: str):
    async def dependency(
        request: Request, session: AsyncSession = Depends(get_db)
    ) -> ApiKey:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise UnauthorizedError("Falta la API key (Authorization: Bearer <key>)")

        key_hash = hash_api_key(auth.removeprefix("Bearer ").strip())
        result = await session.execute(
            sa.select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active.is_(True),
                ApiKey.revoked_at.is_(None),
            )
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise UnauthorizedError("API key inválida o revocada")

        missing = set(required_scopes) - set(api_key.scopes)
        if missing:
            raise ForbiddenError(f"La API key no tiene los scopes: {', '.join(sorted(missing))}")

        api_key.last_used_at = datetime.now(UTC)  # persiste con el commit del endpoint
        return api_key

    return Depends(dependency)
