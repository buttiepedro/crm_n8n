"""Cuentas de WhatsApp Business gestionadas por la plataforma.

Las credenciales (access token, secreto HMAC del webhook a n8n) se guardan
cifradas con AES-256-GCM; ver app/core/crypto.py.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedMixin, UUIDPkMixin
from app.db.models.enums import WaAccountStatus, WaAccountStatusType


class WhatsAppAccount(UUIDPkMixin, TimestampedMixin, Base):
    __tablename__ = "whatsapp_accounts"

    name: Mapped[str] = mapped_column(sa.Text, nullable=False)  # alias interno: 'Ventas AR'
    waba_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Clave de ruteo de los webhooks de Meta (una URL para todas las cuentas)
    phone_number_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    display_phone_number: Mapped[str] = mapped_column(sa.Text, nullable=False)
    access_token_ciphertext: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    token_key_version: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=1)
    status: Mapped[WaAccountStatus] = mapped_column(
        WaAccountStatusType, nullable=False, default=WaAccountStatus.active
    )
    # Webhook saliente hacia n8n (configurable por cuenta desde el panel)
    n8n_inbound_webhook_url: Mapped[str | None] = mapped_column(sa.Text)
    n8n_webhook_secret_ciphertext: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
