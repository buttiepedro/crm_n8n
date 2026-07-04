"""Sesiones server-side: cookie httpOnly con token opaco (256 bits); en DB
solo vive sha256(token). Revocación inmediata = borrar la fila."""

import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AuthSession, User, UserPermission
from app.modules.auth.passwords import verify_password
from app.modules.auth.permissions import expand_permissions

SESSION_COOKIE = "crm_session"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(sa.select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()
    # Verificar siempre (respuesta idéntica para "no existe" y "clave incorrecta")
    ok = verify_password(user.password_hash, password) if user else False
    if not user or not user.is_active or not ok:
        return None
    return user


async def create_session(
    session: AsyncSession, user: User, *, ip: str | None, user_agent: str | None
) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash_token(token),
            ip=ip,
            user_agent=(user_agent or "")[:500],
            expires_at=datetime.now(UTC) + timedelta(hours=get_settings().session_ttl_hours),
        )
    )
    user.last_login_at = datetime.now(UTC)
    return token


async def get_session_with_user(
    session: AsyncSession, token: str
) -> tuple[AuthSession, User] | None:
    result = await session.execute(
        sa.select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == _hash_token(token))
    )
    row = result.first()
    if row is None:
        return None
    auth_session, user = row
    if auth_session.expires_at <= datetime.now(UTC) or not user.is_active:
        return None
    return auth_session, user


async def revoke_session(session: AsyncSession, token: str) -> None:
    await session.execute(
        sa.delete(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    )


async def revoke_all_sessions(
    session: AsyncSession, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
) -> None:
    stmt = sa.delete(AuthSession).where(AuthSession.user_id == user_id)
    if except_session_id is not None:
        stmt = stmt.where(AuthSession.id != except_session_id)
    await session.execute(stmt)


async def load_permissions(session: AsyncSession, user: User) -> set[str]:
    result = await session.execute(
        sa.select(UserPermission.permission).where(UserPermission.user_id == user.id)
    )
    granted = set(result.scalars().all())
    return expand_permissions(user.role, granted)


# ── Anti fuerza bruta (en memoria; suficiente single-instance) ─────────────
_attempts: dict[str, deque[float]] = defaultdict(deque)


def rate_limit_ok(key: str, *, max_per_minute: int = 5) -> bool:
    now = time.monotonic()
    window = _attempts[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= max_per_minute:
        return False
    window.append(now)
    return True
