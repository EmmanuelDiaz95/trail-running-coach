# Architecture Overview

This document serves as a critical, living template designed to equip agents with a rapid and comprehensive understanding of the Tarahumara Ultra Tracker Dashboard's architecture, enabling efficient navigation and effective contribution from day one. Update this document as the codebase evolves.

## 1. Project Structure

The dashboard is a single-page static application that visualizes training data from the Tarahumara Ultra Tracker CLI system. It lives alongside the existing Python-based tracker as a complementary visualization layer.

```
running/                          # Parent project root
├── plan.json                     # Master 30-week training plan (source of truth)
├── tracker/                      # Python package (CLI backend)
│   ├── __init__.py
│   ├── config.py                 # Constants: race info, thresholds, weights
│   ├── models.py                 # Data classes: PlannedWorkout, WeekPlan, GarminActivity, WeekActual, Alert
│   ├── plan_data.py              # Plan loading/querying from plan.json
│   ├── garmin_sync.py            # Garmin Connect API integration (auth, pull, normalize)
│   ├── analysis.py               # Planned vs actual comparison, compliance scoring
│   ├── alerts.py                 # Rule-based alert engine (6 rules)
│   └── report.py                 # Markdown report generation
├── scripts/                      # CLI entry points
│   ├── sync.py                   # Pull activities from Garmin Connect
│   ├── report.py                 # Generate weekly markdown reports
│   └── status.py                 # Quick terminal dashboard
├── data/                         # Persisted data (gitignored secrets excluded)
│   ├── activities/               # Cached Garmin JSON by date range
│   │   └── YYYY-MM-DD_YYYY-MM-DD.json
│   └── reports/                  # Generated markdown reports
│       └── week_NN.md
├── dashboard/                    # << THIS PROJECT
│   ├── dashboard.html            # Single-file dashboard (HTML + CSS + JS)
│   └── ARCHITECTURE.md           # This document
└── venv/                         # Python 3.9 virtual environment
```

## 2. High-Level System Diagram

```
[Garmin Watch] --> [Garmin Connect Cloud]
                          |
                    (garminconnect lib)
                          |
                   [scripts/sync.py]
                          |
                   [data/activities/*.json]    [plan.json]
                          |                        |
                   [tracker/analysis.py] <---------+
                          |
                   [tracker/alerts.py]
                          |
              +-----------+-----------+
              |                       |
      [scripts/report.py]    [dashboard/dashboard.html]
              |                       |
      [data/reports/          [Browser - Static
       week_NN.md]             Visualization]
```

The dashboard operates as a **data-driven single-page app** with all week data embedded in a JavaScript `WEEKS` array. It reads no files at runtime — plan targets, actual metrics, activities, and alerts are hardcoded in the HTML. The entire UI below the hero header is rendered dynamically, allowing the user to switch between weeks via a dropdown selector.

**Data flow for adding new weeks**: After running `scripts/sync.py` and `scripts/report.py`, manually add the new week's data to the `WEEKS` array in `dashboard.html`. Each entry contains `plan` (targets), `actual` (recorded metrics or `null`), `compliance` (score or `null`), `activities` (array of Garmin activities), and `alerts`.

**Future path**: The dashboard could be converted to read `plan.json` and `data/activities/*.json` dynamically via a local Python server or by generating the HTML via a build script.

## 3. Core Components

### 3.1. Frontend

**Name**: Tarahumara Ultra Tracker Dashboard

**Description**: A dark-mode, single-page dashboard that visualizes training progress for a 30-week ultra marathon preparation plan. Features a week selector dropdown to browse any training week, with clear visual labeling distinguishing actual (recorded Garmin) data from planned targets. Displays race countdown, weekly compliance scores, planned-vs-actual metrics (distance, elevation, long run, gym sessions), an activity feed from Garmin, volume progression charts, and training alerts. Designed for the athlete to open in a browser for a quick visual status check.

**Technologies**: Vanilla HTML5, CSS3 (custom properties, grid, flexbox, animations), vanilla JavaScript (ES6+), Google Fonts (Syne, Outfit, JetBrains Mono). No build tools, no frameworks, no dependencies.

**Deployment**: Local file opened in browser (`open dashboard.html`). No server required.

