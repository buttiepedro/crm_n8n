"""Los dos webhooks entrantes para n8n.

1. POST /hooks/n8n/messages — respuestas de n8n que se envían a WhatsApp.
2. POST /hooks/n8n/leads — upsert de leads + notas internas desde n8n.

Contratos completos en roadmap/next_steps_webhooks_n8n.md y en /api/docs.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey
from app.db.models.enums import MessageOrigin
from app.db.session import get_db
from app.modules.hooks.auth import SCOPE_HOOKS_LEADS, SCOPE_HOOKS_MESSAGES, require_api_key
from app.modules.leads.service import upsert_lead_from_webhook
from app.modules.messages.outbound import queue_outbound_message
from app.schemas.hooks import N8nLeadIn, N8nLeadOut, N8nMessageIn, N8nMessageOut

router = APIRouter(prefix="/hooks/n8n", tags=["hooks-n8n"])


@router.post("/messages", status_code=202, response_model=N8nMessageOut)
async def n8n_send_message(
    body: N8nMessageIn,
    session: AsyncSession = Depends(get_db),
    api_key: ApiKey = require_api_key(SCOPE_HOOKS_MESSAGES),
) -> N8nMessageOut:
    message = await queue_outbound_message(
        session,
        conversation_id=body.conversation_id,
        account_id=body.account_id,
        to_wa_id=body.to,
        content=body.message,
        origin=MessageOrigin.n8n,
    )
    return N8nMessageOut(message_id=message.id, status=message.status.value)


@router.post("/leads", response_model=N8nLeadOut)
async def n8n_upsert_lead(
    body: N8nLeadIn,
    response: Response,
    session: AsyncSession = Depends(get_db),
    api_key: ApiKey = require_api_key(SCOPE_HOOKS_LEADS),
) -> N8nLeadOut:
    result = await upsert_lead_from_webhook(session, body, api_key_id=api_key.id)
    response.status_code = 201 if result.created else 200
    return result
