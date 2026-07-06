#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

from datetime import date, timedelta
from tracker.plan_data import get_current_week, get_week, get_week_dates, days_to_race
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
from tracker.data_loader import load_week_range
from tracker.db import get_daily_health
from coach.engine import run_coaching
from coach.classifier import classify_question
from coach.narrator import Narrator
from coach.refresh import refresh
from coach.health_readiness import compute_health_readiness, merge_verdict


def _get_narrator() -> Narrator | None:
    """Create a Narrator if ANTHROPIC_API_KEY is set. Returns None otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    athlete_path = Path(__file__).resolve().parent / "athlete.json"
    try:
        with open(athlete_path) as f:
            athlete = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: could not load athlete profile ({e}). Narrator disabled.")
        return None
    return Narrator(api_key=api_key, athlete=athlete)


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


def cmd_report(week_num: int | None = None, regenerate: bool = False, raw_json: bool = False):
    """Generate coaching report with narrative."""
    if week_num is None:
        week_num = get_current_week()
    if week_num is None:
        print("Training plan has not started or has ended.")
        return

    coaching_dir = Path(__file__).resolve().parent / "data" / "coaching"
    coaching_dir.mkdir(parents=True, exist_ok=True)
    coaching_file = coaching_dir / f"week_{week_num:02d}_coaching.json"
    narrative_file = coaching_dir / f"week_{week_num:02d}_narrative.md"

    if regenerate:
        # Load existing coaching JSON and re-narrate
        if not coaching_file.exists():
            print(f"No coaching data for week {week_num}. Run: python coach.py report --week {week_num}")
            return
        with open(coaching_file) as f:
            coaching_data = json.load(f)
    else:
        # Generate fresh coaching data
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
        coaching_data = output.to_dict()

        with open(coaching_file, "w") as f:
            json.dump(coaching_data, f, indent=2, default=str)

    # Raw JSON mode
    if raw_json:
        print(json.dumps(coaching_data, indent=2, default=str))
        if not regenerate:
            print(f"\nSaved to {coaching_file}")
        return

    # Try to narrate
    narrator = _get_narrator()
    if narrator is None:
        print(json.dumps(coaching_data, indent=2, default=str))
        print(f"\nSaved to {coaching_file}")
        print("\nSet ANTHROPIC_API_KEY to get a coaching narrative.")
        return

    print(f"\nGenerating coaching narrative for week {week_num}...\n")
    narrative = narrator.narrate_report(coaching_data)
    print(narrative)

    # Save narrative
    with open(narrative_file, "w") as f:
        f.write(narrative)
    print(f"\n---\nSaved to {narrative_file}")


def cmd_ask(question: str):
    """Answer a free-form coaching question."""
    narrator = _get_narrator()
    if narrator is None:
        print("ANTHROPIC_API_KEY not set. Set it in .env or environment to use conversational mode.")
        return

    # Get current week's coaching data for context
    week_num = get_current_week()
    coaching_data = None

    if week_num is not None:
        coaching_file = Path(__file__).resolve().parent / "data" / "coaching" / f"week_{week_num:02d}_coaching.json"
        if coaching_file.exists():
            with open(coaching_file) as f:
                coaching_data = json.load(f)
        else:
            # Try to generate coaching data on the fly
            plan = get_week(week_num)
            if plan is not None:
                start, end = get_week_dates(week_num)
                activities = load_cached_activities(start, end)
                if activities is not None:
                    current = build_week_actual(activities, week_num)
                    lookback_start = max(1, week_num - 3)
                    history = load_week_range(lookback_start, week_num)
                    output = run_coaching(plan, current, history)
                    coaching_data = output.to_dict()

    if coaching_data is None:
        coaching_data = {"note": "No training data available yet. Answer based on general coaching knowledge."}

    category = classify_question(question)
    response = narrator.answer_question(question, category, coaching_data)
    print(f"\n{response}\n")


def cmd_refresh(silent: bool = False):
    """Self-healing data refresh: gap-fill activities + health, rebuild snapshots."""
    if silent:
        import contextlib
        with open(os.devnull, "w") as _devnull, contextlib.redirect_stdout(_devnull):
            summary = refresh()
        return summary
    summary = refresh()
    print("=== REFRESH ===")
    print(f"  Weeks synced:  {summary.weeks_synced or '—'}")
    print(f"  Health days:   {len(summary.health_days_synced)}")
    for w in summary.warnings:
        print(f"  ⚠ {w}")
    for e in summary.errors:
        print(f"  ✗ {e}")
    if summary.rate_limited:
        print(f"  🔴 Garmin rate-limited; retry in ~{summary.retry_after}s. Partial refresh.")
    return summary


def cmd_checkin():
    """Refresh, then print one merged readiness read (health + training load)."""
    cmd_refresh()

    today = date.today()
    week_num = get_current_week()
    coaching = None
    if week_num is not None:
        plan = get_week(week_num)
        start, end = get_week_dates(week_num)
        activities = load_cached_activities(start, end)
        if plan is not None and activities:
            current = build_week_actual(activities, week_num)
            history = load_week_range(max(1, week_num - 3), week_num)
            coaching = run_coaching(plan, current, history)

    rows = get_daily_health(today - timedelta(days=37), today)
    health = compute_health_readiness(rows, today)
    verdict, advice, _level = merge_verdict(health, coaching)

    print(f"\n=== CHECK-IN — {today} (semana {week_num or '—'}) ===")
    for s, txt in health.checks:
        print(f"  {s}  {txt}")
    if coaching and coaching.readiness:
        r = coaching.readiness
        print(f"  📈 Carga: readiness {r.score}/10 ({r.acwr_zone}), ACWR {r.acwr}, {r.recommendation}")
    print(f"\n  VEREDICTO: {verdict}")
    print(f"  {advice}")
    nxt = get_week((week_num or 0) + 1)
    if nxt:
        print(f"  Plan sem {(week_num or 0)+1}: {nxt.distance_km:.0f} km / larga {nxt.long_run_km:.0f} km")
    if coaching and coaching.adjustments:
        top = coaching.adjustments[0]
        print(f"  Ajuste: [{top.priority.upper()}] {top.message}")


_SUBCOMMANDS = {"status", "report", "ask", "checkin", "refresh", "-h", "--help"}


def main():
    # Handle bare question BEFORE argparse — argparse with subparsers
    # would exit(2) on unrecognized first args like "how's my week?"
    if (len(sys.argv) > 1
            and sys.argv[1] not in _SUBCOMMANDS
            and not sys.argv[1].startswith("-")):
        cmd_ask(" ".join(sys.argv[1:]))
        return

    parser = argparse.ArgumentParser(description="Trail Running Coach")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Quick readiness snapshot")

    report_parser = subparsers.add_parser("report", help="Weekly coaching narrative")
    report_parser.add_argument("--week", type=int, default=None, help="Week number (1-30)")
    report_parser.add_argument("--regenerate", action="store_true", help="Re-generate narrative from saved data")
    report_parser.add_argument("--json", action="store_true", dest="raw_json", help="Output raw JSON instead of narrative")

    ask_parser = subparsers.add_parser("ask", help="Ask a coaching question")
    ask_parser.add_argument("question", nargs="+", help="Your question")

    subparsers.add_parser("checkin", help="Refresh + merged readiness read")
    refresh_parser = subparsers.add_parser("refresh", help="Self-healing data refresh")
    refresh_parser.add_argument("--silent", action="store_true")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "report":
        cmd_report(args.week, regenerate=args.regenerate, raw_json=args.raw_json)
    elif args.command == "ask":
        cmd_ask(" ".join(args.question))
    elif args.command == "checkin":
        cmd_checkin()
    elif args.command == "refresh":
        cmd_refresh(silent=args.silent)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
