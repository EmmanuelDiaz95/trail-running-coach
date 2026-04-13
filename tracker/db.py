from __future__ import annotations

import json
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
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def save_activities(activities: list[dict], week_number: int, profile_id: str = "default") -> int:
    """Insert activities. Returns count of newly inserted rows (skips duplicates via ON CONFLICT garmin_id)."""
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


# ---------------------------------------------------------------------------
# Daily Health
# ---------------------------------------------------------------------------

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
                health_date, profile_id,
                data.get("sleep_hours"), data.get("sleep_score"),
                data.get("deep_sleep_min"), data.get("rem_sleep_min"),
                data.get("light_sleep_min"), data.get("hrv_weekly_avg"),
                data.get("hrv_last_night"), data.get("resting_hr"),
                data.get("body_battery_am"), data.get("body_battery_pm"),
                data.get("training_readiness"), data.get("stress_avg"),
                data.get("spo2_avg"), data.get("weight_kg"),
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


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Week Snapshots
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Training Plan
# ---------------------------------------------------------------------------

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
            cur.execute(
                f"UPDATE training_plan SET {field} = %s, updated_at = NOW() "
                f"WHERE week_number = %s AND profile_id = %s",
                (new_value, week_number, profile_id),
            )
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
