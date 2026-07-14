"""Agrega leads.archived_at: permite archivar leads cerrados (etapa
terminal: ganado/perdido/etc.) para sacarlos del kanban sin borrarlos ni
afectar las métricas de analytics, que siguen leyendo todos los leads no
borrados.

Revision ID: 0009_lead_archived_at
Revises: 0008_bot_paused_by_global
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_lead_archived_at"
down_revision: Union[str, None] = "0008_bot_paused_by_global"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "archived_at")
