# Postgres Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all JSON file storage with a single Railway PostgreSQL database for activities, daily health, conversations, week snapshots, and a mutable training plan with audit trail.

**Architecture:** New `tracker/db.py` module owns all database access (psycopg2, raw SQL). Existing modules swap file I/O calls for `db.*` functions. Schema auto-creates on startup via `CREATE TABLE IF NOT EXISTS`. One-time `seed_db.py` backfills historical data.

**Tech Stack:** psycopg2-binary, PostgreSQL (Railway-hosted), existing FastAPI + Python 3.9

**Spec:** `docs/superpowers/specs/2026-04-12-postgres-migration-design.md`

---

## File Structure

### New files
| File | Purpose |
|---|---|
| `tracker/schema.sql` | All CREATE TABLE / CREATE INDEX statements |
| `tracker/db.py` | Connection pool + all query functions |
| `scripts/seed_db.py` | One-time migration: load JSON data into Postgres |
| `tests/test_db.py` | Unit tests for db.py |

### Modified files
| File | Change |
|---|---|
| `requirements.txt` | Add `psycopg2-binary>=2.9.0` |
| `api/app.py` | Call `db.init_db()` on startup, `db.close_pool()` on shutdown |
| `tracker/garmin_sync.py` | Replace JSON file read/write with `db.save_activities()` / `db.get_activities()`. Add `sync_daily_health()`. |
| `tracker/plan_data.py` | `load_plan()` and `get_week()` read from DB, fallback to `plan.json` |
| `api/conversation.py` | Rewrite `save_message()`, `load_history()`, `clear_history()` to use DB |
| `dashboard/serve.py` | `_update_weeks_cache()` → `db.upsert_week_snapshot()`. `_handle_weeks()` reads from DB. |
| `api/routes_dashboard.py` | `get_weeks()` reads from DB. Remove cache file fallback. |
| `api/routes_coach.py` | Remove `_build_coaching_data_from_cache()`. Add daily health + plan changes to coaching context. |

### Deleted files
| File | Reason |
|---|---|
| `scripts/push_data.py` | No longer needed — DB replaces git-push workflow |

---

## Task 1: Schema + Dependencies

**Files:**
- Create: `tracker/schema.sql`
- Modify: `requirements.txt`

- [ ] **Step 1: Add psycopg2-binary to requirements.txt**

```
garminconnect==0.2.8
tabulate==0.9.0
pytest>=7.0.0
anthropic>=0.80.0
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sse-starlette>=2.0.0
psycopg2-binary>=2.9.0
```

- [ ] **Step 2: Install the new dependency**

Run: `source venv/bin/activate && pip install psycopg2-binary>=2.9.0`
Expected: Successfully installed psycopg2-binary-2.9.x

- [ ] **Step 3: Create tracker/schema.sql**

```sql
-- Tarahumara Ultra Tracker — Database Schema
-- Run on every startup; all statements are idempotent (IF NOT EXISTS).

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

CREATE TABLE IF NOT EXISTS conversations (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    question        TEXT NOT NULL,
    category        TEXT NOT NULL,
    response        TEXT NOT NULL,
    week_number     SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS week_snapshots (
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    data            JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);

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
    start_date      TEXT,
    end_date        TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);

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

- [ ] **Step 4: Commit**

```bash
git add tracker/schema.sql requirements.txt
git commit -m "feat: add Postgres schema and psycopg2 dependency"
```

---

## Task 2: Database Module (tracker/db.py) — Connection + Schema Init

**Files:**
- Create: `tracker/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write test for init_db and close_pool**

Create `tests/test_db.py`:

```python
from __future__ import annotations

import os
import pytest

# Skip entire module if no DATABASE_URL
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


def test_init_db_creates_tables():
    from tracker import db
    db.init_db()
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
    assert "activities" in tables
    assert "daily_health" in tables
    assert "conversations" in tables
    assert "week_snapshots" in tables
    assert "training_plan" in tables
    assert "plan_changes" in tables
    db.close_pool()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: FAIL (module tracker.db not found) or SKIP if DATABASE_URL not set

- [ ] **Step 3: Write tracker/db.py — connection pool and schema init**

```python
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2 import pool

_pool: pool.ThreadedConnectionPool | None = None
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db():
    """Initialize the connection pool and ensure schema exists."""
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable is required")
    _pool = pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=dsn)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())
        conn.commit()


