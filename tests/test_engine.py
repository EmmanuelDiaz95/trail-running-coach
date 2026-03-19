from __future__ import annotations

from coach.engine import run_coaching
from coach.models import CoachingOutput


def test_run_coaching_produces_output(make_week_plan, make_week_actual):
    plan = make_week_plan(week_number=3, phase="base")
    current = make_week_actual(week_number=3, total_distance_km=25)
    history = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=23),
        current,
    ]
    result = run_coaching(plan, current, history)
    assert isinstance(result, CoachingOutput)
    assert result.week_number == 3
    assert result.phase == "base"
    assert result.compliance_score >= 0
    assert result.readiness is not None
    assert isinstance(result.trends, list)
    assert isinstance(result.adjustments, list)
    assert isinstance(result.alerts, list)


def test_run_coaching_with_minimal_data(make_week_plan, make_week_actual):
    plan = make_week_plan(week_number=1, phase="base")
    current = make_week_actual(week_number=1, total_distance_km=26)
    result = run_coaching(plan, current, [current])
    assert isinstance(result, CoachingOutput)
    assert result.week_number == 1


def test_run_coaching_recovery_week(make_week_plan, make_week_actual):
    plan = make_week_plan(week_number=4, phase="base", is_recovery=True)
    current = make_week_actual(week_number=4, total_distance_km=18)
    history = [
        make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 4)
    ] + [current]
    result = run_coaching(plan, current, history)
    assert result.is_recovery_week is True


def test_to_dict(make_week_plan, make_week_actual):
    plan = make_week_plan(week_number=1)
    current = make_week_actual(week_number=1)
    result = run_coaching(plan, current, [current])
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "week_number" in d
    assert "readiness" in d
    assert "trends" in d
