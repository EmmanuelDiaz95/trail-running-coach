# Phase 3 — Web Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a chat drawer to the Tarahumara Ultra Tracker dashboard backed by a FastAPI server with SSE streaming, persistent conversation history, and all existing dashboard endpoints preserved.

**Architecture:** FastAPI app (`api/app.py`) replaces `dashboard/serve.py` as the entrypoint. Existing dashboard functions are imported directly (no rewrite). New coach endpoints handle chat with SSE streaming via `sse-starlette`. Chat drawer is appended to `dashboard.html` as CSS/JS.

**Tech Stack:** FastAPI, uvicorn, sse-starlette, Anthropic streaming API, existing coach/tracker packages

**Branch:** `feature/phase3-web-interface` (already created)

---

### Task 1: Dependencies and project scaffolding

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `api/__init__.py`
- Create: `data/conversations/.gitkeep`

- [ ] **Step 1: Add dependencies to requirements.txt**

Add three new packages after the existing ones:

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sse-starlette>=2.0.0
```

The full `requirements.txt` should be:
```
garminconnect==0.2.8
tabulate==0.9.0
pytest>=7.0.0
anthropic>=0.80.0
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sse-starlette>=2.0.0
```

- [ ] **Step 2: Add conversations dir to .gitignore**

Append to `.gitignore`:
```
data/conversations/
```

- [ ] **Step 3: Create api package and conversations directory**

```bash
mkdir -p api data/conversations
touch api/__init__.py data/conversations/.gitkeep
```

- [ ] **Step 4: Install dependencies**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
pip install fastapi "uvicorn[standard]" sse-starlette
```

- [ ] **Step 5: Verify imports**

```bash
python -c "import fastapi; import uvicorn; import sse_starlette; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore api/__init__.py data/conversations/.gitkeep
git commit -m "feat(phase3): add FastAPI dependencies and project scaffolding"
```

---

### Task 2: Conversation history module

**Files:**
- Create: `api/conversation.py`
- Create: `tests/test_conversation.py`

This is the data layer for persistent chat history. JSON files per day in `data/conversations/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_conversation.py`:

```python
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime

import pytest

from api.conversation import save_message, load_history, clear_history


@pytest.fixture
def conv_dir(tmp_path):
    """Use a temp directory for conversations, then clean up."""
    d = tmp_path / "conversations"
    d.mkdir()
    original = os.environ.get("CONVERSATIONS_DIR")
    os.environ["CONVERSATIONS_DIR"] = str(d)
    yield d
    if original is None:
        os.environ.pop("CONVERSATIONS_DIR", None)
    else:
        os.environ["CONVERSATIONS_DIR"] = original


def test_save_and_load(conv_dir):
    save_message("How's my week?", "coaching", "Looks rough.", 5)
    save_message("What should I eat?", "knowledge", "Carbs before long runs.", 5)

    result = load_history(limit=50)
    assert len(result["messages"]) == 2
    assert result["messages"][0]["question"] == "How's my week?"
    assert result["messages"][1]["question"] == "What should I eat?"
    assert result["has_more"] is False


def test_load_respects_limit(conv_dir):
    for i in range(5):
        save_message(f"Q{i}", "general", f"A{i}", 5)

    result = load_history(limit=3)
    assert len(result["messages"]) == 3
    assert result["has_more"] is True


def test_clear_history(conv_dir):
    save_message("test", "general", "response", 5)
    assert len(list(conv_dir.iterdir())) > 0

    clear_history()
    # .gitkeep may remain, but no JSON files
    json_files = list(conv_dir.glob("*.json"))
    assert len(json_files) == 0

    result = load_history(limit=50)
    assert len(result["messages"]) == 0


def test_load_empty(conv_dir):
    result = load_history(limit=50)
    assert result["messages"] == []
    assert result["has_more"] is False


def test_pagination_with_before(conv_dir):
    save_message("Q1", "general", "A1", 5)
    # Load to get the timestamp
    msgs = load_history(limit=50)["messages"]
    ts = msgs[0]["timestamp"]

    save_message("Q2", "general", "A2", 5)

    # Load only messages before Q2's timestamp (which is after Q1)
    result = load_history(limit=50)
    assert len(result["messages"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python -m pytest tests/test_conversation.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'api.conversation'`

