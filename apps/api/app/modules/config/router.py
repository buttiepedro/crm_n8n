"""Panel técnico (/api/v1/config/**): TODAS las rutas exigen sesión con
config:access + step-up vigente con ADMIN_PANEL_PASSWORD (get_config_auth).

Desde acá se configura todo lo que NO va en el .env: credenciales de
WhatsApp por cuenta, verify token / app secret de Meta, webhooks a n8n,
API keys, usuarios y visores de logs/entregas.
"""

import secrets
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.security import generate_api_key
from app.db.models import (
    ApiKey,
    EventLog,
    Message,
    User,
    WebhookDelivery,
    WhatsAppAccount,
)
from app.db.models.enums import MessageStatus, UserRole, WaAccountStatus
from app.db.session import get_db
from app.infra.queue import TASK_DISPATCH_N8N, TASK_SEND_MESSAGE, get_queue
from app.modules.accounts.service import (
    decrypt_access_token,
    encrypt_access_token,
    encrypt_webhook_secret,
    has_token,
)
from app.modules.audit.service import log_event
from app.modules.auth.deps import AuthContext, get_config_auth
from app.modules.auth.passwords import hash_password
from app.modules.auth.service import revoke_all_sessions
from app.modules.n8n_dispatch.service import EVENT_MESSAGE_RECEIVED
from app.modules.settings.service import (
    KEY_GRAPH_VERSION,
    KEY_N8N_WEBHOOK_SECRET,
    KEY_N8N_WEBHOOK_URL,
    KEY_WA_APP_SECRET,
    KEY_WA_VERIFY_TOKEN,
    get_setting,
    set_setting,
)
from app.modules.whatsapp.graph_client import GraphApiError, WhatsAppGraphClient
from app.schemas.hooks import CamelModel

log = structlog.get_logger()
router = APIRouter(prefix="/config", tags=["config-panel"],
                   dependencies=[Depends(get_config_auth)])


# ── Plataforma (Meta: verify token, app secret, versión) ──────────────────

@router.get("/platform")
async def get_platform(db: AsyncSession = Depends(get_db)) -> dict:
    verify_token = await get_setting(db, KEY_WA_VERIFY_TOKEN)
    app_secret = await get_setting(db, KEY_WA_APP_SECRET)
    return {
        # el verify token se muestra: hay que pegarlo en la config de Meta
        "verifyToken": verify_token,
        "appSecretSet": bool(app_secret),
        "graphApiVersion": await get_setting(db, KEY_GRAPH_VERSION, "v21.0"),
        # Webhook GLOBAL hacia n8n (todas las cuentas; una cuenta puede pisarlo)
        "n8nWebhookUrl": await get_setting(db, KEY_N8N_WEBHOOK_URL),
        "n8nWebhookSecretSet": bool(await get_setting(db, KEY_N8N_WEBHOOK_SECRET)),
    }


class PlatformIn(CamelModel):
    verify_token: str | None = None
    app_secret: str | None = None
    graph_api_version: str | None = None
    # alias explícito: to_camel("n8n_…") generaría "n8N…" (el 8 rompe el camelCase)
    n8n_webhook_url: str | None = Field(None, alias="n8nWebhookUrl")  # "" → quitar
    n8n_webhook_secret: str | None = Field(None, alias="n8nWebhookSecret")


@router.put("/platform")
async def update_platform(
    body: PlatformIn,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    changed = []
    if body.verify_token is not None:
        await set_setting(db, KEY_WA_VERIFY_TOKEN, body.verify_token, updated_by=auth.user.id)
        changed.append("verify_token")
    if body.app_secret is not None:
        await set_setting(db, KEY_WA_APP_SECRET, body.app_secret, updated_by=auth.user.id)
        changed.append("app_secret")
    if body.graph_api_version is not None:
        await set_setting(db, KEY_GRAPH_VERSION, body.graph_api_version,
                          updated_by=auth.user.id)
        changed.append("graph_api_version")
    if body.n8n_webhook_url is not None:
        await set_setting(db, KEY_N8N_WEBHOOK_URL, body.n8n_webhook_url or None,
                          updated_by=auth.user.id)
        changed.append("n8n_webhook_url")
    if body.n8n_webhook_secret is not None:
        await set_setting(db, KEY_N8N_WEBHOOK_SECRET, body.n8n_webhook_secret or None,
                          updated_by=auth.user.id)
        changed.append("n8n_webhook_secret")
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="platform.settings_updated", metadata={"changed": changed})
    await db.commit()
    return {"ok": True, "changed": changed}


