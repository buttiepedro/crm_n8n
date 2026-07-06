"""Agrega conversations.bot_paused (silenciar bot para respuesta manual).

Revision ID: 0002_conversation_bot_paused
Revises: 0001_init
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_conversation_bot_paused"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("bot_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("conversations", "bot_paused")
