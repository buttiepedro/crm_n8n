from datetime import UTC, datetime, timedelta

from app.modules.messages.outbound import is_window_open

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)


def test_open_within_24h():
    assert is_window_open(NOW - timedelta(hours=23, minutes=59), now=NOW)


def test_closed_after_24h():
    assert not is_window_open(NOW - timedelta(hours=24, seconds=1), now=NOW)


def test_closed_exactly_at_24h():
    assert not is_window_open(NOW - timedelta(hours=24), now=NOW)


def test_closed_without_inbound():
    """Sin mensaje entrante del cliente nunca hay ventana abierta."""
    assert not is_window_open(None, now=NOW)
