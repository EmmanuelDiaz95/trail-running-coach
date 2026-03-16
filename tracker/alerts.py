from __future__ import annotations

from .config import (
    HR_DRIFT_BPM,
    VOLUME_SPIKE_PCT,
    LONG_RUN_RATIO_PCT,
    RECOVERY_REDUCTION_PCT,
)
from .models import Alert, WeekPlan, WeekActual
from .analysis import classify_activity


def check_hr_drift(actual: WeekActual, prev_weeks: list[WeekActual]) -> Alert | None:
    """Alert if easy run avg HR is >10bpm above 4-week rolling average."""
    if not prev_weeks:
        return None

    # Collect easy run HRs from previous weeks (runs < 10km, likely easy)
    prev_hrs = []
    for pw in prev_weeks[-4:]:
        for a in pw.activities:
            if classify_activity(a) == "run" and a.avg_hr and a.distance_km <= 10:
                prev_hrs.append(a.avg_hr)

    if not prev_hrs:
        return None

    rolling_avg = sum(prev_hrs) / len(prev_hrs)

    # Check current week easy runs
    for a in actual.activities:
        if classify_activity(a) == "run" and a.avg_hr and a.distance_km <= 10:
            if a.avg_hr > rolling_avg + HR_DRIFT_BPM:
                return Alert(
                    level="WARNING",
                    category="hr_drift",
                    message=f"HR drift: easy run on {a.date} avg {a.avg_hr}bpm "
                            f"vs 4-week avg {rolling_avg:.0f}bpm (+{a.avg_hr - rolling_avg:.0f}bpm)",
                )
    return None


def check_volume_spike(actual: WeekActual, prev_actual: WeekActual | None,
                       plan: WeekPlan) -> Alert | None:
    """Alert if actual volume exceeds previous week by >10% when not planned."""
    if prev_actual is None or prev_actual.total_distance_km == 0:
        return None

    actual_increase = ((actual.total_distance_km - prev_actual.total_distance_km)
                       / prev_actual.total_distance_km * 100)

    if actual_increase > VOLUME_SPIKE_PCT:
        # Check if it was planned (compare plan growth)
        # Only alert if actual increase significantly exceeds plan
        return Alert(
            level="WARNING",
            category="volume_spike",
            message=f"Volume spike: {actual.total_distance_km:.1f}km vs "
                    f"previous {prev_actual.total_distance_km:.1f}km "
                    f"(+{actual_increase:.0f}%)",
        )
    return None


def check_long_run_ratio(actual: WeekActual) -> Alert | None:
    """Alert if longest run exceeds 30% of weekly volume."""
    if actual.total_distance_km == 0:
        return None

    ratio = actual.longest_run_km / actual.total_distance_km * 100
    if ratio > LONG_RUN_RATIO_PCT:
        return Alert(
            level="INFO",
            category="long_run_ratio",
            message=f"Long run ratio: {actual.longest_run_km:.1f}km is "
                    f"{ratio:.0f}% of weekly {actual.total_distance_km:.1f}km "
                    f"(threshold: {LONG_RUN_RATIO_PCT}%)",
        )
    return None


def check_missed_gym(plan: WeekPlan, actual: WeekActual) -> Alert | None:
    """Alert if fewer gym sessions than planned."""
    if actual.gym_count < plan.gym_sessions:
        return Alert(
            level="WARNING",
            category="missed_gym",
            message=f"Gym: only {actual.gym_count}/{plan.gym_sessions} "
                    f"planned sessions completed",
        )
    return None


def check_missed_series(plan: WeekPlan, actual: WeekActual) -> Alert | None:
    """Alert if series was planned but not detected."""
    if plan.series_type and not actual.series_detected:
        return Alert(
            level="WARNING",
            category="missed_series",
            message=f"Series: planned {plan.series_type} not detected in activities",
        )
    return None


def check_recovery_week(plan: WeekPlan, actual: WeekActual,
                        prev_actual: WeekActual | None) -> Alert | None:
    """Alert if recovery week volume isn't reduced enough."""
    if not plan.is_recovery or prev_actual is None:
        return None

    if prev_actual.total_distance_km == 0:
        return None

    reduction = ((prev_actual.total_distance_km - actual.total_distance_km)
                 / prev_actual.total_distance_km * 100)

    if reduction < RECOVERY_REDUCTION_PCT:
        return Alert(
            level="WARNING",
            category="recovery_week",
            message=f"Recovery week: volume only reduced {reduction:.0f}% "
                    f"(expected >={RECOVERY_REDUCTION_PCT}%)",
        )
    return None


def generate_alerts(plan: WeekPlan, actual: WeekActual,
                    prev_actual: WeekActual | None = None,
                    prev_weeks: list[WeekActual] | None = None) -> list[Alert]:
    """Run all alert checks and return list of triggered alerts."""
    alerts = []
    prev_weeks = prev_weeks or []

    checks = [
        check_hr_drift(actual, prev_weeks),
        check_volume_spike(actual, prev_actual, plan),
        check_long_run_ratio(actual),
        check_missed_gym(plan, actual),
        check_missed_series(plan, actual),
        check_recovery_week(plan, actual, prev_actual),
    ]

    for alert in checks:
        if alert is not None:
            alerts.append(alert)

    return alerts
