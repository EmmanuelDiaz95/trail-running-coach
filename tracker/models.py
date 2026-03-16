from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlannedWorkout:
    day: str                    # "monday", "tuesday", etc.
    date: Optional[str]         # "2026-03-03" or None for weekly-only weeks
    type: str                   # "run", "long_run", "series", "gym", "rest"
    description: str            # "6km easy", "Tempo 3x5min", "Full body"
    distance_km: Optional[float] = None
    vert_m: Optional[int] = None
    target_pace: Optional[str] = None       # "7:30-8:00"
    target_hr: Optional[str] = None         # "125-140"
    series_type: Optional[str] = None       # "tempo", "hills", "fartlek"


@dataclass
class WeekPlan:
    week_number: int
    start_date: str             # "2026-03-02"
    end_date: str               # "2026-03-08"
    phase: str                  # "base", "specific", "taper", "race"
    is_recovery: bool
    distance_km: float
    vert_m: int
    long_run_km: float
    gym_sessions: int
    series_type: Optional[str]  # "tempo", "hills", "fartlek", or None
    workouts: list[PlannedWorkout] = field(default_factory=list)


@dataclass
class GarminActivity:
    activity_id: str
    date: str                   # "2026-03-03"
    activity_type: str          # "running", "trail_running", "strength_training"
    name: str
    distance_km: float
    duration_seconds: float
    avg_hr: Optional[int]
    max_hr: Optional[int]
    avg_pace_min_km: Optional[float]  # minutes per km as float
    elevation_gain_m: Optional[int]
    calories: Optional[int]


@dataclass
class WeekActual:
    week_number: int
    total_distance_km: float
    total_vert_m: int
    longest_run_km: float
    gym_count: int
    series_detected: bool
    activities: list[GarminActivity] = field(default_factory=list)


@dataclass
class Alert:
    level: str          # "WARNING", "INFO", "CRITICAL"
    category: str       # "hr_drift", "volume_spike", "long_run_ratio", etc.
    message: str
