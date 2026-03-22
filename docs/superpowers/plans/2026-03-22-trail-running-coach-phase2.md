# Trail Running Coach — Phase 2 (LLM Narrator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM narrator layer that translates the rule engine's structured `CoachingOutput` JSON into natural, coach-like language — plus a keyword-based question classifier and conversational CLI mode.

**Architecture:** The classifier routes user questions by type (data/coaching/knowledge/off-topic) using keyword pattern matching (no API calls). The narrator wraps the Claude API with a rich system prompt embodying the coach persona — it receives only pre-digested `CoachingOutput` JSON, never raw activity data. The CLI gains a conversational mode: `python coach.py "how's my week?"`.

**Tech Stack:** Python 3.9, `anthropic` SDK (0.86.0, already in venv), Claude claude-sonnet-4-5-20250514 for narration.

**Spec:** `docs/superpowers/specs/2026-03-18-trail-running-coach-agent-design.md`

**Spec deviation:** This plan moves `classifier.py` from Phase 4 to Phase 2 because the conversational CLI mode depends on question routing to work properly. The classifier is pure Python with zero external dependencies.

**Existing code context:**
- `coach/models.py` — `CoachingOutput` dataclass with `to_dict()` method (the narrator contract)
- `coach/engine.py` — `run_coaching(plan, current, history, prev_plan)` returns `CoachingOutput`
- `coach.py` — CLI entry point with `status` and `report` subcommands
- `athlete.json` — athlete profile (name, weight, HR zones, race info)
- `knowledge.json` — coaching thresholds (ACWR zones, nutrition targets, etc.)
- `data/coaching/week_01_coaching.json` — real example of coaching JSON output
- `tests/conftest.py` — shared fixtures (`make_activity`, `make_week_plan`, `make_week_actual`)
- All commands run from `personal_health/running/` with venv activated

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `coach/classifier.py` | Keyword-based question routing — classifies user input into `data`, `coaching`, `knowledge`, or `general` |
| Create | `coach/narrator.py` | Claude API wrapper — takes `CoachingOutput` dict + optional user question → natural language coaching response |
| Create | `tests/test_classifier.py` | Tests for classifier |
| Create | `tests/test_narrator.py` | Tests for narrator (mocked API calls) |
| Modify | `coach.py` | Add conversational mode, `--regenerate` flag for reports, narrative output |
| Modify | `requirements.txt` | Add `anthropic>=0.80.0` |

---

## Task 1: Question Classifier

**Files:**
- Create: `tests/test_classifier.py`
- Create: `coach/classifier.py`

The classifier is pure Python pattern matching. It routes user questions to determine which coaching modules to emphasize in the narrator context. Four categories per spec:

| Type | Example | Behavior |
|------|---------|----------|
| `data` | "What was my vert last week?" | Rule engine data → minimal LLM wrapping |
| `coaching` | "Should I push harder?" | Readiness + trends + adjustments → LLM narrates |
| `knowledge` | "What to eat at aid stations?" | Knowledge.json context → LLM narrates |
| `general` | Anything unmatched | LLM responds with full coaching context |

- [ ] **Step 1: Write classifier tests**

```python
# tests/test_classifier.py
from __future__ import annotations

from coach.classifier import classify_question


class TestClassifyQuestion:
    """Tests for keyword-based question classification."""

    # Data questions — ask about specific metrics or past weeks
    def test_data_question_vert(self):
        assert classify_question("What was my vert last week?") == "data"

    def test_data_question_distance(self):
        assert classify_question("How far did I run this week?") == "data"

    def test_data_question_compliance(self):
        assert classify_question("What's my compliance score?") == "data"

    def test_data_question_hr(self):
        assert classify_question("What was my average heart rate?") == "data"

    def test_data_question_long_run(self):
        assert classify_question("How long was my long run?") == "data"

    def test_data_question_gym(self):
        assert classify_question("How many gym sessions did I do?") == "data"

    # Coaching questions — ask for advice or recommendations
    def test_coaching_question_push(self):
        assert classify_question("Should I push harder this week?") == "coaching"

    def test_coaching_question_ready(self):
        assert classify_question("Am I ready for more volume?") == "coaching"

    def test_coaching_question_skip(self):
        assert classify_question("Can I skip my rest day?") == "coaching"

    def test_coaching_question_adjust(self):
        assert classify_question("Should I adjust my plan?") == "coaching"

    def test_coaching_question_how_am_i(self):
        assert classify_question("How am I doing?") == "coaching"

    def test_coaching_question_hows_my_week(self):
        assert classify_question("How's my week looking?") == "coaching"

    # Knowledge questions — nutrition, injury, recovery, strength
    def test_knowledge_question_nutrition(self):
        assert classify_question("What should I eat before a long run?") == "knowledge"

    def test_knowledge_question_injury(self):
        assert classify_question("My knee hurts after downhills") == "knowledge"

    def test_knowledge_question_recovery(self):
        assert classify_question("How should I recover after a hard week?") == "knowledge"

    def test_knowledge_question_strength(self):
        assert classify_question("What strength exercises should I do?") == "knowledge"

    def test_knowledge_question_hydration(self):
        assert classify_question("How much water should I drink at altitude?") == "knowledge"

    # General — unmatched falls through
    def test_general_question(self):
        assert classify_question("Tell me about the Tarahumara") == "general"

    def test_general_greeting(self):
        assert classify_question("Hello coach") == "general"

    # Case insensitivity
    def test_case_insensitive(self):
        assert classify_question("WHAT WAS MY VERT?") == "data"

    # Empty / whitespace
    def test_empty_string(self):
        assert classify_question("") == "general"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -m pytest tests/test_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coach.classifier'`

