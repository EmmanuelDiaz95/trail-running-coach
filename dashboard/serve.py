#!/usr/bin/env python3
"""Dashboard server — serves static files + Garmin sync API."""
from __future__ import annotations

import html as html_mod
import json
import os
import sys
import time
import threading
from datetime import date, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.plan_data import get_current_week, get_week, get_week_dates, load_plan
from tracker.garmin_sync import sync_activities, load_cached_activities, DEFAULT_PROFILE
from tracker.analysis import build_week_actual, compliance_score
from tracker.alerts import generate_alerts

DASHBOARD_DIR = Path(__file__).resolve().parent
API_KEY = os.environ.get("API_KEY", "")
SYNC_COOLDOWN_SECONDS = 60
AUTO_SYNC_INTERVAL = int(os.environ.get("AUTO_SYNC_INTERVAL", 86400))  # default: 24h
_last_sync_time: dict[str, float] = {}  # key: "profile:week"


def _load_profiles() -> list[dict]:
    """Load profiles from PROFILES env var. Format: id1:Name1,id2:Name2"""
    raw = os.environ.get("PROFILES", "")
    profiles = []
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if ":" in entry:
                pid, name = entry.split(":", 1)
                profiles.append({"id": pid.strip(), "name": name.strip()})
            elif entry:
                profiles.append({"id": entry.strip(), "name": entry.strip()})
    if not profiles:
        profiles = [{"id": DEFAULT_PROFILE, "name": "Default"}]
    return profiles

PROFILES = _load_profiles()
MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
LOCATION_WORDS = {
    "Calimaya", "Metepec", "Cuajimalpa", "Toluca", "Morelos",
    "Zapopan", "Urique", "de", "la", "el", "los", "las",
}


def sanitize_activity_name(name: str) -> str:
    """Strip location words from Garmin activity names."""
    parts = name.split()
    clean = [p for p in parts if p not in LOCATION_WORDS]
    return " ".join(clean) if clean else name


def format_date_short(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}"


