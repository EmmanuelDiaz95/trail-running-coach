#!/usr/bin/env python3
"""Pull activities from Garmin Connect for a given week."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.plan_data import get_current_week, get_week_dates
from tracker.garmin_sync import sync_activities


def main():
    parser = argparse.ArgumentParser(description="Sync Garmin activities")
    parser.add_argument("--week", type=int, help="Week number (1-30). Defaults to current week.")
    args = parser.parse_args()

    week = args.week or get_current_week()
    if week is None:
        print("Not currently in the training plan window. Use --week N to specify.")
        sys.exit(1)

    start, end = get_week_dates(week)
    print(f"Syncing Week {week}: {start} to {end}")

    activities = sync_activities(start, end)

    if not activities:
        print("No activities found for this period.")
        return

    print(f"\nFound {len(activities)} activities:\n")
    for a in activities:
        hr_str = f"HR:{a.avg_hr}" if a.avg_hr else ""
        vert_str = f"↑{a.elevation_gain_m}m" if a.elevation_gain_m else ""
        print(f"  {a.date}  {a.activity_type:<20} {a.distance_km:>6.1f}km  {hr_str:>8}  {vert_str}")

    print(f"\nCached to data/activities/")


if __name__ == "__main__":
    main()
