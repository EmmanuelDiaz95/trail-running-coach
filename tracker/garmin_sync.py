from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

from .config import ACTIVITIES_DIR, PROJECT_ROOT
from .models import GarminActivity


def _load_env():
    """Load credentials from .env file if it exists."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _get_client() -> Garmin:
    """Authenticate with Garmin Connect. Uses saved tokens, then .env, then prompt."""
    _load_env()
    token_dir = Path(os.environ.get("GARMIN_TOKEN_DIR", Path.home() / ".garminconnect"))
    token_dir.mkdir(exist_ok=True)

    if (token_dir / "oauth1_token.json").exists():
        try:
            client = Garmin()
            client.login(str(token_dir))
            return client
        except Exception:
            pass  # tokens expired, fall through to password auth

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        if not sys.stdin.isatty():
            raise RuntimeError("GARMIN_EMAIL and GARMIN_PASSWORD env vars required in headless mode")
        email = email or input("Garmin email: ")
        password = password or getpass("Garmin password: ")
    client = Garmin(email, password)
    client.login()
    client.garth.dump(str(token_dir))
    return client


def _normalize_activity(raw: dict) -> GarminActivity:
    """Convert raw Garmin API activity dict to GarminActivity."""
    # Distance: meters → km
    distance_m = raw.get("distance") or 0
    distance_km = round(distance_m / 1000, 2)

    # Duration in seconds
    duration = raw.get("duration") or raw.get("movingDuration") or 0

    # Pace: if distance > 0 and it's a run, compute min/km
    avg_pace = None
    if distance_km > 0 and duration > 0:
        pace_seconds_per_km = duration / distance_km
        avg_pace = round(pace_seconds_per_km / 60, 2)

    # Activity type normalization
    activity_type = (raw.get("activityType", {}).get("typeKey", "") or "").lower()

    # Start date
    start_local = raw.get("startTimeLocal", "")
    activity_date = start_local[:10] if start_local else ""

    return GarminActivity(
        activity_id=str(raw.get("activityId", "")),
        date=activity_date,
        activity_type=activity_type,
        name=raw.get("activityName", ""),
        distance_km=distance_km,
        duration_seconds=round(duration, 1),
        avg_hr=raw.get("averageHR"),
        max_hr=raw.get("maxHR"),
        avg_pace_min_km=avg_pace,
        elevation_gain_m=raw.get("elevationGain"),
        calories=raw.get("calories"),
    )


def sync_activities(start_date: date, end_date: date) -> list[GarminActivity]:
    """Pull activities from Garmin Connect for a date range and cache them."""
    client = _get_client()

    raw_activities = client.get_activities_by_date(
        start_date.isoformat(),
        end_date.isoformat(),
    )

    activities = [_normalize_activity(a) for a in raw_activities]

    # Cache raw JSON
    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = ACTIVITIES_DIR / f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    with open(cache_file, "w") as f:
        json.dump(raw_activities, f, indent=2, default=str)

    return activities


def load_cached_activities(start_date: date, end_date: date) -> list[GarminActivity] | None:
    """Load activities from cache if available."""
    cache_file = ACTIVITIES_DIR / f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    if not cache_file.exists():
        return None

    with open(cache_file) as f:
        raw_activities = json.load(f)

    return [_normalize_activity(a) for a in raw_activities]
