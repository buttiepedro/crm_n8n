"""Cuentas WhatsApp: lookup y manejo de credenciales cifradas.

Los tokens descifrados viven solo en memoria durante el request/tarea;
jamás se loguean ni se devuelven por API.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import CredentialsCipher
from app.db.models import WhatsAppAccount


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> WhatsAppAccount | None:
    return await session.get(WhatsAppAccount, account_id)


async def get_account_by_phone_number_id(
    session: AsyncSession, phone_number_id: str
) -> WhatsAppAccount | None:
    result = await session.execute(
        sa.select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_number_id)
    )
    return result.scalar_one_or_none()


def _cipher(settings: Settings) -> CredentialsCipher:
    return CredentialsCipher(settings.encryption_key_bytes)


def decrypt_access_token(settings: Settings, account: WhatsAppAccount) -> str:
    return _cipher(settings).decrypt(account.access_token_ciphertext, aad=str(account.id))


def encrypt_access_token(settings: Settings, account_id: uuid.UUID, token: str) -> bytes:
    return _cipher(settings).encrypt(token, aad=str(account_id))


def decrypt_webhook_secret(settings: Settings, account: WhatsAppAccount) -> str | None:
    if account.n8n_webhook_secret_ciphertext is None:
        return None
    return _cipher(settings).decrypt(
        account.n8n_webhook_secret_ciphertext, aad=f"n8n:{account.id}"
    )


def encrypt_webhook_secret(settings: Settings, account_id: uuid.UUID, secret: str) -> bytes:
    return _cipher(settings).encrypt(secret, aad=f"n8n:{account_id}")