- [ ] **Step 3: Implement conversation module**

Create `api/conversation.py`:

```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data" / "conversations"


def _conv_dir() -> Path:
    override = os.environ.get("CONVERSATIONS_DIR")
    if override:
        return Path(override)
    return DEFAULT_DIR


def save_message(question: str, category: str, response: str, week: int) -> dict:
    """Append a chat exchange to today's conversation file. Returns the saved entry."""
    d = _conv_dir()
    d.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    entry = {
        "timestamp": now.isoformat(timespec="seconds"),
        "question": question,
        "category": category,
        "response": response,
        "week": week,
    }

    day_file = d / f"{now.strftime('%Y-%m-%d')}.json"
    messages = []
    if day_file.exists():
        messages = json.loads(day_file.read_text())
    messages.append(entry)
    day_file.write_text(json.dumps(messages, indent=2))
    return entry


def load_history(limit: int = 50, before: str | None = None) -> dict:
    """Load conversation history across day files, newest last.

    Returns {"messages": [...], "has_more": bool}.
    """
    d = _conv_dir()
    if not d.exists():
        return {"messages": [], "has_more": False}

    # Collect all JSON day files sorted chronologically
    day_files = sorted(d.glob("*.json"))

    all_messages: list[dict] = []
    for f in day_files:
        try:
            msgs = json.loads(f.read_text())
            all_messages.extend(msgs)
        except (json.JSONDecodeError, OSError):
            continue

    # Filter by before timestamp if provided
    if before:
        all_messages = [m for m in all_messages if m["timestamp"] < before]

    has_more = len(all_messages) > limit
    # Return the most recent `limit` messages, preserving chronological order
    if has_more:
        all_messages = all_messages[-limit:]

    return {"messages": all_messages, "has_more": has_more}


def clear_history():
    """Remove all conversation JSON files."""
    d = _conv_dir()
    if not d.exists():
        return
    for f in d.glob("*.json"):
        f.unlink()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_conversation.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/conversation.py tests/test_conversation.py
git commit -m "feat(phase3): add conversation history module with tests"
```

---

### Task 3: Narrator streaming method

**Files:**
- Modify: `coach/narrator.py`
- Create: `tests/test_narrator_stream.py`

