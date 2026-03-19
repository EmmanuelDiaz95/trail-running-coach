from __future__ import annotations

from datetime import datetime

from tracker.models import WeekPlan, WeekActual
from tracker.analysis import compliance_score, compute_deltas
from tracker.alerts import generate_alerts
from tracker.plan_data import days_to_race
from coach.models import CoachingOutput, ComplianceBreakdown
from coach.trends import analyze_trends
from coach.readiness import compute_readiness
from coach.adjustments import generate_adjustments


def run_coaching(
    plan: WeekPlan,
    current: WeekActual,
    history: list[WeekActual],
    prev_plan: WeekPlan | None = None,
) -> CoachingOutput:
    # Compliance
    score = compliance_score(plan, current)
    deltas = compute_deltas(plan, current)

    breakdown: dict[str, ComplianceBreakdown] = {}
    for key in ("distance_km", "vert_m", "long_run_km", "gym_sessions"):
        d = deltas.get(key, {})
        planned = d.get("planned")
        actual = d.get("actual")
        if planned is not None and planned > 0 and actual is not None:
            pct = round(actual / planned * 100)
        else:
            pct = None
        breakdown[key] = ComplianceBreakdown(planned=planned, actual=actual, pct=pct)

    # Series is boolean — handle separately
    series_d = deltas.get("series", {})
    series_planned = series_d.get("planned")
    series_actual = series_d.get("actual")
    if series_planned:
        breakdown["series"] = ComplianceBreakdown(
            planned=1.0 if series_planned else 0.0,
            actual=1.0 if series_actual else 0.0,
            pct=100 if series_actual else 0,
        )
    else:
        breakdown["series"] = ComplianceBreakdown(planned=None, actual=None, pct=None)

    # Alerts
    prev_actual = None
    prev_weeks: list[WeekActual] = []
    for w in history:
        if w.week_number < current.week_number:
            prev_weeks.append(w)
    if prev_weeks:
        prev_actual = prev_weeks[-1]

    alerts = generate_alerts(plan, current, prev_actual, prev_weeks or None)
    alert_dicts = [{"level": a.level, "category": a.category, "message": a.message} for a in alerts]

    # Trends
    trends = analyze_trends(history)

    # Readiness
    readiness = compute_readiness(history, plan)

    # Adjustments
    adjustments = generate_adjustments(
        plan, current, score,
        prev_actual=prev_actual,
        prev_plan=prev_plan,
    )

    return CoachingOutput(
        week_number=current.week_number,
        generated_at=datetime.now().isoformat(),
        phase=plan.phase,
        is_recovery_week=plan.is_recovery,
        days_to_race=days_to_race(),
        compliance_score=score,
        compliance_breakdown=breakdown,
        readiness=readiness,
        trends=trends,
        adjustments=adjustments,
        alerts=alert_dicts,
    )
