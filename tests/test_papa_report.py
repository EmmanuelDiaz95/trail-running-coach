from __future__ import annotations

from dataclasses import dataclass

from scripts.papa_report import papa_compliance, week_plan_from_dict


@dataclass
class FakeActual:
    total_distance_km: float
    total_vert_m: float
    longest_run_km: float


def _plan(dist=50, vert=1800, long=30):
    return week_plan_from_dict({
        "week_number": 5, "start_date": "2026-08-10", "end_date": "2026-08-16",
        "phase": "build", "is_recovery": False, "distance_km": dist, "vert_m": vert,
        "long_run_km": long, "gym_sessions": 0, "series_type": None,
    })


def test_papa_compliance_perfect_and_over():
    p = _plan(50, 1800, 30)
    assert papa_compliance(p, FakeActual(50, 1800, 30)) == 100
    # exceeding targets still caps at 100 (no bonus for overtraining)
    assert papa_compliance(p, FakeActual(70, 3000, 40)) == 100


def test_papa_compliance_zero_and_partial():
    p = _plan(50, 1800, 30)
    assert papa_compliance(p, FakeActual(0, 0, 0)) == 0
    # hit distance fully, missed vert & long entirely -> weighted ~43%
    partial = papa_compliance(p, FakeActual(50, 0, 0))
    assert 40 <= partial <= 46


def test_papa_compliance_ignores_gym_and_series():
    # A zero-volume plan week would be undefined; a normal plan scores only the
    # three metrics that exist for papa (no gym/series inflation to 100).
    p = _plan(40, 1000, 20)
    # meeting distance+long but half the vert
    score = papa_compliance(p, FakeActual(40, 500, 20))
    assert 80 <= score <= 90  # not pinned to 100 by phantom gym/series credit
