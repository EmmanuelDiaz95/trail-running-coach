from __future__ import annotations

from unittest.mock import MagicMock, patch

from coach.narrator import Narrator


def _make_narrator():
    """Create a Narrator with a dummy API key and athlete profile."""
    return Narrator(
        api_key="test-key",
        athlete={
            "name": "Test",
            "altitude_m": 2600,
            "race": {"name": "UTT", "distance_km": 59, "vert_m": 2400, "date": "2026-10-02"},
        },
    )


def test_stream_answer_yields_tokens():
    narrator = _make_narrator()

    mock_event_1 = MagicMock()
    mock_event_1.type = "content_block_delta"
    mock_event_1.delta = MagicMock()
    mock_event_1.delta.text = "Hello "

    mock_event_2 = MagicMock()
    mock_event_2.type = "content_block_delta"
    mock_event_2.delta = MagicMock()
    mock_event_2.delta.text = "world"

    mock_event_3 = MagicMock()
    mock_event_3.type = "message_stop"

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.__iter__ = MagicMock(return_value=iter([mock_event_1, mock_event_2, mock_event_3]))

    with patch.object(narrator._client.messages, "stream", return_value=mock_stream):
        tokens = list(narrator.stream_answer("How's my week?", "coaching", {"week": 5}))

    assert tokens == ["Hello ", "world"]


def test_stream_answer_handles_api_error():
    narrator = _make_narrator()

    with patch.object(narrator._client.messages, "stream", side_effect=Exception("API down")):
        tokens = list(narrator.stream_answer("test", "general", {}))

    assert len(tokens) == 1
    assert "unavailable" in tokens[0].lower() or "error" in tokens[0].lower()
