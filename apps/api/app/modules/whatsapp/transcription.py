"""Transcripción de audio entrante vía OpenAI (gpt-4o-transcribe).

Best-effort: cualquier fallo (sin key, red, cuota, formato) se loguea y
devuelve None — nunca bloquea la descarga del audio ni la ingesta.
"""

import httpx
import structlog

from app.modules.settings.service import KEY_OPENAI_API_KEY, get_setting_cached

log = structlog.get_logger()

_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "gpt-4o-transcribe"
_TIMEOUT = httpx.Timeout(30.0)


async def transcribe_audio(data: bytes, mime_type: str, file_name: str | None) -> str | None:
    api_key = await get_setting_cached(KEY_OPENAI_API_KEY)
    if not api_key:
        return None

    # TODO: WhatsApp manda el audio como "audio/ogg; codecs=opus". La API de
    # OpenAI dice soportar ogg, pero hay reportes de que rechaza ese opus real
    # con "invalid file format". Si pasa acá (ver log transcription_failed con
    # detalle de formato), convertir a mp3/wav con ffmpeg antes de mandarlo.
    files = {"file": (file_name or "audio.ogg", data, mime_type)}
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _TRANSCRIBE_URL, headers=headers, data={"model": _MODEL}, files=files
            )
    except httpx.HTTPError as exc:
        log.warning("transcription_network_error", error=str(exc))
        return None

    if resp.status_code >= 400:
        log.warning("transcription_failed", status=resp.status_code, detail=resp.text[:500])
        return None

    text = resp.json().get("text")
    log.info("audio_transcribed", chars=len(text) if text else 0)
    return text
