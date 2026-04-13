from __future__ import annotations

import os
import sys
from datetime import date

import pytest

# Load .env before importing db so DATABASE_URL is available
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tracker.garmin_sync import _load_env

_load_env()

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB tests",
)

from tracker import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_test_activities(conn):
    """Remove activities inserted by tests (garmin_id 99901, 99902)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM activities WHERE garmin_id IN (99901, 99902)")
    conn.commit()


def _cleanup_test_health(conn):
    """Remove daily_health rows inserted by tests."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM daily_health WHERE date = %s AND profile_id = %s",
                     (date(2026, 4, 10), "test"))
    conn.commit()


def _cleanup_test_conversations(conn):
    """Remove conversation rows inserted by tests."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE question LIKE 'TEST:%%'")
    conn.commit()


def _cleanup_test_snapshots(conn):
    """Remove week_snapshots inserted by tests."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM week_snapshots WHERE week_number = 99 AND profile_id = 'test'")
    conn.commit()


def _cleanup_test_plan(conn):
    """Remove training_plan and plan_changes inserted by tests."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM plan_changes WHERE week_number = 99 AND profile_id = 'test'")
        cur.execute("DELETE FROM training_plan WHERE week_number = 99 AND profile_id = 'test'")
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_init_db_creates_tables():
    """init_db should create all 6 tables."""
    try:
        db.init_db()
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                          'activities', 'daily_health', 'conversations',
                          'week_snapshots', 'training_plan', 'plan_changes'
                      )
                    ORDER BY table_name
                """)
                tables = [row[0] for row in cur.fetchall()]
        expected = sorted([
            "activities", "daily_health", "conversations",
            "week_snapshots", "training_plan", "plan_changes",
        ])
        assert tables == expected, f"Missing tables: {set(expected) - set(tables)}"
    finally:
        db.close_pool()


def test_save_and_get_activities():
    """save_activities inserts rows; re-save deduplicates on garmin_id."""
    try:
        db.init_db()
        # Cleanup before test
        with db.get_conn() as conn:
            _cleanup_test_activities(conn)

        activities = [
            {
                "garmin_id": 99901,
                "activity_date": "2026-04-06",
                "activity_type": "running",
                "activity_name": "Test Easy Run",
                "distance_km": 8.0,
                "elevation_m": 120,
                "duration_min": 50.0,
                "avg_hr": 138,
                "avg_pace": "6:15",
                "calories": 400,
            },
            {
                "garmin_id": 99902,
                "activity_date": "2026-04-07",
                "activity_type": "strength_training",
                "activity_name": "Test Gym Session",
                "sets": 4,
                "reps": 12,
                "duration_min": 45.0,
                "calories": 250,
            },
        ]

        inserted = db.save_activities(activities, week_number=6, profile_id="default")
        assert inserted == 2

        rows = db.get_activities(week_number=6, profile_id="default")
        garmin_ids = [r["garmin_id"] for r in rows]
        assert 99901 in garmin_ids
        assert 99902 in garmin_ids

        # Re-save should insert 0 (dedup)
        inserted2 = db.save_activities(activities, week_number=6, profile_id="default")
        assert inserted2 == 0

        # Cleanup after test
        with db.get_conn() as conn:
            _cleanup_test_activities(conn)
    finally:
        db.close_pool()


def test_save_and_get_daily_health():
    """save_daily_health upserts; second call updates existing row."""
    try:
        db.init_db()
        with db.get_conn() as conn:
            _cleanup_test_health(conn)

        health_date = date(2026, 4, 10)
        data1 = {
            "sleep_hours": 7.5,
            "sleep_score": 82,
            "resting_hr": 52,
            "hrv_weekly_avg": 48.0,
            "body_battery_am": 85,
        }
        db.save_daily_health(health_date, profile_id="test", data=data1)

        rows = db.get_daily_health(health_date, health_date, profile_id="test")
        assert len(rows) == 1
        assert rows[0]["sleep_score"] == 82

        # Upsert with changed sleep_score
        data2 = {**data1, "sleep_score": 90}
        db.save_daily_health(health_date, profile_id="test", data=data2)

        rows = db.get_daily_health(health_date, health_date, profile_id="test")
        assert len(rows) == 1
        assert rows[0]["sleep_score"] == 90

        with db.get_conn() as conn:
            _cleanup_test_health(conn)
    finally:
        db.close_pool()


