from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
import pytest

from coach.narrator import Narrator, build_system_prompt


@pytest.fixture
def sample_coaching_dict():
    """A realistic coaching output dict (mirrors week_01_coaching.json structure)."""
    return {
        "week_number": 1,
        "generated_at": "2026-03-19T08:06:31",
        "phase": "base",
        "is_recovery_week": False,
        "days_to_race": 197,
        "compliance_score": 99,
        "compliance_breakdown": {
            "distance_km": {"planned": 27, "actual": 26.3, "pct": 97},
            "vert_m": {"planned": 400, "actual": 715, "pct": 179},
            "long_run_km": {"planned": 14, "actual": 14.0, "pct": 100},
            "gym_sessions": {"planned": 3, "actual": 2, "pct": 67},
            "series": {"planned": None, "actual": None, "pct": None},
        },
        "readiness": {
            "score": 8,
            "acwr": 1.0,
            "acwr_zone": "optimal",
            "recommendation": "maintain",
            "signals": ["Limited data: only 1 week(s) recorded"],
        },
        "trends": [],
        "adjustments": [],
        "alerts": [
            {"level": "INFO", "category": "long_run_ratio", "message": "Long run ratio: 53%"}
        ],
    }


@pytest.fixture
def sample_athlete():
    return {
        "name": "Emmanuel Diaz",
        "weight_kg": 70,
        "altitude_m": 2600,
        "race": {
            "name": "Ultra Trail Tarahumara",
            "date": "2026-10-02",
            "distance_km": 59,
            "vert_m": 2400,
        },
    }


class TestBuildSystemPrompt:
    def test_contains_persona_elements(self, sample_athlete):
        prompt = build_system_prompt(sample_athlete)
        assert "trail" in prompt.lower()
        assert "coach" in prompt.lower()
        assert "Ultra Trail Tarahumara" in prompt
        assert "never contradict" in prompt.lower() or "NEVER contradict" in prompt

    def test_contains_athlete_context(self, sample_athlete):
        prompt = build_system_prompt(sample_athlete)
        assert "Emmanuel" in prompt
        assert "59" in prompt  # race distance
        assert "2600" in prompt or "2,600" in prompt  # altitude

    def test_contains_narrator_constraints(self, sample_athlete):
        prompt = build_system_prompt(sample_athlete)
        assert "medical" in prompt.lower()
        # Should warn against inventing data
        assert "invent" in prompt.lower() or "fabricate" in prompt.lower()


class TestNarrator:
    @patch("coach.narrator.anthropic")
    def test_narrate_report_calls_api(self, mock_anthropic, sample_coaching_dict, sample_athlete):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great first week, Emmanuel!")]
        mock_client.messages.create.return_value = mock_response

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        result = narrator.narrate_report(sample_coaching_dict)

        assert result == "Great first week, Emmanuel!"
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250514"
        assert any("coach" in m.get("content", "").lower() for m in [{"content": call_kwargs["system"]}])

    @patch("coach.narrator.anthropic")
    def test_narrate_report_includes_coaching_json_in_user_message(
        self, mock_anthropic, sample_coaching_dict, sample_athlete
    ):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Narrative here")]
        mock_client.messages.create.return_value = mock_response

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        narrator.narrate_report(sample_coaching_dict)

        call_kwargs = mock_client.messages.create.call_args[1]
        user_msgs = [m for m in call_kwargs["messages"] if m["role"] == "user"]
        user_text = user_msgs[0]["content"]
        # Coaching JSON should be embedded in the user message
        assert "compliance_score" in user_text
        assert "99" in user_text

    @patch("coach.narrator.anthropic")
    def test_answer_question_includes_question_and_category(
        self, mock_anthropic, sample_coaching_dict, sample_athlete
    ):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="You ran 26.3km")]
        mock_client.messages.create.return_value = mock_response

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        result = narrator.answer_question(
            question="How far did I run?",
            category="data",
            coaching_data=sample_coaching_dict,
        )

        assert result == "You ran 26.3km"
        call_kwargs = mock_client.messages.create.call_args[1]
        user_msgs = [m for m in call_kwargs["messages"] if m["role"] == "user"]
        user_text = user_msgs[0]["content"]
        assert "How far did I run?" in user_text
        assert "data" in user_text

    @patch("coach.narrator.anthropic")
    def test_api_failure_returns_fallback(self, mock_anthropic, sample_coaching_dict, sample_athlete):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        result = narrator.narrate_report(sample_coaching_dict)

        # Should return fallback, not raise
        assert "error" in result.lower() or "unavailable" in result.lower()

    @patch("coach.narrator.anthropic")
    def test_answer_question_api_failure(self, mock_anthropic, sample_coaching_dict, sample_athlete):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        result = narrator.answer_question(
            question="Am I on track?",
            category="coaching",
            coaching_data=sample_coaching_dict,
        )

        # Should return fallback, not raise
        assert "error" in result.lower() or "unavailable" in result.lower()

    @patch("coach.narrator.anthropic")
    def test_answer_question_coaching_category_has_distinct_guidance(
        self, mock_anthropic, sample_coaching_dict, sample_athlete
    ):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="You're ready to push next week.")]
        mock_client.messages.create.return_value = mock_response

        narrator = Narrator(api_key="test-key", athlete=sample_athlete)
        narrator.answer_question(
            question="Should I increase my volume?",
            category="coaching",
            coaching_data=sample_coaching_dict,
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        user_msgs = [m for m in call_kwargs["messages"] if m["role"] == "user"]
        user_text = user_msgs[0]["content"]
        # "readiness" appears in the coaching category guidance string specifically
        assert "readiness" in user_text
