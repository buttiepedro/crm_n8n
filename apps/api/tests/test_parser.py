import json
from datetime import UTC, datetime
from pathlib import Path

from app.db.models.enums import MessageStatus, MessageType
from app.modules.whatsapp.parser import parse_meta_event

FIXTURES = Path(__file__).parent / "fixtures" / "meta"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_text_message():
    inbound, statuses = parse_meta_event(_load("text_message.json"))
    assert len(inbound) == 1 and not statuses
    msg = inbound[0]
    assert msg.phone_number_id == "106540352242922"
    assert msg.wa_from == "5491122334455"
    assert msg.profile_name == "Juan Pérez"
    assert msg.type == MessageType.text
    assert msg.body == "Hola, quiero info del plan premium"
    assert msg.media is None
    assert msg.wa_timestamp == datetime.fromtimestamp(1719960000, tz=UTC)
    assert msg.raw["id"] == msg.wamid  # el payload crudo se conserva


def test_parse_image_message_with_caption_and_reply():
    inbound, _ = parse_meta_event(_load("image_message.json"))
    msg = inbound[0]
    assert msg.type == MessageType.image
    assert msg.body == "Mirá esta foto del producto"
    assert msg.media is not None
    assert msg.media.media_id == "1013859600742115"
    assert msg.media.mime_type == "image/jpeg"
    assert msg.reply_to_wamid is not None


def test_parse_status_event():
    inbound, statuses = parse_meta_event(_load("status_delivered.json"))
    assert not inbound and len(statuses) == 1
    st = statuses[0]
    assert st.status == MessageStatus.delivered
    assert st.wamid.startswith("wamid.")


def test_unknown_message_type_falls_back():
    event = _load("text_message.json")
    msg = event["entry"][0]["changes"][0]["value"]["messages"][0]
    msg["type"] = "algo_nuevo_de_meta"
    inbound, _ = parse_meta_event(event)
    assert inbound[0].type == MessageType.unknown
    assert inbound[0].raw["type"] == "algo_nuevo_de_meta"  # nada se pierde


def test_empty_or_foreign_event():
    assert parse_meta_event({}) == ([], [])
    assert parse_meta_event({"entry": [{"changes": [{"value": {}}]}]}) == ([], [])