- [ ] **Step 3: Implement classifier**

```python
# coach/classifier.py
from __future__ import annotations

import re

# Patterns are checked in order; first match wins.
# Each pattern list maps to a question type.

_DATA_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(what|how)\b.*(distance|vert|elevation|km|miles|heart rate|hr|pace|compliance|score|long run|gym session)",
        r"\b(how (far|long|much|many))\b",
        r"\blast (week|month)\b",
        r"\bthis week\b.*\b(number|total|average|avg)\b",
        r"\bstats\b",
    ]
]

_COACHING_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bshould I\b",
        r"\bcan I\b.*\b(skip|push|increase|add|run)\b",
        r"\bam I\b.*\b(ready|on track|doing|overtraining|behind)\b",
        r"\b(adjust|change|modify)\b.*\b(plan|schedule|training)\b",
        r"\bhow('?s| is| am)\b.*\b(my|I|me)\b.*(week|training|doing|progress|look)",
        r"\b(push|back off|maintain|rest|recover)\b.*\?",
        r"\b(ready|readiness|fatigue|tired|fresh)\b",
    ]
]

_KNOWLEDGE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(eat|food|fuel|nutrition|carb|protein|calorie|diet|supplement)\b",
        r"\b(drink|hydrat|water|electrolyte)\b",
        r"\b(injur|pain|hurt|sore|ache|knee|ankle|shin|plantar|achilles|IT band)\b",
        r"\b(recover|recovery|ice|foam roll|massage|sleep)\b",
        r"\b(strength|gym|exercise|stretch|mobility|warm.?up|cool.?down)\b",
        r"\b(altitude|elevation.*(effect|impact|adjust))\b",
    ]
]


def classify_question(question: str) -> str:
    """Classify a user question into a routing category.

    Returns one of: 'data', 'coaching', 'knowledge', 'general'.
    Uses keyword pattern matching — no API calls.
    Unmatched questions return 'general' (narrator handles with full context).
    """
    if not question or not question.strip():
        return "general"

    # Check patterns in priority order
    for pattern in _COACHING_PATTERNS:
        if pattern.search(question):
            return "coaching"

    for pattern in _DATA_PATTERNS:
        if pattern.search(question):
            return "data"

    for pattern in _KNOWLEDGE_PATTERNS:
        if pattern.search(question):
            return "knowledge"

    return "general"
```

**Design note:** Coaching patterns are checked first because questions like "Should I push harder this week?" contain metric words ("week") that would false-match data patterns. The spec says unmatched queries fall through to the LLM with full context, which is the `general` path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python -m pytest tests/test_classifier.py -v`
Expected: All pass. If any fail, adjust patterns (not test expectations).

- [ ] **Step 5: Commit**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
git add tests/test_classifier.py coach/classifier.py
git commit -m "feat(coach): add keyword-based question classifier with tests"
```

---

## Task 2: Narrator — Claude API Wrapper

**Files:**
- Create: `tests/test_narrator.py`
- Create: `coach/narrator.py`

The narrator is the **only** component that calls the Claude API. It receives a `CoachingOutput` dict (from `to_dict()`) and optionally a user question with its classification. It returns natural language coaching text.

Key constraints from spec:
- NEVER contradicts rule engine output
- NEVER invents data not in the coaching JSON
- NEVER gives medical advice
- CAN add motivational context, connect dots between weeks
- CAN ask follow-up questions

- [ ] **Step 1: Write narrator tests (mocked API)**

