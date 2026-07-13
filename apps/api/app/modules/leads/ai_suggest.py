"""Sugerencia de campos de lead a partir del historial de una conversación,
vía OpenAI (chat/completions, JSON mode).

A diferencia de la transcripción de audio (best-effort y silenciosa, ver
whatsapp/transcription.py), acá el usuario dispara la acción a mano desde el
form de alta de lead y espera una respuesta clara — los fallos se propagan
como DomainError en vez de devolver None.
"""

import json
import uuid

import httpx
import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models import Message, Pipeline, PipelineStage
from app.modules.settings.service import KEY_OPENAI_API_KEY, get_setting_cached

log = structlog.get_logger()

_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o-mini"
_TIMEOUT = httpx.Timeout(30.0)
_MAX_MESSAGES = 40

_SYSTEM_PROMPT = (
    "Analizás una conversación de WhatsApp entre un cliente y un negocio para "
    "ayudar a un agente a cargar un lead. Con la transcripción y la lista de "
    "etapas disponibles, respondé SOLO un JSON con las claves: "
    '"title" (nombre del cliente o de la oportunidad, string o null), '
    '"company" (empresa mencionada, string o null), '
    '"notes" (resumen breve de 1-2 oraciones de lo que quiere el cliente, string o null), '
    '"stageId" (el id de la etapa más adecuada de la lista dada, o null si ninguna aplica). '
    "No inventes datos que no estén en la conversación."
)


async def suggest_lead_fields(db: AsyncSession, conversation_id: uuid.UUID) -> dict:
    api_key = await get_setting_cached(KEY_OPENAI_API_KEY)
    if not api_key:
        raise DomainError(
            "El análisis con IA no está configurado (falta la API key de OpenAI en el panel técnico)",
            code="OPENAI_NOT_CONFIGURED", http_status=409,
        )

    rows = (await db.execute(
        sa.select(Message.direction, Message.body)
        .where(Message.conversation_id == conversation_id, Message.body.is_not(None))
        .order_by(Message.created_at.desc()).limit(_MAX_MESSAGES)
    )).all()
    if not rows:
        raise DomainError("La conversación no tiene mensajes de texto para analizar",
                          code="NO_MESSAGES", http_status=409)
    transcript = "\n".join(
        f"{'Cliente' if direction.value == 'inbound' else 'Agente'}: {body}"
        for direction, body in reversed(rows)
    )

    pipeline = (await db.execute(
        sa.select(Pipeline).where(Pipeline.is_default.is_(True))
    )).scalar_one_or_none()
    stages: list[PipelineStage] = []
    if pipeline is not None:
        stages = list((await db.execute(
            sa.select(PipelineStage).where(PipelineStage.pipeline_id == pipeline.id)
            .order_by(PipelineStage.position)
        )).scalars().all())
    stage_list = "\n".join(f"- {s.id}: {s.name}" for s in stages) or "(sin etapas configuradas)"

    user_prompt = f"Conversación:\n{transcript}\n\nEtapas disponibles:\n{stage_list}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": _MODEL,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
    except httpx.HTTPError as exc:
        log.warning("lead_analysis_network_error", error=str(exc))
        raise DomainError("No se pudo contactar a OpenAI", code="OPENAI_REQUEST_FAILED",
                          http_status=502) from exc

    if resp.status_code >= 400:
        log.warning("lead_analysis_failed", status=resp.status_code, detail=resp.text[:500])
        raise DomainError("OpenAI rechazó la solicitud de análisis",
                          code="OPENAI_REQUEST_FAILED", http_status=502)

    try:
        raw = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("lead_analysis_bad_response", body=resp.text[:500])
        raise DomainError("La respuesta de la IA no se pudo interpretar",
                          code="OPENAI_BAD_RESPONSE", http_status=502) from exc

    valid_stage_ids = {str(s.id) for s in stages}
    stage_id = parsed.get("stageId")
    if stage_id not in valid_stage_ids:
        stage_id = None

    log.info("lead_analyzed", conversation_id=str(conversation_id))
    return {
        "title": parsed.get("title") or None,
        "company": parsed.get("company") or None,
        "notes": parsed.get("notes") or None,
        "stageId": stage_id,
    }