@router.post("/platform/generate-verify-token")
async def generate_verify_token(
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = secrets.token_urlsafe(24)
    await set_setting(db, KEY_WA_VERIFY_TOKEN, token, updated_by=auth.user.id)
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="platform.verify_token_generated")
    await db.commit()
    return {"verifyToken": token}


# ── Cuentas WhatsApp ───────────────────────────────────────────────────────

def _account_row(a: WhatsAppAccount) -> dict:
    return {
        "id": str(a.id), "name": a.name, "wabaId": a.waba_id,
        "phoneNumberId": a.phone_number_id, "displayPhoneNumber": a.display_phone_number,
        "status": a.status.value,
        "n8nInboundWebhookUrl": a.n8n_inbound_webhook_url,
        "hasWebhookSecret": a.n8n_webhook_secret_ciphertext is not None,
        "tokenSet": has_token(a),
        "settings": a.settings,
        "createdAt": a.created_at.isoformat(),
    }


@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db)) -> dict:
    accounts = (await db.execute(
        sa.select(WhatsAppAccount).order_by(WhatsAppAccount.created_at))).scalars().all()
    return {"items": [_account_row(a) for a in accounts]}


class AccountIn(CamelModel):
    name: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str
    access_token: str = Field(min_length=10)  # write-only: jamás se devuelve
    n8n_inbound_webhook_url: str | None = Field(None, alias="n8nInboundWebhookUrl")
    n8n_webhook_secret: str | None = Field(None, alias="n8nWebhookSecret")


@router.post("/accounts", status_code=201)
async def create_account(
    body: AccountIn,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    account = WhatsAppAccount(
        id=uuid7(), name=body.name, waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        display_phone_number=body.display_phone_number,
        access_token_ciphertext=b"pendiente",
        n8n_inbound_webhook_url=body.n8n_inbound_webhook_url,
    )
    account.access_token_ciphertext = encrypt_access_token(settings, account.id,
                                                           body.access_token)
    if body.n8n_webhook_secret:
        account.n8n_webhook_secret_ciphertext = encrypt_webhook_secret(
            settings, account.id, body.n8n_webhook_secret)
    db.add(account)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="account.created",
                    entity_type="whatsapp_account", entity_id=account.id,
                    metadata={"name": body.name, "phoneNumberId": body.phone_number_id})
    await db.commit()
    return _account_row(account)


