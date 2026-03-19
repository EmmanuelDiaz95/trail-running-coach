from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tracker.data_loader import load_week_range
from tracker.models import WeekActual


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary activities directory with cached data."""
    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    return activities_dir


def _write_cache(cache_dir: Path, start: date, end: date, activities: list[dict]):
    """Write a fake cache file matching garmin_sync naming convention."""
    filename = f"{start.isoformat()}_{end.isoformat()}.json"
    (cache_dir / filename).write_text(json.dumps(activities))


def _make_raw_activity(activity_type="running", distance_m=5000, avg_hr=140, max_hr=155, elevation=50):
    """Create a raw Garmin API activity dict (pre-normalization)."""
    return {
        "activityId": 1,
        "startTimeLocal": "2026-03-02 08:00:00",
        "activityType": {"typeKey": activity_type},
        "activityName": "Test",
        "distance": distance_m,
        "duration": 1800,
        "averageHR": avg_hr,
        "maxHR": max_hr,
        "averageRunningCadenceInStepsPerMinute": 170,
        "averageSpeed": 2.78,
        "elevationGain": elevation,
        "calories": 300,
    }


def _patch_activities_dir(monkeypatch, cache_dir):
    """Monkeypatch the ACTIVITIES_DIR binding in garmin_sync so load_cached_activities
    reads from the temp dir.

    garmin_sync imports ACTIVITIES_DIR directly via `from .config import ACTIVITIES_DIR`,
    creating a local name binding. We must patch tracker.garmin_sync.ACTIVITIES_DIR
    (not tracker.config.ACTIVITIES_DIR) so that _get_activities_dir() returns the
    temp dir for the default profile.
    """
    monkeypatch.setattr("tracker.garmin_sync.ACTIVITIES_DIR", cache_dir)


def test_load_single_week(cache_dir, monkeypatch):
    """Load one week of cached data."""
    _patch_activities_dir(monkeypatch, cache_dir)
    _write_cache(cache_dir, date(2026, 3, 2), date(2026, 3, 8), [
        _make_raw_activity(distance_m=10000),
        _make_raw_activity(activity_type="strength_training", distance_m=0),
    ])
    results = load_week_range(1, 1)
    assert len(results) == 1
    assert results[0].week_number == 1
    assert results[0].total_distance_km == pytest.approx(10.0, abs=0.1)
    assert results[0].gym_count == 1


def test_load_multiple_weeks(cache_dir, monkeypatch):
    """Load 3 weeks of cached data."""
    _patch_activities_dir(monkeypatch, cache_dir)
    for week in range(1, 4):
        start = date(2026, 3, 2 + (week - 1) * 7)
        end = date(2026, 3, 8 + (week - 1) * 7)
        _write_cache(cache_dir, start, end, [_make_raw_activity(distance_m=week * 5000)])
    results = load_week_range(1, 3)
    assert len(results) == 3
    assert results[0].week_number == 1
    assert results[2].week_number == 3


def test_missing_week_skipped(cache_dir, monkeypatch):
    """Missing weeks are skipped, not errored."""
    _patch_activities_dir(monkeypatch, cache_dir)
    # Only cache week 1 and 3, skip 2
    _write_cache(cache_dir, date(2026, 3, 2), date(2026, 3, 8), [_make_raw_activity()])
    _write_cache(cache_dir, date(2026, 3, 16), date(2026, 3, 22), [_make_raw_activity()])
    results = load_week_range(1, 3)
    assert len(results) == 2
    assert results[0].week_number == 1
    assert results[1].week_number == 3


def test_empty_range(cache_dir, monkeypatch):
    """No cached data returns empty list."""
    _patch_activities_dir(monkeypatch, cache_dir)
    results = load_week_range(1, 4)
    assert results == []
