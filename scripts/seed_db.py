#!/usr/bin/env python3
"""One-time migration: load existing JSON data into Postgres.

Idempotent — safe to re-run. Uses ON CONFLICT / upsert semantics
so duplicate rows are silently skipped or updated.

Usage:
    source venv/bin/activate
    python scripts/seed_db.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.config import ACTIVITIES_DIR, PLAN_FILE, PLAN_START, TOTAL_WEEKS
from tracker.garmin_sync import _load_env, _normalize_activity, DEFAULT_PROFILE
from tracker import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_number_for_date(activity_date: date) -> int | None:
    """Return week number (1-30) for an activity date, or None if outside plan."""
    if activity_date < PLAN_START:
        return None
    delta = (activity_date - PLAN_START).days
    week_num = delta // 7 + 1
    if week_num > TOTAL_WEEKS:
        return None
    return week_num


def _format_pace(avg_pace_min_km: float | None) -> str | None:
    """Convert float pace (e.g. 7.52) to mm:ss string (e.g. '7:31')."""
    if avg_pace_min_km is None:
        return None
    minutes = int(avg_pace_min_km)
    seconds = int((avg_pace_min_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_plan():
    """Load plan.json and upsert every week into the training_plan table."""
    with open(PLAN_FILE) as f:
        data = json.load(f)

    weeks = data["weeks"]
    for w in weeks:
        db.upsert_plan_week(w, profile_id=DEFAULT_PROFILE)

    print(f"[seed] Training plan: {len(weeks)} weeks inserted")


def seed_activities():
    """Read all cached activity JSON files, normalize, and save to DB."""
    if not ACTIVITIES_DIR.exists():
        print("[seed] Activities: no data/activities/ directory — skipped")
        return

    files = sorted(ACTIVITIES_DIR.glob("*.json"))
    total_inserted = 0
    total_skipped = 0

    for fpath in files:
        if fpath.name == ".gitkeep":
            continue

        with open(fpath) as f:
            raw_list = json.load(f)

        # Group activities by week number
        by_week: dict[int, list[dict]] = {}
        for raw in raw_list:
            activity = _normalize_activity(raw)
            activity_date = date.fromisoformat(activity.date) if activity.date else None

            if activity_date is None:
                total_skipped += 1
                continue

            week_num = _week_number_for_date(activity_date)
            if week_num is None:
                total_skipped += 1
                continue

            row = {
                "garmin_id": activity.activity_id,
                "activity_date": activity.date,
                "activity_type": activity.activity_type,
                "activity_name": activity.name,
                "distance_km": activity.distance_km,
                "elevation_m": activity.elevation_gain_m,
                "duration_min": round(activity.duration_seconds / 60, 1) if activity.duration_seconds else None,
                "avg_hr": activity.avg_hr,
                "avg_pace": _format_pace(activity.avg_pace_min_km),
                "calories": activity.calories,
                "sets": None,
                "reps": None,
                "route_svg": activity.route_svg,
                "raw_json": raw,
            }
            by_week.setdefault(week_num, []).append(row)

        for week_num, rows in by_week.items():
            inserted = db.save_activities(rows, week_num, profile_id=DEFAULT_PROFILE)
            total_inserted += inserted

    print(f"[seed] Activities: {total_inserted} inserted, {total_skipped} skipped (outside plan window)")


def seed_conversations():
    """Read all cached conversation JSON files and save to DB."""
    conv_dir = PROJECT_ROOT / "data" / "conversations"
    if not conv_dir.exists():
        print("[seed] Conversations: no data/conversations/ directory — skipped")
        return

    files = sorted(conv_dir.glob("*.json"))
    total = 0

    for fpath in files:
        if fpath.name == ".gitkeep":
            continue

        with open(fpath) as f:
            messages = json.load(f)

        for msg in messages:
            db.save_conversation(
                question=msg["question"],
                category=msg.get("category", "general"),
                response=msg["response"],
                week_number=msg.get("week", 0),
            )
            total += 1

    print(f"[seed] Conversations: {total} messages inserted")


def seed_week_snapshots():
    """Rebuild week snapshots from cached data and save to DB."""
    from dashboard.serve import build_week_json

    from tracker.plan_data import get_current_week, load_plan

    plan_weeks = load_plan()
    current = get_current_week()
    count = 0

    for wp in plan_weeks:
        wn = wp.week_number
        # Only build snapshots for weeks up to and including the current week
        if current is not None and wn <= current:
            snapshot = build_week_json(wn, do_sync=False, profile_id=DEFAULT_PROFILE)
            if "error" not in snapshot:
                db.upsert_week_snapshot(wn, DEFAULT_PROFILE, snapshot)
                count += 1

    print(f"[seed] Week snapshots: {count} weeks saved")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _load_env()
    db.init_db()
    print("[seed] Database initialized\n")

    seed_plan()
    seed_activities()
    seed_conversations()
    seed_week_snapshots()

    print("\n[seed] Done!")
    db.close_pool()
