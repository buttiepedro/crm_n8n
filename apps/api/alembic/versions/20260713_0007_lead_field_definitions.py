"""Campos custom de lead configurables por admin (esquema; los valores viven
en leads.attributes[key]).

Revision ID: 0007_lead_field_definitions
Revises: 0006_conversation_tags
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_lead_field_definitions"
down_revision: Union[str, None] = "0006_conversation_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE lead_field_definitions (
	key TEXT NOT NULL,
	label TEXT NOT NULL,
	type TEXT NOT NULL,
	options JSONB,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key),
	CONSTRAINT ck_field_def_type CHECK (type IN ('text', 'number', 'date', 'select'))
)"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_field_definitions CASCADE")
