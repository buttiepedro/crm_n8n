"""Dependencias FastAPI de autenticación y autorización.

- get_auth: sesión válida (cookie) → AuthContext(user, session, permisos).
- require_permissions(...): además exige permisos concretos.
- get_config_auth: panel técnico = sesión + config:access + step-up vigente
  con la contraseña explícita ADMIN_PANEL_PASSWORD del .env.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, ForbiddenError, UnauthorizedError
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.modules.auth.service import SESSION_COOKIE, get_session_with_user, load_permissions


@dataclass
class AuthContext:
    user: User
    session: AuthSession
    permissions: set[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions


async def get_auth(request: Request, db: AsyncSession = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthorizedError("Sesión requerida")
    found = await get_session_with_user(db, token)
    if found is None:
        raise UnauthorizedError("Sesión inválida o expirada")
    auth_session, user = found
    return AuthContext(user=user, session=auth_session, permissions=await load_permissions(db, user))


def require_permissions(*permissions: str):
    async def dependency(auth: AuthContext = Depends(get_auth)) -> AuthContext:
        missing = [p for p in permissions if p not in auth.permissions]
        if missing:
            raise ForbiddenError(f"Faltan permisos: {', '.join(missing)}")
        return auth

    return dependency


async def get_config_auth(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if "config:access" not in auth.permissions:
        raise ForbiddenError("Sin acceso al panel técnico")
    until = auth.session.config_panel_until
    if until is None or until <= datetime.now(UTC):
        raise DomainError(
            "Se requiere la contraseña del panel técnico",
            code="CONFIG_STEPUP_REQUIRED",
            http_status=403,
        )
    return auth