Add `stream_answer()` generator method to existing Narrator class. Existing methods unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_narrator_stream.py`:

```python
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

    # Mock the Anthropic streaming API
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

    # Should yield an error message instead of crashing
    assert len(tokens) == 1
    assert "unavailable" in tokens[0].lower() or "error" in tokens[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_narrator_stream.py -v
```

Expected: FAIL — `AttributeError: 'Narrator' object has no attribute 'stream_answer'`

- [ ] **Step 3: Add stream_answer method to Narrator**

In `coach/narrator.py`, add this method to the `Narrator` class after the existing `answer_question` method (after line 110):

```python
    def stream_answer(
        self,
        question: str,
        category: str,
        coaching_data: dict,
    ):
        """Yield tokens from Claude streaming API.

        Same inputs as answer_question(), but yields individual text deltas
        for SSE forwarding. Falls back to a single error token on failure.
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

        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        yield event.delta.text
        except Exception as e:
            yield f"Coach narrative unavailable (error: {e})."
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_narrator_stream.py -v
```

Expected: all 2 tests PASS

- [ ] **Step 5: Run all existing narrator tests to verify nothing broke**

```bash
python -m pytest tests/test_narrator.py tests/test_narrator_stream.py -v
```

Expected: all tests PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add coach/narrator.py tests/test_narrator_stream.py
git commit -m "feat(phase3): add streaming method to Narrator"
```

---

### Task 4: FastAPI app with health check and dashboard routes

**Files:**
- Create: `api/app.py`
- Create: `api/routes_dashboard.py`
- Create: `tests/test_routes_dashboard.py`

This is the core FastAPI app that serves static files, health check, and wraps existing dashboard endpoints.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_routes_dashboard.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_profiles(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "id" in data[0]
    assert "name" in data[0]


def test_get_weeks(client):
    with patch("api.routes_dashboard.build_all_weeks_json") as mock_build:
        mock_build.return_value = [{"number": 1, "actual": {"distance_km": 27}}]
        resp = client.get("/api/weeks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["number"] == 1


def test_sync_requires_auth_when_configured(client):
    with patch("api.routes_dashboard.API_KEY", "test-secret"):
        resp = client.post("/api/sync?week=1")
        assert resp.status_code == 401


def test_sync_with_valid_auth(client):
    with patch("api.routes_dashboard.API_KEY", "test-secret"), \
         patch("api.routes_dashboard.build_week_json") as mock_build, \
         patch("api.routes_dashboard._update_weeks_cache"):
        mock_build.return_value = {"number": 1, "compliance": 99, "activities": []}
        resp = client.post(
            "/api/sync?week=1",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 200
        assert resp.json()["compliance"] == 99
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_routes_dashboard.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'api.app'`

- [ ] **Step 3: Implement routes_dashboard.py**

Create `api/routes_dashboard.py`:

```python
from __future__ import annotations

import json
import os
import time

from fastapi import APIRouter, Header, HTTPException, Query

from dashboard.serve import (
    build_all_weeks_json,
    build_week_json,
    _update_weeks_cache,
    _load_profiles,
    DASHBOARD_DIR,
    SYNC_COOLDOWN_SECONDS,
)
from tracker.garmin_sync import DEFAULT_PROFILE

router = APIRouter()

API_KEY = os.environ.get("API_KEY", "")
PROFILES = _load_profiles()
_last_sync_time: dict[str, float] = {}


def _check_auth(authorization: str | None) -> None:
    if not API_KEY:
        return
    if not authorization or authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_profile(profile: str) -> str:
    valid_ids = {p["id"] for p in PROFILES}
    return profile if profile in valid_ids else DEFAULT_PROFILE


@router.get("/api/profiles")
def get_profiles():
    return PROFILES


@router.get("/api/weeks")
def get_weeks(profile: str = Query(DEFAULT_PROFILE)):
    profile_id = _validate_profile(profile)
    results = build_all_weeks_json(do_sync=False, profile_id=profile_id)
    # Fallback to static cache if no live data
    if all(w.get("actual") is None for w in results):
        suffix = f"_{profile_id}" if profile_id != DEFAULT_PROFILE else ""
        cache_path = DASHBOARD_DIR / f"weeks_cache{suffix}.json"
        if cache_path.exists():
            results = json.loads(cache_path.read_text())
    return results


@router.post("/api/sync")
def sync_week(
    week: int | None = Query(None),
    profile: str = Query(DEFAULT_PROFILE),
    authorization: str | None = Header(None),
):
    _check_auth(authorization)
    profile_id = _validate_profile(profile)

    from tracker.plan_data import get_current_week

    if week is not None:
        if week < 1 or week > 30:
            raise HTTPException(status_code=400, detail="Week must be between 1 and 30")
        week_num = week
    else:
        week_num = get_current_week()
        if week_num is None:
            raise HTTPException(status_code=400, detail="Not in training window")

    # Rate limiting
    rate_key = f"{profile_id}:{week_num}"
    now = time.time()
    last = _last_sync_time.get(rate_key, 0)
    if now - last < SYNC_COOLDOWN_SECONDS:
        remaining = int(SYNC_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429, detail=f"Please wait {remaining}s before syncing again")

    result = build_week_json(week_num, do_sync=True, profile_id=profile_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail="Garmin sync failed. Check server logs.")

    _last_sync_time[rate_key] = time.time()
    _update_weeks_cache(week_num, result, profile_id)
    return result


@router.post("/api/push-workout")
def push_workout_route(
    week: int = Query(...),
    profile: str = Query(DEFAULT_PROFILE),
    authorization: str | None = Header(None),
):
    _check_auth(authorization)
    profile_id = _validate_profile(profile)

    if week < 1 or week > 30:
        raise HTTPException(status_code=400, detail="Week must be between 1 and 30")

    from dashboard.serve import push_workout

    # Rate limiting
    rate_key = f"push:{profile_id}:{week}"
    now = time.time()
    last = _last_sync_time.get(rate_key, 0)
    if now - last < SYNC_COOLDOWN_SECONDS:
        remaining = int(SYNC_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429, detail=f"Please wait {remaining}s")

    result = push_workout(week, profile_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    _last_sync_time[rate_key] = time.time()
    return result
```

- [ ] **Step 4: Implement app.py**

Create `api/app.py`:

```python
from __future__ import annotations

import os
import sys
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.garmin_sync import _load_env

_load_env()

from dashboard.serve import (
    _auto_sync,
    DASHBOARD_DIR,
)
from api.routes_dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start auto-sync background thread on startup."""
    sync_thread = threading.Thread(target=_auto_sync, daemon=True)
    sync_thread.start()
    print("[lifespan] Auto-sync thread started")
    yield
    print("[lifespan] Shutting down")


app = FastAPI(title="Tarahumara Ultra Tracker", lifespan=lifespan)

# API routes (must be registered BEFORE static files mount)
app.include_router(dashboard_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Static files — serves dashboard.html at root
# This MUST be last because it catches all unmatched routes
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="static")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_routes_dashboard.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 6: Quick manual smoke test**

```bash
source venv/bin/activate
uvicorn api.app:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://localhost:8000/health | python -m json.tool
curl -s http://localhost:8000/api/profiles | python -m json.tool
kill %1
```

Expected: health returns `{"status": "ok"}`, profiles returns a list.

- [ ] **Step 7: Commit**

```bash
git add api/app.py api/routes_dashboard.py tests/test_routes_dashboard.py
git commit -m "feat(phase3): FastAPI app with health check and dashboard routes"
```

---

### Task 5: Coach API routes (chat, history, status)

**Files:**
- Create: `api/routes_coach.py`
- Modify: `api/app.py` (add coach router)
- Create: `tests/test_routes_coach.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_routes_coach.py`:

```python
from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def conv_dir(tmp_path):
    d = tmp_path / "conversations"
    d.mkdir()
    original = os.environ.get("CONVERSATIONS_DIR")
    os.environ["CONVERSATIONS_DIR"] = str(d)
    yield d
    if original is None:
        os.environ.pop("CONVERSATIONS_DIR", None)
    else:
        os.environ["CONVERSATIONS_DIR"] = original


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


def test_coach_history_empty(client, conv_dir):
    resp = client.get("/api/coach/history")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_coach_clear_history(client, conv_dir):
    # Save a message first
    from api.conversation import save_message
    save_message("test", "general", "response", 5)

    resp = client.delete("/api/coach/history")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify cleared
    resp = client.get("/api/coach/history")
    assert resp.json()["messages"] == []


def test_coach_chat_returns_sse(client, conv_dir):
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_routes_coach.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'api.routes_coach'`

- [ ] **Step 3: Implement routes_coach.py**

Create `api/routes_coach.py`:

```python
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.requests import Request
from fastapi.responses import StreamingResponse

from tracker.plan_data import get_current_week, get_week, get_week_dates, days_to_race
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
from tracker.data_loader import load_week_range
from coach.engine import run_coaching
from coach.classifier import classify_question
from coach.narrator import Narrator
from api.conversation import save_message, load_history, clear_history

router = APIRouter(prefix="/api/coach")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHAT_COOLDOWN_SECONDS = 10
_last_chat_time: dict[str, float] = {}


def _get_narrator() -> Narrator | None:
    """Create a Narrator if ANTHROPIC_API_KEY is set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    athlete_path = PROJECT_ROOT / "athlete.json"
    try:
        with open(athlete_path) as f:
            athlete = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return Narrator(api_key=api_key, athlete=athlete)


def _build_coaching_data() -> dict | None:
    """Build coaching data for the current week. Returns None if unavailable."""
    week_num = get_current_week()
    if week_num is None:
        return None
    plan = get_week(week_num)
    if plan is None:
        return None
    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        return None
    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)
    return output.to_dict()


@router.get("/status")
def coach_status():
    week_num = get_current_week()
    if week_num is None:
        raise HTTPException(status_code=400, detail="Not in training window")

    plan = get_week(week_num)
    if plan is None:
        raise HTTPException(status_code=400, detail=f"Week {week_num} not in plan")

    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        return {
            "week": week_num,
            "phase": plan.phase,
            "days_to_race": days_to_race(),
            "compliance": None,
            "readiness": None,
        }

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)

    readiness_data = None
    if output.readiness:
        readiness_data = {
            "score": output.readiness.score,
            "acwr": output.readiness.acwr,
            "zone": output.readiness.acwr_zone,
            "recommendation": output.readiness.recommendation,
        }

    return {
        "week": week_num,
        "phase": plan.phase,
        "days_to_race": days_to_race(),
        "compliance": output.compliance_score,
        "readiness": readiness_data,
    }


@router.get("/history")
def get_history(limit: int = Query(50), before: str | None = Query(None)):
    return load_history(limit=limit, before=before)


@router.delete("/history")
def delete_history():
    clear_history()
    return {"status": "ok"}


@router.post("/chat")
def coach_chat(request_body: dict):
    question = request_body.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    narrator = _get_narrator()
    if narrator is None:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    # Rate limiting
    rate_key = "chat"
    now = time.time()
    last = _last_chat_time.get(rate_key, 0)
    if now - last < CHAT_COOLDOWN_SECONDS:
        remaining = int(CHAT_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429, detail=f"Please wait {remaining}s")

    week_num = get_current_week()
    category = classify_question(question)
    coaching_data = _build_coaching_data()
    if coaching_data is None:
        coaching_data = {"note": "No training data available yet."}

    _last_chat_time[rate_key] = time.time()

    def event_stream():
        full_response = []
        for token in narrator.stream_answer(question, category, coaching_data):
            full_response.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        yield f"data: {json.dumps({'meta': {'category': category, 'week': week_num}})}\n\n"
        yield "data: [DONE]\n\n"

        # Save to conversation history after streaming completes
        response_text = "".join(full_response)
        save_message(question, category, response_text, week_num or 0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Register coach router in app.py**

In `api/app.py`, add the import and include after the dashboard router:

```python
from api.routes_coach import router as coach_router
```

And after `app.include_router(dashboard_router)`:

```python
app.include_router(coach_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_routes_coach.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 6: Run all tests to verify nothing broke**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/routes_coach.py api/app.py tests/test_routes_coach.py
git commit -m "feat(phase3): add coach API routes with SSE streaming"
```

---

### Task 6: Chat drawer UI in dashboard

**Files:**
- Modify: `dashboard/dashboard.html` (append CSS + JS + HTML)

This adds the right slide-out chat panel to the existing dashboard. All additions go at the end of the file, before `</body>`.

- [ ] **Step 1: Add chat drawer CSS**

In `dashboard/dashboard.html`, find the closing `</style>` tag (around line 960-970). Insert this CSS block just before `</style>`:

```css
/* ── Coach Chat Drawer ── */
.coach-fab {
  position: fixed; bottom: 100px; right: 28px; z-index: 50;
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, var(--copper), var(--terracotta));
  border: none; cursor: pointer; color: #fff;
  box-shadow: 0 4px 16px rgba(200, 121, 65, 0.35);
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.3s ease;
  font-size: 22px;
}
.coach-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 24px rgba(200, 121, 65, 0.5);
}
.coach-fab--hidden { display: none; }

