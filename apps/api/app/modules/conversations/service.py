"""Servicio de contactos y conversaciones (compartido por ingesta, hooks y CRM)."""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Contact, Conversation


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
