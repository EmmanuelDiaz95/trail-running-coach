from __future__ import annotations

from coach.adjustments import generate_adjustments


def test_no_adjustments_high_compliance(make_week_plan, make_week_actual):
    plan = make_week_plan(distance_km=25, gym_sessions=3)
    actual = make_week_actual(total_distance_km=24, gym_count=3)
    result = generate_adjustments(plan, actual, compliance_score=92)
    assert len(result) == 0


def test_major_deviation(make_week_plan, make_week_actual):
    plan = make_week_plan(distance_km=30, gym_sessions=3)
    actual = make_week_actual(total_distance_km=12, gym_count=1)
    result = generate_adjustments(plan, actual, compliance_score=45)
    assert len(result) > 0
    assert any(a.priority == "high" for a in result)
    assert any("significant" in a.message.lower() or "major" in a.message.lower() for a in result)


def test_moderate_deviation(make_week_plan, make_week_actual):
    plan = make_week_plan(distance_km=30, gym_sessions=3)
    actual = make_week_actual(total_distance_km=20, gym_count=2)
    result = generate_adjustments(plan, actual, compliance_score=70)
    assert len(result) > 0
    assert any(a.priority == "medium" for a in result)


def test_overtraining_flag(make_week_plan, make_week_actual):
    plan = make_week_plan(distance_km=25)
    actual = make_week_actual(total_distance_km=38)
    result = generate_adjustments(plan, actual, compliance_score=100)
    assert any(a.category == "volume" for a in result)


def test_insufficient_recovery(make_week_plan, make_week_actual):
    plan = make_week_plan(distance_km=20, is_recovery=True)
    actual = make_week_actual(total_distance_km=28)
    prev = make_week_actual(week_number=0, total_distance_km=30)
    result = generate_adjustments(plan, actual, compliance_score=85, prev_actual=prev)
    assert any(a.category == "recovery" for a in result)


def test_gym_lagging(make_week_plan, make_week_actual):
    plan = make_week_plan(gym_sessions=3)
    actual = make_week_actual(gym_count=1)
    result = generate_adjustments(plan, actual, compliance_score=75)
    assert any(a.category == "gym" for a in result)


def test_phase_transition(make_week_plan, make_week_actual):
    plan = make_week_plan(week_number=13, phase="specific")
    actual = make_week_actual(week_number=13)
    prev_plan = make_week_plan(week_number=12, phase="base")
    result = generate_adjustments(plan, actual, compliance_score=90, prev_plan=prev_plan)
    assert any(a.category == "phase_transition" for a in result)
