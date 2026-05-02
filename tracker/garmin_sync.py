from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

from .config import PROJECT_ROOT, RUNNING_TYPES
from .models import GarminActivity
from .route import polyline_to_svg

# Default profile ID
DEFAULT_PROFILE = "default"

# In-memory client cache to avoid re-running OAuth on every request.
# OAuth2 tokens have ~1h TTL; cache expires slightly under that.
_CLIENT_TTL_SECONDS = 50 * 60
_client_cache: dict[str, tuple[Garmin, float]] = {}
_cache_lock = threading.Lock()

# Circuit breaker: when Garmin returns 429 on the OAuth exchange endpoint,
# Garmin keeps the cooldown active longer the more we hit it. Stop hitting it.
# Backoff schedule (per consecutive failure): 15m, 30m, 1h, 2h, 4h, 8h, 12h cap.
_RATE_LIMIT_BASE_SECONDS = 15 * 60
_RATE_LIMIT_MAX_SECONDS = 12 * 3600
_rate_limit_until: dict[str, float] = {}  # profile_id -> epoch seconds


def _backoff_seconds(failures: int) -> int:
    """Exponential backoff: 15m * 2^(failures-1), capped at 12h."""
    if failures < 1:
        failures = 1
    return min(_RATE_LIMIT_BASE_SECONDS * (2 ** (failures - 1)), _RATE_LIMIT_MAX_SECONDS)


class GarminRateLimited(RuntimeError):
    """Raised when Garmin auth is in cooldown after a 429 from /oauth-service/oauth/exchange."""

    def __init__(self, until_epoch: float, original: Exception | None = None):
        self.until_epoch = until_epoch
        self.retry_after = max(0, int(until_epoch - time.time()))
        msg = f"Garmin rate-limited, retry in {self.retry_after}s"
        if original is not None:
            msg = f"{msg}: {original}"
        super().__init__(msg)


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


def _load_tokens_from_db(profile_id: str) -> tuple[str | None, str | None]:
    """Read OAuth tokens from Postgres. Returns (None, None) if DB unavailable or no row."""
    try:
        from tracker import db
        tokens = db.get_garmin_tokens(profile_id)
        if tokens:
            return tokens["oauth1"], tokens["oauth2"]
    except Exception as e:
        print(f"[garmin] Warning: failed to load tokens from DB: {e}")
    return None, None


def _load_tokens_from_env(profile_id: str) -> tuple[str | None, str | None]:
    """Read OAuth tokens from base64-encoded env vars."""
    import base64
    oauth1_b64 = _profile_env("GARMIN_OAUTH1", profile_id)
    oauth2_b64 = _profile_env("GARMIN_OAUTH2", profile_id)
    if not oauth1_b64 or not oauth2_b64:
        return None, None
    try:
        return base64.b64decode(oauth1_b64).decode(), base64.b64decode(oauth2_b64).decode()
    except Exception as e:
        print(f"[garmin] Warning: failed to decode env tokens: {e}")
        return None, None


def _seed_tokens(token_dir: Path, profile_id: str = DEFAULT_PROFILE):
    """Seed OAuth tokens to disk for garth to load. Priority: DB > env vars."""
    oauth1, oauth2 = _load_tokens_from_db(profile_id)
    source = "db"
    if not oauth1 or not oauth2:
        oauth1, oauth2 = _load_tokens_from_env(profile_id)
        source = "env"
    if not oauth1 or not oauth2:
        return

    oauth1_path = token_dir / "oauth1_token.json"
    oauth2_path = token_dir / "oauth2_token.json"
    if (oauth1_path.exists() and oauth1_path.read_text() == oauth1
            and oauth2_path.exists() and oauth2_path.read_text() == oauth2):
        return  # disk already current
    token_dir.mkdir(parents=True, exist_ok=True)
    oauth1_path.write_text(oauth1)
    oauth2_path.write_text(oauth2)
    print(f"[garmin] Seeded tokens from {source} (profile: {profile_id})")


def _persist_tokens_to_db(token_dir: Path, profile_id: str):
    """Save current disk tokens to Postgres so future cold starts skip OAuth exchange."""
    try:
        from tracker import db
        oauth1_path = token_dir / "oauth1_token.json"
        oauth2_path = token_dir / "oauth2_token.json"
        if not (oauth1_path.exists() and oauth2_path.exists()):
            return
        db.save_garmin_tokens(profile_id, oauth1_path.read_text(), oauth2_path.read_text())
    except Exception as e:
        print(f"[garmin] Warning: failed to persist tokens to DB: {e}")


def _get_token_dir(profile_id: str = DEFAULT_PROFILE) -> Path:
    """Get token directory for a profile."""
    base = Path(os.environ.get("GARMIN_TOKEN_DIR", Path.home() / ".garminconnect"))
    if profile_id and profile_id != DEFAULT_PROFILE:
        return base.parent / f"{base.name}_{profile_id}"
    return base


def _check_rate_limit(profile_id: str) -> None:
    """Raise GarminRateLimited if profile is in cooldown. Caller must hold _cache_lock.

    Uses the later of in-memory and DB cooldowns so that a longer cooldown set by
    another worker (or by an out-of-band escalation) cannot be undercut by stale
    in-memory state.
    """
    now = time.time()
    mem_until = _rate_limit_until.get(profile_id, 0.0)

    db_until_epoch = 0.0
    try:
        from tracker import db
        db_until = db.get_garmin_rate_limit_until(profile_id)
        if db_until is not None:
            db_until_epoch = db_until.timestamp()
    except Exception as e:
        print(f"[garmin] Warning: failed to read rate-limit from DB: {e}")

    effective_until = max(mem_until, db_until_epoch)
    if effective_until > mem_until:
        _rate_limit_until[profile_id] = effective_until
    if now < effective_until:
        raise GarminRateLimited(effective_until)