def close_pool():
    """Shut down the connection pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    """Get a connection from the pool. Auto-returns on exit."""
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: PASS (or SKIP if no DATABASE_URL)

- [ ] **Step 5: Commit**

```bash
git add tracker/db.py tests/test_db.py
git commit -m "feat: add db module with connection pool and schema init"
```

---

## Task 3: Database Module — Activity Queries

**Files:**
- Modify: `tracker/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write tests for save_activities and get_activities**

Append to `tests/test_db.py`:

```python
def test_save_and_get_activities():
    from tracker import db
    db.init_db()

    # Clean up from prior runs
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE garmin_id IN (99901, 99902)")
        conn.commit()

    activities = [
        {
            "garmin_id": 99901,
            "activity_date": "2026-04-06",
            "week_number": 6,
            "activity_type": "trail_running",
            "activity_name": "Trail Run",
            "distance_km": 14.0,
            "elevation_m": 364,
            "duration_min": 105.0,
            "avg_hr": 153,
            "avg_pace": "7:31",
            "calories": 1296,
            "raw_json": {"activityId": 99901, "test": True},
        },
        {
            "garmin_id": 99902,
            "activity_date": "2026-04-07",
            "week_number": 6,
            "activity_type": "strength_training",
            "activity_name": "Gym",
            "distance_km": 0,
            "elevation_m": 0,
            "duration_min": 60.0,
            "avg_hr": 120,
            "calories": 400,
            "sets": 5,
            "reps": 10,
            "raw_json": {"activityId": 99902, "test": True},
        },
    ]

    saved = db.save_activities(activities, week_number=6, profile_id="default")
    assert saved == 2

    # Save again — duplicates should be skipped
    saved_again = db.save_activities(activities, week_number=6, profile_id="default")
    assert saved_again == 0

    result = db.get_activities(week_number=6, profile_id="default")
    garmin_ids = [a["garmin_id"] for a in result]
    assert 99901 in garmin_ids
    assert 99902 in garmin_ids

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE garmin_id IN (99901, 99902)")
        conn.commit()
    db.close_pool()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_save_and_get_activities -v`
Expected: FAIL — save_activities not defined

- [ ] **Step 3: Implement save_activities and get_activities in tracker/db.py**

Append to `tracker/db.py`:

```python
import json


def save_activities(activities: list[dict], week_number: int, profile_id: str = "default") -> int:
    """Insert activities. Returns count of newly inserted rows (skips duplicates)."""
    if not activities:
        return 0
    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for a in activities:
                cur.execute("""
                    INSERT INTO activities (
                        profile_id, garmin_id, activity_date, week_number,
                        activity_type, activity_name, distance_km, elevation_m,
                        duration_min, avg_hr, avg_pace, calories, sets, reps,
                        route_svg, raw_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (garmin_id) DO NOTHING
                """, (
                    profile_id,
                    a.get("garmin_id"),
                    a["activity_date"],
                    week_number,
                    a.get("activity_type"),
                    a.get("activity_name"),
                    a.get("distance_km"),
                    a.get("elevation_m"),
                    a.get("duration_min"),
                    a.get("avg_hr"),
                    a.get("avg_pace"),
                    a.get("calories"),
                    a.get("sets"),
                    a.get("reps"),
                    a.get("route_svg"),
                    json.dumps(a.get("raw_json")) if a.get("raw_json") else None,
                ))
                if cur.rowcount > 0:
                    inserted += 1
        conn.commit()
    return inserted


def get_activities(week_number: int, profile_id: str = "default") -> list[dict]:
    """Get all activities for a week, ordered by date."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT garmin_id, activity_date, week_number, activity_type,
                       activity_name, distance_km, elevation_m, duration_min,
                       avg_hr, avg_pace, calories, sets, reps, route_svg, raw_json
                FROM activities
                WHERE week_number = %s AND profile_id = %s
                ORDER BY activity_date
            """, (week_number, profile_id))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_save_and_get_activities -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tracker/db.py tests/test_db.py
git commit -m "feat: add activity save/get queries to db module"
```

---

## Task 4: Database Module — Daily Health Queries

**Files:**
- Modify: `tracker/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write test for save_daily_health and get_daily_health**

Append to `tests/test_db.py`:

```python
from datetime import date


def test_save_and_get_daily_health():
    from tracker import db
    db.init_db()

    test_date = date(2026, 4, 10)

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM daily_health WHERE date = %s AND profile_id = 'default'", (test_date,))
        conn.commit()

    health = {
        "sleep_hours": 7.5,
        "sleep_score": 82,
        "deep_sleep_min": 90.0,
        "rem_sleep_min": 85.0,
        "light_sleep_min": 180.0,
        "hrv_last_night": 45.0,
        "resting_hr": 52,
        "body_battery_am": 75,
        "training_readiness": 68,
        "stress_avg": 35,
        "spo2_avg": 94.5,
    }
    db.save_daily_health(test_date, "default", health)

    # Upsert — update sleep_score
    health["sleep_score"] = 90
    db.save_daily_health(test_date, "default", health)

    results = db.get_daily_health(test_date, test_date, "default")
    assert len(results) == 1
    assert results[0]["sleep_score"] == 90
    assert results[0]["resting_hr"] == 52

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM daily_health WHERE date = %s AND profile_id = 'default'", (test_date,))
        conn.commit()
    db.close_pool()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_save_and_get_daily_health -v`
Expected: FAIL — save_daily_health not defined

- [ ] **Step 3: Implement save_daily_health and get_daily_health**

Append to `tracker/db.py`:

```python
def save_daily_health(health_date, profile_id: str, data: dict):
    """Upsert a daily health row."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_health (
                    date, profile_id, sleep_hours, sleep_score,
                    deep_sleep_min, rem_sleep_min, light_sleep_min,
                    hrv_weekly_avg, hrv_last_night, resting_hr,
                    body_battery_am, body_battery_pm, training_readiness,
                    stress_avg, spo2_avg, weight_kg, body_fat_pct, raw_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (date, profile_id) DO UPDATE SET
                    sleep_hours = EXCLUDED.sleep_hours,
                    sleep_score = EXCLUDED.sleep_score,
                    deep_sleep_min = EXCLUDED.deep_sleep_min,
                    rem_sleep_min = EXCLUDED.rem_sleep_min,
                    light_sleep_min = EXCLUDED.light_sleep_min,
                    hrv_weekly_avg = EXCLUDED.hrv_weekly_avg,
                    hrv_last_night = EXCLUDED.hrv_last_night,
                    resting_hr = EXCLUDED.resting_hr,
                    body_battery_am = EXCLUDED.body_battery_am,
                    body_battery_pm = EXCLUDED.body_battery_pm,
                    training_readiness = EXCLUDED.training_readiness,
                    stress_avg = EXCLUDED.stress_avg,
                    spo2_avg = EXCLUDED.spo2_avg,
                    weight_kg = EXCLUDED.weight_kg,
                    body_fat_pct = EXCLUDED.body_fat_pct,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = NOW()
            """, (
                health_date,
                profile_id,
                data.get("sleep_hours"),
                data.get("sleep_score"),
                data.get("deep_sleep_min"),
                data.get("rem_sleep_min"),
                data.get("light_sleep_min"),
                data.get("hrv_weekly_avg"),
                data.get("hrv_last_night"),
                data.get("resting_hr"),
                data.get("body_battery_am"),
                data.get("body_battery_pm"),
                data.get("training_readiness"),
                data.get("stress_avg"),
                data.get("spo2_avg"),
                data.get("weight_kg"),
                data.get("body_fat_pct"),
                json.dumps(data.get("raw_json")) if data.get("raw_json") else None,
            ))
        conn.commit()


def get_daily_health(start_date, end_date, profile_id: str = "default") -> list[dict]:
    """Get daily health rows for a date range, ordered by date."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, sleep_hours, sleep_score, deep_sleep_min, rem_sleep_min,
                       light_sleep_min, hrv_weekly_avg, hrv_last_night, resting_hr,
                       body_battery_am, body_battery_pm, training_readiness,
                       stress_avg, spo2_avg, weight_kg, body_fat_pct
                FROM daily_health
                WHERE date >= %s AND date <= %s AND profile_id = %s
                ORDER BY date
            """, (start_date, end_date, profile_id))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_save_and_get_daily_health -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tracker/db.py tests/test_db.py
git commit -m "feat: add daily health save/get queries to db module"
```

---

## Task 5: Database Module — Conversation Queries

**Files:**
- Modify: `tracker/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write test for conversation functions**

Append to `tests/test_db.py`:

```python
def test_conversations():
    from tracker import db
    db.init_db()

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE question LIKE 'TEST:%%'")
        conn.commit()

    db.save_conversation("TEST: How far did I run?", "data", "You ran 14km this week.", 6)
    db.save_conversation("TEST: Should I rest?", "coaching", "Yes, your volume is high.", 6)

    history = db.get_conversations(limit=10)
    test_msgs = [m for m in history if m["question"].startswith("TEST:")]
    assert len(test_msgs) == 2
    assert test_msgs[0]["question"] == "TEST: How far did I run?"
    assert test_msgs[1]["category"] == "coaching"

    db.clear_conversations()
    assert len(db.get_conversations(limit=10)) == 0

    db.close_pool()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_conversations -v`
Expected: FAIL — save_conversation not defined

- [ ] **Step 3: Implement conversation queries**

Append to `tracker/db.py`:

```python
def save_conversation(question: str, category: str, response: str, week_number: int) -> dict:
    """Insert a chat exchange. Returns the saved entry."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (question, category, response, week_number)
                VALUES (%s, %s, %s, %s)
                RETURNING id, created_at
            """, (question, category, response, week_number))
            row = cur.fetchone()
        conn.commit()
    return {
        "id": row[0],
        "timestamp": row[1].isoformat(),
        "question": question,
        "category": category,
        "response": response,
        "week": week_number,
    }


def get_conversations(limit: int = 50) -> list[dict]:
    """Load recent conversation history, oldest first."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, created_at, question, category, response, week_number
                FROM conversations
                ORDER BY created_at ASC
                OFFSET GREATEST((SELECT COUNT(*) FROM conversations) - %s, 0)
            """, (limit,))
            columns = ["id", "timestamp", "question", "category", "response", "week"]
            rows = []
            for row in cur.fetchall():
                entry = dict(zip(columns, row))
                entry["timestamp"] = entry["timestamp"].isoformat()
                rows.append(entry)
            return rows


def clear_conversations():
    """Delete all conversation history."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations")
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_conversations -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tracker/db.py tests/test_db.py
git commit -m "feat: add conversation queries to db module"
```

---

## Task 6: Database Module — Week Snapshots + Training Plan Queries

**Files:**
- Modify: `tracker/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write tests for week snapshots and training plan**