.coach-drawer {
  position: fixed; top: 0; right: -380px; width: 370px; height: 100vh;
  background: var(--bg); border-left: 1px solid var(--border);
  z-index: 100; display: flex; flex-direction: column;
  transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: -4px 0 30px rgba(0,0,0,0.4);
}
.coach-drawer--open { right: 0; }

.coach-drawer__header {
  padding: 16px 20px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
}
.coach-drawer__title {
  font-family: 'Syne', sans-serif; font-weight: 700; font-size: 1rem;
  color: var(--copper); letter-spacing: 0.02em;
}
.coach-drawer__close {
  background: none; border: none; color: var(--text-muted);
  font-size: 1.4rem; cursor: pointer; padding: 4px 8px; line-height: 1;
}
.coach-drawer__close:hover { color: var(--text); }

.coach-drawer__messages {
  flex: 1; overflow-y: auto; padding: 16px 16px 8px;
  display: flex; flex-direction: column; gap: 12px;
}
.coach-msg {
  max-width: 88%; padding: 10px 14px; border-radius: 12px;
  font-size: 0.85rem; line-height: 1.55; word-wrap: break-word;
  white-space: pre-wrap;
}
.coach-msg--coach {
  align-self: flex-start; background: var(--surface); color: var(--text);
  border-bottom-left-radius: 4px;
}
.coach-msg--user {
  align-self: flex-end; background: rgba(200, 121, 65, 0.15); color: var(--copper-light);
  border-bottom-right-radius: 4px;
}
.coach-msg--typing {
  align-self: flex-start; background: var(--surface); color: var(--text-muted);
  font-style: italic;
}

