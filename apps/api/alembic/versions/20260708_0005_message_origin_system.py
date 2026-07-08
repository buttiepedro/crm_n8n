"""Agrega el valor 'system' a message_origin (auto-respuestas del backend).

Revision ID: 0005_message_origin_system
Revises: 0004_attachment_transcript
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_message_origin_system"
down_revision: Union[str, None] = "0004_attachment_transcript"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE message_origin ADD VALUE IF NOT EXISTS 'system'")


def downgrade() -> None:
    # Postgres no soporta DROP VALUE de un enum: no-op (queda el valor, sin uso).
    pass
