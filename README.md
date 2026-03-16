# Tarahumara Ultra Tracker

Training tracker for the **Ultra Trail Tarahumara 59km** (October 2, 2026).

## Goal

Complete 59km / 2,400m D+ in Sierra Tarahumara, Chihuahua.
Predicted finish: 9:30-10:30 hours based on historical Garmin data.

## Athlete Profile

- **Location:** High altitude (~2,600m), Central Mexico
- **Race history:** Two ultras completed (33-39km range)
- **Strengths:** HR control, gym consistency (3.4x/week), trail experience
- **Area to improve:** Easy run pacing (Z2 discipline)

## 30-Week Plan Overview

| Phase | Weeks | Dates | Volume | Long Run |
|-------|-------|-------|--------|----------|
| Base (rebuild) | 1-12 | Mar 2 - May 24 | 25→50 km/wk | 14→22 km |
| Specific | 13-27 | May 25 - Sep 6 | 50→75 km/wk | 22→42 km |
| Taper | 28-30 | Sep 7 - Sep 27 | 55→25 km/wk | 22→10 km |
| **Race** | - | **Oct 2, 2026** | - | **59 km** |

Recovery weeks every 4th week with 25-30% volume reduction.

## Project Structure

```
running/
├── README.md                                    # this file
├── plan.json                                    # structured 30-week plan
├── requirements.txt                             # Python dependencies
├── .env                                         # Garmin credentials (gitignored)
├── tracker/                                     # Python package
│   ├── config.py                                # paths, constants, thresholds
│   ├── models.py                                # data models
│   ├── plan_data.py                             # plan loader + week utilities
│   ├── garmin_sync.py                           # Garmin Connect integration
│   ├── analysis.py                              # planned vs actual comparison
│   ├── alerts.py                                # rule-based alerts
│   └── report.py                                # markdown report generator
├── scripts/                                     # CLI tools
│   ├── sync.py                                  # pull Garmin data
│   ├── report.py                                # generate weekly report
│   └── status.py                                # quick dashboard
└── data/                                        # runtime data (gitignored)
    ├── activities/                              # cached Garmin JSON
    └── reports/                                 # generated weekly reports
```

## Quick Start

```bash
source venv/bin/activate

# Dashboard — current week, targets, days to race
python scripts/status.py

# Pull activities from Garmin
python scripts/sync.py --week 1

# Generate weekly report
python scripts/report.py --week 1

# Generate report with fresh Garmin data
python scripts/report.py --week 1 --sync
```

## Key Metrics Tracked

- **Compliance Score (0-100%):** distance (30%), vert (20%), long run (20%), gym (15%), series (15%)
- **Alerts:** HR drift, volume spikes, long run ratio, missed gym/series, recovery compliance

## Data Sources

- **Garmin Connect:** activities synced via `garminconnect` library
- **plan.json:** weeks 1-4 have daily workouts, weeks 5-30 have weekly targets (updated monthly)