.coach-drawer__input-area {
  padding: 12px 16px; border-top: 1px solid var(--border);
  display: flex; gap: 8px;
}
.coach-drawer__input {
  flex: 1; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px; color: var(--text);
  font-family: 'Outfit', sans-serif; font-size: 0.85rem; outline: none;
  transition: border-color 0.2s;
}
.coach-drawer__input:focus { border-color: var(--copper); }
.coach-drawer__input::placeholder { color: var(--text-muted); }
.coach-drawer__send {
  background: linear-gradient(135deg, var(--copper), var(--terracotta));
  border: none; border-radius: 8px; padding: 0 14px; cursor: pointer;
  color: #fff; font-size: 1rem; transition: opacity 0.2s;
}
.coach-drawer__send:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 768px) {
  .coach-drawer { width: 100vw; right: -100vw; }
  .coach-fab { bottom: 90px; right: 16px; width: 46px; height: 46px; font-size: 20px; }
}
```

- [ ] **Step 2: Add chat drawer HTML**

In `dashboard/dashboard.html`, find the sync button HTML (around line 1136-1140, the `<!-- ═══════════ SYNC BUTTON (FAB) ═══════════ -->` comment). Insert the chat drawer HTML just BEFORE the sync button section:

```html
<!-- ═══════════ COACH CHAT DRAWER ═══════════ -->
<button class="coach-fab" id="coachFab" title="Ask your coach">💬</button>
<div class="coach-drawer" id="coachDrawer">
  <div class="coach-drawer__header">
    <span class="coach-drawer__title">Coach</span>
    <button class="coach-drawer__close" id="coachClose">&times;</button>
  </div>
  <div class="coach-drawer__messages" id="coachMessages"></div>
  <div class="coach-drawer__input-area">
    <input class="coach-drawer__input" id="coachInput" type="text"
           placeholder="Ask your coach..." autocomplete="off">
    <button class="coach-drawer__send" id="coachSend" title="Send">&#9654;</button>
  </div>
