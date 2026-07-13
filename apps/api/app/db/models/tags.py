"""Tags de conversación: catálogo y asociación conversación↔tag."""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPkMixin


class Tag(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    color: Mapped[str] = mapped_column(sa.Text, nullable=False)


class ConversationTag(CreatedAtMixin, Base):
    __tablename__ = "conversation_tags"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
