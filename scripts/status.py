#!/usr/bin/env python3
"""Quick dashboard: current week, phase, targets, days to race."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.plan_data import get_current_week, get_week, days_to_race, get_week_dates
from tracker.config import RACE_NAME, RACE_DATE, RACE_DISTANCE_KM, RACE_VERT_M, TOTAL_WEEKS


def main():
    dtr = days_to_race()
    week_num = get_current_week()

    print(f"{'='*50}")
    print(f"  TARAHUMARA ULTRA TRACKER")
    print(f"{'='*50}")
    print()
    print(f"  Race:  {RACE_NAME}")
    print(f"  Date:  {RACE_DATE}  ({dtr} days away)")
    print(f"  Goal:  {RACE_DISTANCE_KM}km / {RACE_VERT_M}m D+")
    print()

    if week_num is None:
        if dtr > 0:
            print(f"  Training starts soon. Hang tight!")
        else:
            print(f"  Race is complete. Review your reports in data/reports/")
        print(f"{'='*50}")
        return

    plan = get_week(week_num)
    if plan is None:
        print(f"  Week {week_num} not found in plan.")
        return

    start, end = get_week_dates(week_num)
    weeks_remaining = TOTAL_WEEKS - week_num
    progress = round(week_num / TOTAL_WEEKS * 100)
    bar_filled = round(progress / 5)
    bar = "#" * bar_filled + "-" * (20 - bar_filled)

    print(f"  Current Week:  {week_num} / {TOTAL_WEEKS}")
    print(f"  Progress:      [{bar}] {progress}%")
    print(f"  Dates:         {start} to {end}")
    print(f"  Phase:         {plan.phase.upper()}")
    print(f"  Recovery Week: {'YES' if plan.is_recovery else 'No'}")
    print(f"  Weeks Left:    {weeks_remaining}")
    print()
    print(f"  --- Week {week_num} Targets ---")
    print(f"  Distance:      {plan.distance_km} km")
    print(f"  Vert:          {plan.vert_m} m")
    print(f"  Long Run:      {plan.long_run_km} km")
    print(f"  Gym Sessions:  {plan.gym_sessions}")
    series_str = plan.series_type.title() if plan.series_type else "None"
    print(f"  Series:        {series_str}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