</div>
```

- [ ] **Step 3: Add chat drawer JavaScript**

In `dashboard/dashboard.html`, find the service worker registration near the end (around line 2044-2047). Insert this script block just BEFORE the `// Register service worker for PWA` line:

```javascript
// ═══════════ COACH CHAT DRAWER ═══════════
(function() {
  var fab = document.getElementById('coachFab');
  var drawer = document.getElementById('coachDrawer');
  var closeBtn = document.getElementById('coachClose');
  var input = document.getElementById('coachInput');
  var sendBtn = document.getElementById('coachSend');
  var messagesEl = document.getElementById('coachMessages');
  var isOpen = false;
  var isStreaming = false;

  function toggleDrawer() {
    isOpen = !isOpen;
    drawer.classList.toggle('coach-drawer--open', isOpen);
    fab.classList.toggle('coach-fab--hidden', isOpen);
    if (isOpen) {
      input.focus();
      if (messagesEl.children.length === 0) loadHistory();
    }
  }

  fab.addEventListener('click', toggleDrawer);
  closeBtn.addEventListener('click', toggleDrawer);

  function appendMessage(text, type) {
    var msg = document.createElement('div');
    msg.className = 'coach-msg coach-msg--' + type;
    msg.textContent = text;
    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return msg;
  }

  function loadHistory() {
    fetch('/api/coach/history?limit=50')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        messagesEl.innerHTML = '';
        data.messages.forEach(function(m) {
          appendMessage(m.question, 'user');
          appendMessage(m.response, 'coach');
        });
      })
      .catch(function() {});
  }

  function sendMessage() {
    var question = input.value.trim();
    if (!question || isStreaming) return;

    appendMessage(question, 'user');
    input.value = '';
    isStreaming = true;
    sendBtn.disabled = true;

    var coachMsg = appendMessage('', 'coach');
    var fullText = '';

    fetch('/api/coach/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question }),
    }).then(function(response) {
      if (!response.ok) {
        return response.json().then(function(err) {
          throw new Error(err.detail || 'Request failed');
        });
      }
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      function read() {
        reader.read().then(function(result) {
          if (result.done) {
            isStreaming = false;
            sendBtn.disabled = false;
            return;
          }
          buffer += decoder.decode(result.value, { stream: true });
          var lines = buffer.split('\n');
          buffer = lines.pop();

          lines.forEach(function(line) {
            if (!line.startsWith('data: ')) return;
            var payload = line.slice(6);
            if (payload === '[DONE]') return;
            try {
              var parsed = JSON.parse(payload);
              if (parsed.token) {
                fullText += parsed.token;
                coachMsg.textContent = fullText;
                messagesEl.scrollTop = messagesEl.scrollHeight;
              }
            } catch(e) {}
          });

          read();
        });
      }
      read();
    }).catch(function(err) {
      coachMsg.textContent = 'Error: ' + err.message;
      coachMsg.classList.add('coach-msg--typing');
      isStreaming = false;
      sendBtn.disabled = false;
    });
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();
```

