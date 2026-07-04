"""Seed de desarrollo (idempotente): pipeline por defecto, cuenta WhatsApp de
prueba (token cifrado) y API key para n8n — la key se imprime UNA sola vez.

Uso:  uv run python scripts/seed.py   (requiere DB migrada: alembic upgrade head)
"""

import asyncio
import os

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.security import generate_api_key
from app.db.models import ApiKey, Pipeline, PipelineStage, WhatsAppAccount
from app.db.session import get_sessionmaker, init_engine
from app.modules.accounts.service import encrypt_access_token
from app.modules.hooks.auth import SCOPE_HOOKS_LEADS, SCOPE_HOOKS_MESSAGES

DEFAULT_STAGES = [
    ("Nuevo", 1, False, None),
    ("Contactado", 2, False, None),
    ("Calificado", 3, False, None),
    ("Propuesta", 4, False, None),
    ("Ganado", 5, True, "won"),
    ("Perdido", 6, True, "lost"),
]


async def main() -> None:
    settings = get_settings()
    init_engine(settings)

    async with get_sessionmaker()() as session:
        # Pipeline por defecto
        pipeline = (
            await session.execute(sa.select(Pipeline).where(Pipeline.is_default.is_(True)))
        ).scalar_one_or_none()
        if pipeline is None:
            pipeline = Pipeline(name="Ventas", is_default=True)
            session.add(pipeline)
            await session.flush()
            for name, position, is_terminal, outcome in DEFAULT_STAGES:
                session.add(
                    PipelineStage(
                        pipeline_id=pipeline.id, name=name, position=position,
                        is_terminal=is_terminal, outcome=outcome,
                    )
                )
            print(f"✔ Pipeline por defecto 'Ventas' creado ({len(DEFAULT_STAGES)} etapas)")
        else:
            print("• Pipeline por defecto ya existe")

        # Cuenta WhatsApp de prueba
        account = (
            await session.execute(
                sa.select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == "000000000000")
            )
        ).scalar_one_or_none()
        if account is None:
            account = WhatsAppAccount(
                name="Cuenta de prueba",
                waba_id="TEST_WABA",
                phone_number_id="000000000000",
                display_phone_number="+54 9 11 0000-0000",
                access_token_ciphertext=b"pendiente",
                # n8n es externo: N8N_WEBHOOK_BASE viene del .env
                # (desde Docker, "localhost" no es tu máquina → host.docker.internal)
                n8n_inbound_webhook_url=(
                    os.environ.get("N8N_WEBHOOK_BASE", "http://localhost:5678")
                    + "/webhook/whatsapp-in"
                ),
            )
            session.add(account)
            await session.flush()
            account.access_token_ciphertext = encrypt_access_token(
                settings, account.id, "TOKEN_DE_PRUEBA_REEMPLAZAR"
            )
            print("✔ Cuenta WhatsApp de prueba creada (reemplazar token desde el panel/DB)")
        else:
            print("• Cuenta de prueba ya existe")

        # API key para n8n
        existing_key = (
            await session.execute(sa.select(ApiKey).where(ApiKey.name == "n8n-dev"))
        ).scalar_one_or_none()
        if existing_key is None:
            full_key, prefix, key_hash = generate_api_key()
            session.add(
                ApiKey(
                    name="n8n-dev",
                    key_hash=key_hash,
                    key_prefix=prefix,
                    scopes=[SCOPE_HOOKS_MESSAGES, SCOPE_HOOKS_LEADS],
                )
            )
            print("✔ API key 'n8n-dev' creada. GUARDALA — no se vuelve a mostrar:")
            print(f"    {full_key}")
        else:
            print("• API key 'n8n-dev' ya existe (revocarla y re-correr para regenerar)")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