class AccountPatch(CamelModel):
    name: str | None = None
    waba_id: str | None = None
    phone_number_id: str | None = None  # corregible mientras esté mal cargado
    display_phone_number: str | None = None
    status: WaAccountStatus | None = None
    access_token: str | None = None  # reemplazo write-only
    n8n_inbound_webhook_url: str | None = Field(None, alias="n8nInboundWebhookUrl")
    n8n_webhook_secret: str | None = Field(None, alias="n8nWebhookSecret")
    clear_webhook_url: bool = False


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: uuid.UUID,
    body: AccountPatch,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    account = await db.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta inexistente")
    changed = []
    if body.name:
        account.name = body.name; changed.append("name")
    if body.waba_id:
        account.waba_id = body.waba_id; changed.append("waba_id")
    if body.phone_number_id and body.phone_number_id != account.phone_number_id:
        dup = (await db.execute(
            sa.select(WhatsAppAccount.id).where(
                WhatsAppAccount.phone_number_id == body.phone_number_id,
                WhatsAppAccount.id != account.id,
            )
        )).scalar_one_or_none()
        if dup:
            raise ConflictError("Ya existe otra cuenta con ese Phone Number ID")
        account.phone_number_id = body.phone_number_id
        changed.append("phone_number_id")
    if body.display_phone_number:
        account.display_phone_number = body.display_phone_number; changed.append("phone")
    if body.status is not None:
        account.status = body.status; changed.append("status")
    if body.access_token:
        account.access_token_ciphertext = encrypt_access_token(settings, account.id,
                                                               body.access_token)
        account.token_key_version = 1
        changed.append("access_token")
    if body.clear_webhook_url:
        account.n8n_inbound_webhook_url = None; changed.append("webhook_url")
    elif body.n8n_inbound_webhook_url is not None:
        account.n8n_inbound_webhook_url = body.n8n_inbound_webhook_url
        changed.append("webhook_url")
    if body.n8n_webhook_secret:
        account.n8n_webhook_secret_ciphertext = encrypt_webhook_secret(
            settings, account.id, body.n8n_webhook_secret)
        changed.append("webhook_secret")
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="account.updated",
                    entity_type="whatsapp_account", entity_id=account.id,
                    metadata={"changed": changed})
    await db.commit()
    return _account_row(account)


