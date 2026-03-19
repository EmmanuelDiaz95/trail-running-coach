from __future__ import annotations

import json
import os
from typing import Optional

from tracker.models import WeekActual, WeekPlan
from coach.models import ReadinessScore

# Path to knowledge.json at the project root (same directory as this package's parent)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KNOWLEDGE_PATH = os.path.join(_PROJECT_ROOT, "knowledge.json")

# Default ACWR zone thresholds (used if knowledge.json is not found)
_DEFAULT_ZONES = {
    "optimal": [0.8, 1.3],
    "caution": [1.3, 1.5],
    "danger": [1.5, None],
}


def _load_acwr_zones() -> dict:
    """Load ACWR zone thresholds from knowledge.json, falling back to defaults."""
    try:
        with open(_KNOWLEDGE_PATH) as f:
            data = json.load(f)
        return data.get("acwr_zones", _DEFAULT_ZONES)
    except (FileNotFoundError, json.JSONDecodeError):
        return _DEFAULT_ZONES


def _training_load(week: WeekActual) -> float:
    """Compute simplified training load: distance_km + vert_m/100 + gym_count*3."""
    return week.total_distance_km + (week.total_vert_m / 100.0) + (week.gym_count * 3)


def _classify_zone(acwr: float, is_recovery: bool, zones: dict) -> str:
    """Classify ACWR value into a zone string."""
    optimal_lo, optimal_hi = zones["optimal"]
    caution_lo, caution_hi = zones["caution"]
    danger_lo = zones["danger"][0]

    if acwr >= danger_lo:
        return "danger"
    if acwr >= caution_lo:
        return "caution"
    if acwr >= optimal_lo:
        return "optimal"
    # acwr < optimal_lo (below 0.8)
    if is_recovery:
        return "expected_recovery"
    return "detraining"


def _zone_to_score(zone: str) -> int:
    """Map ACWR zone to a numeric score (1-10)."""
    mapping = {
        "optimal": 8,
        "expected_recovery": 6,
        "detraining": 6,
        "caution": 4,
        "danger": 2,
    }
    return mapping.get(zone, 5)


def _zone_to_recommendation(zone: str) -> str:
    """Map ACWR zone to a recommendation string."""
    if zone == "optimal":
        return "maintain"
    if zone == "expected_recovery":
        return "maintain"
    if zone == "detraining":
        return "push"
    if zone in ("caution", "danger"):
        return "back_off"
    return "maintain"


def compute_readiness(
    weeks: list[WeekActual],
    plan: WeekPlan,
    min_weeks: int = 2,
) -> ReadinessScore:
    """Compute ACWR-based readiness score.

    Args:
        weeks: List of WeekActual objects (sorted by week_number ascending).
               The last entry is treated as the current (acute) week.
        plan:  The WeekPlan for the current week (used to check is_recovery).
        min_weeks: Minimum number of weeks required for a reliable ACWR calculation.

    Returns:
        ReadinessScore with score, acwr, acwr_zone, recommendation, and signals.
    """
    zones = _load_acwr_zones()
    signals: list[str] = []

    if not weeks:
        return ReadinessScore(
            score=5,
            acwr=1.0,
            acwr_zone="optimal",
            recommendation="maintain",
            signals=["Insufficient data: no weeks recorded yet"],
        )

    if len(weeks) < min_weeks:
        # Only one week available — use it as both acute and chronic
        load = _training_load(weeks[-1])
        acwr = 1.0  # By definition when only one data point
        zone = _classify_zone(acwr, plan.is_recovery, zones)
        score = _zone_to_score(zone)
        recommendation = _zone_to_recommendation(zone)
        signals.append(
            f"Limited data: only {len(weeks)} week(s) recorded; "
            "ACWR estimate may be unreliable"
        )
        return ReadinessScore(
            score=score,
            acwr=acwr,
            acwr_zone=zone,
            recommendation=recommendation,
            signals=signals,
        )

    # Compute loads for all weeks
    loads = [_training_load(w) for w in weeks]

    # Acute load = most recent week
    acute_load = loads[-1]

    # Chronic load = average of all weeks (including acute)
    chronic_load = sum(loads) / len(loads)

    if chronic_load == 0:
        acwr = 1.0
        signals.append("Chronic load is zero; defaulting ACWR to 1.0")
    else:
        acwr = acute_load / chronic_load

    zone = _classify_zone(acwr, plan.is_recovery, zones)
    score = _zone_to_score(zone)
    recommendation = _zone_to_recommendation(zone)

    # Build descriptive signals
    signals.append(
        f"ACWR={acwr:.2f} (acute={acute_load:.1f}, chronic={chronic_load:.1f}) "
        f"over {len(weeks)} week(s)"
    )

    if zone == "danger":
        signals.append("Workload spike detected: high injury risk")
    elif zone == "caution":
        signals.append("Workload rising quickly: consider moderating intensity")
    elif zone == "expected_recovery":
        signals.append("Low load expected during recovery week")
    elif zone == "detraining":
        signals.append("Load is below training stimulus threshold: increase volume")

    return ReadinessScore(
        score=score,
        acwr=round(acwr, 4),
        acwr_zone=zone,
        recommendation=recommendation,
        signals=signals,
    )
