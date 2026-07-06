"""Agrega whatsapp_accounts.is_test (canal de prueba del panel técnico → n8n).

Revision ID: 0003_whatsapp_account_is_test
Revises: 0002_conversation_bot_paused
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_whatsapp_account_is_test"
down_revision: Union[str, None] = "0002_conversation_bot_paused"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_accounts",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_accounts", "is_test")
