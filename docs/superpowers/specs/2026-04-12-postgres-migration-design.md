# Postgres Migration — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Branch:** `feat/postgres-migration` (to be created)

## Problem

The Tarahumara Ultra Tracker stores all data as JSON files on disk. On Railway (production), the filesystem is ephemeral — `data/activities/` and `data/conversations/` are gitignored and lost on every deploy. This causes:

- The coach LLM has no training data on prod (says "no training logged yet")
- Conversation history doesn't persist across deploys
- A manual `push_data.py` → git push workflow is needed to update the dashboard cache
- No way to query training data (e.g., "show all weeks where compliance < 70%")
- No way to modify the training plan dynamically or track changes over time

## Solution

Migrate to a single Railway-hosted PostgreSQL database using psycopg2 (raw SQL). Both local development and production connect to the same database via `DATABASE_URL`.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Activities + Conversations + Weeks cache + Training plan + Daily health | Covers prod needs + adds health tracking + mutable plan |
| Environment | Single Railway Postgres (local + prod) | One source of truth, no sync headaches |
| File workflow | Clean break — no more JSON writes | Simplicity, DB is the single source |
| DB layer | psycopg2, raw SQL | 6 tables, single user, straightforward queries — no ORM overhead needed |
| Plan modifications | Dedicated API endpoint (phase 1), LLM tool-calling (future) | Incremental — get the data layer right first |

## Schema

### `activities`

Replaces `data/activities/*.json`. One row per Garmin activity.

```sql
CREATE TABLE IF NOT EXISTS activities (
    id              SERIAL PRIMARY KEY,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    garmin_id       BIGINT UNIQUE,
    activity_date   DATE NOT NULL,
    week_number     SMALLINT NOT NULL,
    activity_type   TEXT,
    activity_name   TEXT,
    distance_km     REAL,
    elevation_m     REAL,
    duration_min    REAL,
    avg_hr          REAL,
    avg_pace        TEXT,
    calories        REAL,
    sets            INTEGER,
    reps            INTEGER,
    route_svg       TEXT,
    raw_json        JSONB,
    synced_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_week ON activities (week_number, profile_id);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities (activity_date);
```

- `garmin_id` UNIQUE prevents duplicate inserts on re-sync
- `raw_json` stores full Garmin payload — future-proofs against new fields
- `route_svg` stores the SVG path string for the dashboard map visualization

### `daily_health`

New table. One row per day with wellness/recovery metrics from Garmin.

```sql
CREATE TABLE IF NOT EXISTS daily_health (
    date            DATE NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    sleep_hours     REAL,
    sleep_score     SMALLINT,
    deep_sleep_min  REAL,
    rem_sleep_min   REAL,
    light_sleep_min REAL,
    hrv_weekly_avg  REAL,
    hrv_last_night  REAL,
    resting_hr      SMALLINT,
    body_battery_am SMALLINT,
    body_battery_pm SMALLINT,
    training_readiness SMALLINT,
    stress_avg      SMALLINT,
    spo2_avg        REAL,
    weight_kg       REAL,
    body_fat_pct    REAL,
    raw_json        JSONB,
    synced_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, profile_id)
);
```

- UPSERT by `(date, profile_id)` — re-syncing a day overwrites with latest
- `raw_json` captures everything from all Garmin health endpoints for the day

### `conversations`

Replaces `data/conversations/*.json`. One row per chat exchange.

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    question        TEXT NOT NULL,
    category        TEXT NOT NULL,
    response        TEXT NOT NULL,
    week_number     SMALLINT NOT NULL
);
```

### `week_snapshots`

Replaces `dashboard/weeks_cache.json`. Pre-built week summaries for the dashboard.

```sql
CREATE TABLE IF NOT EXISTS week_snapshots (
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    data            JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);
```

- JSONB `data` column stores the exact object the dashboard JS expects
- UPSERT on sync — replaces the snapshot with fresh data

### `training_plan`

Replaces `plan.json` at runtime. Mutable training plan.

```sql
CREATE TABLE IF NOT EXISTS training_plan (
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    phase           TEXT NOT NULL,
    is_recovery     BOOLEAN DEFAULT FALSE,
    distance_km     REAL,
    vert_m          REAL,
    long_run_km     REAL,
    gym_sessions    SMALLINT,
    series_type     TEXT,
    workouts        JSONB,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);
