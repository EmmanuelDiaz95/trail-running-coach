from __future__ import annotations

import json
from datetime import date, timedelta

from .config import PLAN_FILE, PLAN_START, RACE_DATE, TOTAL_WEEKS
from .models import WeekPlan, PlannedWorkout


def load_plan() -> list[WeekPlan]:
    """Load plan.json and return list of WeekPlan objects."""
    with open(PLAN_FILE) as f:
        data = json.load(f)

    weeks = []
    for w in data["weeks"]:
        workouts = [
            PlannedWorkout(
                day=wo["day"],
                date=wo.get("date"),
                type=wo["type"],
                description=wo["description"],
                distance_km=wo.get("distance_km"),
                vert_m=wo.get("vert_m"),
                target_pace=wo.get("target_pace"),
                target_hr=wo.get("target_hr"),
                series_type=wo.get("series_type"),
            )
            for wo in w.get("workouts", [])
        ]
        weeks.append(WeekPlan(
            week_number=w["week_number"],
            start_date=w["start_date"],
            end_date=w["end_date"],
            phase=w["phase"],
            is_recovery=w["is_recovery"],
            distance_km=w["distance_km"],
            vert_m=w["vert_m"],
            long_run_km=w["long_run_km"],
            gym_sessions=w["gym_sessions"],
            series_type=w.get("series_type"),
            workouts=workouts,
        ))
    return weeks


def get_week(n: int) -> WeekPlan | None:
    """Get a specific week by number (1-30)."""
    weeks = load_plan()
    for w in weeks:
        if w.week_number == n:
            return w
    return None


def get_current_week() -> int | None:
    """Return the current week number (1-30), or None if outside the plan window."""
    today = date.today()
    if today < PLAN_START:
        return None
    delta = (today - PLAN_START).days
    week_num = delta // 7 + 1
    if week_num > TOTAL_WEEKS:
        return None
    return week_num


def get_week_dates(week_number: int) -> tuple[date, date]:
    """Return (start_date, end_date) for a given week number."""
    start = PLAN_START + timedelta(weeks=week_number - 1)
    end = start + timedelta(days=6)
    return start, end


def days_to_race() -> int:
    """Return number of days until race day."""
    return (RACE_DATE - date.today()).days