Append to `tests/test_db.py`:

```python
def test_week_snapshots():
    from tracker import db
    db.init_db()

    data = {"number": 99, "phase": "test", "compliance": 85, "activities": []}
    db.upsert_week_snapshot(99, "default", data)

    # Upsert — update
    data["compliance"] = 92
    db.upsert_week_snapshot(99, "default", data)

    snapshots = db.get_week_snapshots("default")
    test_snap = [s for s in snapshots if s["data"]["number"] == 99]
    assert len(test_snap) == 1
    assert test_snap[0]["data"]["compliance"] == 92

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM week_snapshots WHERE week_number = 99")
        conn.commit()
    db.close_pool()


def test_training_plan():
    from tracker import db
    db.init_db()

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM training_plan WHERE week_number = 99")
            cur.execute("DELETE FROM plan_changes WHERE week_number = 99")
        conn.commit()

    week = {
        "week_number": 99,
        "phase": "test",
        "is_recovery": False,
        "distance_km": 40.0,
        "vert_m": 600,
        "long_run_km": 18.0,
        "gym_sessions": 3,
        "series_type": "tempo",
        "start_date": "2099-01-01",
        "end_date": "2099-01-07",
    }
    db.upsert_plan_week(week, "default")

    plan = db.get_plan("default")
    test_weeks = [w for w in plan if w["week_number"] == 99]
    assert len(test_weeks) == 1
    assert test_weeks[0]["distance_km"] == 40.0

    # Update a field
    db.update_plan_field(99, "default", "distance_km", "40.0", "35.0", "Reduce for recovery", "manual")

    updated = db.get_week_plan(99, "default")
    assert updated["distance_km"] == 35.0

    changes = db.get_plan_changes(99, "default")
    assert len(changes) == 1
    assert changes[0]["field"] == "distance_km"
    assert changes[0]["old_value"] == "40.0"
    assert changes[0]["new_value"] == "35.0"
    assert changes[0]["source"] == "manual"

    # Clean up
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM training_plan WHERE week_number = 99")
            cur.execute("DELETE FROM plan_changes WHERE week_number = 99")
        conn.commit()
    db.close_pool()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py::test_week_snapshots tests/test_db.py::test_training_plan -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement week snapshot and training plan queries**

Append to `tracker/db.py`:

```python
def upsert_week_snapshot(week_number: int, profile_id: str, data: dict):
    """Insert or update a week snapshot."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO week_snapshots (week_number, profile_id, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (week_number, profile_id) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """, (week_number, profile_id, json.dumps(data, default=str)))
        conn.commit()


def get_week_snapshots(profile_id: str = "default") -> list[dict]:
    """Get all week snapshots for a profile, ordered by week."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT week_number, data, updated_at
                FROM week_snapshots
                WHERE profile_id = %s
                ORDER BY week_number
            """, (profile_id,))
            return [
                {"week_number": row[0], "data": row[1], "updated_at": row[2].isoformat()}
                for row in cur.fetchall()
            ]


def upsert_plan_week(week: dict, profile_id: str = "default"):
    """Insert or update a single week in the training plan."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO training_plan (
                    week_number, profile_id, phase, is_recovery,
                    distance_km, vert_m, long_run_km, gym_sessions,
                    series_type, workouts, start_date, end_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (week_number, profile_id) DO UPDATE SET
                    phase = EXCLUDED.phase,
                    is_recovery = EXCLUDED.is_recovery,
                    distance_km = EXCLUDED.distance_km,
                    vert_m = EXCLUDED.vert_m,
                    long_run_km = EXCLUDED.long_run_km,
                    gym_sessions = EXCLUDED.gym_sessions,
                    series_type = EXCLUDED.series_type,
                    workouts = EXCLUDED.workouts,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    updated_at = NOW()
            """, (
                week["week_number"], profile_id, week["phase"], week.get("is_recovery", False),
                week.get("distance_km"), week.get("vert_m"), week.get("long_run_km"),
                week.get("gym_sessions"), week.get("series_type"),
                json.dumps(week.get("workouts")) if week.get("workouts") else None,
                week.get("start_date"), week.get("end_date"),
            ))
        conn.commit()


def get_plan(profile_id: str = "default") -> list[dict]:
    """Get all weeks from the training plan, ordered by week number."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT week_number, phase, is_recovery, distance_km, vert_m,
                       long_run_km, gym_sessions, series_type, workouts,
                       start_date, end_date
                FROM training_plan
                WHERE profile_id = %s
                ORDER BY week_number
            """, (profile_id,))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_week_plan(week_number: int, profile_id: str = "default") -> dict | None:
    """Get a single week from the training plan."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT week_number, phase, is_recovery, distance_km, vert_m,
                       long_run_km, gym_sessions, series_type, workouts,
                       start_date, end_date
                FROM training_plan
                WHERE week_number = %s AND profile_id = %s
            """, (week_number, profile_id))
            row = cur.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))


