from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app


# In-memory store for mocking db conversation functions
_conv_store: list[dict] = []


def _mock_save_conversation(question, category, response, week):
    entry = {
        "id": len(_conv_store) + 1,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "category": category,
        "response": response,
        "week": week,
    }
    _conv_store.append(entry)
    return entry


def _mock_get_conversations(limit=50):
    return list(_conv_store[-limit:])


def _mock_clear_conversations():
    _conv_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_conv_db():
    """Mock tracker.db conversation functions used by api.conversation."""
    _conv_store.clear()
    with patch("api.conversation.db") as mock:
        mock.save_conversation = MagicMock(side_effect=_mock_save_conversation)
        mock.get_conversations = MagicMock(side_effect=_mock_get_conversations)
        mock.clear_conversations = MagicMock(side_effect=_mock_clear_conversations)
        yield mock


def test_coach_status(client):
    mock_output = MagicMock()
    mock_output.compliance_score = 44
    mock_output.readiness = MagicMock()
    mock_output.readiness.score = 6
    mock_output.readiness.acwr = 0.60
    mock_output.readiness.acwr_zone = "detraining"
    mock_output.readiness.recommendation = "push"

    with patch("api.routes_coach.get_current_week", return_value=5), \
         patch("api.routes_coach.get_week") as mock_plan, \
         patch("api.routes_coach.get_week_dates", return_value=("2026-03-30", "2026-04-05")), \
         patch("api.routes_coach.load_cached_activities", return_value=[MagicMock()]), \
         patch("api.routes_coach.build_week_actual"), \
         patch("api.routes_coach.load_week_range", return_value=[]), \
         patch("api.routes_coach.run_coaching", return_value=mock_output), \
         patch("api.routes_coach.days_to_race", return_value=181):
        mock_plan.return_value = MagicMock(phase="base")
        resp = client.get("/api/coach/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["week"] == 5
    assert data["compliance"] == 44
    assert data["readiness"]["score"] == 6


def test_coach_history_empty(client, mock_conv_db):
    resp = client.get("/api/coach/history")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_coach_clear_history(client, mock_conv_db):
    from api.conversation import save_message
    save_message("test", "general", "response", 5)

    resp = client.delete("/api/coach/history")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.get("/api/coach/history")
    assert resp.json()["messages"] == []


def test_coach_chat_returns_sse(client, mock_conv_db):
    def fake_stream(*args, **kwargs):
        yield "Hello "
        yield "coach!"

    mock_narrator = MagicMock()
    mock_narrator.stream_answer = MagicMock(side_effect=fake_stream)

    with patch("api.routes_coach._get_narrator", return_value=mock_narrator), \
         patch("api.routes_coach.get_current_week", return_value=5), \
         patch("api.routes_coach._build_coaching_data", return_value={"week": 5}), \
         patch("api.routes_coach.classify_question", return_value="coaching"):
        resp = client.post(
            "/api/coach/chat",
            json={"question": "How's my week?"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert '"token"' in body


def test_coach_chat_no_api_key(client):
    with patch("api.routes_coach._get_narrator", return_value=None):
        resp = client.post("/api/coach/chat", json={"question": "test"})
    assert resp.status_code == 503
