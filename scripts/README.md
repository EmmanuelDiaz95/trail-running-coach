# scripts/ — CLI Tools

Command-line scripts to interact with the tracker. Run from the `running/` directory with the venv activated.

## sync.py — Pull Garmin Data

```bash
# Sync current week
python scripts/sync.py

# Sync a specific week
python scripts/sync.py --week 3
```

Downloads activities from Garmin Connect and caches the raw JSON in `data/activities/`. First run requires Garmin credentials (via `.env` file or interactive prompt). Subsequent runs use saved tokens.

## report.py — Weekly Report

```bash
# Report from cached data (run sync first)
python scripts/report.py --week 1

# Report with fresh Garmin pull
python scripts/report.py --week 1 --sync
```

Generates a markdown report comparing planned vs actual training. Includes compliance score, activity breakdown, and alerts. Reports are printed to terminal and saved to `data/reports/`.

### Example Output

```
# Week 1 Report (2026-03-02 to 2026-03-08)
Phase: Base | Recovery: No

| Metric        | Planned | Actual | Delta  |
|---------------|---------|--------|--------|
| Distance (km) | 27.0    | 26.3   | -2.6%  |
| Vert (m)      | 400     | 715    | +78.8% |
| Long Run (km) | 14.0    | 14.0   | +0.0%  |
| Gym Sessions  | 3       | 5      | +2     |

Compliance Score: 99%
```

## status.py — Quick Dashboard

```bash
python scripts/status.py
```

Shows at a glance:
- Current week number and progress bar
- Training phase (Base / Specific / Taper)
- Days until race
- This week's targets (distance, vert, long run, gym, series)