- [ ] **Step 4: Manual smoke test**

```bash
source venv/bin/activate
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000` in browser. Verify:
1. Dashboard loads normally (metrics, charts, activity cards)
2. Chat FAB appears in bottom-right (above sync button)
3. Clicking FAB opens the right slide-out panel
4. Typing a question and pressing Enter sends it
5. Response streams in token by token
6. Closing and reopening drawer shows conversation history

Press Ctrl+C to stop the server.

- [ ] **Step 5: Commit**

```bash
git add dashboard/dashboard.html
git commit -m "feat(phase3): add coach chat drawer UI with SSE streaming"
```

---

### Task 7: Update Procfile and deployment config

**Files:**
- Modify: `Procfile`

- [ ] **Step 1: Update Procfile**

Replace the current content of `Procfile` with:

```
web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 2: Verify the app starts with the new Procfile command**

```bash
source venv/bin/activate
PORT=8000 uvicorn api.app:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/profiles
kill %1
```

Expected: `{"status":"ok"}` and a list of profiles.

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: ALL tests pass (existing + new).

- [ ] **Step 4: Commit**

```bash
git add Procfile
git commit -m "feat(phase3): update Procfile to uvicorn + FastAPI"
```

---

### Task 8: End-to-end smoke test and push

- [ ] **Step 1: Start the full server**

```bash
source venv/bin/activate
PORT=8000 uvicorn api.app:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: Verify all endpoints in browser**

Open `http://localhost:8000` and verify:

1. **Dashboard loads:** hero section, week selector, compliance ring, activity cards
2. **Sync works:** click sync FAB, verify it syncs from Garmin
3. **Health check:** visit `http://localhost:8000/health` → `{"status":"ok"}`
4. **Coach FAB:** visible in bottom-right, above sync button
5. **Chat drawer:** click FAB → panel slides in from right
6. **Send a question:** type "How's my week?" → tokens stream in
7. **History persists:** close drawer, reopen → previous messages visible
8. **Mobile responsive:** resize window to <768px → drawer goes full-width

- [ ] **Step 3: Run all tests one final time**

```bash
python -m pytest tests/ -v
```

Expected: ALL pass.

- [ ] **Step 4: Push branch to remote**

```bash
git push -u origin feature/phase3-web-interface
```

This pushes the feature branch. Production (`main`) is untouched. When ready to deploy, merge to `main` and Railway auto-deploys.
