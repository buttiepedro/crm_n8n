"""Tests de la app FastAPI sin base de datos: health, verificación del
webhook de Meta y rechazo de firmas inválidas.

El verify token y el app secret viven en DB (settings de plataforma);
acá se inyectan al cache con prime_cache para no requerir DB."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.settings import service as platform

APP_SECRET = "app-secret-test"
VERIFY_TOKEN = "verify-token-test"


@pytest.fixture(autouse=True)
def _prime_platform_settings():
    platform.prime_cache(platform.KEY_WA_VERIFY_TOKEN, VERIFY_TOKEN)
    platform.prime_cache(platform.KEY_WA_APP_SECRET, APP_SECRET)
    yield
    platform.invalidate_cache()


def _signed(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_health():
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert "X-Trace-Id" in resp.headers


def test_webhook_verification_ok():
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "12345"


def test_webhook_verification_wrong_token():
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "malo", "hub.challenge": "x"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_webhook_post_rejects_invalid_signature():
    body = json.dumps({"entry": []}).encode()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/whatsapp/webhook",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=" + "0" * 64,
                     "Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_webhook_post_rejects_missing_signature():
    with TestClient(app) as client:
        resp = client.post("/api/v1/whatsapp/webhook", content=b"{}")
        assert resp.status_code == 401


def test_webhook_post_accepts_valid_signature():
    """Con firma válida responde 200 inmediato (la ingesta corre async)."""
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/whatsapp/webhook",
            content=body,
            headers={"X-Hub-Signature-256": _signed(body),
                     "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "received"}


def test_hooks_require_api_key_header():
    """Sin Authorization los hooks de n8n devuelven 401 sin tocar la DB."""
    with TestClient(app) as client:
        resp = client.post("/api/v1/hooks/n8n/leads", json={})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_crm_requires_session_cookie():
    """El CRM exige sesión; sin cookie → 401."""
    with TestClient(app) as client:
        assert client.get("/api/v1/conversations").status_code == 401
        assert client.get("/api/v1/auth/me").status_code == 401


def test_config_panel_requires_session():
    """El panel técnico exige sesión (y luego step-up)."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/config/accounts")
        assert resp.status_code == 401
