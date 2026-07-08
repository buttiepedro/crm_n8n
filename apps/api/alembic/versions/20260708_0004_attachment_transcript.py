"""Agrega attachments.transcript (transcripción de audio vía OpenAI).

Revision ID: 0004_attachment_transcript
Revises: 0003_whatsapp_account_is_test
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_attachment_transcript"
down_revision: Union[str, None] = "0003_whatsapp_account_is_test"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("transcript", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("attachments", "transcript")
