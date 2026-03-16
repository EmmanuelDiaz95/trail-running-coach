#!/usr/bin/env python3
"""Generate a weekly training report."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.plan_data import get_current_week, get_week, get_week_dates
from tracker.garmin_sync import load_cached_activities, sync_activities
from tracker.analysis import build_week_actual
from tracker.alerts import generate_alerts
from tracker.report import generate_report, save_report


def main():
    parser = argparse.ArgumentParser(description="Generate weekly training report")
    parser.add_argument("--week", type=int, help="Week number (1-30). Defaults to current week.")
    parser.add_argument("--sync", action="store_true", help="Pull fresh data from Garmin before reporting.")
    args = parser.parse_args()

    week_num = args.week or get_current_week()
    if week_num is None:
        print("Not currently in the training plan window. Use --week N to specify.")
        sys.exit(1)

    plan = get_week(week_num)
    if plan is None:
        print(f"Week {week_num} not found in plan.")
        sys.exit(1)

    start, end = get_week_dates(week_num)

    # Load or sync activities
    if args.sync:
        activities = sync_activities(start, end)
    else:
        activities = load_cached_activities(start, end)
        if activities is None:
            print(f"No cached data for week {week_num}. Run sync first or use --sync flag.")
            sys.exit(1)

    actual = build_week_actual(activities, week_num)

    # Load previous week for alert context
    prev_actual = None
    if week_num > 1:
        prev_start, prev_end = get_week_dates(week_num - 1)
        prev_activities = load_cached_activities(prev_start, prev_end)
        if prev_activities:
            prev_actual = build_week_actual(prev_activities, week_num - 1)

    # Load up to 4 prior weeks for HR drift analysis
    prev_weeks = []
    for w in range(max(1, week_num - 4), week_num):
        ws, we = get_week_dates(w)
        wa = load_cached_activities(ws, we)
        if wa:
            prev_weeks.append(build_week_actual(wa, w))

    alerts = generate_alerts(plan, actual, prev_actual, prev_weeks)
    report = generate_report(plan, actual, alerts)

    print(report)

    filepath = save_report(report, week_num)
    print(f"\nSaved to: {filepath}")


if __name__ == "__main__":
    main()
