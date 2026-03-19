from __future__ import annotations

import pytest
from datetime import date
from tracker.models import GarminActivity, WeekPlan, WeekActual, Alert


@pytest.fixture
def make_activity():
    """Factory fixture for creating GarminActivity with sensible defaults."""
    def _make(
        activity_type: str = "running",
        distance_km: float = 5.0,
        avg_hr: int = 140,
        max_hr: int = 155,
        elevation_gain_m: int = 50,
        duration_seconds: int = 1800,
        dt: date | None = None,
    ) -> GarminActivity:
        return GarminActivity(
            activity_id="1",
            date=(dt or date(2026, 3, 2)).isoformat(),
            activity_type=activity_type,
            name="Test Run",
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            avg_hr=avg_hr,
            max_hr=max_hr,
            avg_pace_min_km=duration_seconds / 60 / distance_km if distance_km else 0,
            elevation_gain_m=elevation_gain_m,
            calories=300,
        )
    return _make


@pytest.fixture
def make_week_plan():
    """Factory fixture for creating WeekPlan."""
    def _make(
        week_number: int = 1,
        phase: str = "base",
        is_recovery: bool = False,
        distance_km: float = 27.0,
        vert_m: float = 400.0,
        long_run_km: float = 14.0,
        gym_sessions: int = 3,
        series_type: str | None = "tempo",
    ) -> WeekPlan:
        start = date(2026, 3, 2)
        from datetime import timedelta
        start_dt = start + timedelta(weeks=week_number - 1)
        end_dt = start_dt + timedelta(days=6)
        return WeekPlan(
            week_number=week_number,
            start_date=start_dt.isoformat(),
            end_date=end_dt.isoformat(),
            phase=phase,
            is_recovery=is_recovery,
            distance_km=distance_km,
            vert_m=vert_m,
            long_run_km=long_run_km,
            gym_sessions=gym_sessions,
            series_type=series_type,
            workouts=[],
        )
    return _make


@pytest.fixture
def make_week_actual():
    """Factory fixture for creating WeekActual."""
    def _make(
        week_number: int = 1,
        total_distance_km: float = 26.0,
        total_vert_m: int = 700,
        longest_run_km: float = 14.0,
        gym_count: int = 3,
        series_detected: bool = True,
        activities: list | None = None,
    ) -> WeekActual:
        return WeekActual(
            week_number=week_number,
            total_distance_km=total_distance_km,
            total_vert_m=total_vert_m,
            longest_run_km=longest_run_km,
            gym_count=gym_count,
            series_detected=series_detected,
            activities=activities or [],
        )
    return _make
