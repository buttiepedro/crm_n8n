"""Cuentas WhatsApp: lookup y manejo de credenciales cifradas.

Los tokens descifrados viven solo en memoria durante el request/tarea;
jamás se loguean ni se devuelven por API.
"""

import uuid

import sqlalchemy as sa
from cryptography.exceptions import InvalidTag
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import CredentialsCipher
from app.core.errors import ConflictError
from app.db.models import WhatsAppAccount

# Marcador de cuenta sin token cargado (auto-registrada o recién creada):
# recibe y reenvía a n8n, pero NO puede enviar hasta pegar el token en el panel.
TOKEN_PENDING = b"pendiente"

# Cuenta sintética única para el chat de prueba del panel técnico (is_test=True).
# phone_number_id fijo: nunca colisiona con un Phone Number ID real de Meta.
TEST_ACCOUNT_PHONE_NUMBER_ID = "test-channel"


def has_token(account: WhatsAppAccount) -> bool:
    return bool(account.access_token_ciphertext) and account.access_token_ciphertext != TOKEN_PENDING


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> WhatsAppAccount | None:
    return await session.get(WhatsAppAccount, account_id)


async def get_account_by_phone_number_id(
    session: AsyncSession, phone_number_id: str
) -> WhatsAppAccount | None:
    result = await session.execute(
        sa.select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_number_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_test_account(session: AsyncSession) -> WhatsAppAccount:
    """Cuenta única del chat de prueba (idempotente). Sin token: el envío
    saliente para esta cuenta se simula, nunca llama a la Graph API."""
    account = await get_account_by_phone_number_id(session, TEST_ACCOUNT_PHONE_NUMBER_ID)
    if account is None:
        account = WhatsAppAccount(
            name="Canal de prueba (n8n)",
            waba_id="test",
            phone_number_id=TEST_ACCOUNT_PHONE_NUMBER_ID,
            display_phone_number="test",
            access_token_ciphertext=TOKEN_PENDING,
            is_test=True,
        )
        session.add(account)
        await session.flush()
    return account


def _cipher(settings: Settings) -> CredentialsCipher:
    return CredentialsCipher(settings.encryption_key_bytes)


def decrypt_access_token(settings: Settings, account: WhatsAppAccount) -> str:
    if not has_token(account):
        raise ConflictError(
            f"La cuenta '{account.name}' no tiene access token: cargalo en el panel → Cuenta",
            code="ACCOUNT_TOKEN_MISSING",
        )
    try:
        return _cipher(settings).decrypt(account.access_token_ciphertext, aad=str(account.id))
    except (InvalidTag, ValueError) as exc:
        raise ConflictError(
            f"El token de '{account.name}' no se puede descifrar: fue guardado con otra "
            "CREDENTIALS_ENCRYPTION_KEY. Volvé a pegarlo en el panel → Cuenta",
            code="CREDENTIALS_UNREADABLE",
        ) from exc


def encrypt_access_token(settings: Settings, account_id: uuid.UUID, token: str) -> bytes:
    return _cipher(settings).encrypt(token, aad=str(account_id))


def decrypt_webhook_secret(settings: Settings, account: WhatsAppAccount) -> str | None:
    if account.n8n_webhook_secret_ciphertext is None:
        return None
    try:
        return _cipher(settings).decrypt(
            account.n8n_webhook_secret_ciphertext, aad=f"n8n:{account.id}"
        )
    except (InvalidTag, ValueError) as exc:
        raise ConflictError(
            f"El secreto de webhook de '{account.name}' no se puede descifrar "
            "(clave de cifrado cambiada): regeneralo en el panel → Cuenta",
            code="CREDENTIALS_UNREADABLE",
        ) from exc


def encrypt_webhook_secret(settings: Settings, account_id: uuid.UUID, secret: str) -> bytes:
    return _cipher(settings).encrypt(secret, aad=f"n8n:{account_id}")
