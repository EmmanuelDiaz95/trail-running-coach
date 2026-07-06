from __future__ import annotations

from datetime import date, timedelta

_HEALTH_FIELDS = ("resting_hr", "hrv_last_night", "training_readiness",
                  "sleep_hours", "body_battery_am")


def detect_week_gap(snapshots: list, current_week: int, max_weeks: int) -> tuple:
    """Return (from_week, to_week, capped). Always includes current_week."""
    last_good = 0
    for s in snapshots:
        n = s.get("week_number")
        actual = (s.get("data") or {}).get("actual") or {}
        if n is not None and n <= current_week and actual.get("distance_km") is not None:
            last_good = max(last_good, n)

    floor = max(1, current_week - max_weeks + 1)
    from_week = last_good + 1 if last_good else floor
    capped = (last_good == 0) or (from_week < floor)
    if from_week < floor:
        from_week = floor
    from_week = min(from_week, current_week)  # always include current week
    return from_week, current_week, capped


def _row_date(r) -> date:
    d = r.get("date")
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def detect_health_gap(health_rows: list, today: date, max_days: int) -> tuple:
    """Return (from_date, to_date, capped). Always includes today."""
    populated = [r for r in health_rows
                 if any(isinstance(r.get(f), (int, float)) for f in _HEALTH_FIELDS)]
    floor = today - timedelta(days=max_days - 1)
    if populated:
        last = max(_row_date(r) for r in populated)
        from_date = last + timedelta(days=1)
    else:
        from_date = floor
    capped = (len(populated) == 0) or (from_date < floor)
    if from_date < floor:
        from_date = floor
    from_date = min(from_date, today)  # always include today
    return from_date, today, capped


from dataclasses import dataclass, field


@dataclass
class RefreshSummary:
    weeks_synced: list = field(default_factory=list)
    health_days_synced: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    rate_limited: bool = False
    retry_after: int = None


def refresh(profile_id: str = "default", today=None, max_weeks: int = 8,
            max_health_days: int = 21) -> RefreshSummary:
    from tracker.garmin_sync import _load_env, sync_daily_health, GarminRateLimited
    from tracker import db
    from tracker.plan_data import get_current_week
    from dashboard.serve import build_week_json, _update_weeks_cache

    _load_env()
    db.init_db()
    today = today or date.today()
    summary = RefreshSummary()

    current_week = get_current_week()
    if current_week is not None:
        snapshots = db.get_week_snapshots(profile_id)
        from_w, to_w, capped_w = detect_week_gap(snapshots, current_week, max_weeks)
        if capped_w:
            summary.warnings.append(f"week backfill capped to weeks {from_w}-{to_w}")
        for w in range(from_w, to_w + 1):
            try:
                result = build_week_json(w, do_sync=True, profile_id=profile_id)
            except GarminRateLimited as e:
                summary.rate_limited = True
                summary.retry_after = e.retry_after
                return summary
            if isinstance(result, dict) and result.get("error"):
                if result.get("rate_limited"):
                    summary.rate_limited = True
                    summary.retry_after = result.get("retry_after")
                    return summary
                summary.errors.append(f"week {w}: {result['error']}")
                continue
            _update_weeks_cache(w, result, profile_id)
            summary.weeks_synced.append(w)
    else:
        summary.warnings.append("not in training window; skipped activity sync")

    health_rows = db.get_daily_health(today - timedelta(days=max_health_days + 7),
                                      today, profile_id)
    from_d, to_d, capped_h = detect_health_gap(health_rows, today, max_health_days)
    if capped_h:
        summary.warnings.append(f"health backfill capped to {from_d}..{to_d}")
    d = from_d
    while d <= to_d:
        try:
            sync_daily_health(d, profile_id=profile_id)
            summary.health_days_synced.append(d.isoformat())
        except GarminRateLimited as e:
            summary.rate_limited = True
            summary.retry_after = e.retry_after
            return summary
        except Exception as e:  # noqa: BLE001 — record and continue
            summary.errors.append(f"health {d}: {e}")
        d += timedelta(days=1)

    return summary
