"""Catálogo de tags de conversación (nombre + color). La asociación
conversación↔tag vive en el router de conversations (recurso anidado)."""

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Tag
from app.db.session import get_db
from app.modules.audit.service import log_event
from app.modules.auth import permissions as perms
from app.modules.auth.deps import AuthContext, require_permissions
from app.schemas.hooks import CamelModel

router = APIRouter(tags=["tags"])


def _tag_row(t: Tag) -> dict:
    return {"id": str(t.id), "name": t.name, "color": t.color}


@router.get("/tags")
async def list_tags(
    auth: AuthContext = Depends(require_permissions(perms.CONVERSATIONS_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tags = (await db.execute(sa.select(Tag).order_by(Tag.name))).scalars().all()
    return {"items": [_tag_row(t) for t in tags]}


class TagIn(CamelModel):
    name: str
    color: str


@router.post("/tags", status_code=201)
async def create_tag(
    body: TagIn,
    auth: AuthContext = Depends(require_permissions(perms.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(
        sa.select(Tag.id).where(sa.func.lower(Tag.name) == body.name.strip().lower())
    )).scalar_one_or_none()
    if existing:
        raise ConflictError("Ya existe un tag con ese nombre")
    tag = Tag(name=body.name.strip(), color=body.color)
    db.add(tag)
    await db.flush()
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="tag.created",
                    entity_type="tag", entity_id=tag.id, metadata={"name": tag.name})
    await db.commit()
    return _tag_row(tag)


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: uuid.UUID,
    auth: AuthContext = Depends(require_permissions(perms.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError("Tag inexistente")
    await db.delete(tag)  # cascada: conversation_tags
    await log_event(db, actor_type="user", actor_id=auth.user.id, action="tag.deleted",
                    entity_type="tag", entity_id=tag_id)
    await db.commit()
    return {"ok": True}