**Key Design Decisions**:
- **Single-file architecture**: Everything in one `.html` file for portability — no build step, no asset pipeline, just open and view
- **Data-driven rendering**: All week data lives in a JavaScript `WEEKS` array. The entire dashboard below the hero is rendered dynamically via `renderAll()` → `renderSelector()`, `renderStats()`, `renderActivities()`, `renderChart()`, `renderAlerts()`. Switching weeks re-renders all sections with a fade transition
- **Week selector**: Custom dropdown component (not native `<select>`) with prev/next arrow buttons, click-to-expand panel listing all weeks, and keyboard navigation (left/right arrows, Escape to close). Each option shows distance targets, badges for recovery/series type, and whether actual data exists
- **Actual vs Planned labeling**: A `.tag` component system provides clear visual distinction throughout the dashboard:
  - `.tag--actual` (copper background): marks recorded Garmin data — appears on metric values, compliance ring, activity section headers, and chart legend
  - `.tag--planned` (gray border): marks plan targets — appears on metric values, upcoming weeks, and chart legend
  - `.tag--pending` (blue tint): marks weeks awaiting sync — appears on empty activity sections
  - Metric cards use a dual-column layout with explicit "Actual" and "Planned" labels above each value
- **Empty state handling**: Weeks without actual data show: grayed-out compliance ring with "—", single "Target" values in metrics with "Awaiting sync..." notes, dashed-border empty state card for activities, and no alerts section
- **Canyon-inspired aesthetic**: Dark mode with copper/terracotta accent palette inspired by Sierra Tarahumara geology
- **Topographic SVG background**: Subtle contour lines via inline SVG pattern, grain texture overlay for depth
- **Entrance animations**: Staggered `fadeUp` keyframes on each section (100ms delays) for polished load feel
- **Content transitions**: Switching weeks triggers a 200ms opacity fade via `.dynamic-content--fading` class, then re-renders and fades back in
- **Live countdown**: JavaScript `setInterval` updates race day countdown every second
- **Responsive**: CSS Grid layout adapts from 3-column (desktop) to single-column (mobile). Week selector dates hide on small screens

### 3.2. Backend Services

#### 3.2.1. Garmin Sync Service

**Name**: `scripts/sync.py`

**Description**: CLI script that authenticates with Garmin Connect via the `garminconnect` library, pulls activities for a given week's date range, and caches the raw JSON to `data/activities/`. Uses `garth` for token persistence at `~/.garminconnect/`.

**Technologies**: Python 3.9, `garminconnect` 0.2.8, `garth`

**Deployment**: Local CLI (`python scripts/sync.py [--week N]`)

#### 3.2.2. Analysis Engine

**Name**: `tracker/analysis.py`

**Description**: Computes weekly compliance scores by comparing planned targets (from `plan.json`) against actual aggregated data (from cached Garmin activities). Produces weighted scores across 5 dimensions: distance (30%), vert (20%), long run (20%), gym (15%), series (15%).

**Technologies**: Python 3.9, standard library only

#### 3.2.3. Alert Engine

**Name**: `tracker/alerts.py`

**Description**: Evaluates 6 rule-based alerts per week: HR drift, volume spike, long run ratio, missed gym, missed series, recovery week compliance. Each alert has a severity level (INFO, WARNING, CRITICAL).

**Technologies**: Python 3.9, standard library only

#### 3.2.4. Report Generator

**Name**: `scripts/report.py`

**Description**: Generates markdown weekly reports combining plan targets, actual metrics, compliance score, activity detail, and alerts. Saves to `data/reports/week_NN.md`.

**Technologies**: Python 3.9, standard library only

## 4. Data Stores

### 4.1. Training Plan

**Name**: Master Training Plan

**Type**: JSON file (`plan.json`)

**Purpose**: Single source of truth for the 30-week training program. Contains race metadata, weekly targets (distance, vert, long run, gym, series type), and daily workout detail for weeks 1-4.

**Key Schemas**:
- `race`: name, date, distance_km, vert_m, location
- `weeks[].week_number`, `start_date`, `end_date`, `phase`, `is_recovery`
- `weeks[].distance_km`, `vert_m`, `long_run_km`, `gym_sessions`, `series_type`
- `weeks[].workouts[]`: day, date, type, description, distance_km, vert_m, target_pace, target_hr

### 4.2. Activity Cache

**Name**: Garmin Activity Cache

**Type**: JSON files (`data/activities/YYYY-MM-DD_YYYY-MM-DD.json`)

**Purpose**: Cached raw responses from Garmin Connect API. One file per sync date range. Contains full activity metadata: distance (meters), duration (seconds), HR, elevation, pace, calories, training effect, HR zone times, exercise sets (for strength), and more.

### 4.3. Weekly Reports

**Name**: Generated Reports

**Type**: Markdown files (`data/reports/week_NN.md`)

**Purpose**: Human-readable weekly training reports with planned-vs-actual comparison tables, compliance scores, activity lists, and alert summaries.

## 5. External Integrations / APIs

**Garmin Connect**:
- **Purpose**: Source of all training activity data (runs, strength sessions, cycling, etc.)
- **Integration Method**: Python SDK (`garminconnect` library) wrapping Garmin's REST API
- **Auth**: OAuth via `garth` library, tokens persisted at `~/.garminconnect/`
- **Data pulled**: Activity list by date range (JSON)

