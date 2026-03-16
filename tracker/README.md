# tracker/ — Core Python Package

The engine behind the Tarahumara Ultra Tracker. Each module handles one responsibility.

## Modules

### config.py
Constants and thresholds used across the project:
- File paths (plan.json, data directories)
- Race info (date, distance, vert)
- Alert thresholds (HR drift: 10bpm, volume spike: 10%, long run ratio: 30%)
- Compliance score weights
- Activity type mappings (which Garmin types count as "run" vs "gym")

### models.py
Dataclasses that define the data structures:
- `PlannedWorkout` — a single planned session (day, type, distance, pace, HR targets)
- `WeekPlan` — weekly plan with targets and list of workouts
- `GarminActivity` — normalized activity from Garmin (distance in km, pace in min/km)
- `WeekActual` — aggregated weekly actuals (total distance, vert, gym count, etc.)
- `Alert` — triggered alert with level, category, and message

### plan_data.py
Loads and queries the training plan:
- `load_plan()` — parse plan.json into WeekPlan objects
- `get_week(n)` — get a specific week (1-30)
- `get_current_week()` — calculate current week from today's date
- `get_week_dates(n)` — Monday-Sunday date range for a week
- `days_to_race()` — countdown to October 2, 2026

### garmin_sync.py
Garmin Connect integration:
- Auth flow: saved tokens → .env credentials → interactive prompt
- Pulls activities via `get_activities_by_date()`
- Normalizes Garmin fields (meters→km, seconds→min/km pace)
- Caches raw JSON to `data/activities/`
- Token persistence at `~/.garminconnect/`

### analysis.py
Compares actual activities against the plan:
- `classify_activity()` — maps Garmin types to run/gym/other
- `build_week_actual()` — aggregates activities into weekly totals
- `compute_deltas()` — planned vs actual with percentage differences
- `compliance_score()` — weighted 0-100 score

### alerts.py
Rule-based alert engine (6 rules):
- **HR Drift** — easy run HR >10bpm above 4-week rolling average
- **Volume Spike** — >10% increase over previous week
- **Long Run Ratio** — longest run >30% of weekly volume
- **Missed Gym** — fewer sessions than planned
- **Missed Series** — planned interval workout not detected
- **Recovery Week** — volume not reduced ≥20% in recovery weeks

### report.py
Generates markdown reports:
- Weekly summary table (planned vs actual vs delta)
- Compliance score
- Activity list with pace/HR/vert details
- Alert section
- Saves to `data/reports/week_NN.md`
