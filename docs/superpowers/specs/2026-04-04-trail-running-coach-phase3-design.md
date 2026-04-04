# Phase 3 — Web Interface Design

**Date:** 2026-04-04
**Status:** Approved
**Builds on:** Phase 1 (Rule Engine), Phase 2 (LLM Narrator)

## Goal

Add a browser-based chat interface to the existing Tarahumara Ultra Tracker dashboard so Emmanuel can talk to his trail running coach from any device. Replace the current `dashboard/serve.py` (built-in `http.server`) with a FastAPI app that serves both the dashboard and the new coach API — single service, single Railway deployment.

## Non-Goals

- **Dashboard endpoint migration is NOT in scope.** Existing `/api/weeks`, `/api/sync`, and `/api/push-workout` logic is imported as-is from `serve.py` functions into FastAPI routes — no rewrite, no refactor. Full migration to idiomatic FastAPI is deferred (tracked as tech debt).
- No new coach domain modules (nutrition, pacing, mental — those are Phase 4).
- No changes to the rule engine or narrator logic.

## Architecture

```
┌─────────────────────────────────────────────┐
│              FastAPI (uvicorn)               │
│                                             │
│  Static files:  dashboard.html, sw.js, etc. │
│                                             │
│  Dashboard endpoints (imported, not rewritten):
│    GET  /api/weeks      → build_all_weeks_json()
│    POST /api/sync       → sync + _update_weeks_cache()
│    POST /api/push-workout → push_workout()
│    GET  /api/profiles   → profile list
│                                             │
│  Coach endpoints (new):                     │
│    POST /api/coach/chat     (SSE streaming) │
│    GET  /api/coach/history                  │
│    DELETE /api/coach/history                │
│    GET  /api/coach/status                   │
│                                             │
│  Health:                                    │
│    GET  /health                              │
│                                             │
│  Shared: Bearer token auth, rate limiting   │
├─────────────────────────────────────────────┤
│  coach/    tracker/    dashboard/            │
│  (existing packages — unchanged)            │
└─────────────────────────────────────────────┘
```

**Key principle:** The FastAPI app is a thin HTTP layer. All logic lives in existing modules (`coach/engine.py`, `coach/narrator.py`, `coach/classifier.py`, `tracker/*`). The API routes are glue code only.

## Chat Drawer UI

The coach chat is a **right slide-out panel** embedded in the existing `dashboard.html`:

- **Trigger:** Floating action button (FAB) in bottom-right corner, same style as existing sync FAB
- **Panel:** Slides in from the right edge, ~350px wide. Dashboard content shrinks to accommodate.
- **Components:**
  - Header bar with "Coach" title and close button
  - Scrollable message area (coach messages left-aligned, user messages right-aligned)
  - Text input with send button at the bottom
  - Loading indicator during streaming (typing dots)
