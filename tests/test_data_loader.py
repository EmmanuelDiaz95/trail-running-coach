from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from tracker.data_loader import load_week_range
from tracker.models import GarminActivity, WeekActual


def _make_activity(activity_type="running", distance_km=5.0, avg_hr=140, max_hr=155, elevation=50):
    """Create a GarminActivity (post-normalization)."""
    return GarminActivity(
        activity_id="1",
        date="2026-03-02",
        activity_type=activity_type,
        name="Test",
        distance_km=distance_km,
        duration_seconds=1800,
        avg_hr=avg_hr,
        max_hr=max_hr,
        avg_pace_min_km=6.0 if distance_km > 0 else None,
        elevation_gain_m=elevation,
        calories=300,
        route_svg=None,
    )


def _mock_load_cached(activities_by_week: dict):
    """Return a function that returns activities for specific week date ranges."""
    def _load(start_date, end_date, profile_id="default"):
        from tracker.plan_data import PLAN_START
        week_num = (start_date - PLAN_START).days // 7 + 1
        return activities_by_week.get(week_num)
    return _load


def test_load_single_week():
    """Load one week of cached data."""
    activities = [
        _make_activity(distance_km=10.0),
        _make_activity(activity_type="strength_training", distance_km=0),
    ]
    mock_fn = _mock_load_cached({1: activities})

    with patch("tracker.data_loader.load_cached_activities", side_effect=mock_fn):
        results = load_week_range(1, 1)

    assert len(results) == 1
    assert results[0].week_number == 1
    assert results[0].total_distance_km == pytest.approx(10.0, abs=0.1)
    assert results[0].gym_count == 1


def test_load_multiple_weeks():
    """Load 3 weeks of cached data."""
    week_data = {}
    for week in range(1, 4):
        week_data[week] = [_make_activity(distance_km=week * 5.0)]
    mock_fn = _mock_load_cached(week_data)

    with patch("tracker.data_loader.load_cached_activities", side_effect=mock_fn):
        results = load_week_range(1, 3)

    assert len(results) == 3
    assert results[0].week_number == 1
    assert results[2].week_number == 3


def test_missing_week_skipped():
    """Missing weeks are skipped, not errored."""
    week_data = {
        1: [_make_activity()],
        3: [_make_activity()],
    }
    mock_fn = _mock_load_cached(week_data)

    with patch("tracker.data_loader.load_cached_activities", side_effect=mock_fn):
        results = load_week_range(1, 3)

    assert len(results) == 2
    assert results[0].week_number == 1
    assert results[1].week_number == 3


def test_empty_range():
    """No cached data returns empty list."""
    mock_fn = _mock_load_cached({})

    with patch("tracker.data_loader.load_cached_activities", side_effect=mock_fn):
        results = load_week_range(1, 4)

    assert results == []
