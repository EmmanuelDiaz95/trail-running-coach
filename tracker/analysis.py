from __future__ import annotations

from .config import RUNNING_TYPES, GYM_TYPES, COMPLIANCE_WEIGHTS
from .models import GarminActivity, WeekPlan, WeekActual


def classify_activity(activity: GarminActivity) -> str:
    """Classify a Garmin activity into: run, gym, or other."""
    if activity.activity_type in RUNNING_TYPES:
        return "run"
    if activity.activity_type in GYM_TYPES:
        return "gym"
    return "other"


def _is_series(activity: GarminActivity) -> bool:
    """Heuristic: detect if a run was likely a series/interval workout.
    Looks for high max HR relative to avg HR (interval pattern) or short distance with high effort.
    """
    if classify_activity(activity) != "run":
        return False
    if activity.avg_hr and activity.max_hr:
        hr_spread = activity.max_hr - activity.avg_hr
        if hr_spread >= 20 and activity.max_hr >= 160:
            return True
    # Short runs with high average HR
    if activity.distance_km and activity.avg_hr:
        if activity.distance_km <= 10 and activity.avg_hr >= 155:
            return True
    return False


def build_week_actual(activities: list[GarminActivity], week_number: int) -> WeekActual:
    """Aggregate activities into weekly actuals."""
    run_activities = [a for a in activities if classify_activity(a) == "run"]
    gym_activities = [a for a in activities if classify_activity(a) == "gym"]

    total_distance = sum(a.distance_km for a in run_activities)
    total_vert = sum(a.elevation_gain_m or 0 for a in run_activities)
    longest_run = max((a.distance_km for a in run_activities), default=0)
    gym_count = len(gym_activities)
    series_detected = any(_is_series(a) for a in run_activities)

    return WeekActual(
        week_number=week_number,
        total_distance_km=round(total_distance, 1),
        total_vert_m=round(total_vert),
        longest_run_km=round(longest_run, 1),
        gym_count=gym_count,
        series_detected=series_detected,
        activities=activities,
    )


def compute_deltas(plan: WeekPlan, actual: WeekActual) -> dict:
    """Compute differences between planned and actual."""
    def pct_delta(planned: float, actual_val: float) -> float | None:
        if planned == 0:
            return None
        return round((actual_val - planned) / planned * 100, 1)

    return {
        "distance_km": {
            "planned": plan.distance_km,
            "actual": actual.total_distance_km,
            "delta_pct": pct_delta(plan.distance_km, actual.total_distance_km),
        },
        "vert_m": {
            "planned": plan.vert_m,
            "actual": actual.total_vert_m,
            "delta_pct": pct_delta(plan.vert_m, actual.total_vert_m),
        },
        "long_run_km": {
            "planned": plan.long_run_km,
            "actual": actual.longest_run_km,
            "delta_pct": pct_delta(plan.long_run_km, actual.longest_run_km),
        },
        "gym_sessions": {
            "planned": plan.gym_sessions,
            "actual": actual.gym_count,
            "delta_abs": actual.gym_count - plan.gym_sessions,
        },
        "series": {
            "planned": plan.series_type is not None,
            "actual": actual.series_detected,
        },
    }


def compliance_score(plan: WeekPlan, actual: WeekActual) -> int:
    """Compute a 0-100 compliance score."""
    scores = {}

    # Distance: score based on how close actual is to planned (cap at 100%)
    if plan.distance_km > 0:
        ratio = min(actual.total_distance_km / plan.distance_km, 1.2)
        scores["distance"] = min(ratio, 1.0) * 100
    else:
        scores["distance"] = 100

    # Vert
    if plan.vert_m > 0:
        ratio = min(actual.total_vert_m / plan.vert_m, 1.2)
        scores["vert"] = min(ratio, 1.0) * 100
    else:
        scores["vert"] = 100

    # Long run
    if plan.long_run_km > 0:
        ratio = min(actual.longest_run_km / plan.long_run_km, 1.2)
        scores["long_run"] = min(ratio, 1.0) * 100
    else:
        scores["long_run"] = 100

    # Gym: binary per session
    if plan.gym_sessions > 0:
        ratio = min(actual.gym_count / plan.gym_sessions, 1.0)
        scores["gym"] = ratio * 100
    else:
        scores["gym"] = 100

    # Series
    if plan.series_type is not None:
        scores["series"] = 100 if actual.series_detected else 0
    else:
        scores["series"] = 100

    # Weighted average
    total = sum(scores[k] * COMPLIANCE_WEIGHTS[k] for k in COMPLIANCE_WEIGHTS)
    return round(total)
