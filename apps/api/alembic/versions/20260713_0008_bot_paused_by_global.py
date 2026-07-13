"""Agrega conversations.bot_paused_by_global: distingue pausa por el
silenciador global de pausa manual, para que "reanudar todos" no reactive
conversaciones que un agente silenció a mano.

Revision ID: 0008_bot_paused_by_global
Revises: 0007_lead_field_definitions
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_bot_paused_by_global"
down_revision: Union[str, None] = "0007_lead_field_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("bot_paused_by_global", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("conversations", "bot_paused_by_global")
