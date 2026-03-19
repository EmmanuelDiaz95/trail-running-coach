from __future__ import annotations

from tracker.models import GarminActivity
from tracker.analysis import _is_series
from tracker import config


INTENSITY_FACTORS: dict[str, float] = {
    "easy": 1.0,
    "tempo": 1.5,
    "intervals": 2.0,
    "long_run": 1.2,
    "gym": 0.8,
    "other": 0.5,
}


def classify_intensity(
    activity: GarminActivity,
    long_run_threshold_km: float | None = None,
) -> str:
    """Classify a GarminActivity into an intensity type.

    Reuses the _is_series() heuristic from analysis.py for consistency
    with the existing alert engine.

    Args:
        activity: The activity to classify.
        long_run_threshold_km: If set, easy runs above this distance
            are classified as long_run instead.

    Returns:
        One of: easy, tempo, intervals, long_run, gym, other
    """
    # Gym
    if activity.activity_type in config.GYM_TYPES:
        return "gym"

    # Not a run
    if activity.activity_type not in config.RUNNING_TYPES:
        return "other"

    # Intervals (reuses existing series heuristic from analysis.py)
    if _is_series(activity):
        return "intervals"

    # Tempo: avg HR in upper range, sustained effort (> 20 min)
    if (activity.avg_hr is not None
            and activity.avg_hr >= 145
            and activity.duration_seconds > 1200):
        return "tempo"

    # Long run
    if long_run_threshold_km is not None and activity.distance_km >= long_run_threshold_km:
        return "long_run"

    # Default: easy
    return "easy"
