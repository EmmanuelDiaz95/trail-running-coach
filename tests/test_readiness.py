from __future__ import annotations

from coach.readiness import compute_readiness


def test_optimal_acwr(make_week_actual, make_week_plan):
    weeks = [make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 5)]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "optimal"
    assert result.recommendation in ("push", "maintain")
    assert 0.8 <= result.acwr <= 1.3


def test_high_acwr_danger(make_week_actual, make_week_plan):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=20),
        make_week_actual(week_number=3, total_distance_km=20),
        make_week_actual(week_number=4, total_distance_km=45),
    ]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone in ("caution", "danger")
    assert result.recommendation == "back_off"


def test_recovery_week_low_acwr_expected(make_week_actual, make_week_plan):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=30),
        make_week_actual(week_number=4, total_distance_km=15),
    ]
    plan = make_week_plan(week_number=4, is_recovery=True)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "expected_recovery"
    assert result.recommendation == "maintain"


def test_detraining_non_recovery(make_week_actual, make_week_plan):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=30),
        make_week_actual(week_number=4, total_distance_km=10),
    ]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "detraining"
    assert result.recommendation == "push"


def test_insufficient_data(make_week_actual, make_week_plan):
    weeks = [make_week_actual(week_number=1, total_distance_km=25)]
    plan = make_week_plan(week_number=1)
    result = compute_readiness(weeks, plan)
    assert result.score > 0
    assert any("limited" in s.lower() or "insufficient" in s.lower() for s in result.signals)


def test_score_range(make_week_actual, make_week_plan):
    weeks = [make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 5)]
    plan = make_week_plan(week_number=4)
    result = compute_readiness(weeks, plan)
    assert 1 <= result.score <= 10
