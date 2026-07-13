"""Tags de conversación: catálogo (tags) + asociación (conversation_tags).

Revision ID: 0006_conversation_tags
Revises: 0005_message_origin_system
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_conversation_tags"
down_revision: Union[str, None] = "0005_message_origin_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE tags (
	name TEXT NOT NULL,
	color TEXT NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
)"""
    )
    op.execute(
        """CREATE TABLE conversation_tags (
	conversation_id UUID NOT NULL,
	tag_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (conversation_id, tag_id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE CASCADE
)"""
    )
    op.execute("CREATE INDEX idx_conversation_tags_tag ON conversation_tags (tag_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_tags CASCADE")
    op.execute("DROP TABLE IF EXISTS tags CASCADE")
