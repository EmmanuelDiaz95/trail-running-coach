from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from dashboard.serve import (
    build_all_weeks_json,
    build_week_json,
    _update_weeks_cache,
    _get_cache_last_synced,
    _load_profiles,
    DASHBOARD_DIR,
    SYNC_COOLDOWN_SECONDS,
)
from tracker.garmin_sync import DEFAULT_PROFILE

router = APIRouter()

API_KEY = os.environ.get("API_KEY", "")
PROFILES = _load_profiles()
_last_sync_time: dict[str, float] = {}


def _check_auth(authorization: Optional[str]) -> None:
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
    # Merge with static cache: fill in weeks missing actual data
    suffix = f"_{profile_id}" if profile_id != DEFAULT_PROFILE else ""
    cache_path = DASHBOARD_DIR / f"weeks_cache{suffix}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        cached_by_num = {w["number"]: w for w in cached}
        for i, w in enumerate(results):
            if w.get("actual") is None and w["number"] in cached_by_num:
                results[i] = cached_by_num[w["number"]]
    return {"weeks": results, "last_synced": _get_cache_last_synced(profile_id)}


@router.post("/api/sync")
def sync_week(
    week: Optional[int] = Query(None),
    profile: str = Query(DEFAULT_PROFILE),
    authorization: Optional[str] = Header(None),
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
    result["synced_at"] = datetime.now().strftime("%b %-d, %Y %-I:%M %p")
    return result


@router.post("/api/push-workout")
def push_workout_route(
    week: int = Query(...),
    profile: str = Query(DEFAULT_PROFILE),
    authorization: Optional[str] = Header(None),
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