def test_conversations():
    """save_conversation, get_conversations, clear_conversations round-trip."""
    try:
        db.init_db()
        # Cleanup before
        with db.get_conn() as conn:
            _cleanup_test_conversations(conn)

        entry1 = db.save_conversation(
            question="TEST: How should I pace my long run?",
            category="pacing",
            response="Start conservative at 6:30/km.",
            week_number=5,
        )
        assert "id" in entry1
        assert entry1["category"] == "pacing"

        entry2 = db.save_conversation(
            question="TEST: What about nutrition?",
            category="nutrition",
            response="Take a gel every 45 min.",
            week_number=5,
        )

        convos = db.get_conversations(limit=50)
        test_convos = [c for c in convos if c["question"].startswith("TEST:")]
        assert len(test_convos) == 2

        # Clear and verify
        db.clear_conversations()
        convos_after = db.get_conversations(limit=50)
        test_after = [c for c in convos_after if c["question"].startswith("TEST:")]
        assert len(test_after) == 0
    finally:
        db.close_pool()


def test_week_snapshots():
    """upsert_week_snapshot inserts then updates; only 1 row per (week, profile)."""
    try:
        db.init_db()
        with db.get_conn() as conn:
            _cleanup_test_snapshots(conn)

        data1 = {"compliance": 0.85, "distance_km": 25.0}
        db.upsert_week_snapshot(week_number=99, profile_id="test", data=data1)

        snapshots = db.get_week_snapshots(profile_id="test")
        week99 = [s for s in snapshots if s["week_number"] == 99]
        assert len(week99) == 1
        assert week99[0]["data"]["compliance"] == 0.85

        # Upsert with changed compliance
        data2 = {"compliance": 0.92, "distance_km": 27.0}
        db.upsert_week_snapshot(week_number=99, profile_id="test", data=data2)

        snapshots = db.get_week_snapshots(profile_id="test")
        week99 = [s for s in snapshots if s["week_number"] == 99]
        assert len(week99) == 1
        assert week99[0]["data"]["compliance"] == 0.92

        with db.get_conn() as conn:
            _cleanup_test_snapshots(conn)
    finally:
        db.close_pool()


def test_training_plan():
    """upsert_plan_week, get_week_plan, update_plan_field, get_plan_changes round-trip."""
    try:
        db.init_db()
        with db.get_conn() as conn:
            _cleanup_test_plan(conn)

        week_data = {
            "week_number": 99,
            "phase": "base",
            "is_recovery": False,
            "distance_km": 30.0,
            "vert_m": 500,
            "long_run_km": 15.0,
            "gym_sessions": 3,
            "series_type": "tempo",
            "start_date": "2026-12-01",
            "end_date": "2026-12-07",
        }
        db.upsert_plan_week(week_data, profile_id="test")

        plan_row = db.get_week_plan(week_number=99, profile_id="test")
        assert plan_row is not None
        assert plan_row["phase"] == "base"
        assert plan_row["distance_km"] == 30.0

        # Update distance_km and verify
        db.update_plan_field(
            week_number=99,
            profile_id="test",
            field="distance_km",
            old_value="30.0",
            new_value="35.0",
            reason="Athlete recovering well, increase volume",
            source="coach",
        )

        updated = db.get_week_plan(week_number=99, profile_id="test")
        assert updated["distance_km"] == 35.0

        changes = db.get_plan_changes(week_number=99, profile_id="test")
        assert len(changes) >= 1
        assert changes[0]["field"] == "distance_km"
        assert changes[0]["old_value"] == "30.0"
        assert changes[0]["new_value"] == "35.0"
        assert changes[0]["source"] == "coach"

        with db.get_conn() as conn:
            _cleanup_test_plan(conn)
    finally:
        db.close_pool()