def update_plan_field(week_number: int, profile_id: str, field: str,
                      old_value: str, new_value: str, reason: str, source: str):
    """Update a single field in the training plan and log the change."""
    allowed_fields = {"distance_km", "vert_m", "long_run_km", "gym_sessions", "series_type", "phase", "is_recovery"}
    if field not in allowed_fields:
        raise ValueError(f"Cannot update field '{field}'. Allowed: {allowed_fields}")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Update the plan
            cur.execute(
                f"UPDATE training_plan SET {field} = %s, updated_at = NOW() "
                f"WHERE week_number = %s AND profile_id = %s",
                (new_value, week_number, profile_id),
            )
            # Log the change
            cur.execute("""
                INSERT INTO plan_changes (week_number, profile_id, field, old_value, new_value, reason, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (week_number, profile_id, field, old_value, new_value, reason, source))
        conn.commit()


def get_plan_changes(week_number: int, profile_id: str = "default", limit: int = 20) -> list[dict]:
    """Get plan change history for a week, newest first."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT field, old_value, new_value, reason, source, created_at
                FROM plan_changes
                WHERE week_number = %s AND profile_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (week_number, profile_id, limit))
            columns = [desc[0] for desc in cur.description]
            rows = []
            for row in cur.fetchall():
                entry = dict(zip(columns, row))
                entry["created_at"] = entry["created_at"].isoformat()
                rows.append(entry)
            return rows
```

- [ ] **Step 4: Run all db tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tracker/db.py tests/test_db.py
git commit -m "feat: add week snapshot and training plan queries to db module"
```

---

## Task 7: Seed Script

**Files:**
- Create: `scripts/seed_db.py`

- [ ] **Step 1: Create scripts/seed_db.py**

```python
#!/usr/bin/env python3
"""One-time migration: load existing JSON data into Postgres."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.garmin_sync import _load_env, _normalize_activity, DEFAULT_PROFILE
from tracker.plan_data import get_week_dates
from tracker import db


def seed_plan():
    """Load plan.json into training_plan table."""
    plan_path = PROJECT_ROOT / "plan.json"
    data = json.loads(plan_path.read_text())
    count = 0
    for w in data["weeks"]:
        week = {
            "week_number": w["week_number"],
            "phase": w["phase"],
            "is_recovery": w["is_recovery"],
            "distance_km": w["distance_km"],
            "vert_m": w["vert_m"],
            "long_run_km": w["long_run_km"],
            "gym_sessions": w["gym_sessions"],
            "series_type": w.get("series_type"),
            "workouts": w.get("workouts"),
            "start_date": w["start_date"],
            "end_date": w["end_date"],
        }
        db.upsert_plan_week(week, DEFAULT_PROFILE)
        count += 1
    print(f"[seed] Training plan: {count} weeks inserted")


def seed_activities():
    """Load data/activities/*.json into activities table."""
    act_dir = PROJECT_ROOT / "data" / "activities"
    if not act_dir.exists():
        print("[seed] No activities directory found, skipping")
        return

    files = sorted(act_dir.glob("*.json"))
    total_inserted = 0
    total_skipped = 0

    for f in files:
        if f.name == ".gitkeep":
            continue
        raw_activities = json.loads(f.read_text())
        if not raw_activities:
            continue

        # Determine week number from filename dates
        parts = f.stem.split("_")
        if len(parts) != 2:
            continue

        rows = []
        for raw in raw_activities:
            normalized = _normalize_activity(raw)
            # Determine week number from activity date
            from datetime import date as date_type
            act_date = date_type.fromisoformat(normalized.date) if normalized.date else None
            if not act_date:
                continue

            from tracker.plan_data import PLAN_START, TOTAL_WEEKS
            if act_date < PLAN_START:
                continue
            week_num = (act_date - PLAN_START).days // 7 + 1
            if week_num < 1 or week_num > TOTAL_WEEKS:
                continue

            rows.append({
                "garmin_id": int(normalized.activity_id) if normalized.activity_id else None,
                "activity_date": normalized.date,
                "week_number": week_num,
                "activity_type": normalized.activity_type,
                "activity_name": normalized.name,
                "distance_km": normalized.distance_km,
                "elevation_m": normalized.elevation_gain_m,
                "duration_min": round(normalized.duration_seconds / 60, 1) if normalized.duration_seconds else None,
                "avg_hr": normalized.avg_hr,
                "avg_pace": f"{int(normalized.avg_pace_min_km)}:{int((normalized.avg_pace_min_km % 1) * 60):02d}" if normalized.avg_pace_min_km else None,
                "calories": normalized.calories,
                "route_svg": normalized.route_svg,
                "raw_json": raw,
            })

        if rows:
            inserted = db.save_activities(rows, week_number=rows[0]["week_number"], profile_id=DEFAULT_PROFILE)
            total_inserted += inserted
            total_skipped += len(rows) - inserted

    print(f"[seed] Activities: {len(files)} files, {total_inserted} inserted, {total_skipped} duplicates skipped")


def seed_conversations():
    """Load data/conversations/*.json into conversations table."""
    conv_dir = PROJECT_ROOT / "data" / "conversations"
    if not conv_dir.exists():
        print("[seed] No conversations directory found, skipping")
        return

    files = sorted(conv_dir.glob("*.json"))
    count = 0
    for f in files:
        messages = json.loads(f.read_text())
        for msg in messages:
            db.save_conversation(
                question=msg["question"],
                category=msg["category"],
                response=msg["response"],
                week_number=msg.get("week", 0),
            )
            count += 1

    print(f"[seed] Conversations: {len(files)} day files, {count} messages inserted")


def seed_week_snapshots():
    """Rebuild week snapshots from the DB activity data."""
    from dashboard.serve import build_week_json
    from tracker.plan_data import get_current_week

    current = get_current_week() or 1
    count = 0
    for wn in range(1, current + 1):
        result = build_week_json(wn, do_sync=False, profile_id=DEFAULT_PROFILE)
        if result.get("actual") is not None:
            db.upsert_week_snapshot(wn, DEFAULT_PROFILE, result)
            count += 1

    print(f"[seed] Week snapshots: {count} weeks rebuilt")


if __name__ == "__main__":
    _load_env()
    db.init_db()

    print("=== Seeding database ===")
    print()
    seed_plan()
    seed_activities()
    seed_conversations()
    seed_week_snapshots()
    print()
    print("[seed] Done.")

    db.close_pool()
```

- [ ] **Step 2: Test the seed script**

