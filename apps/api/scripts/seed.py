"""Seed (idempotente): usuario admin inicial, pipeline por defecto, cuenta
WhatsApp de prueba y API key para n8n — credenciales se imprimen UNA sola vez.

Uso:  uv run python scripts/seed.py   (requiere DB migrada: alembic upgrade head)
"""

import asyncio
import secrets

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.security import generate_api_key
from app.db.models import ApiKey, Pipeline, PipelineStage, User
from app.db.models.enums import UserRole
from app.db.session import get_sessionmaker, init_engine
from app.modules.auth.passwords import hash_password
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
        # Usuario admin inicial (si no hay ningún usuario)
        any_user = (await session.execute(sa.select(User.id).limit(1))).scalar_one_or_none()
        if any_user is None:
            password = secrets.token_urlsafe(12)
            session.add(
                User(email="admin@crm.local", name="Administrador",
                     password_hash=hash_password(password), role=UserRole.admin)
            )
            print("✔ Usuario admin creado. GUARDÁ estas credenciales (no se repiten):")
            print("    email:    admin@crm.local")
            print(f"    password: {password}")
            print("  (cambiá la contraseña desde el panel al entrar)")
        else:
            print("• Ya existen usuarios")

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

        # Nota: ya NO se crea cuenta de prueba. Las cuentas se auto-registran
        # cuando llega el primer mensaje de WhatsApp (o se crean por el panel).

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
