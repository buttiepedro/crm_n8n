"""Parser de payloads del webhook de Meta → estructuras internas.

Funciones puras (testeables con fixtures). El payload de Meta es evolutivo:
campos desconocidos se conservan en raw; tipos no reconocidos caen a
MessageType.unknown — el parser nunca explota por campos extra.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db.models.enums import MessageStatus, MessageType

# Tipos de mensaje de Meta que traen media descargable
MEDIA_TYPES = {"image", "audio", "video", "document", "sticker"}


@dataclass
class ParsedMedia:
    media_id: str
    mime_type: str
    file_name: str | None = None
    sha256: str | None = None


@dataclass
class ParsedInboundMessage:
    phone_number_id: str
    wamid: str
    wa_from: str  # wa_id del cliente
    profile_name: str | None
    type: MessageType
    body: str | None
    media: ParsedMedia | None
    reply_to_wamid: str | None
    wa_timestamp: datetime
    raw: dict = field(repr=False, default_factory=dict)


@dataclass
class ParsedStatusEvent:
    phone_number_id: str
    wamid: str
    status: MessageStatus
    occurred_at: datetime
    errors: list[dict] = field(default_factory=list)
    raw: dict = field(repr=False, default_factory=dict)


def _ts(value: str | int | None) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _extract_body(msg: dict, msg_type: str) -> str | None:
    match msg_type:
        case "text":
            return (msg.get("text") or {}).get("body")
        case "image" | "video" | "document" | "audio" | "sticker":
            return (msg.get(msg_type) or {}).get("caption")
        case "location":
            loc = msg.get("location") or {}
            parts = [str(loc.get("latitude", "")), str(loc.get("longitude", ""))]
            name = loc.get("name") or loc.get("address")
            return (f"{name} — " if name else "") + ",".join(parts)
        case "reaction":
            return (msg.get("reaction") or {}).get("emoji")
        case "interactive":
            interactive = msg.get("interactive") or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            return reply.get("title")
        case "button":
            return (msg.get("button") or {}).get("text")
    return None


def _extract_media(msg: dict, msg_type: str) -> ParsedMedia | None:
    if msg_type not in MEDIA_TYPES:
        return None
    media = msg.get(msg_type) or {}
    if not media.get("id"):
        return None
    return ParsedMedia(
        media_id=media["id"],
        mime_type=media.get("mime_type", "application/octet-stream"),
        file_name=media.get("filename"),
        sha256=media.get("sha256"),
    )


def parse_meta_event(
    event: dict,
) -> tuple[list[ParsedInboundMessage], list[ParsedStatusEvent]]:
    inbound: list[ParsedInboundMessage] = []
    statuses: list[ParsedStatusEvent] = []

    for entry in event.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            if not phone_number_id:
                continue

            profiles = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", [])
            }

            for msg in value.get("messages", []):
                raw_type = msg.get("type", "unknown")
                try:
                    msg_type = MessageType(raw_type)
                except ValueError:
                    msg_type = MessageType.unknown
                wa_from = msg.get("from", "")
                inbound.append(
                    ParsedInboundMessage(
                        phone_number_id=phone_number_id,
                        wamid=msg.get("id", ""),
                        wa_from=wa_from,
                        profile_name=profiles.get(wa_from),
                        type=msg_type,
                        body=_extract_body(msg, raw_type),
                        media=_extract_media(msg, raw_type),
                        reply_to_wamid=(msg.get("context") or {}).get("id"),
                        wa_timestamp=_ts(msg.get("timestamp")),
                        raw=msg,
                    )
                )

            for st in value.get("statuses", []):
                try:
                    status = MessageStatus(st.get("status", ""))
                except ValueError:
                    continue  # estado desconocido: se ignora (queda en logs de Meta)
                statuses.append(
                    ParsedStatusEvent(
                        phone_number_id=phone_number_id,
                        wamid=st.get("id", ""),
                        status=status,
                        occurred_at=_ts(st.get("timestamp")),
                        errors=st.get("errors", []),
                        raw=st,
                    )
                )

    return inbound, statuses
