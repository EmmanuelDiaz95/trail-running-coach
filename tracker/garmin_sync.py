from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

from .config import ACTIVITIES_DIR, PROJECT_ROOT, RUNNING_TYPES
from .models import GarminActivity
from .route import polyline_to_svg

# Default profile ID
DEFAULT_PROFILE = "default"


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


def _profile_env(key: str, profile_id: str) -> str | None:
    """Get env var for a profile. Tries PROFILE_{ID}_{KEY} first, then {KEY} for default."""
    if profile_id and profile_id != DEFAULT_PROFILE:
        val = os.environ.get(f"PROFILE_{profile_id.upper()}_{key}")
        if val:
            return val
    return os.environ.get(key)


def _seed_tokens_from_env(token_dir: Path, profile_id: str = DEFAULT_PROFILE):
    """Write OAuth tokens from env vars to disk (for Railway/cloud deploys)."""
    import base64
    oauth1_b64 = _profile_env("GARMIN_OAUTH1", profile_id)
    oauth2_b64 = _profile_env("GARMIN_OAUTH2", profile_id)
    if not oauth1_b64 or not oauth2_b64:
        return
    oauth1_path = token_dir / "oauth1_token.json"
    oauth2_path = token_dir / "oauth2_token.json"
    if oauth1_path.exists() and oauth2_path.exists():
        return  # already seeded
    token_dir.mkdir(parents=True, exist_ok=True)
    oauth1_path.write_text(base64.b64decode(oauth1_b64).decode())
    oauth2_path.write_text(base64.b64decode(oauth2_b64).decode())
    print(f"[garmin] Seeded tokens from environment (profile: {profile_id})")


def _get_token_dir(profile_id: str = DEFAULT_PROFILE) -> Path:
    """Get token directory for a profile."""
    base = Path(os.environ.get("GARMIN_TOKEN_DIR", Path.home() / ".garminconnect"))
    if profile_id and profile_id != DEFAULT_PROFILE:
        return base.parent / f"{base.name}_{profile_id}"
    return base


def _get_client(profile_id: str = DEFAULT_PROFILE) -> Garmin:
    """Authenticate with Garmin Connect for a specific profile."""
    _load_env()
    token_dir = _get_token_dir(profile_id)
    token_dir.mkdir(parents=True, exist_ok=True)

    # Seed tokens from env vars if available (Railway deploy)
    _seed_tokens_from_env(token_dir, profile_id)

    if (token_dir / "oauth1_token.json").exists():
        try:
            client = Garmin()
            client.login(str(token_dir))
            # Save refreshed tokens back
            client.garth.dump(str(token_dir))
            return client
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                raise RuntimeError(f"Garmin rate-limited, retry later: {e}")
            pass  # tokens expired, fall through to password auth

    email = _profile_env("GARMIN_EMAIL", profile_id)
    password = _profile_env("GARMIN_PASSWORD", profile_id)
    if not email or not password:
        if not sys.stdin.isatty():
            raise RuntimeError(f"Garmin credentials required for profile '{profile_id}' in headless mode")
        email = email or input(f"Garmin email ({profile_id}): ")
        password = password or getpass(f"Garmin password ({profile_id}): ")
    client = Garmin(email, password)
    client.login()
    client.garth.dump(str(token_dir))
    return client


def _get_activities_dir(profile_id: str = DEFAULT_PROFILE) -> Path:
    """Get activities cache directory for a profile."""
    if profile_id and profile_id != DEFAULT_PROFILE:
        return ACTIVITIES_DIR.parent / f"activities_{profile_id}"
    return ACTIVITIES_DIR


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
        route_svg=raw.get("route_svg"),
    )


def _fetch_route_svg(client: Garmin, activity_id: str) -> str | None:
    """Fetch GPS polyline from Garmin and convert to SVG path."""
    try:
        details = client.get_activity_details(activity_id, maxpoly=500)
        poly_dto = details.get("geoPolylineDTO") or {}
        raw_points = poly_dto.get("polyline", [])
        points = [(p["lat"], p["lon"]) for p in raw_points if "lat" in p and "lon" in p]
        return polyline_to_svg(points)
    except Exception as e:
        print(f"[garmin] Warning: failed to fetch route for {activity_id}: {e}")
        return None


def sync_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity]:
    """Pull activities from Garmin Connect for a date range and cache them."""
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

    # Cache raw JSON
    act_dir = _get_activities_dir(profile_id)
    act_dir.mkdir(parents=True, exist_ok=True)
    cache_file = act_dir / f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    with open(cache_file, "w") as f:
        json.dump(raw_activities, f, indent=2, default=str)

    return activities


def load_cached_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity] | None:
    """Load activities from cache if available."""
    act_dir = _get_activities_dir(profile_id)
    cache_file = act_dir / f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    if not cache_file.exists():
        return None

    with open(cache_file) as f:
        raw_activities = json.load(f)

    return [_normalize_activity(a) for a in raw_activities]