```python
# tests/test_narrator.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python -m pytest tests/test_narrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coach.narrator'`

- [ ] **Step 3: Implement narrator**

```python
# coach/narrator.py
from __future__ import annotations

import json
import anthropic


def build_system_prompt(athlete: dict) -> str:
    """Build the narrator system prompt with coach persona and athlete context.

    The system prompt defines WHO the coach is and HOW it communicates.
    The coaching JSON (injected per-request in the user message) provides
    WHAT to talk about.
    """
    race = athlete.get("race", {})
    name = athlete.get("name", "athlete")
    altitude = athlete.get("altitude_m", 0)

    return f"""You are an experienced trail and ultramarathon running coach. You specialize in mountain ultras and are deeply familiar with the Copper Canyons (Barrancas del Cobre) and Tarahumara running culture.

## Your Athlete
- Name: {name}
- Training altitude: {altitude}m
- Target race: {race.get('name', 'Unknown')} — {race.get('distance_km', '?')}km / {race.get('vert_m', '?')}m D+
- Race date: {race.get('date', 'TBD')}

## Your Coaching Style
- Direct and honest — you don't sugarcoat bad weeks, but you frame everything constructively
- Data-informed but not data-obsessed — lead with insight, back with numbers
- You know when to push and when to hold back
- You use trail running language naturally (vert, bonk, negative split, power hike, send it)
- You're aware {name} trains at {altitude}m altitude — factor this into advice
- Keep responses conversational and concise (2-4 short paragraphs for reports, 1-2 for questions)

## HARD CONSTRAINTS — you MUST follow these:
- NEVER contradict the coaching data provided. The numbers are ground truth.
- NEVER invent or fabricate metrics, distances, times, or data not present in the coaching JSON.
- NEVER give medical advice. If an injury or health concern arises, say "see a physio" or "check with your doctor."
- You CAN add motivational context, race perspective, and connect dots between weeks.
- You CAN ask follow-up questions to clarify ambiguous input.
- If you don't have enough data to answer, say so honestly.

## Response Format
- Use plain text, not markdown (this will be displayed in a terminal)
- No headers, bullet points, or formatting — write like you're texting your athlete
- Use line breaks between paragraphs for readability"""


class Narrator:
    """Claude API wrapper for translating coaching data into natural language.

    This is the ONLY component that calls the Claude API.
    It receives pre-digested CoachingOutput JSON — never raw activity data.
    """

    def __init__(self, api_key: str, athlete: dict, model: str = "claude-sonnet-4-5-20250514"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._system_prompt = build_system_prompt(athlete)
        self._model = model

    def narrate_report(self, coaching_data: dict) -> str:
        """Generate a coaching narrative for a weekly report.

        Args:
            coaching_data: The output of CoachingOutput.to_dict()

        Returns:
            Natural language coaching narrative, or a fallback message on API failure.
        """
        user_message = (
            "Here is this week's coaching data. Write a coaching narrative "
            "covering: how the week went (compliance), current readiness, "
            "any trends worth noting, and what to focus on next. "
            "Keep it conversational and concise.\n\n"
            f"COACHING DATA:\n{json.dumps(coaching_data, indent=2, default=str)}"
        )
        return self._call_api(user_message)

    def answer_question(
        self,
        question: str,
        category: str,
        coaching_data: dict,
    ) -> str:
        """Answer a user question using coaching data as context.

        Args:
            question: The user's natural language question.
            category: Question type from classifier ('data', 'coaching',
                      'knowledge', 'general').
            coaching_data: The output of CoachingOutput.to_dict()

        Returns:
            Natural language answer, or a fallback message on API failure.
        """
        category_guidance = {
            "data": "The athlete is asking a data question. Answer concisely with the specific numbers from the coaching data. Don't editorialize unless the numbers warrant a brief note.",
            "coaching": "The athlete is asking for coaching advice. Use the readiness, trends, and adjustment data to give a thoughtful recommendation. Be direct.",
            "knowledge": "The athlete is asking a knowledge question about training, nutrition, recovery, or injury. Draw on your coaching expertise to answer. Remember your hard constraints — no medical advice.",
            "general": "The athlete is asking a general question. Answer naturally, staying in your role as their trail running coach.",
        }

        guidance = category_guidance.get(category, category_guidance["general"])

        user_message = (
            f"QUESTION TYPE: {category}\n"
            f"GUIDANCE: {guidance}\n\n"
            f"ATHLETE'S QUESTION: {question}\n\n"
            f"CURRENT COACHING DATA:\n{json.dumps(coaching_data, indent=2, default=str)}"
        )
        return self._call_api(user_message)

    def _call_api(self, user_message: str) -> str:
        """Make a single Claude API call with error handling.

        Returns the response text, or a fallback message on failure.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as e:
            return (
                f"Coach narrative unavailable (API error: {e}). "
                "The structured coaching data was saved successfully — "
                "you can regenerate the narrative later with: "
                "python coach.py report --week N --regenerate"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python -m pytest tests/test_narrator.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
git add tests/test_narrator.py coach/narrator.py
git commit -m "feat(coach): add LLM narrator with Claude API wrapper and tests"
```

