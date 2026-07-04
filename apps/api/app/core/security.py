"""Primitivas de seguridad de bordes: firmas HMAC y API keys.

- Webhook de Meta: valida X-Hub-Signature-256 sobre el body crudo.
- Webhook saliente a n8n: firma X-Signature-256 con el secreto de la cuenta.
- API keys de n8n: en DB solo se guarda sha256(key) + prefijo visible.
"""

import hashlib
import hmac
import secrets

API_KEY_PREFIX = "ck_live_"


def verify_meta_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def sign_payload(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Devuelve (key_completa, prefijo_visible, hash). La key completa se
    muestra UNA sola vez al crearla; nunca se persiste en claro."""
    full_key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return full_key, full_key[:12], hash_api_key(full_key)