```

### `plan_changes`

Audit log for every plan modification.

```sql
CREATE TABLE IF NOT EXISTS plan_changes (
    id              SERIAL PRIMARY KEY,
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    field           TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT,
    source          TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plan_changes_week ON plan_changes (week_number, profile_id);
```

- `source` values: `'initial_seed'`, `'coach_chat'`, `'manual'`, `'auto_adjustment'`
- `field` is the column name that changed (e.g., `'distance_km'`, `'series_type'`)
- `old_value` / `new_value` cast to TEXT for uniformity across field types

## Module Architecture

### New files

**`tracker/db.py`** — single data access module, all DB queries live here.

```
init_db()                              # Create pool, run schema
close_pool()                           # Shutdown
get_conn()                             # Context manager for connections

# Activities
save_activities(activities, week, profile)
get_activities(week, profile) -> list[dict]
get_all_activities(profile) -> list[dict]

# Daily health
save_daily_health(date, profile, data)
get_daily_health(start, end, profile) -> list[dict]

# Conversations
save_conversation(question, category, response, week)
get_conversations(limit) -> list[dict]
clear_conversations()

# Week snapshots
upsert_week_snapshot(week, profile, data)
get_week_snapshots(profile) -> list[dict]

# Training plan
get_plan() -> list[dict]
get_week_plan(week, profile) -> dict
update_plan_field(week, profile, field, old_val, new_val, reason, source)
get_plan_changes(week, profile, limit) -> list[dict]
```

**`tracker/schema.sql`** — all CREATE TABLE statements. Run on every startup (idempotent via IF NOT EXISTS).

**`scripts/seed_db.py`** — one-time migration script:
1. Load `plan.json` → `training_plan` (with `plan_changes` entries, source: `'initial_seed'`)
2. Load `data/activities/*.json` → `activities` (ON CONFLICT skip)
3. Load `data/conversations/*.json` → `conversations`
4. Rebuild all `week_snapshots` from inserted activities

### Modified files

| File | What changes |
|---|---|
| `tracker/garmin_sync.py` | `sync_activities()` writes to DB via `db.save_activities()`. `load_cached_activities()` reads from DB via `db.get_activities()`. New `sync_daily_health()` function fetches health endpoints and calls `db.save_daily_health()`. |
| `tracker/plan_data.py` | `load_plan()` and `get_week()` read from DB via `db.get_plan()` / `db.get_week_plan()`. Falls back to `plan.json` if DB unavailable (graceful degradation for CLI). |
| `api/conversation.py` | `save_message()` calls `db.save_conversation()`. `load_history()` calls `db.get_conversations()`. `clear_history()` calls `db.clear_conversations()`. |
| `api/routes_coach.py` | Remove `_build_coaching_data_from_cache()`. Add daily health + plan changes to coaching context. |
| `api/routes_dashboard.py` | `get_weeks()` reads from `db.get_week_snapshots()`. Remove cache file fallback. |
| `dashboard/serve.py` | `_update_weeks_cache()` calls `db.upsert_week_snapshot()`. `_handle_weeks()` reads from DB. Remove file-based cache logic. |
| `api/app.py` | Call `db.init_db()` in lifespan startup, `db.close_pool()` on shutdown. |
| `requirements.txt` | Add `psycopg2-binary>=2.9.0`. |

### Deleted files

| File | Reason |
|---|---|
| `scripts/push_data.py` | No longer needed — no git-push workflow for cache |

### Unchanged files

- `plan.json` — kept in git as original baseline, no longer read at runtime
- `athlete.json`, `knowledge.json` — static config, stay as files
- `coach/narrator.py` — receives richer context, no structural change
- `dashboard/dashboard.html` — JS already works with API responses
- `tracker/models.py`, `tracker/analysis.py`, `tracker/alerts.py` — core logic untouched

## Data Sync Flow

### Garmin sync (activities + health)

```
Garmin Connect API
        │
   ┌────┴────┐
   ▼         ▼
Activities  Health endpoints (sleep, HRV, RHR,
   │        body battery, readiness, stress, SpO2,
   │        body composition)
   ▼         ▼
db.save_activities()    db.save_daily_health()
   │                         │
   └────────┬────────────────┘
            ▼
   db.upsert_week_snapshot()
   (rebuild week summary)
```

### Coach chat flow

```
User question
    │
    ▼
routes_coach.py
    ├── db.get_conversations(limit=20)     → chat history
    ├── db.get_activities(current_week)     → current week data
    ├── db.get_daily_health(last 7 days)   → recovery context
    ├── db.get_plan()                       → current plan targets
    ├── db.get_plan_changes(last 5)         → recent adjustments
    ├── run_coaching(plan, actual, history)  → analysis engine
    │
    ▼
narrator.stream_answer(question, context, history)
    │
    ▼
db.save_conversation(question, category, response, week)
```

### Dashboard flow

```
GET /api/weeks → db.get_week_snapshots(profile) → JSON → browser
```

## Connection Management

- `psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5)`
- Single `DATABASE_URL` env var (Railway auto-injects it)
- Pool initialized on app startup via `db.init_db()`
- Schema is run on every startup (IF NOT EXISTS — idempotent)
- CLI scripts call `db.init_db()` before doing work

## Environment Configuration

| Variable | Local (.env) | Railway |
|---|---|---|
| `DATABASE_URL` | Copied from Railway Postgres "Connect" tab | Auto-injected by Railway Postgres plugin |
| `GARMIN_EMAIL` | Same as now | Same as now |
| `GARMIN_OAUTH1/2` | Not needed | Same as now |
| `ANTHROPIC_API_KEY` | Same as now | Same as now |
| `API_KEY` | Optional | Same as now |

## Migration & Seed Strategy

One-time `scripts/seed_db.py` script:

1. Reads `plan.json` → inserts 30 weeks into `training_plan` + logs in `plan_changes` (source: `'initial_seed'`)
2. Reads `data/activities/*.json` → inserts into `activities` (ON CONFLICT garmin_id DO NOTHING)
3. Reads `data/conversations/*.json` → inserts into `conversations`
4. Rebuilds all `week_snapshots` from inserted activity data

Script is idempotent — safe to run multiple times.

After migration is verified:
- Delete `scripts/push_data.py`
- Remove `dashboard/weeks_cache*.json` from git
- Clean up JSON file I/O code

## Setup Steps (for Emmanuel — when the time comes)

1. Railway dashboard → "New" → "Database" → "PostgreSQL"
2. Copy `DATABASE_URL` from the Postgres service "Connect" tab (public network)
3. Add `DATABASE_URL=postgresql://...` to local `.env`
4. Run `python scripts/seed_db.py` to backfill existing data
5. Deploy branch to Railway, verify dashboard + coach work
6. Merge to main

## Plan Modifications (Phase 1)

Phase 1: Dedicated API endpoint for plan changes.

```
POST /api/plan/update
{
    "week": 8,
    "field": "distance_km",
    "new_value": 38,
    "reason": "Reducing volume — HRV trending down"
}
```

The coach can suggest changes in chat. The user confirms via the API or a future UI button. Every change is logged in `plan_changes`.

Future: LLM tool-calling so the coach can propose and execute changes in conversation flow with user confirmation.

## Testing Strategy

- Unit tests for `tracker/db.py` using a test database (separate `DATABASE_URL_TEST` or create/drop a test schema)
- Integration tests for sync → DB → API → dashboard flow
- Existing tests continue to work — mock `db.*` functions the same way they currently mock file I/O
- Seed script tested by running against empty DB and verifying row counts