@router.post("/accounts/{account_id}/test")
async def test_account(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.settings.service import get_setting_cached

    settings = get_settings()
    account = await db.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta inexistente")
    client = WhatsAppGraphClient(
        access_token=decrypt_access_token(settings, account),
        phone_number_id=account.phone_number_id,
        api_version=await get_setting_cached(KEY_GRAPH_VERSION, "v21.0"),
    )
    try:
        info = await client.check_connection()
        if account.status == WaAccountStatus.error:
            account.status = WaAccountStatus.active
        await db.commit()
        return {"ok": True, "phone": info.get("display_phone_number"),
                "quality": info.get("quality_rating")}
    except GraphApiError as exc:
        account.status = WaAccountStatus.error
        await db.commit()
        return {"ok": False, "status": exc.status, "detail": exc.detail}


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Borra una cuenta SOLO si no tiene mensajes ni conversaciones (p.ej. la
    de prueba del seed). Con historial, pausarla en vez de borrarla."""
    from app.db.models import Conversation

    account = await db.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta inexistente")
    msg_count = (await db.execute(
        sa.select(sa.func.count()).where(Message.whatsapp_account_id == account_id)
    )).scalar_one()
    conv_count = (await db.execute(
        sa.select(sa.func.count()).where(Conversation.whatsapp_account_id == account_id)
    )).scalar_one()
    if msg_count or conv_count:
        raise ConflictError(
            f"La cuenta tiene historial ({msg_count} mensajes): pausala en vez de borrarla")
    await db.execute(
        sa.delete(WebhookDelivery).where(WebhookDelivery.whatsapp_account_id == account_id))
    await db.delete(account)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="account.deleted",
                    entity_type="whatsapp_account", entity_id=account_id,
                    metadata={"name": account.name})
    await db.commit()
    return {"ok": True}


@router.post("/accounts/{account_id}/subscribe")
async def subscribe_account_waba(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Suscribe la app a la WABA de la cuenta (requisito de Meta para que
    lleguen los webhooks; configurar el webhook de la app NO alcanza)."""
    from app.modules.settings.service import get_setting_cached

    settings = get_settings()
    account = await db.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta inexistente")
    client = WhatsAppGraphClient(
        access_token=decrypt_access_token(settings, account),
        phone_number_id=account.phone_number_id,
        api_version=await get_setting_cached(KEY_GRAPH_VERSION, "v21.0"),
    )
    try:
        result = await client.subscribe_app(account.waba_id)
        subs = await client.get_subscribed_apps(account.waba_id)
        await log_event(db, actor_type="user", actor_id=auth.user.id,
                        action="account.waba_subscribed", entity_type="whatsapp_account",
                        entity_id=account.id, metadata={"wabaId": account.waba_id})
        await db.commit()
        return {"ok": True, "result": result, "subscribedApps": subs.get("data", [])}
    except GraphApiError as exc:
        return {"ok": False, "status": exc.status, "detail": exc.detail}


@router.post("/accounts/{account_id}/test-webhook")
async def test_account_webhook(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    account = await db.get(WhatsAppAccount, account_id)
    if account is None:
        raise NotFoundError("Cuenta inexistente")
    target_url = account.n8n_inbound_webhook_url or await get_setting(db, KEY_N8N_WEBHOOK_URL)
    if not target_url:
        raise ConflictError(
            "Sin webhook n8n: configurar el global (WhatsApp/Meta) o uno en la cuenta")
    payload = {
        "event": EVENT_MESSAGE_RECEIVED, "eventId": str(uuid7()),
        "occurredAt": datetime.now(UTC).isoformat(), "test": True,
        "account": {"id": str(account.id), "name": account.name,
                    "phoneNumberId": account.phone_number_id,
                    "displayPhoneNumber": account.display_phone_number},
        "conversation": {"id": str(uuid7()), "status": "open", "assignedUserId": None},
        "contact": {"id": str(uuid7()), "waId": "5491100000000",
                    "profileName": "Evento de prueba"},
        "lead": None,
        "message": {"id": str(uuid7()), "wamid": "wamid.TEST", "type": "text",
                    "body": "Evento de prueba desde el panel técnico",
                    "waTimestamp": datetime.now(UTC).isoformat(), "attachments": []},
    }
    delivery = WebhookDelivery(
        whatsapp_account_id=account.id, target_url=target_url,
        event_type=EVENT_MESSAGE_RECEIVED, payload=payload,
    )
    db.add(delivery)
    await db.commit()
    await get_queue().enqueue(TASK_DISPATCH_N8N, {"delivery_id": str(delivery.id)})
    return {"deliveryId": str(delivery.id)}


# ── API keys para n8n ──────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(db: AsyncSession = Depends(get_db)) -> dict:
    keys = (await db.execute(sa.select(ApiKey).order_by(ApiKey.created_at))).scalars().all()
    return {"items": [
        {"id": str(k.id), "name": k.name, "prefix": k.key_prefix, "scopes": k.scopes,
         "isActive": k.is_active and k.revoked_at is None,
         "lastUsedAt": k.last_used_at.isoformat() if k.last_used_at else None,
         "createdAt": k.created_at.isoformat()}
        for k in keys
    ]}


class ApiKeyIn(CamelModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["hooks:messages", "hooks:leads"])


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyIn,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    full_key, prefix, key_hash = generate_api_key()
    key = ApiKey(name=body.name, key_hash=key_hash, key_prefix=prefix,
                 scopes=body.scopes, created_by=auth.user.id)
    db.add(key)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="api_key.created",
                    entity_type="api_key", entity_id=key.id, metadata={"name": body.name})
    await db.commit()
    # El valor completo se devuelve UNA sola vez
    return {"id": str(key.id), "apiKey": full_key}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    key = await db.get(ApiKey, key_id)
    if key is None:
        raise NotFoundError("API key inexistente")
    key.is_active = False
    key.revoked_at = datetime.now(UTC)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="api_key.revoked",
                    entity_type="api_key", entity_id=key.id)
    await db.commit()
    return {"ok": True}


# ── Usuarios ───────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)) -> dict:
    users = (await db.execute(sa.select(User).order_by(User.created_at))).scalars().all()
    return {"items": [
        {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role.value,
         "isActive": u.is_active,
         "lastLoginAt": u.last_login_at.isoformat() if u.last_login_at else None}
        for u in users
    ]}


class UserIn(CamelModel):
    email: str
    name: str
    role: UserRole = UserRole.agent
    password: str = Field(min_length=10)