def _record_rate_limit(profile_id: str, original: Exception) -> GarminRateLimited:
    """Set in-memory + DB cooldown with exponential backoff. Returns the exception to raise."""
    failures = 1
    try:
        from tracker import db
        state = db.get_garmin_rate_limit_state(profile_id)
        failures = (state["failures"] or 0) + 1
    except Exception as e:
        print(f"[garmin] Warning: failed to read rate-limit state from DB: {e}")

    backoff = _backoff_seconds(failures)
    until_epoch = time.time() + backoff
    _rate_limit_until[profile_id] = until_epoch
    print(f"[garmin] Recorded 429 (failure #{failures}), cooldown {backoff}s ({backoff // 60}m)")

    try:
        from tracker import db
        until_dt = datetime.fromtimestamp(until_epoch, tz=timezone.utc)
        db.set_garmin_rate_limit(profile_id, until_dt, failures)
    except Exception as e:
        print(f"[garmin] Warning: failed to persist rate-limit to DB: {e}")
    return GarminRateLimited(until_epoch, original)


def _clear_rate_limit(profile_id: str) -> None:
    """Reset cooldown + failure count after a successful auth."""
    _rate_limit_until.pop(profile_id, None)
    try:
        from tracker import db
        db.clear_garmin_rate_limit(profile_id)
    except Exception as e:
        print(f"[garmin] Warning: failed to clear rate-limit in DB: {e}")


def _is_rate_limit_error(e: Exception) -> bool:
    s = str(e)
    return "429" in s or "Too Many" in s


def _get_client(profile_id: str = DEFAULT_PROFILE) -> Garmin:
    """Authenticate with Garmin Connect for a specific profile.

    Reuses an in-memory client across calls within the same process to avoid
    repeatedly hitting Garmin's OAuth exchange endpoint (which rate-limits aggressively).
    """
    with _cache_lock:
        cached = _client_cache.get(profile_id)
        if cached and (time.time() - cached[1]) < _CLIENT_TTL_SECONDS:
            return cached[0]
        _check_rate_limit(profile_id)
        client = _build_client(profile_id)
        _client_cache[profile_id] = (client, time.time())
        return client


def _build_client(profile_id: str) -> Garmin:
    """Authenticate with Garmin. Caller must hold _cache_lock."""
    _load_env()
    token_dir = _get_token_dir(profile_id)
    token_dir.mkdir(parents=True, exist_ok=True)
    _seed_tokens(token_dir, profile_id)

    if (token_dir / "oauth1_token.json").exists():
        try:
            client = Garmin()
            client.login(str(token_dir))
            client.garth.dump(str(token_dir))
            _persist_tokens_to_db(token_dir, profile_id)
            _clear_rate_limit(profile_id)
            return client
        except Exception as e:
            if _is_rate_limit_error(e):
                raise _record_rate_limit(profile_id, e)
            # tokens expired, fall through to password auth

    email = _profile_env("GARMIN_EMAIL", profile_id)
    password = _profile_env("GARMIN_PASSWORD", profile_id)
    if not email or not password:
        if not sys.stdin.isatty():
            raise RuntimeError(f"Garmin credentials required for profile '{profile_id}' in headless mode")
        email = email or input(f"Garmin email ({profile_id}): ")
        password = password or getpass(f"Garmin password ({profile_id}): ")
    try:
        client = Garmin(email, password)
        client.login()
    except Exception as e:
        if _is_rate_limit_error(e):
            raise _record_rate_limit(profile_id, e)
        raise
    client.garth.dump(str(token_dir))
    _persist_tokens_to_db(token_dir, profile_id)
    _clear_rate_limit(profile_id)
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
    """Pull activities from Garmin Connect for a date range and save to database."""
    from tracker.plan_data import PLAN_START, TOTAL_WEEKS
    from tracker import db

    client = _get_client(profile_id)
    raw_activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())

    # Fetch route SVG for running activities
    for raw in raw_activities:
        activity_type = (raw.get("activityType", {}).get("typeKey", "") or "").lower()
        if activity_type in RUNNING_TYPES and raw.get("hasPolyline"):
            activity_id = str(raw.get("activityId", ""))
            raw["route_svg"] = _fetch_route_svg(client, activity_id)
            time.sleep(0.5)
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
            week_num = 0
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


def load_cached_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity] | None:
    """Load activities from database for a date range."""
    from tracker.plan_data import PLAN_START, TOTAL_WEEKS
    from tracker import db

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
            health["hrv_last_night"] = summary.get("lastNightAvg")
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
            # API returns a list — grab the first entry
            entry = readiness[0] if isinstance(readiness, list) else readiness
            health["training_readiness"] = entry.get("score")
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
                health["weight_kg"] = round(health["weight_kg"] / 1000, 1)
            health["body_fat_pct"] = body.get("bodyFat")
            health["raw_json"]["body_composition"] = body
    except Exception as e:
        print(f"[health] Body composition failed: {e}")

    db.save_daily_health(target_date, profile_id, health)
    print(f"[health] Saved health data for {date_str}")
    return health
