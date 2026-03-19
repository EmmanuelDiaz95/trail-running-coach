from __future__ import annotations

from typing import Optional

from tracker.models import WeekActual, WeekPlan
from coach.models import Adjustment

# Compliance thresholds
_MAJOR_DEVIATION_THRESHOLD = 60
_MODERATE_DEVIATION_THRESHOLD = 80

# Overtraining multiplier: actual > planned * this value
_OVERTRAINING_MULTIPLIER = 1.3

# Recovery week: must reduce volume by at least this fraction vs previous week
_MIN_RECOVERY_REDUCTION = 0.20

# Phase descriptions used in phase transition recommendations
_PHASE_DESCRIPTIONS: dict[str, str] = {
    "base": "aerobic base building — focus on consistent volume and easy effort",
    "specific": "race-specific preparation — terrain, vert, and intensity increase",
    "taper": "taper phase — volume drops, maintain intensity, trust the training",
}


def generate_adjustments(
    plan: WeekPlan,
    actual: WeekActual,
    compliance_score: int,
    prev_plan: Optional[WeekPlan] = None,
    prev_actual: Optional[WeekActual] = None,
) -> list[Adjustment]:
    """Generate plan adjustment recommendations for the current week.

    Rules applied (in order):
    1. Phase transition — if prev_plan.phase != plan.phase
    2. Major deviation — compliance < 60% → high priority
    3. Moderate deviation — compliance 60-80% → medium priority
    4. Gym lagging — gym_count < gym_sessions - 1 even with OK compliance
    5. Overtraining — actual distance > planned * 1.3
    6. Insufficient recovery — recovery week with < 20% volume reduction

    Args:
        plan:             WeekPlan for the current week.
        actual:           WeekActual results for the current week.
        compliance_score: Overall compliance percentage (0-100).
        prev_plan:        WeekPlan from the previous week (optional).
        prev_actual:      WeekActual from the previous week (optional).

    Returns:
        List of Adjustment recommendations (may be empty).
    """
    adjustments: list[Adjustment] = []

    # Rule 1: Phase transition
    if prev_plan is not None and prev_plan.phase != plan.phase:
        description = _PHASE_DESCRIPTIONS.get(
            plan.phase,
            f"new phase: {plan.phase}",
        )
        adjustments.append(
            Adjustment(
                category="phase_transition",
                priority="medium",
                message=(
                    f"Entering {plan.phase} phase (week {plan.week_number}): "
                    f"{description}."
                ),
            )
        )

    # Rule 2: Major deviation — compliance < 60%
    if compliance_score < _MAJOR_DEVIATION_THRESHOLD:
        adjustments.append(
            Adjustment(
                category="volume",
                priority="high",
                message=(
                    f"Significant deviation this week: compliance at {compliance_score}%. "
                    "Review training load and identify barriers before the next session."
                ),
            )
        )

    # Rule 3: Moderate deviation — compliance 60-80%
    elif compliance_score < _MODERATE_DEVIATION_THRESHOLD:
        # Identify the lagging dimensions
        lagging: list[str] = []
        if plan.distance_km > 0 and actual.total_distance_km < plan.distance_km * 0.8:
            lagging.append("distance")
        if plan.vert_m > 0 and actual.total_vert_m < plan.vert_m * 0.8:
            lagging.append("elevation")
        if plan.long_run_km > 0 and actual.longest_run_km < plan.long_run_km * 0.8:
            lagging.append("long run")
        if plan.gym_sessions > 0 and actual.gym_count < plan.gym_sessions * 0.8:
            lagging.append("gym")
        if plan.series_type and not actual.series_detected:
            lagging.append("series/intervals")

        dimension_str = (
            f" Lagging dimensions: {', '.join(lagging)}." if lagging else ""
        )
        adjustments.append(
            Adjustment(
                category="volume",
                priority="medium",
                message=(
                    f"Moderate deviation this week: compliance at {compliance_score}%.{dimension_str} "
                    "Consider prioritising the lagging areas next week."
                ),
            )
        )

    # Rule 4: Gym lagging (even when overall compliance is OK)
    if (
        compliance_score >= _MODERATE_DEVIATION_THRESHOLD
        and plan.gym_sessions > 0
        and actual.gym_count < plan.gym_sessions - 1
    ):
        adjustments.append(
            Adjustment(
                category="gym",
                priority="medium",
                message=(
                    f"Gym sessions lagging: completed {actual.gym_count} of "
                    f"{plan.gym_sessions} planned. "
                    "Strength work supports injury prevention — try to reschedule missed sessions."
                ),
            )
        )
    # Also flag gym when in moderate deviation zone but gym specifically is low
    elif (
        compliance_score < _MODERATE_DEVIATION_THRESHOLD
        and plan.gym_sessions > 0
        and actual.gym_count < plan.gym_sessions - 1
    ):
        adjustments.append(
            Adjustment(
                category="gym",
                priority="medium",
                message=(
                    f"Gym sessions lagging: completed {actual.gym_count} of "
                    f"{plan.gym_sessions} planned. "
                    "Strength work supports injury prevention — try to reschedule missed sessions."
                ),
            )
        )

    # Rule 5: Overtraining — actual distance > planned * 1.3
    if plan.distance_km > 0 and actual.total_distance_km > plan.distance_km * _OVERTRAINING_MULTIPLIER:
        adjustments.append(
            Adjustment(
                category="volume",
                priority="medium",
                message=(
                    f"Volume exceeded plan by more than 30%: ran {actual.total_distance_km:.1f} km "
                    f"vs {plan.distance_km:.1f} km planned. "
                    "Ensure adequate recovery to avoid accumulated fatigue."
                ),
            )
        )

    # Rule 6: Insufficient recovery — recovery week without adequate volume reduction
    if plan.is_recovery and prev_actual is not None and prev_actual.total_distance_km > 0:
        reduction = (
            prev_actual.total_distance_km - actual.total_distance_km
        ) / prev_actual.total_distance_km
        if reduction < _MIN_RECOVERY_REDUCTION:
            adjustments.append(
                Adjustment(
                    category="recovery",
                    priority="high",
                    message=(
                        f"Recovery week volume reduction insufficient: "
                        f"{reduction * 100:.0f}% reduction vs {_MIN_RECOVERY_REDUCTION * 100:.0f}% minimum. "
                        "Reduce intensity and distance to allow adaptation."
                    ),
                )
            )

    return adjustments