@router.post("/users", status_code=201)
async def create_user(
    body: UserIn,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = body.email.lower().strip()
    exists = (await db.execute(sa.select(User.id).where(User.email == email))).scalar_one_or_none()
    if exists:
        raise ConflictError("Ya existe un usuario con ese email")
    user = User(email=email, name=body.name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="user.created",
                    entity_type="user", metadata={"email": email, "role": body.role.value})
    await db.commit()
    return {"id": str(user.id)}


class UserPatch(CamelModel):
    name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=10)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Usuario inexistente")
    if body.name:
        user.name = body.name
    if body.role is not None:
        user.role = body.role
    if body.password:
        user.password_hash = hash_password(body.password)
        await revoke_all_sessions(db, user.id)
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await revoke_all_sessions(db, user.id)
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="user.updated",
                    entity_type="user", entity_id=user.id,
                    metadata=body.model_dump(mode="json", exclude={"password"},
                                             exclude_none=True))
    await db.commit()
    return {"ok": True}


# ── Logs: auditoría, entregas a n8n, mensajes fallidos ─────────────────────

@router.get("/event-logs")
async def list_event_logs(
    action: str | None = None,
    entity_type: str | None = Query(None, alias="entityType"),
    before: datetime | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = sa.select(EventLog).order_by(EventLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(EventLog.action.ilike(f"%{action}%"))
    if entity_type:
        stmt = stmt.where(EventLog.entity_type == entity_type)
    if before:
        stmt = stmt.where(EventLog.created_at < before)
    logs = (await db.execute(stmt)).scalars().all()
    return {"items": [
        {"id": str(e.id), "actorType": e.actor_type,
         "actorId": str(e.actor_id) if e.actor_id else None,
         "action": e.action, "entityType": e.entity_type,
         "entityId": str(e.entity_id) if e.entity_id else None,
         "metadata": e.metadata_json, "traceId": e.trace_id,
         "createdAt": e.created_at.isoformat()}
        for e in logs
    ]}


@router.get("/webhook-deliveries")
async def list_deliveries(
    account_id: uuid.UUID | None = Query(None, alias="accountId"),
    only_failed: bool = Query(False, alias="onlyFailed"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = sa.select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)
    if account_id:
        stmt = stmt.where(WebhookDelivery.whatsapp_account_id == account_id)
    if only_failed:
        stmt = stmt.where(WebhookDelivery.succeeded.is_(False))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [
        {"id": str(d.id), "accountId": str(d.whatsapp_account_id),
         "eventType": d.event_type, "targetUrl": d.target_url, "attempt": d.attempt,
         "responseStatus": d.response_status, "succeeded": d.succeeded,
         "createdAt": d.created_at.isoformat()}
        for d in rows
    ]}


@router.post("/webhook-deliveries/{delivery_id}/redeliver")
async def redeliver(
    delivery_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    delivery = await db.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise NotFoundError("Entrega inexistente")
    delivery.succeeded = False
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="delivery.redelivered", entity_type="webhook_delivery",
                    entity_id=delivery.id)
    await db.commit()
    await get_queue().enqueue(TASK_DISPATCH_N8N, {"delivery_id": str(delivery.id)})
    return {"ok": True}


@router.get("/failed-messages")
async def list_failed_messages(
    limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (await db.execute(
        sa.select(Message).where(Message.status == MessageStatus.failed)
        .order_by(Message.created_at.desc()).limit(limit)
    )).scalars().all()
    return {"items": [
        {"id": str(m.id), "conversationId": str(m.conversation_id), "type": m.type.value,
         "body": (m.body or "")[:120], "errorDetail": m.error_detail,
         "createdAt": m.created_at.isoformat()}
        for m in rows
    ]}


@router.post("/messages/{message_id}/requeue")
async def requeue_message(
    message_id: uuid.UUID,
    auth: AuthContext = Depends(get_config_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    message = await db.get(Message, message_id)
    if message is None or message.status != MessageStatus.failed:
        raise NotFoundError("Mensaje inexistente o no está en estado failed")
    message.status = MessageStatus.queued
    message.error_detail = None
    await log_event(db, actor_type="user", actor_id=auth.user.id,
                    action="message.requeued", entity_type="message", entity_id=message.id)
    await db.commit()
    await get_queue().enqueue(TASK_SEND_MESSAGE, {"message_id": str(message.id)})
    return {"ok": True}
