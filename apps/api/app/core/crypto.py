"""Cifrado AES-256-GCM para credenciales dinámicas (tokens de WhatsApp,
secretos HMAC de webhooks).

Formato del blob almacenado:  key_version (1 byte) || IV (12 bytes) || ciphertext+tag.
El AAD (additional authenticated data) liga el ciphertext a su fila (p.ej. el
UUID de la cuenta): un blob no puede trasplantarse a otra cuenta.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CURRENT_KEY_VERSION = 1
_IV_LEN = 12


class CredentialsCipher:
    def __init__(self, key: bytes, key_version: int = CURRENT_KEY_VERSION) -> None:
        if len(key) != 32:
            raise ValueError("La clave AES-256 debe tener exactamente 32 bytes")
        self._aesgcm = AESGCM(key)
        self._version = key_version

    def encrypt(self, plaintext: str, *, aad: str) -> bytes:
        iv = os.urandom(_IV_LEN)
        ciphertext = self._aesgcm.encrypt(iv, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return bytes([self._version]) + iv + ciphertext

    def decrypt(self, blob: bytes, *, aad: str) -> str:
        if len(blob) < 1 + _IV_LEN + 16:
            raise ValueError("Blob cifrado inválido (demasiado corto)")
        version, iv, ciphertext = blob[0], blob[1 : 1 + _IV_LEN], blob[1 + _IV_LEN :]
        if version != self._version:
            # Rotación de clave maestra: ver roadmap/next_steps_seguridad.md
            raise ValueError(f"key_version {version} no soportada por la clave configurada")
        plaintext = self._aesgcm.decrypt(iv, ciphertext, aad.encode("utf-8"))
        return plaintext.decode("utf-8")