Run: `source venv/bin/activate && python scripts/seed_db.py`
Expected:
```
=== Seeding database ===

[seed] Training plan: 30 weeks inserted
[seed] Activities: 11 files, ~47 inserted, 0 duplicates skipped
[seed] Conversations: N day files, N messages inserted
[seed] Week snapshots: 6 weeks rebuilt

[seed] Done.
```

- [ ] **Step 3: Run it again to confirm idempotency**

Run: `source venv/bin/activate && python scripts/seed_db.py`
Expected: Activities shows 0 inserted (all duplicates skipped), everything else upserts cleanly.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_db.py
git commit -m "feat: add seed script to backfill Postgres from JSON files"
```

---

## Task 8: Wire Up App Startup

**Files:**
- Modify: `api/app.py`

- [ ] **Step 1: Update api/app.py lifespan to init/close DB**

Replace the current lifespan in `api/app.py` (lines 30-37):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB pool and start auto-sync background thread on startup."""
    from tracker import db
    db.init_db()
    print("[lifespan] Database initialized")
    sync_thread = threading.Thread(target=_auto_sync, daemon=True)
    sync_thread.start()
    print("[lifespan] Auto-sync thread started")
    yield
    print("[lifespan] Shutting down")
    db.close_pool()
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `source venv/bin/activate && python -m pytest tests/test_routes_dashboard.py tests/test_routes_coach.py -v`
Expected: All PASS (these tests mock the functions that call DB, so they don't need a real connection)

- [ ] **Step 3: Commit**

```bash
git add api/app.py
git commit -m "feat: init DB pool on app startup, close on shutdown"
```

---

## Task 9: Migrate garmin_sync.py to DB

**Files:**
- Modify: `tracker/garmin_sync.py`

- [ ] **Step 1: Update sync_activities() to write to DB instead of JSON**

Replace lines 158-186 of `tracker/garmin_sync.py`. The function signature stays the same but now writes to DB:

```python
def sync_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity]:
    """Pull activities from Garmin Connect for a date range and save to database."""
    from tracker.plan_data import PLAN_START, TOTAL_WEEKS
    from tracker import db

    client = _get_client(profile_id)

    raw_activities = client.get_activities_by_date(
        start_date.isoformat(),
        end_date.isoformat(),
    )

    # Fetch route SVG for running activities
    for raw in raw_activities:
        activity_type = (raw.get("activityType", {}).get("typeKey", "") or "").lower()
        if activity_type in RUNNING_TYPES and raw.get("hasPolyline"):
            activity_id = str(raw.get("activityId", ""))
            raw["route_svg"] = _fetch_route_svg(client, activity_id)
            time.sleep(0.5)  # Rate limit
        else:
            raw["route_svg"] = None

    activities = [_normalize_activity(a) for a in raw_activities]

    # Save to database
    rows = []
    for norm, raw in zip(activities, raw_activities):
        act_date = date.fromisoformat(norm.date) if norm.date else None
        if not act_date:
            continue
        if act_date < PLAN_START:
            week_num = 0  # Pre-plan activity
        else:
            week_num = min((act_date - PLAN_START).days // 7 + 1, TOTAL_WEEKS)

        rows.append({
            "garmin_id": int(norm.activity_id) if norm.activity_id else None,
            "activity_date": norm.date,
            "week_number": week_num,
            "activity_type": norm.activity_type,
            "activity_name": norm.name,
            "distance_km": norm.distance_km,
            "elevation_m": norm.elevation_gain_m,
            "duration_min": round(norm.duration_seconds / 60, 1) if norm.duration_seconds else None,
            "avg_hr": norm.avg_hr,
            "avg_pace": f"{int(norm.avg_pace_min_km)}:{int((norm.avg_pace_min_km % 1) * 60):02d}" if norm.avg_pace_min_km else None,
            "calories": norm.calories,
            "route_svg": norm.route_svg,
            "raw_json": raw,
        })

    if rows:
        inserted = db.save_activities(rows, week_number=rows[0]["week_number"], profile_id=profile_id)
        print(f"[garmin] Saved {inserted} new activities to database")

    return activities
```

- [ ] **Step 2: Update load_cached_activities() to read from DB**

Replace lines 189-199 of `tracker/garmin_sync.py`:

```python
def load_cached_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity] | None:
    """Load activities from database for a date range."""
    from tracker.plan_data import PLAN_START, TOTAL_WEEKS
    from tracker import db

    # Determine week number from start_date
    if start_date < PLAN_START:
        return None
    week_num = (start_date - PLAN_START).days // 7 + 1
    if week_num < 1 or week_num > TOTAL_WEEKS:
        return None

    try:
        rows = db.get_activities(week_number=week_num, profile_id=profile_id)
    except Exception:
        return None

    if not rows:
        return None

    # Convert DB rows back to GarminActivity objects
    activities = []
    for r in rows:
        pace = None
        if r.get("avg_pace"):
            parts = r["avg_pace"].split(":")
            if len(parts) == 2:
                pace = int(parts[0]) + int(parts[1]) / 60

        activities.append(GarminActivity(
            activity_id=str(r["garmin_id"]) if r.get("garmin_id") else "",
            date=str(r["activity_date"]),
            activity_type=r.get("activity_type", ""),
            name=r.get("activity_name", ""),
            distance_km=r.get("distance_km") or 0,
            duration_seconds=(r["duration_min"] * 60) if r.get("duration_min") else 0,
            avg_hr=int(r["avg_hr"]) if r.get("avg_hr") else None,
            max_hr=None,
            avg_pace_min_km=pace,
            elevation_gain_m=int(r["elevation_m"]) if r.get("elevation_m") else None,
            calories=int(r["calories"]) if r.get("calories") else None,
            route_svg=r.get("route_svg"),
        ))

    return activities
