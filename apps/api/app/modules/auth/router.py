"""Endpoints de autenticación: login, logout, me, cambio de contraseña y
step-up del panel técnico (ADMIN_PANEL_PASSWORD del .env, comparación en
tiempo constante, ventana corta renovable)."""

import hmac
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import DomainError, UnauthorizedError
from app.db.session import get_db
from app.modules.audit.service import log_event
from app.modules.auth.deps import AuthContext, get_auth
from app.modules.auth.passwords import hash_password, verify_password
from app.modules.auth.service import (
    SESSION_COOKIE,
    authenticate,
    create_session,
    rate_limit_ok,
    revoke_all_sessions,
    revoke_session,
)
from app.schemas.hooks import CamelModel

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(CamelModel):
    email: str
    password: str


class StepUpIn(CamelModel):
    password: str


class ChangePasswordIn(CamelModel):
    current_password: str
    new_password: str = Field(min_length=10)


def _me_payload(auth: AuthContext) -> dict:
    until = auth.session.config_panel_until
    return {
        "id": str(auth.user.id),
        "email": auth.user.email,
        "name": auth.user.name,
        "role": auth.user.role.value,
        "permissions": sorted(auth.permissions),
        "configPanelUntil": until.isoformat() if until else None,
    }


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    settings = get_settings()
    ip = request.client.host if request.client else "?"
    if not rate_limit_ok(f"login:{ip}:{body.email.lower()}"):
        raise DomainError("Demasiados intentos; esperá un minuto", code="RATE_LIMITED",
                          http_status=429)

    user = await authenticate(db, body.email, body.password)
    if user is None:
        await log_event(db, actor_type="system", action="auth.login_failed",
                        metadata={"email": body.email.lower(), "ip": ip})
        await db.commit()
        raise UnauthorizedError("Credenciales inválidas")

    token = await create_session(db, user, ip=ip,
                                 user_agent=request.headers.get("User-Agent"))
    await log_event(db, actor_type="user", actor_id=user.id, action="auth.login")
    await db.commit()

    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600, path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response,
                 db: AsyncSession = Depends(get_db)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await revoke_session(db, token)
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(auth: AuthContext = Depends(get_auth)) -> dict:
    return _me_payload(auth)


@router.post("/config-panel")
async def config_panel_stepup(
    body: StepUpIn, request: Request,
    auth: AuthContext = Depends(get_auth), db: AsyncSession = Depends(get_db),
) -> dict:
    """Step-up: ni siquiera un admin logueado entra al panel técnico sin la
    contraseña explícita del .env."""
    settings = get_settings()
    if "config:access" not in auth.permissions:
        raise DomainError("Sin acceso al panel técnico", code="FORBIDDEN", http_status=403)

    ip = request.client.host if request.client else "?"
    if not rate_limit_ok(f"stepup:{auth.user.id}", max_per_minute=3):
        raise DomainError("Demasiados intentos; esperá un minuto", code="RATE_LIMITED",
                          http_status=429)

    expected = settings.admin_panel_password.get_secret_value().encode()
    if not hmac.compare_digest(expected, body.password.encode()):
        await log_event(db, actor_type="user", actor_id=auth.user.id,
                        action="auth.config_stepup_failed", metadata={"ip": ip})
        await db.commit()
        raise UnauthorizedError("Contraseña del panel incorrecta")

    until = datetime.now(UTC) + timedelta(minutes=settings.config_panel_ttl_minutes)
    auth.session.config_panel_until = until
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="auth.config_stepup_ok")
    await db.commit()
    return {"configPanelUntil": until.isoformat()}


@router.post("/password")
async def change_password(
    body: ChangePasswordIn,
    auth: AuthContext = Depends(get_auth), db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_password(auth.user.password_hash, body.current_password):
        raise UnauthorizedError("Contraseña actual incorrecta")
    auth.user.password_hash = hash_password(body.new_password)
    await revoke_all_sessions(db, auth.user.id, except_session_id=auth.session.id)
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="auth.password_changed")
    await db.commit()
    return {"ok": True}
