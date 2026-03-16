#!/usr/bin/env python3
"""Sync Garmin data locally, build sanitized cache, and push to Railway."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.plan_data import get_current_week, get_week_dates
from tracker.garmin_sync import sync_activities
from dashboard.serve import build_all_weeks_json

LOCATION_WORDS = {
    "Calimaya", "Metepec", "Cuajimalpa", "Toluca", "Morelos",
    "Zapopan", "Urique", "de", "la", "el", "los", "las",
}
CACHE_PATH = PROJECT_ROOT / "dashboard" / "weeks_cache.json"


def sync_weeks():
    current = get_current_week()
    if current is None:
        print("Not in training window yet.")
        return
    print(f"Current week: {current}")
    for w in range(1, current + 1):
        start, end = get_week_dates(w)
        print(f"  Week {w} ({start} → {end}): ", end="", flush=True)
        try:
            acts = sync_activities(start, end)
            print(f"{len(acts)} activities")
        except Exception as e:
            print(f"error: {e}")


def build_cache():
    weeks = build_all_weeks_json(do_sync=False)
    for w in weeks:
        for a in w.get("activities") or []:
            parts = a["name"].split()
            clean = [p for p in parts if p not in LOCATION_WORDS]
            a["name"] = " ".join(clean) if clean else a["name"]
    CACHE_PATH.write_text(json.dumps(weeks, indent=2))
    with_data = sum(1 for w in weeks if w.get("actual"))
    print(f"Cache built: {with_data} weeks with data → {CACHE_PATH.name}")


def git_push():
    subprocess.run(["git", "add", str(CACHE_PATH)], cwd=PROJECT_ROOT, check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=PROJECT_ROOT,
    )
    if result.returncode == 0:
        print("No changes to push.")
        return
    subprocess.run(
        ["git", "commit", "-m", "Update weeks cache with latest Garmin data"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=PROJECT_ROOT, check=True)
    print("Pushed to Railway!")


if __name__ == "__main__":
    print("=== 1. Syncing from Garmin ===")
    sync_weeks()
    print()
    print("=== 2. Building sanitized cache ===")
    build_cache()
    print()
    print("=== 3. Pushing to Railway ===")
    git_push()
