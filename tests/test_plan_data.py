from __future__ import annotations

from unittest.mock import patch

from tracker.plan_data import load_plan


def _row(week_number: int, distance_km: float, workouts):
    return {
        "week_number": week_number,
        "start_date": "2026-06-29",
        "end_date": "2026-07-05",
        "phase": "specific",
        "is_recovery": False,
        "distance_km": distance_km,
        "vert_m": 600.0,
        "long_run_km": 10.0,
        "gym_sessions": 3,
        "series_type": "tempo",
        "workouts": workouts,
    }


def test_load_plan_tolerates_malformed_workouts():
    """A malformed `workouts` value (a dict instead of a list) must NOT crash row
    parsing and silently fall back to plan.json — that discarded the entire live DB
    plan in prod. The DB plan should still load, with the bad workouts ignored.
    """
    rows = [_row(18, 22.0, {"back_to_back": {"day1_km": 16}})]  # dict, not list

    with patch("tracker.db.get_plan", return_value=rows):
        plan = load_plan()

    assert len(plan) == 1                      # DB plan, not the 30-week plan.json
    assert plan[0].week_number == 18
    assert plan[0].distance_km == 22.0         # from DB (plan.json week 18 is 60)
    assert plan[0].workouts == []              # malformed workouts safely ignored


def test_load_plan_parses_well_formed_workouts():
    """A correct list of workout dicts still parses into PlannedWorkout objects."""
    rows = [_row(22, 32.0, [
        {"day": "Saturday", "type": "long_run", "description": "B2B day 1", "distance_km": 16},
        {"day": "Sunday", "type": "long_run", "description": "B2B day 2", "distance_km": 8},
    ])]

    with patch("tracker.db.get_plan", return_value=rows):
        plan = load_plan()

    assert len(plan) == 1
    assert len(plan[0].workouts) == 2
    assert plan[0].workouts[0].distance_km == 16
    assert plan[0].workouts[1].day == "Sunday"


from datetime import date as _date

from tracker.plan_data import week_for_date


def test_week_for_date_in_window():
    # PLAN_START = 2026-03-02 (Monday of week 1)
    assert week_for_date(_date(2026, 3, 2)) == 1
    assert week_for_date(_date(2026, 3, 8)) == 1   # day 6 of week 1
    assert week_for_date(_date(2026, 3, 9)) == 2   # first day of week 2
    assert week_for_date(_date(2026, 6, 10)) == 15
    assert week_for_date(_date(2026, 7, 11)) == 19


def test_week_for_date_outside_window():
    assert week_for_date(_date(2026, 3, 1)) == 0    # before PLAN_START
    assert week_for_date(_date(2026, 10, 5)) == 0   # after week 30