```

- [ ] **Step 3: Add sync_daily_health() function**

Append to `tracker/garmin_sync.py`:

```python
def sync_daily_health(target_date: date, profile_id: str = DEFAULT_PROFILE) -> dict | None:
    """Pull health/wellness data from Garmin for a single day and save to database."""
    from tracker import db

    client = _get_client(profile_id)
    date_str = target_date.isoformat()
    health: dict = {"raw_json": {}}

    try:
        sleep = client.get_sleep_data(date_str)
        if sleep:
            daily = sleep.get("dailySleepDTO", {})
            health["sleep_hours"] = round((daily.get("sleepTimeSeconds") or 0) / 3600, 1)
            health["sleep_score"] = daily.get("sleepScores", {}).get("overall", {}).get("value")
            health["deep_sleep_min"] = round((daily.get("deepSleepSeconds") or 0) / 60, 1)
            health["rem_sleep_min"] = round((daily.get("remSleepSeconds") or 0) / 60, 1)
            health["light_sleep_min"] = round((daily.get("lightSleepSeconds") or 0) / 60, 1)
            health["raw_json"]["sleep"] = sleep
    except Exception as e:
        print(f"[health] Sleep data failed: {e}")

    try:
        hrv = client.get_hrv_data(date_str)
        if hrv:
            summary = hrv.get("hrvSummary", {})
            health["hrv_weekly_avg"] = summary.get("weeklyAvg")
            health["hrv_last_night"] = summary.get("lastNight")
            health["raw_json"]["hrv"] = hrv
    except Exception as e:
        print(f"[health] HRV data failed: {e}")

    try:
        rhr = client.get_rhr_day(date_str)
        if rhr:
            values = rhr.get("allMetrics", {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE", [])
            if values:
                health["resting_hr"] = values[0].get("value")
            health["raw_json"]["rhr"] = rhr
    except Exception as e:
        print(f"[health] RHR data failed: {e}")

    try:
        bb = client.get_body_battery(date_str, date_str)
        if bb and isinstance(bb, list) and len(bb) > 0:
            entry = bb[0]
            health["body_battery_am"] = entry.get("charged")
            health["body_battery_pm"] = entry.get("drained")
            health["raw_json"]["body_battery"] = bb
    except Exception as e:
        print(f"[health] Body battery failed: {e}")

    try:
        readiness = client.get_training_readiness(date_str)
        if readiness:
            health["training_readiness"] = readiness.get("score")
            health["raw_json"]["training_readiness"] = readiness
    except Exception as e:
        print(f"[health] Training readiness failed: {e}")

    try:
        stress = client.get_stress_data(date_str)
        if stress:
            health["stress_avg"] = stress.get("overallStressLevel")
            health["raw_json"]["stress"] = stress
    except Exception as e:
        print(f"[health] Stress data failed: {e}")

    try:
        spo2 = client.get_spo2_data(date_str)
        if spo2:
            health["spo2_avg"] = spo2.get("averageSpO2")
            health["raw_json"]["spo2"] = spo2
    except Exception as e:
        print(f"[health] SpO2 data failed: {e}")

    try:
        body = client.get_body_composition(date_str, date_str)
        if body:
            health["weight_kg"] = body.get("weight")
            if health["weight_kg"]:
                health["weight_kg"] = round(health["weight_kg"] / 1000, 1)  # grams to kg
            health["body_fat_pct"] = body.get("bodyFat")
            health["raw_json"]["body_composition"] = body
    except Exception as e:
        print(f"[health] Body composition failed: {e}")

    db.save_daily_health(target_date, profile_id, health)
    print(f"[health] Saved health data for {date_str}")
    return health
```

- [ ] **Step 4: Remove old imports no longer needed**

The `_get_activities_dir()` function (lines 100-104) and the `ACTIVITIES_DIR` import from config are no longer used. Remove:
- `from .config import ACTIVITIES_DIR, PROJECT_ROOT, RUNNING_TYPES` → `from .config import PROJECT_ROOT, RUNNING_TYPES`
- Delete the `_get_activities_dir()` function entirely

- [ ] **Step 5: Run existing tests to verify they still pass**

Run: `source venv/bin/activate && python -m pytest tests/ -v --ignore=tests/test_db.py`
Expected: All existing tests PASS (they mock sync_activities/load_cached_activities)

- [ ] **Step 6: Commit**

```bash
git add tracker/garmin_sync.py
git commit -m "feat: migrate garmin_sync to database storage + add daily health sync"
```

---

## Task 10: Migrate plan_data.py to DB

**Files:**
- Modify: `tracker/plan_data.py`

- [ ] **Step 1: Update load_plan() to read from DB with JSON fallback**

Replace `tracker/plan_data.py` `load_plan()` (lines 10-44) and `get_week()` (lines 47-53):

```python
def load_plan() -> list[WeekPlan]:
    """Load training plan from database, falling back to plan.json."""
    try:
        from tracker import db
        rows = db.get_plan()
        if rows:
            weeks = []
            for r in rows:
                workouts_raw = r.get("workouts") or []
                workouts = [
                    PlannedWorkout(
                        day=wo["day"], date=wo.get("date"), type=wo["type"],
                        description=wo["description"], distance_km=wo.get("distance_km"),
                        vert_m=wo.get("vert_m"), target_pace=wo.get("target_pace"),
                        target_hr=wo.get("target_hr"), series_type=wo.get("series_type"),
                    )
                    for wo in workouts_raw
                ]
                weeks.append(WeekPlan(
                    week_number=r["week_number"], start_date=r.get("start_date", ""),
                    end_date=r.get("end_date", ""), phase=r["phase"],
                    is_recovery=r["is_recovery"], distance_km=r["distance_km"],
                    vert_m=r["vert_m"], long_run_km=r["long_run_km"],
                    gym_sessions=r["gym_sessions"], series_type=r.get("series_type"),
                    workouts=workouts,
                ))
            return weeks
    except Exception:
        pass  # DB not available — fall back to JSON

    # Fallback: load from plan.json (CLI without DATABASE_URL)
    with open(PLAN_FILE) as f:
        data = json.load(f)

    weeks = []
    for w in data["weeks"]:
        workouts = [
            PlannedWorkout(
                day=wo["day"], date=wo.get("date"), type=wo["type"],
                description=wo["description"], distance_km=wo.get("distance_km"),
                vert_m=wo.get("vert_m"), target_pace=wo.get("target_pace"),
                target_hr=wo.get("target_hr"), series_type=wo.get("series_type"),
            )
            for wo in w.get("workouts", [])
        ]
        weeks.append(WeekPlan(
            week_number=w["week_number"], start_date=w["start_date"],
            end_date=w["end_date"], phase=w["phase"],
            is_recovery=w["is_recovery"], distance_km=w["distance_km"],
            vert_m=w["vert_m"], long_run_km=w["long_run_km"],
            gym_sessions=w["gym_sessions"], series_type=w.get("series_type"),
            workouts=workouts,
        ))
    return weeks


def get_week(n: int) -> WeekPlan | None:
    """Get a specific week by number (1-30)."""
    weeks = load_plan()
    for w in weeks:
        if w.week_number == n:
            return w
    return None
```

- [ ] **Step 2: Run existing tests**

Run: `source venv/bin/activate && python -m pytest tests/ -v --ignore=tests/test_db.py`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tracker/plan_data.py
git commit -m "feat: migrate plan_data to read from DB with JSON fallback"
```

---

## Task 11: Migrate conversation.py to DB

**Files:**
- Modify: `api/conversation.py`

- [ ] **Step 1: Rewrite conversation.py to use DB**

Replace the entire file content:

```python
from __future__ import annotations

from tracker import db


def save_message(question: str, category: str, response: str, week: int) -> dict:
    """Save a chat exchange to the database. Returns the saved entry."""
    return db.save_conversation(question, category, response, week)


def load_history(limit: int = 50, before: str | None = None) -> dict:
    """Load conversation history from the database.

    Returns {"messages": [...], "has_more": bool}.
    """
    # Get one extra to detect has_more
    messages = db.get_conversations(limit=limit + 1)
    has_more = len(messages) > limit
    if has_more:
        messages = messages[-limit:]
    return {"messages": messages, "has_more": has_more}


def clear_history():
    """Remove all conversation history."""
    db.clear_conversations()
```

- [ ] **Step 2: Run coach tests**

Run: `source venv/bin/activate && python -m pytest tests/test_routes_coach.py -v`
Expected: All PASS (tests mock conversation functions)

- [ ] **Step 3: Commit**

```bash
git add api/conversation.py
git commit -m "feat: migrate conversation storage to database"
```

---

## Task 12: Migrate Dashboard Serve + Routes to DB

**Files:**
- Modify: `dashboard/serve.py`
- Modify: `api/routes_dashboard.py`

- [ ] **Step 1: Update _update_weeks_cache() in serve.py**

Replace `_update_weeks_cache()` (lines 238-260 in `dashboard/serve.py`):

```python
def _update_weeks_cache(week_num: int, week_data: dict, profile_id: str = DEFAULT_PROFILE):
    """Update the week snapshot in the database."""
    try:
        from tracker import db
        db.upsert_week_snapshot(week_num, profile_id, week_data)
        print(f"[cache] Updated week {week_num} snapshot in database")
    except Exception as e:
        print(f"[cache] Failed to update snapshot: {e}")
```

- [ ] **Step 2: Update _handle_weeks() in serve.py**

Replace `_handle_weeks()` (lines 452-467 in `dashboard/serve.py`):

```python
    def _handle_weeks(self, parsed):
        params = parse_qs(parsed.query)
        profile_id = self._validate_profile(params)
        print(f"[weeks] Loading all weeks for profile '{profile_id}'...")
        results = build_all_weeks_json(do_sync=False, profile_id=profile_id)
        # Fallback to DB snapshots if no activity data was found
        if all(w.get("actual") is None for w in results):
            try:
                from tracker import db
                snapshots = db.get_week_snapshots(profile_id)
                if snapshots:
                    results = [s["data"] for s in snapshots]
                    print(f"[weeks] No live data, using DB snapshots for '{profile_id}'")
            except Exception:
                pass
        last_synced = _get_cache_last_synced(profile_id)
        print(f"[weeks] Loaded {len(results)} weeks")
        self._send_json({
            "weeks": results,
            "last_synced": last_synced,
        })
```

- [ ] **Step 3: Update _get_cache_last_synced() to check DB**

Replace `_get_cache_last_synced()` in `dashboard/serve.py`:

```python
def _get_cache_last_synced(profile_id: str = DEFAULT_PROFILE) -> str | None:
    """Return the last-synced timestamp from the database or cache file mtime."""
    try:
        from tracker import db
        snapshots = db.get_week_snapshots(profile_id)
        if snapshots:
            # Find the most recent updated_at
            latest = max(s["updated_at"] for s in snapshots)
            # Parse ISO and format nicely
            from datetime import datetime as dt
            ts = dt.fromisoformat(latest)
            return ts.strftime("%b %-d, %Y %-I:%M %p")
    except Exception:
        pass
    # Fallback to file mtime
    suffix = f"_{profile_id}" if profile_id != DEFAULT_PROFILE else ""
    cache_path = DASHBOARD_DIR / f"weeks_cache{suffix}.json"
    if cache_path.exists():
        mtime = cache_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%b %-d, %Y %-I:%M %p")
    return None
```

- [ ] **Step 4: Update routes_dashboard.py get_weeks()**

Replace `get_weeks()` in `api/routes_dashboard.py`:

```python
@router.get("/api/weeks")
def get_weeks(profile: str = Query(DEFAULT_PROFILE)):
    profile_id = _validate_profile(profile)
    results = build_all_weeks_json(do_sync=False, profile_id=profile_id)
    # Fallback to DB snapshots if no live data
    if all(w.get("actual") is None for w in results):
        try:
            from tracker import db
            snapshots = db.get_week_snapshots(profile_id)
            if snapshots:
                results = [s["data"] for s in snapshots]
        except Exception:
            pass
    return {"weeks": results, "last_synced": _get_cache_last_synced(profile_id)}
```

- [ ] **Step 5: Run dashboard tests**

Run: `source venv/bin/activate && python -m pytest tests/test_routes_dashboard.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/serve.py api/routes_dashboard.py
git commit -m "feat: migrate dashboard weeks cache to database snapshots"
```

---

## Task 13: Enrich Coach Context with Health + Plan Changes

**Files:**
- Modify: `api/routes_coach.py`

- [ ] **Step 1: Update _build_coaching_data() to include health and plan changes**

Replace the entire `_build_coaching_data_from_cache()` and `_build_coaching_data()` functions (lines 101-200 in `api/routes_coach.py`) with:

```python
def _build_coaching_data() -> Optional[dict]:
    """Build full coaching context: current week analysis + training history + health + plan changes."""
    week_num = get_current_week()
    if week_num is None:
        return None
    plan = get_week(week_num)
    if plan is None:
        return None
    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if not activities:
        # Try DB snapshots as fallback context
        try:
            from tracker import db
            snapshots = db.get_week_snapshots()
            if snapshots:
                data = {"training_history": [], "upcoming_plan": _build_upcoming_plan(week_num)}
                for s in snapshots:
                    w = s["data"]
                    data["training_history"].append({
                        "week": w.get("number"), "phase": w.get("phase"),
                        "is_recovery": w.get("recovery", False),
                        "plan": w.get("plan", {}), "actual": w.get("actual"),
                        "compliance": w.get("compliance"),
                    })
                data["week_number"] = week_num
                data["phase"] = plan.phase
                data["days_to_race"] = days_to_race()
                # Add health data
                _enrich_with_health(data, week_num)
                _enrich_with_plan_changes(data, week_num)
                return data
        except Exception:
            pass
        return None

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)

    data = output.to_dict()
    data["training_history"] = _build_training_history(week_num)
    data["upcoming_plan"] = _build_upcoming_plan(week_num)

    # Load knowledge base for domain context
    knowledge_path = PROJECT_ROOT / "knowledge.json"
    if knowledge_path.exists():
        try:
            data["knowledge"] = json.loads(knowledge_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Enrich with health and plan change data
    _enrich_with_health(data, week_num)
    _enrich_with_plan_changes(data, week_num)

    return data


def _enrich_with_health(data: dict, week_num: int):
    """Add recent daily health data to coaching context."""
    try:
        from tracker import db
        from datetime import timedelta
        end = date.today()
        start = end - timedelta(days=7)
        health = db.get_daily_health(start, end)
        if health:
            data["daily_health"] = health
    except Exception:
        pass


def _enrich_with_plan_changes(data: dict, week_num: int):
    """Add recent plan changes to coaching context."""
    try:
        from tracker import db
        changes = db.get_plan_changes(week_num)
        if changes:
            data["plan_changes"] = changes
    except Exception:
        pass
```

- [ ] **Step 2: Add missing import at top of routes_coach.py**

Add `from datetime import date` to the imports if not already present.

- [ ] **Step 3: Run coach tests**

Run: `source venv/bin/activate && python -m pytest tests/test_routes_coach.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add api/routes_coach.py
git commit -m "feat: enrich coach context with daily health and plan changes"
```

---

## Task 14: Integrate Daily Health into Auto-Sync

**Files:**
- Modify: `dashboard/serve.py`

- [ ] **Step 1: Update _auto_sync() to also sync health data**

In `dashboard/serve.py`, update the `_auto_sync()` function to call `sync_daily_health` after syncing activities:

```python
def _auto_sync():
    """Background thread: sync current week for all profiles on a daily interval."""
    from tracker.garmin_sync import sync_daily_health
    from datetime import date as date_type

    # Initial delay to let the server start up
    time.sleep(10)
    while True:
        current_week = get_current_week()
        if current_week is None:
            print("[auto-sync] Not in training window, skipping")
        else:
            for profile in PROFILES:
                pid = profile["id"]
                print(f"[auto-sync] Syncing week {current_week} for '{pid}'...")
                try:
                    result = build_week_json(current_week, do_sync=True, profile_id=pid)
                    if "error" in result:
                        print(f"[auto-sync] Failed for '{pid}': {result['error']}")
                    else:
                        _update_weeks_cache(current_week, result, pid)
                        print(f"[auto-sync] Week {current_week} [{pid}]: {result.get('compliance', '—')}% compliance, {len(result.get('activities', []))} activities")
                except Exception as e:
                    print(f"[auto-sync] Error for '{pid}': {e}")

                # Sync daily health for today
                try:
                    sync_daily_health(date_type.today(), profile_id=pid)
                except Exception as e:
                    print(f"[auto-sync] Health sync failed for '{pid}': {e}")

        print(f"[auto-sync] Next sync in {AUTO_SYNC_INTERVAL}s")
        time.sleep(AUTO_SYNC_INTERVAL)
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/serve.py
git commit -m "feat: sync daily health data in auto-sync background thread"
```

---

## Task 15: Delete push_data.py + Clean Up

**Files:**
- Delete: `scripts/push_data.py`
- Modify: `api/routes_dashboard.py` (remove `_get_cache_last_synced` import from serve if needed)

- [ ] **Step 1: Delete push_data.py**

```bash
git rm scripts/push_data.py
```

- [ ] **Step 2: Run the full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -v --ignore=tests/test_db.py`
Expected: All existing tests PASS

- [ ] **Step 3: Run DB tests if DATABASE_URL is set**

Run: `source venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: All PASS (or SKIP if DATABASE_URL not set)

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove push_data.py — replaced by database storage"
```

---

## Task 16: Plan Update API Endpoint

**Files:**
- Modify: `api/routes_coach.py`

- [ ] **Step 1: Add POST /api/plan/update endpoint**

Append to `api/routes_coach.py`:

```python
@router.post("/plan/update")
def update_plan(request_body: dict):
    from tracker import db

    week = request_body.get("week")
    field = request_body.get("field")
    new_value = request_body.get("new_value")
    reason = request_body.get("reason", "")

    if not week or not field or new_value is None:
        raise HTTPException(status_code=400, detail="week, field, and new_value are required")

    current = db.get_week_plan(week)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Week {week} not found in plan")

    old_value = str(current.get(field, ""))
    db.update_plan_field(week, "default", field, old_value, str(new_value), reason, "manual")

    return {"status": "ok", "week": week, "field": field, "old_value": old_value, "new_value": str(new_value)}
```

- [ ] **Step 2: Test the endpoint manually**

Run: `curl -X POST http://localhost:8000/api/coach/plan/update -H 'Content-Type: application/json' -d '{"week": 7, "field": "distance_km", "new_value": 38, "reason": "Testing plan update"}'`
Expected: `{"status": "ok", "week": 7, "field": "distance_km", ...}`

- [ ] **Step 3: Verify the change was logged**

Run: `source venv/bin/activate && python -c "
from tracker.garmin_sync import _load_env; _load_env()
from tracker import db; db.init_db()
changes = db.get_plan_changes(7)
for c in changes: print(c)
"`
Expected: Shows the change entry with reason "Testing plan update"

- [ ] **Step 4: Revert the test change**

Run the same curl with the original value to restore it.

- [ ] **Step 5: Commit**

```bash
git add api/routes_coach.py
git commit -m "feat: add POST /api/plan/update endpoint for training plan modifications"
```

---

## Task 17: End-to-End Verification

- [ ] **Step 1: Start the local dev server and verify dashboard loads**

Run: `source venv/bin/activate && python dashboard/serve.py`
Open: http://localhost:8000
Expected: Dashboard loads with all week data, last synced date shows correctly.

- [ ] **Step 2: Test sync button**

Click the sync button on the dashboard.
Expected: Sync succeeds, footer updates with current time, week data refreshes.

- [ ] **Step 3: Test coach chat**

Open the coach chat and ask "How's my training going?"
Expected: Coach responds with context about your current week, compliance, and training history. No "no training logged yet" message.

- [ ] **Step 4: Verify health data is syncing**

Run: `source venv/bin/activate && python -c "
from tracker.garmin_sync import _load_env; _load_env()
from tracker import db; db.init_db()
from datetime import date
health = db.get_daily_health(date(2026, 4, 12), date(2026, 4, 12))
print(health)
"`
Expected: Shows today's health data (sleep, HRV, etc.)

- [ ] **Step 5: Verify plan is queryable**

Run: `source venv/bin/activate && python -c "
from tracker.garmin_sync import _load_env; _load_env()
from tracker import db; db.init_db()
plan = db.get_plan()
print(f'{len(plan)} weeks in plan')
print(f'Week 6: {plan[5][\"distance_km\"]}km, {plan[5][\"phase\"]} phase')
"`
Expected: Shows 30 weeks, correct data for week 6.

- [ ] **Step 6: Final commit if any tweaks were needed**

```bash
git add -A
git commit -m "fix: end-to-end verification fixes"
```
