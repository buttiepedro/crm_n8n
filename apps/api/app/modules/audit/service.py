"""Auditoría de negocio: quién hizo qué (tabla event_logs, inmutable).

Distinta de los logs técnicos: no se rota ni se muestrea, y es consultable
desde el panel de configuración.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import current_trace_id
from app.db.models import EventLog


async def log_event(
    session: AsyncSession,
    *,
    actor_type: str,  # 'user' | 'api_key' | 'system' | 'meta'
    action: str,  # 'lead.stage_changed', 'account.token_rotated', …
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    session.add(
        EventLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata or {},
            trace_id=current_trace_id(),
        )
    )