def format_activity_date(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    return f"{days[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}"


def pace_str(duration_seconds: float, distance_km: float) -> str | None:
    if distance_km < 0.1:
        return None
    pace = (duration_seconds / 60) / distance_km
    mins = int(pace)
    secs = int((pace % 1) * 60)
    return f"{mins}:{secs:02d}"


def activity_type_for_dashboard(garmin_type: str) -> str:
    if garmin_type in ('running', 'trail_running', 'treadmill_running'):
        return 'trail'
    if garmin_type in ('strength_training', 'indoor_cardio'):
        return 'strength'
    return 'cycling'


def build_week_json(week_num: int, do_sync: bool = False, profile_id: str = DEFAULT_PROFILE) -> dict:
    """Build a single week's data in the dashboard WEEKS format."""
    plan = get_week(week_num)
    if plan is None:
        return {"error": f"Week {week_num} not in plan"}

    start, end = get_week_dates(week_num)

    # Get activities
    activities = None
    if do_sync:
        try:
            activities = sync_activities(start, end, profile_id)
        except Exception as e:
            return {"error": f"Garmin sync failed: {str(e)}"}
    else:
        activities = load_cached_activities(start, end, profile_id)

    # Base plan data
    result = {
        "number": week_num,
        "start": format_date_short(start),
        "end": format_date_short(end),
        "year": start.year,
        "phase": plan.phase,
        "recovery": plan.is_recovery,
        "plan": {
            "distance_km": plan.distance_km,
            "vert_m": plan.vert_m,
            "long_run_km": plan.long_run_km,
            "gym": plan.gym_sessions,
            "series": plan.series_type,
        },
        "actual": None,
        "compliance": None,
        "activities": [],
        "alerts": [],
    }

    if activities is None or len(activities) == 0:
        return result

    # Build actual
    actual = build_week_actual(activities, week_num)
    score = compliance_score(plan, actual)

    # Load context for alerts
    prev_actual = None
    if week_num > 1:
        prev_start, prev_end = get_week_dates(week_num - 1)
        prev_acts = load_cached_activities(prev_start, prev_end, profile_id)
        if prev_acts:
            prev_actual = build_week_actual(prev_acts, week_num - 1)

    prev_weeks = []
    for w in range(max(1, week_num - 4), week_num):
        ws, we = get_week_dates(w)
        wa = load_cached_activities(ws, we, profile_id)
        if wa:
            prev_weeks.append(build_week_actual(wa, w))

    alerts = generate_alerts(plan, actual, prev_actual, prev_weeks)

    result["actual"] = {
        "distance_km": round(actual.total_distance_km, 1),
        "vert_m": actual.total_vert_m,
        "long_run_km": round(actual.longest_run_km, 1),
        "gym": actual.gym_count,
        "series": actual.series_detected,
    }
    result["compliance"] = score

    # Format activities for dashboard
    dash_activities = []
    for a in activities:
        dtype = activity_type_for_dashboard(a.activity_type)
        is_strength = dtype == 'strength'

        entry = {
            "date": format_activity_date(a.date),
            "name": html_mod.escape(sanitize_activity_name(a.name)),
            "type": dtype,
            "dist": round(a.distance_km, 2) if a.distance_km > 0.1 else None,
            "pace": pace_str(a.duration_seconds, a.distance_km),
            "hr": a.avg_hr,
            "elev": a.elevation_gain_m if a.elevation_gain_m and a.elevation_gain_m > 0 else None,
            "cal": a.calories,
            "dur": round(a.duration_seconds / 60),
            "sets": None,
            "reps": None,
        }
        dash_activities.append(entry)

    result["activities"] = dash_activities

    # Format alerts — escape message content to prevent XSS
    result["alerts"] = [
        {"level": a.level.lower(), "text": f"<strong>{html_mod.escape(a.category.replace('_', ' ').title())}:</strong> {html_mod.escape(a.message)}"}
        for a in alerts
    ]

    return result


def _update_weeks_cache(week_num: int, week_data: dict, profile_id: str = DEFAULT_PROFILE):
    """Update the static weeks cache file with fresh data for one week."""
    suffix = f"_{profile_id}" if profile_id != DEFAULT_PROFILE else ""
    cache_path = DASHBOARD_DIR / f"weeks_cache{suffix}.json"
    try:
        if cache_path.exists():
            weeks = json.loads(cache_path.read_text())
        else:
            weeks = []
        # Find and replace the week, or append
        replaced = False
        for i, w in enumerate(weeks):
            if w.get("number") == week_num:
                weeks[i] = week_data
                replaced = True
                break
        if not replaced:
            weeks.append(week_data)
            weeks.sort(key=lambda w: w.get("number", 0))
        cache_path.write_text(json.dumps(weeks, indent=2))
        print(f"[cache] Updated week {week_num} in static cache")
    except Exception as e:
        print(f"[cache] Failed to update cache: {e}")


def build_all_weeks_json(do_sync: bool = False, profile_id: str = DEFAULT_PROFILE) -> list[dict]:
    """Build data for all weeks that have plan data."""
    plan_weeks = load_plan()
    current = get_current_week()
    results = []

    for wp in plan_weeks:
        wn = wp.week_number
        # Only sync current week, load cached for past weeks
        if do_sync and wn == current:
            results.append(build_week_json(wn, do_sync=True, profile_id=profile_id))
        elif wn <= (current or 0):
            results.append(build_week_json(wn, do_sync=False, profile_id=profile_id))
        else:
            # Future week — plan only
            start, end = get_week_dates(wn)
            results.append({
                "number": wn,
                "start": format_date_short(start),
                "end": format_date_short(end),
                "year": start.year,
                "phase": wp.phase,
                "recovery": wp.is_recovery,
                "plan": {
                    "distance_km": wp.distance_km,
                    "vert_m": wp.vert_m,
                    "long_run_km": wp.long_run_km,
                    "gym": wp.gym_sessions,
                    "series": wp.series_type,
                },
                "actual": None,
                "compliance": None,
                "activities": [],
                "alerts": [],
            })

    return results


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def _check_auth(self) -> bool:
        """Verify API key if one is configured."""
        if not API_KEY:
            return True  # No key configured (local dev)
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        return token == API_KEY

    def _block_dotfiles(self, path: str) -> bool:
        """Block access to hidden files."""
        segments = path.strip('/').split('/')
        return any(seg.startswith('.') for seg in segments)

    def do_GET(self):
        parsed = urlparse(self.path)

        if self._block_dotfiles(parsed.path):
            self.send_error(403, "Forbidden")
            return

        if parsed.path in ('/', '/index.html'):
            self.path = '/dashboard.html'
            super().do_GET()
        elif parsed.path == '/api/profiles':
            self._send_json(PROFILES)
        elif parsed.path == '/api/weeks':
            self._handle_weeks(parsed)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/sync':
            self._handle_sync(parsed)
        else:
            self.send_error(405, "Method not allowed")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _validate_profile(self, params: dict) -> str:
        """Extract and validate profile ID from query params."""
        profile_id = params.get('profile', [DEFAULT_PROFILE])[0]
        valid_ids = {p["id"] for p in PROFILES}
        if profile_id not in valid_ids:
            return DEFAULT_PROFILE
        return profile_id

    def _handle_sync(self, parsed):
        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        # Parse and validate params
        params = parse_qs(parsed.query)
        profile_id = self._validate_profile(params)
        week_str = params.get('week', [None])[0]

        if week_str:
            try:
                week_num = int(week_str)
            except ValueError:
                self._send_json({"error": "Invalid week number"}, 400)
                return
            if week_num < 1 or week_num > 30:
                self._send_json({"error": "Week must be between 1 and 30"}, 400)
                return
        else:
            week_num = get_current_week()
            if week_num is None:
                self._send_json({"error": "Not in training window"}, 400)
                return

        # Rate limiting per profile+week
        rate_key = f"{profile_id}:{week_num}"
        now = time.time()
        last = _last_sync_time.get(rate_key, 0)
        if now - last < SYNC_COOLDOWN_SECONDS:
            remaining = int(SYNC_COOLDOWN_SECONDS - (now - last))
            self._send_json({"error": f"Please wait {remaining}s before syncing again"}, 429)
            return

        print(f"[sync] Syncing week {week_num} for profile '{profile_id}' from Garmin...")
        result = build_week_json(week_num, do_sync=True, profile_id=profile_id)

        if "error" in result:
            print(f"[sync] Failed: {result['error']}")
            self._send_json({"error": "Garmin sync failed. Check server logs."}, 500)
        else:
            _last_sync_time[rate_key] = time.time()
            print(f"[sync] Week {week_num} [{profile_id}]: {result.get('compliance', '—')}% compliance, {len(result['activities'])} activities")
            _update_weeks_cache(week_num, result, profile_id)
            self._send_json(result)

    def _handle_weeks(self, parsed):
        params = parse_qs(parsed.query)
        profile_id = self._validate_profile(params)
        print(f"[weeks] Loading all weeks for profile '{profile_id}'...")
        results = build_all_weeks_json(do_sync=False, profile_id=profile_id)
        # Fallback to static cache if no activity data was found
        if all(w.get("actual") is None for w in results):
            cache_path = DASHBOARD_DIR / f"weeks_cache{'_' + profile_id if profile_id != DEFAULT_PROFILE else ''}.json"
            if cache_path.exists():
                print(f"[weeks] No live data, using static cache for '{profile_id}'")
                results = json.loads(cache_path.read_text())
        print(f"[weeks] Loaded {len(results)} weeks")
        self._send_json(results)

    def log_message(self, format, *args):
        try:
            path = str(args[0]).split()[1] if args else ''
        except (IndexError, AttributeError):
            path = ''
        if path.startswith('/api/') or 'error' in format.lower() or 'code' in format.lower():
            super().log_message(format, *args)


def _auto_sync():
    """Background thread: sync current week for all profiles on a daily interval."""
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
        print(f"[auto-sync] Next sync in {AUTO_SYNC_INTERVAL}s")
        time.sleep(AUTO_SYNC_INTERVAL)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = os.environ.get('HOST', '127.0.0.1')
    server = HTTPServer((host, port), DashboardHandler)
    print(f"Tarahumara Dashboard running on port {port}")
    print(f"  Auto-sync every {AUTO_SYNC_INTERVAL}s ({AUTO_SYNC_INTERVAL // 3600}h)")
    print(f"  GET /api/sync         — sync current week from Garmin")
    print(f"  GET /api/sync?week=N  — sync specific week")
    print(f"  GET /api/weeks        — load all weeks (cached)")
    print()
    # Start auto-sync background thread
    sync_thread = threading.Thread(target=_auto_sync, daemon=True)
    sync_thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