---

## Task 3: Update CLI with Conversational Mode

**Files:**
- Modify: `coach.py` — add conversational subcommand and `--regenerate` flag
- Modify: `requirements.txt` — add anthropic

This task wires the classifier and narrator into the existing CLI. Three additions:
1. `python coach.py "how's my week?"` — conversational mode (positional arg)
2. `python coach.py report --week N` — now outputs narrative instead of raw JSON (with `--json` flag for raw)
3. `python coach.py report --week N --regenerate` — re-generates narrative from saved JSON

- [ ] **Step 1: Update requirements.txt**

Add `anthropic>=0.80.0` to `requirements.txt`:

```
garminconnect==0.2.8
tabulate==0.9.0
pytest>=7.0.0
anthropic>=0.80.0
```

- [ ] **Step 2: Update coach.py — add imports and helper**

Add these imports at the top of `coach.py` (after existing imports):

```python
import os
from coach.classifier import classify_question
from coach.narrator import Narrator
```

Add a helper function to create the narrator (loads API key from env, loads athlete.json):

```python
def _get_narrator() -> Narrator | None:
    """Create a Narrator if ANTHROPIC_API_KEY is set. Returns None otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    athlete_path = Path(__file__).resolve().parent / "athlete.json"
    with open(athlete_path) as f:
        athlete = json.load(f)
    return Narrator(api_key=api_key, athlete=athlete)
```

- [ ] **Step 3: Update cmd_report — add narrative output and --regenerate**

Delete the existing `cmd_report` function entirely and replace with the version below. Key changes:
- After saving coaching JSON, call narrator to generate and save narrative
- Add `--regenerate` support: load existing JSON, re-narrate
- Add `--json` flag to output raw JSON instead of narrative
- Fallback: if no API key, output raw JSON with a message

```python
def cmd_report(week_num: int | None = None, regenerate: bool = False, raw_json: bool = False):
    """Generate coaching report with narrative."""
    if week_num is None:
        week_num = get_current_week()
    if week_num is None:
        print("Training plan has not started or has ended.")
        return

    coaching_dir = Path(__file__).resolve().parent / "data" / "coaching"
    coaching_dir.mkdir(parents=True, exist_ok=True)
    coaching_file = coaching_dir / f"week_{week_num:02d}_coaching.json"
    narrative_file = coaching_dir / f"week_{week_num:02d}_narrative.md"

    if regenerate:
        # Load existing coaching JSON and re-narrate
        if not coaching_file.exists():
            print(f"No coaching data for week {week_num}. Run: python coach.py report --week {week_num}")
            return
        with open(coaching_file) as f:
            coaching_data = json.load(f)
    else:
        # Generate fresh coaching data
        plan = get_week(week_num)
        if plan is None:
            print(f"Week {week_num} not found in plan.")
            return

        start, end = get_week_dates(week_num)
        activities = load_cached_activities(start, end)
        if activities is None:
            print(f"No synced data for week {week_num}. Run: python scripts/sync.py --week {week_num}")
            return

        current = build_week_actual(activities, week_num)
        lookback_start = max(1, week_num - 3)
        history = load_week_range(lookback_start, week_num)
        prev_plan = get_week(week_num - 1) if week_num > 1 else None

        output = run_coaching(plan, current, history, prev_plan=prev_plan)
        coaching_data = output.to_dict()

        with open(coaching_file, "w") as f:
            json.dump(coaching_data, f, indent=2, default=str)

    # Raw JSON mode
    if raw_json:
        print(json.dumps(coaching_data, indent=2, default=str))
        print(f"\nSaved to {coaching_file}")
        return

    # Try to narrate
    narrator = _get_narrator()
    if narrator is None:
        print(json.dumps(coaching_data, indent=2, default=str))
        print(f"\nSaved to {coaching_file}")
        print("\nSet ANTHROPIC_API_KEY to get a coaching narrative.")
        return

    print(f"\nGenerating coaching narrative for week {week_num}...\n")
    narrative = narrator.narrate_report(coaching_data)
    print(narrative)

    # Save narrative
    with open(narrative_file, "w") as f:
        f.write(narrative)
    print(f"\n---\nSaved to {narrative_file}")
```

