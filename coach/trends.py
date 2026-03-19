from __future__ import annotations

from tracker.models import WeekActual
from tracker.analysis import _is_series, classify_activity
from coach.models import TrendResult


def _easy_run_avg_hr(week: WeekActual) -> float:
    """Average HR across easy runs (non-series runs) in a week."""
    easy_hrs = [
        a.avg_hr for a in week.activities
        if classify_activity(a) == "run"
        and not _is_series(a)
        and a.avg_hr is not None
    ]
    return sum(easy_hrs) / len(easy_hrs) if easy_hrs else 0.0


def _easy_run_avg_pace(week: WeekActual) -> float:
    """Average pace (min/km) across easy runs in a week."""
    easy_paces = [
        a.avg_pace_min_km for a in week.activities
        if classify_activity(a) == "run"
        and not _is_series(a)
        and a.avg_pace_min_km is not None
        and a.avg_pace_min_km > 0
    ]
    return sum(easy_paces) / len(easy_paces) if easy_paces else 0.0


def _classify_trend(values: list[float], threshold_pct: float = 5.0) -> str:
    """Classify a series of values into a trend category."""
    if len(values) < 2:
        return "plateauing"

    increases = 0
    decreases = 0
    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            increases += 1
        elif values[i] < values[i - 1]:
            decreases += 1

    total_changes = increases + decreases
    if total_changes == 0:
        return "plateauing"

    consistency = max(increases, decreases) / total_changes
    if consistency < 0.7 and total_changes >= 3:
        return "erratic"

    first, last = values[0], values[-1]
    if first == 0:
        pct_change = 100.0 if last > 0 else 0.0
    else:
        pct_change = ((last - first) / abs(first)) * 100

    # Perfectly consistent direction (no changes in opposite direction) counts as a trend
    if increases > 0 and decreases == 0:
        return "improving"
    if decreases > 0 and increases == 0:
        return "declining"

    if pct_change > threshold_pct and increases >= decreases:
        return "improving"
    elif pct_change < -threshold_pct and decreases >= increases:
        return "declining"
    else:
        return "plateauing"


def _format_delta(values: list[float], unit: str = "") -> str:
    if len(values) < 2:
        return "no data"
    first, last = values[0], values[-1]
    diff = last - first
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}{unit} over {len(values)} weeks"


def _significance(trend: str) -> str:
    if trend == "improving":
        return "on_track"
    elif trend in ("declining", "erratic"):
        return "concern"
    elif trend == "plateauing":
        return "watch"
    return "watch"


def analyze_trends(
    weeks: list[WeekActual],
    min_weeks: int = 3,
) -> list[TrendResult]:
    """Analyze trends across multiple weeks of training data."""
    metrics = [
        ("weekly_distance", lambda w: w.total_distance_km, "km"),
        ("weekly_vert", lambda w: w.total_vert_m, "m"),
        ("longest_run", lambda w: w.longest_run_km, "km"),
        ("gym_frequency", lambda w: float(w.gym_count), ""),
        ("easy_run_avg_hr", lambda w: _easy_run_avg_hr(w), "bpm"),
        ("easy_run_avg_pace", lambda w: _easy_run_avg_pace(w), "min/km"),
    ]

    results: list[TrendResult] = []
    for metric_name, extractor, unit in metrics:
        if len(weeks) < min_weeks:
            results.append(TrendResult(
                metric=metric_name,
                trend="insufficient_data",
                values=[],
                delta="insufficient data",
                significance="watch",
            ))
            continue

        values = [extractor(w) for w in weeks]
        trend = _classify_trend(values)
        delta = _format_delta(values, unit)
        sig = _significance(trend)

        results.append(TrendResult(
            metric=metric_name,
            trend=trend,
            values=values,
            delta=delta,
            significance=sig,
        ))

    return results
