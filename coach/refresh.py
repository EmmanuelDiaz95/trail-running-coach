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