- **Styling:** Matches existing dashboard design system — dark background (#111), copper accents, JetBrains Mono for labels, Outfit for body text
- **Responsive:** On mobile (<768px), panel goes full-width overlay instead of side-by-side

Chat drawer JS/CSS is appended to the existing `dashboard.html`. No separate HTML file.

## API Endpoints

### POST /api/coach/chat

Send a question, receive a streamed coaching response.

**Request:**
```json
{
  "question": "How's my week going?"
}
```

**Response:** Server-Sent Events (SSE) stream.

```
data: {"token": "This"}
data: {"token": " week"}
data: {"token": " is"}
data: {"token": " rough"}
...
data: {"meta": {"category": "coaching", "week": 5}}
data: [DONE]
```

Each event contains a single token. The final `meta` event includes classification and context. `[DONE]` signals stream end.

**Flow:**
1. Classify question via `coach/classifier.py`
2. Build coaching data via `coach/engine.py` (current week)
3. Call `narrator.answer_question()` with Anthropic streaming enabled
4. Forward each token as an SSE event
5. After stream completes, save the full exchange to conversation history

**Rate limiting:** 10-second cooldown between chat requests per session.

### GET /api/coach/history

Fetch conversation history.

**Query params:**
- `limit` (int, default 50): max messages to return
- `before` (ISO timestamp, optional): pagination cursor

**Response:**
```json
{
  "messages": [
    {
      "timestamp": "2026-04-04T12:19:22",
      "question": "How's my week going?",
      "category": "coaching",
      "response": "This week is rough — 44% compliance...",
      "week": 5
    }
  ],
  "has_more": false
}
```

### DELETE /api/coach/history

Clear all conversation history. Returns `{"status": "ok"}`.

### GET /api/coach/status

Quick readiness snapshot (same data as `coach.py status`).

**Response:**
```json
{
  "week": 5,
  "phase": "base",
  "days_to_race": 181,
  "compliance": 44,
  "readiness": {
    "score": 6,
    "acwr": 0.60,
    "zone": "detraining",
    "recommendation": "push"
  }
}
```

## Conversation History

**Storage:** JSON files in `data/conversations/`, one file per day.

**File format** (`data/conversations/2026-04-04.json`):
```json
[
  {
    "timestamp": "2026-04-04T12:19:22",
    "question": "How's my week going?",
    "category": "coaching",
    "response": "This week is rough...",
    "week": 5
  }
]
```

**Design choices:**
- One file per day keeps files small and greppable
- Append-only within a day (read → append → write)
- History endpoint reads across day files in reverse chronological order
- `DELETE /api/coach/history` removes all files in the directory
- No session concept — all messages are one continuous conversation

## Streaming Implementation

Uses `sse-starlette` for SSE support in FastAPI. The narrator's `_call_api` method is extended with a `stream=True` option that yields tokens from the Anthropic streaming API (`client.messages.stream()`).

**New method on Narrator:**
```python
def stream_answer(self, question, category, coaching_data):
    """Yield tokens from Claude streaming API."""
    # Uses anthropic client.messages.stream() context manager
    # Yields individual text delta strings
```

The existing `answer_question()` method stays unchanged for CLI use.

## File Structure

**New files:**
```
personal_health/running/
├── api/
│   ├── __init__.py
│   ├── app.py              ← FastAPI app, static files, CORS, auth middleware
│   ├── routes_dashboard.py ← imports serve.py functions, wraps in FastAPI routes
│   ├── routes_coach.py     ← /api/coach/* endpoints
│   └── stream.py           ← SSE streaming wrapper
├── data/
│   └── conversations/      ← chat history (auto-created)
├── Procfile                ← updated: web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
└── requirements.txt        ← adds: fastapi, uvicorn[standard], sse-starlette
```

**Modified files:**
- `dashboard/dashboard.html` — chat drawer JS/CSS appended (existing code untouched)
- `coach/narrator.py` — add `stream_answer()` method alongside existing methods
- `requirements.txt` — add 3 dependencies

**Unchanged:**
- `dashboard/serve.py` — stays on disk, no longer the entrypoint
- `coach/engine.py`, `classifier.py`, `models.py` — no changes
- `coach/trends.py`, `readiness.py`, `adjustments.py` — no changes
- `tracker/*` — no changes

## Dependencies

Added to `requirements.txt`:
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.30.0`
- `sse-starlette>=2.0.0`

## Auth & Security

- Bearer token auth via `API_KEY` env var (same as current serve.py)
- Applied as FastAPI dependency to protected routes (`/api/sync`, `/api/push-workout`, `/api/coach/chat`)
- Read-only endpoints unprotected: `/api/weeks`, `/api/profiles`, `/api/coach/status`, `/api/coach/history`
- Chat input sanitized before passing to classifier/narrator
- ANTHROPIC_API_KEY required for coach endpoints; returns 503 if not set
- Rate limiting: 10s cooldown on `/api/coach/chat`, 60s on `/api/sync` (preserved from serve.py)
- In-memory dict rate limiting (sufficient for single-worker Railway deployment)

## Environment Variables

All existing env vars preserved. No new ones required:
- `API_KEY` — bearer token for API auth
- `ANTHROPIC_API_KEY` — Claude API key (already in .env)
- `PROFILES` — Garmin profile config
- `AUTO_SYNC_INTERVAL` — background sync interval
- `PORT` — server port (Railway sets this)
- `HOST` — bind address

## Deployment

**Branch strategy:** Development on `feature/phase3-web-interface` branch. Merge to `main` only after full smoke test. Production dashboard stays untouched until merge.

**Railway config:** Single service, git-deploy from `main`. Current `runtime.txt` specifies Python 3.11.9 (Railway compatible with FastAPI).

Procfile changes from:
```
web: HOST=0.0.0.0 python dashboard/serve.py
```
to:
```
web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

**Health check endpoint:** Add `GET /health` returning `{"status": "ok"}` for Railway's health check system.

**Static file serving:** FastAPI `StaticFiles` mount with `html=True` serves `dashboard/` directory. Root `/` serves `dashboard.html` automatically.

**Auto-sync background thread:** Moves from serve.py's `threading.Thread` to FastAPI's `lifespan` context manager for clean startup/shutdown.

**Lifespan pattern:**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_thread = threading.Thread(target=_auto_sync, daemon=True)
    sync_thread.start()
    yield
    # cleanup on shutdown

app = FastAPI(lifespan=lifespan)
```

## Tech Debt Note

The dashboard endpoint migration (rewriting serve.py logic as idiomatic FastAPI) is intentionally deferred. Current approach imports existing functions directly — this works but means:
- Error handling patterns differ between dashboard and coach routes
- No Pydantic models for dashboard request/response
- Rate limiting is hand-rolled instead of using FastAPI middleware

This is acceptable for now. A future Phase 3.5 can clean this up if needed.

## Testing

- `tests/test_routes_coach.py` — FastAPI TestClient tests for all coach endpoints
- `tests/test_stream.py` — SSE streaming tests (mock Anthropic API)
- `tests/test_conversation.py` — history read/write/delete
- Manual smoke test: open dashboard, open chat drawer, ask a question, verify streaming response
