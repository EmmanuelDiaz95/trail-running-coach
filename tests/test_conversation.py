from __future__ import annotations

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from api.conversation import save_message, load_history, clear_history


# In-memory store for mocking db functions
_store: list[dict] = []


def _mock_save_conversation(question, category, response, week):
    entry = {
        "id": len(_store) + 1,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "category": category,
        "response": response,
        "week": week,
    }
    _store.append(entry)
    return entry


def _mock_get_conversations(limit=50):
    return list(_store[-limit:])


def _mock_clear_conversations():
    _store.clear()


@pytest.fixture(autouse=True)
def mock_db():
    """Mock tracker.db functions used by conversation module."""
    _store.clear()
    with patch("api.conversation.db") as mock:
        mock.save_conversation = MagicMock(side_effect=_mock_save_conversation)
        mock.get_conversations = MagicMock(side_effect=_mock_get_conversations)
        mock.clear_conversations = MagicMock(side_effect=_mock_clear_conversations)
        yield mock


def test_save_and_load():
    save_message("How's my week?", "coaching", "Looks rough.", 5)
    save_message("What should I eat?", "knowledge", "Carbs before long runs.", 5)

    result = load_history(limit=50)
    assert len(result["messages"]) == 2
    assert result["messages"][0]["question"] == "How's my week?"
    assert result["messages"][1]["question"] == "What should I eat?"
    assert result["has_more"] is False


def test_load_respects_limit():
    for i in range(5):
        save_message(f"Q{i}", "general", f"A{i}", 5)

    result = load_history(limit=3)
    assert len(result["messages"]) == 3
    assert result["has_more"] is True


def test_clear_history():
    save_message("test", "general", "response", 5)
    assert len(_store) > 0

    clear_history()

    result = load_history(limit=50)
    assert len(result["messages"]) == 0


def test_load_empty():
    result = load_history(limit=50)
    assert result["messages"] == []
    assert result["has_more"] is False


def test_pagination_with_before():
    save_message("Q1", "general", "A1", 5)
    msgs = load_history(limit=50)["messages"]
    assert len(msgs) == 1

    save_message("Q2", "general", "A2", 5)

    result = load_history(limit=50)
    assert len(result["messages"]) == 2