- [ ] **Step 4: Add conversational command**

Add a new function for conversational mode:

```python
def cmd_ask(question: str):
    """Answer a free-form coaching question."""
    narrator = _get_narrator()
    if narrator is None:
        print("ANTHROPIC_API_KEY not set. Set it in .env or environment to use conversational mode.")
        return

    # Get current week's coaching data for context
    week_num = get_current_week()
    coaching_data = None

    if week_num is not None:
        coaching_file = Path(__file__).resolve().parent / "data" / "coaching" / f"week_{week_num:02d}_coaching.json"
        if coaching_file.exists():
            with open(coaching_file) as f:
                coaching_data = json.load(f)
        else:
            # Try to generate coaching data on the fly
            plan = get_week(week_num)
            if plan is not None:
                start, end = get_week_dates(week_num)
                activities = load_cached_activities(start, end)
                if activities is not None:
                    current = build_week_actual(activities, week_num)
                    lookback_start = max(1, week_num - 3)
                    history = load_week_range(lookback_start, week_num)
                    output = run_coaching(plan, current, history)
                    coaching_data = output.to_dict()

    if coaching_data is None:
        coaching_data = {"note": "No training data available yet. Answer based on general coaching knowledge."}

    category = classify_question(question)
    response = narrator.answer_question(question, category, coaching_data)
    print(f"\n{response}\n")
```

- [ ] **Step 5: Update argparse to wire everything together**

Replace the `main()` function.

**Important:** The bare question shorthand (`python coach.py "how's my week?"`) must be handled BEFORE argparse, because argparse with subparsers will `sys.exit(2)` on unrecognized subcommands before the fallthrough logic can run.

```python
_SUBCOMMANDS = {"status", "report", "ask", "-h", "--help"}


def main():
    # Handle bare question BEFORE argparse — argparse with subparsers
    # would exit(2) on unrecognized first args like "how's my week?"
    if len(sys.argv) > 1 and sys.argv[1] not in _SUBCOMMANDS:
        cmd_ask(" ".join(sys.argv[1:]))
        return

    parser = argparse.ArgumentParser(description="Trail Running Coach")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Quick readiness snapshot")

    report_parser = subparsers.add_parser("report", help="Weekly coaching narrative")
    report_parser.add_argument("--week", type=int, default=None, help="Week number (1-30)")
    report_parser.add_argument("--regenerate", action="store_true", help="Re-generate narrative from saved data")
    report_parser.add_argument("--json", action="store_true", dest="raw_json", help="Output raw JSON instead of narrative")

    ask_parser = subparsers.add_parser("ask", help="Ask a coaching question")
    ask_parser.add_argument("question", nargs="+", help="Your question")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "report":
        cmd_report(args.week, regenerate=args.regenerate, raw_json=args.raw_json)
    elif args.command == "ask":
        cmd_ask(" ".join(args.question))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run all tests to verify nothing is broken**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python -m pytest tests/ -v`
Expected: All tests pass (existing Phase 1 tests + new classifier + narrator tests).

- [ ] **Step 7: Commit**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
git add coach.py requirements.txt
git commit -m "feat(coach): add conversational CLI mode with LLM narrator integration"
```

---

## Task 4: Manual Smoke Test

**Files:** None (verification only)

- [ ] **Step 1: Verify CLI help**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python coach.py --help`
Expected: Shows `status`, `report`, `ask` subcommands.

- [ ] **Step 2: Test report with narrative (requires ANTHROPIC_API_KEY)**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python coach.py report --week 1`
Expected: Prints a natural language coaching narrative for week 1 and saves `data/coaching/week_01_narrative.md`.

- [ ] **Step 3: Test report with --json flag**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python coach.py report --week 1 --json`
Expected: Prints raw JSON (same as Phase 1 behavior).

- [ ] **Step 4: Test --regenerate flag**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python coach.py report --week 1 --regenerate`
Expected: Loads existing JSON, generates fresh narrative.

- [ ] **Step 5: Test conversational mode**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python coach.py ask "How's my week looking?"`
Expected: Coach responds conversationally using week 1 data.

- [ ] **Step 6: Test bare question shorthand**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python coach.py "What was my vert last week?"`
Expected: Same as `ask` mode — responds with vert data.

- [ ] **Step 7: Verify no API key graceful degradation**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && ANTHROPIC_API_KEY="" python coach.py report --week 1`
Expected: Outputs raw JSON with message "Set ANTHROPIC_API_KEY to get a coaching narrative."