**Google Fonts CDN**:
- **Purpose**: Typography for the dashboard (Syne, Outfit, JetBrains Mono)
- **Integration Method**: `<link>` tag in HTML head
- **Note**: Dashboard requires internet for fonts on first load; falls back to system fonts

## 6. Deployment & Infrastructure

**Cloud Provider**: None (fully local)

**Key Services Used**: Local filesystem, browser

**CI/CD Pipeline**: None currently

**Monitoring & Logging**: None — CLI scripts print to stdout

**How to view the dashboard**:
```bash
open running/dashboard/dashboard.html
# or
python -m http.server 8000 --directory running/dashboard/
```

## 7. Security Considerations

**Authentication**: Garmin Connect tokens stored locally at `~/.garminconnect/` via `garth`. Never committed to version control.

**Authorization**: N/A — single-user local application

**Data Encryption**: N/A — all data stored locally as plaintext JSON

**Key Security Practices**:
- `.garminconnect/` token directory is outside the project and not tracked
- Raw Garmin JSON in `data/activities/` contains personal location data (lat/lng) — should remain gitignored
- Dashboard HTML contains embedded personal training data — treat as private

## 8. Development & Testing Environment

**Local Setup**:
```bash
cd running/
source venv/bin/activate
pip install garminconnect   # if not already installed

# Sync latest activities
python scripts/sync.py --week 1

# Generate report
python scripts/report.py --week 1

# View dashboard
open dashboard/dashboard.html
```

**Testing Frameworks**: None currently — manual verification via CLI output and report inspection

**Code Quality Tools**: None currently

**Python Version**: 3.9.6 (macOS system Python). Use `from __future__ import annotations` for 3.10+ type hint syntax.

## 9. Future Considerations / Roadmap

- **Dynamic data loading**: Convert dashboard from hardcoded `WEEKS` array to reading `plan.json` and `data/activities/*.json` at runtime (via fetch or a build script that auto-generates the WEEKS data)
- ~~**Week navigation**: Add prev/next week controls to browse historical data~~ *(Completed — dropdown + arrows + keyboard nav)*
- ~~**Actual vs Planned labeling**: Clear visual tags distinguishing recorded data from plan targets~~ *(Completed — `.tag--actual`, `.tag--planned`, `.tag--pending` system)*
- **Compliance history chart**: Line chart showing compliance scores across all completed weeks
- **HR trend visualization**: Plot average HR per run over time to detect drift
- **Auto-refresh after sync**: Have `scripts/sync.py` trigger dashboard regeneration
- **Phase timeline**: Visual representation of all 30 weeks color-coded by phase (base, specific, taper, race)
- **PWA support**: Add service worker and manifest for offline access and home screen install
- **Dark/light theme toggle**: Currently dark-only; could add a light canyon theme variant

## 10. Project Identification

**Project Name**: Tarahumara Ultra Tracker — Dashboard

**Repository URL**: Local project (not yet published)

**Primary Contact/Team**: Project maintainer

**Date of Last Update**: 2026-03-09

## 11. Glossary / Acronyms

| Term | Definition |
|------|-----------|
| **Compliance Score** | Weighted 0-100% score measuring how closely actual training matched the plan. Weights: distance 30%, vert 20%, long run 20%, gym 15%, series 15% |
| **D+** | Elevation gain (denivelé positif), measured in meters |
| **Series** | Interval/structured workout — tempo, hills, or fartlek |
| **Tempo** | Sustained effort intervals at lactate threshold pace (~6:30-6:45/km) |
| **Fartlek** | Unstructured speed play with alternating fast/easy segments |
| **HR Drift** | Gradual increase in heart rate at the same pace, indicating fatigue |
| **Recovery Week** | Planned deload week with 20%+ volume reduction for adaptation |
| **Phase: Base** | Weeks 1-8 — building aerobic foundation and running volume |
| **Phase: Specific** | Mid-plan — race-specific training with increased vert and intensity |
| **Phase: Taper** | Pre-race volume reduction for peak performance on race day |
| **Rarámuri** | The indigenous people of Sierra Tarahumara, renowned for ultra-distance running |
| **VO2max** | Maximum rate of oxygen consumption, a key aerobic fitness indicator |
| **Tag (UI)** | Small inline badge (`.tag` CSS class) used to label data provenance: `--actual` (copper, recorded Garmin data), `--planned` (gray, plan targets), `--pending` (blue, awaiting sync) |
| **WEEKS array** | JavaScript data store in `dashboard.html` containing all week data (plan targets, actuals, activities, alerts). New weeks must be added here manually after syncing |
