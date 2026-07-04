import pytest
from cryptography.exceptions import InvalidTag

from app.core.crypto import CURRENT_KEY_VERSION, CredentialsCipher

KEY = b"0" * 32


def test_roundtrip():
    cipher = CredentialsCipher(KEY)
    blob = cipher.encrypt("EAAG-token-secreto", aad="cuenta-123")
    assert cipher.decrypt(blob, aad="cuenta-123") == "EAAG-token-secreto"


def test_version_byte():
    blob = CredentialsCipher(KEY).encrypt("x", aad="a")
    assert blob[0] == CURRENT_KEY_VERSION


def test_wrong_aad_fails():
    """El AAD liga el blob a su fila: no se puede trasplantar a otra cuenta."""
    cipher = CredentialsCipher(KEY)
    blob = cipher.encrypt("token", aad="cuenta-A")
    with pytest.raises(InvalidTag):
        cipher.decrypt(blob, aad="cuenta-B")


def test_tampered_blob_fails():
    cipher = CredentialsCipher(KEY)
    blob = bytearray(cipher.encrypt("token", aad="a"))
    blob[-1] ^= 0xFF
    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(blob), aad="a")


def test_wrong_key_length_rejected():
    with pytest.raises(ValueError):
        CredentialsCipher(b"corta")
