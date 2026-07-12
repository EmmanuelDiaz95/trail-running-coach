#!/usr/bin/env python3
"""Import a Garmin Connect CSV export into the activities table under a
non-default profile. One-time, idempotent (synthetic garmin_id + ON CONFLICT)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `import scripts...` and `import tracker...` when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.csv_import import group_by_week, parse_csv  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", help="Path to the Garmin Connect CSV export")
    ap.add_argument("--profile", default="papa", help="Profile id to store under (not 'default')")
    args = ap.parse_args(argv)

    if args.profile == "default":
        print("Refusing to import into profile 'default'; use a distinct profile id.", file=sys.stderr)
        return 1

    # Imports with side effects (env, DB) happen only past the guard.
    from dotenv import load_dotenv
    from tracker import db

    load_dotenv()
    db.init_db()

    rows, errors = parse_csv(args.csv_path)
    print(f"Parsed {len(rows)} rows ({len(errors)} failed to parse).")
    for lineno, msg in errors:
        print(f"  line {lineno}: {msg}")

    total_inserted = 0
    for week, acts in sorted(group_by_week(rows).items()):
        inserted = db.save_activities(acts, week, args.profile)
        total_inserted += inserted
        print(f"  week {week}: {len(acts)} rows, {inserted} inserted, {len(acts) - inserted} skipped")

    skipped = len(rows) - total_inserted
    print(f"Done. profile='{args.profile}': {total_inserted} inserted, {skipped} skipped (duplicates).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
