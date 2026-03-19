#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracker.plan_data import get_current_week, get_week, get_week_dates, days_to_race
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
from tracker.data_loader import load_week_range
from coach.engine import run_coaching


def cmd_status():
    """Quick readiness snapshot."""
    week_num = get_current_week()
    if week_num is None:
        print("Training plan has not started or has ended.")
        return

    plan = get_week(week_num)
    if plan is None:
        print(f"Week {week_num} not found in plan.")
        return

    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        print(f"No synced data for week {week_num}. Run: python scripts/sync.py --week {week_num}")
        return

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)

    output = run_coaching(plan, current, history)

    print(f"\n{'=' * 50}")
    print(f"  COACH STATUS — Week {week_num} ({plan.phase.upper()} phase)")
    print(f"  {days_to_race()} days to race")
    print(f"{'=' * 50}")
    print(f"\n  Compliance:  {output.compliance_score}%")
    if output.readiness:
        print(f"  Readiness:   {output.readiness.score}/10 ({output.readiness.acwr_zone})")
        print(f"  ACWR:        {output.readiness.acwr}")
        print(f"  Action:      {output.readiness.recommendation.upper()}")
        for sig in output.readiness.signals:
            print(f"  → {sig}")
    if output.adjustments:
        print(f"\n  Adjustments:")
        for adj in output.adjustments:
            print(f"  [{adj.priority.upper()}] {adj.message}")
    if output.alerts:
        print(f"\n  Alerts:")
        for alert in output.alerts:
            print(f"  [{alert['level']}] {alert['message']}")
    print()


def cmd_report(week_num: int | None = None):
    """Generate full coaching JSON for a week."""
    if week_num is None:
        week_num = get_current_week()
    if week_num is None:
        print("Training plan has not started or has ended.")
        return

    plan = get_week(week_num)
    if plan is None:
        print(f"Week {week_num} not found in plan.")
        return

    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        print(f"No synced data for week {week_num}. Run: python scripts/sync.py --week {week_num}")
        return

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    prev_plan = get_week(week_num - 1) if week_num > 1 else None

    output = run_coaching(plan, current, history, prev_plan=prev_plan)

    # Save coaching JSON
    coaching_dir = Path(__file__).resolve().parent / "data" / "coaching"
    coaching_dir.mkdir(parents=True, exist_ok=True)
    coaching_file = coaching_dir / f"week_{week_num:02d}_coaching.json"
    coaching_data = output.to_dict()
    with open(coaching_file, "w") as f:
        json.dump(coaching_data, f, indent=2, default=str)

    print(json.dumps(coaching_data, indent=2, default=str))
    print(f"\nSaved to {coaching_file}")


def main():
    parser = argparse.ArgumentParser(description="Trail Running Coach")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Quick readiness snapshot")

    report_parser = subparsers.add_parser("report", help="Full coaching report (JSON)")
    report_parser.add_argument("--week", type=int, default=None, help="Week number (1-30)")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "report":
        cmd_report(args.week)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
