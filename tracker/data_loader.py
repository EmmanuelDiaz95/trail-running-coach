from __future__ import annotations

from tracker.plan_data import get_week_dates
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
from tracker.models import WeekActual


def load_week_range(start_week: int, end_week: int) -> list[WeekActual]:
    """Load and merge activity data across a range of weeks.

    Gracefully handles missing weeks — returns only weeks that have
    cached data. Callers check len(results) >= min_weeks before
    computing trends.

    Args:
        start_week: First week number (inclusive).
        end_week: Last week number (inclusive).

    Returns:
        List of WeekActual for weeks that have cached data,
        ordered by week number.
    """
    results: list[WeekActual] = []
    for week_num in range(start_week, end_week + 1):
        start_date, end_date = get_week_dates(week_num)
        activities = load_cached_activities(start_date, end_date)
        if activities is None:
            continue
        week_actual = build_week_actual(activities, week_num)
        results.append(week_actual)
    return results
