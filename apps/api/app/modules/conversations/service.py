"""Servicio de contactos y conversaciones (compartido por ingesta, hooks y CRM)."""

import uuid

import sqlalchemy as sa
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Attachment, Contact, Conversation
from app.infra.storage import get_storage


async def build_attachment_response(attachment: Attachment | None) -> Response:
    """Sirve el binario del adjunto (compartido por el panel CRM vía JWT y
    por el hook de n8n vía API key)."""
    if attachment is None or not attachment.gcs_path:
        raise NotFoundError("Adjunto no disponible")
    data = await get_storage().load(attachment.gcs_path)
    # Tipos peligrosos jamás inline (XSS via HTML/SVG)
    disposition = "attachment" if attachment.mime_type in {"text/html", "image/svg+xml"} else "inline"
    filename = (attachment.file_name or str(attachment.id)).replace('"', "")
    return Response(
        content=data, media_type=attachment.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


async def get_or_create_contact(
    session: AsyncSession, wa_id: str, profile_name: str | None = None
) -> Contact:
    result = await session.execute(sa.select(Contact).where(Contact.wa_id == wa_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        contact = Contact(wa_id=wa_id, profile_name=profile_name)
        session.add(contact)
        await session.flush()
    elif profile_name and contact.profile_name != profile_name:
        contact.profile_name = profile_name
    return contact


async def get_or_create_conversation(
    session: AsyncSession, whatsapp_account_id: uuid.UUID, contact_id: uuid.UUID
) -> Conversation:
    result = await session.execute(
        sa.select(Conversation).where(
            Conversation.whatsapp_account_id == whatsapp_account_id,
            Conversation.contact_id == contact_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            whatsapp_account_id=whatsapp_account_id, contact_id=contact_id
        )
        session.add(conversation)
        await session.flush()
    return conversation
