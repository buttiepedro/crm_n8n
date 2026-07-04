"""Webhook de la WhatsApp Cloud API (Meta).

- GET: handshake de verificación (hub.challenge).
- POST: valida la firma HMAC sobre el body crudo, responde 200 de inmediato
  y procesa async (Meta exige respuesta < 20 s y desactiva webhooks lentos).

El verify token y el app secret se configuran desde el panel técnico y viven
cifrados en la DB (cache de 60 s): NADA de esto va en el .env.
"""

import json

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import verify_meta_signature
from app.infra.queue import TASK_INGEST_META, get_queue
from app.modules.settings.service import (
    KEY_WA_APP_SECRET,
    KEY_WA_VERIFY_TOKEN,
    get_setting_cached,
)

log = structlog.get_logger()

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def verify_webhook(request: Request) -> PlainTextResponse:
    params = request.query_params
    verify_token = await get_setting_cached(KEY_WA_VERIFY_TOKEN)
    if not verify_token:
        log.warning("meta_webhook_not_configured", missing="verify_token")
        raise ForbiddenError("Verify token no configurado (panel técnico → WhatsApp)")
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == verify_token
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    log.warning("meta_webhook_verify_failed")
    raise ForbiddenError("Token de verificación inválido")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    raw_body = await request.body()
    app_secret = await get_setting_cached(KEY_WA_APP_SECRET)
    if not app_secret:
        log.warning("meta_webhook_not_configured", missing="app_secret")
        raise UnauthorizedError("App secret no configurado (panel técnico → WhatsApp)")

    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(app_secret, raw_body, signature):
        log.warning("meta_webhook_invalid_signature", has_header=signature is not None)
        raise UnauthorizedError("Firma X-Hub-Signature-256 inválida")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise UnauthorizedError("Body no es JSON válido") from exc

    # Responder rápido: la ingesta corre asíncrona con reintentos
    await get_queue().enqueue(TASK_INGEST_META, {"event": event})
    return {"status": "received"}
