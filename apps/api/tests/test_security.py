import hashlib
import hmac

from app.core.security import (
    generate_api_key,
    hash_api_key,
    sign_payload,
    verify_meta_signature,
)

SECRET = "app-secret-test"
BODY = b'{"entry":[]}'


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    assert verify_meta_signature(SECRET, BODY, _sig(SECRET, BODY))


def test_invalid_signature():
    assert not verify_meta_signature(SECRET, BODY, _sig("otro-secreto", BODY))


def test_missing_or_malformed_header():
    assert not verify_meta_signature(SECRET, BODY, None)
    assert not verify_meta_signature(SECRET, BODY, "md5=abc")


def test_signature_over_different_body_fails():
    assert not verify_meta_signature(SECRET, b'{"entry":[1]}', _sig(SECRET, BODY))


def test_sign_payload_roundtrip():
    signed = sign_payload("secreto-n8n", BODY)
    assert signed.startswith("sha256=")
    assert verify_meta_signature("secreto-n8n", BODY, signed)


def test_api_key_generation():
    full, prefix, key_hash = generate_api_key()
    assert full.startswith("ck_live_")
    assert full.startswith(prefix)
    assert key_hash == hash_api_key(full)
    assert len(key_hash) == 64  # sha256 hex
    # Dos keys nunca coinciden
    assert generate_api_key()[0] != full
