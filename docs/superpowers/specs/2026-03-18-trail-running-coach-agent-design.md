# Trail Running Coach Agent — Design Spec

**Date:** 2026-03-18
**Author:** Emmanuel Diaz + Claude
**Status:** Draft

## Overview

An AI-powered trail running coach built as a rule engine with an LLM narrator layer. The rule engine makes deterministic coaching decisions from structured training data. The LLM (Claude API) translates those decisions into natural, coach-like language. Personalized for Emmanuel's Ultra Trail Tarahumara preparation (59km / 2,400m D+, October 2, 2026) but designed so any athlete can plug in their own `athlete.json` and `plan.json`.

### Interaction Modes

1. **Conversational** — CLI and web chat for interactive coaching Q&A
2. **Automated weekly reports** — coaching narrative generated after each Garmin sync

### Knowledge Scope

- Trail running & ultramarathon training (periodization, HR zones, altitude)
- Endurance science (aerobic base, polarized training, ACWR)
- Nutrition & fueling (daily nutrition, race-day fueling, gut training, supplements)
- Injury prevention & recovery (common injuries, strength programming, mobility)
- Mental performance (race psychology, visualization, motivation, Tarahumara culture)

### Knowledge Strategy

- **Phase 1:** Coaching expertise distilled into structured decision tables (`knowledge.json`) and a rich narrator system prompt
- **Phase 2 (future):** RAG over a library of books, research papers, and articles

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interfaces                       │
│                                                         │
│   CLI Mode                        Web Chat UI           │
│   $ coach "how's my week?"        Browser-based chat    │
│   $ coach report                  Same backend API      │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│              Python Backend (FastAPI)                     │
│                                                         │
│   /api/chat     — conversational endpoint               │
│   /api/report   — weekly coaching narrative              │
│   /api/status   — quick training snapshot                │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ Rule Engine  │ │ Existing │ │ LLM Narrator │
│ (new)        │ │ Tracker  │ │ (Claude API) │
│              │ │          │ │              │
│ • Trends     │ │ • Sync   │ │ Takes struct │
│ • Fatigue    │ │ • Alerts │ │ coaching     │
│ • Readiness  │ │ • Comply │ │ output →     │
│ • Nutrition  │ │ • Report │ │ natural      │
│ • Adjustment │ │          │ │ language     │
│ • Pacing     │ │          │ │              │
└──────────────┘ └──────────┘ └──────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  Data Layer    │
              │                │
              │ plan.json      │
              │ activities/    │
              │ athlete.json   │
              │ knowledge.json │
              └────────────────┘
```

**Dependency direction:** `coach → tracker → data` (coach imports from tracker, never the reverse)

---

## Shared Utilities

### Activity Intensity Classifier (`tracker/classify.py` — new addition to tracker)

The existing tracker classifies activities as `"run"`, `"gym"`, or `"other"`. The coach needs finer-grained intensity classification for ACWR calculation and trend analysis. This classifier extends the tracker (not the coach) because it's a data-level concern.

**Classification rules (using existing GarminActivity fields):**

| Intensity Type | Criteria | Factor |
|---------------|----------|--------|
| `easy` | Run, NOT series (per existing `_is_series()` heuristic), avg HR < Z3 ceiling | 1.0 |
| `tempo` | Run, avg HR in Z3 range, duration > 20min | 1.5 |
| `intervals` | Run, detected as series by `_is_series()` heuristic | 2.0 |
| `long_run` | Run, distance > 60% of week's longest (or > 15km), avg HR < Z3 ceiling | 1.2 |
| `gym` | Activity type in `GYM_TYPES` | 0.8 |
| `other` | Cycling, hiking, etc. | 0.5 |

The classifier reuses the existing `_is_series()` logic from `alerts.py` for consistency. HR zone thresholds come from `athlete.json`.

**"Easy run" definition** (used by both trend analyzer and existing alert engine): any run activity where `_is_series()` returns False AND avg HR is below Z3 ceiling. This definition is shared to prevent drift between the alert engine and coach.

### Multi-Week Data Loader (`tracker/data_loader.py` — new addition to tracker)

The existing `load_cached_activities()` loads one week at a time. The coach needs rolling windows across multiple weeks. New utility:

```python
def load_week_range(start_week: int, end_week: int) -> list[WeekActual]:
    """Load and merge activity data across a range of weeks.

    Gracefully handles missing weeks — returns only weeks that have
    cached data. Callers check len(results) >= min_weeks_for_trend
    before computing trends.
    """
```

**Missing data behavior:** If a week has no cached data (not synced), it is skipped. Modules that need N weeks of data check the count and degrade gracefully:
- Trend analyzer: requires `min_weeks_for_trend` (default 3). If fewer, returns `"insufficient_data"` instead of a trend.
- ACWR: if < 28 days of data, uses available data for chronic load (with a warning flag).

---

## Coaching Output Schema

The coaching JSON is the contract between the rule engine and the LLM narrator. Every module writes to a defined section of this schema.

```json
{
  "week_number": 4,
  "generated_at": "2026-03-22T10:30:00",
  "phase": "base",
  "is_recovery_week": true,
  "days_to_race": 194,

  "compliance": {
    "score": 92,
    "breakdown": {
      "distance": { "planned": 20, "actual": 19.2, "pct": 96 },
      "vert": { "planned": 300, "actual": 280, "pct": 93 },
      "long_run": { "planned": 10, "actual": 11, "pct": 110 },
      "gym": { "planned": 2, "actual": 2, "pct": 100 },
      "series": { "planned": null, "actual": null, "pct": null }
    }
  },

  "readiness": {
    "score": 7,
    "acwr": 0.72,
    "acwr_zone": "expected_recovery",
    "recommendation": "maintain",
    "signals": ["Recovery week — low ACWR is expected and healthy"]
  },

  "trends": [
    {
      "metric": "weekly_distance",
      "trend": "improving",
      "values": [21, 24, 26.7, 19.2],
      "delta": "+27% over 4 weeks (excluding recovery)",
      "significance": "on_track"
    }
  ],

  "adjustments": [],

  "alerts": [
    { "level": "INFO", "category": "long_run_ratio", "message": "Long run was 57% of weekly volume" }
  ],

  "nutrition": {
    "daily_target": { "carbs_g": "350-490", "protein_g": "98-112" },
    "training_load_category": "light",
    "race_countdown_tip": null,
    "altitude_reminder": "Extra 500-1000ml water daily at 2,600m"
  },

  "mental": {
    "phase_focus": "Building consistency habits",
    "trigger": "milestone",
    "message": "First full month of training complete. You haven't missed a gym session yet."
  },

  "pacing": null
}
```

The narrator receives this entire JSON as context. It never sees raw activity data — only pre-digested coaching outputs.

---

## Rule Engine Modules

### 1. Trend Analyzer (`coach/trends.py`)

Multi-week rolling analysis across key metrics.

**Inputs:** Cached activity data for N weeks (default 4), plan targets
**Outputs:** `TrendResult` per metric

| Metric | What it tracks | Source |
|--------|---------------|--------|
| Weekly distance | Volume trajectory | activities |
| Weekly vert | Elevation progression | activities |
| Long run distance | Longest effort trend | activities |
| Easy run avg HR | Aerobic fitness proxy | activities (filtered by type) |
| Easy run avg pace | Pace at same HR over time | activities |
| Gym frequency | Strength consistency | activities |

**Trend classifications:** `improving`, `plateauing`, `declining`, `erratic`

**Example output:**
```json
{
  "metric": "avg_easy_pace",
  "trend": "improving",
  "values": ["7:52", "7:45", "7:38", "7:30"],
  "delta": "-0:22/km over 4 weeks",
  "significance": "on_track"
}
```

### 2. Fatigue & Readiness Scorer (`coach/readiness.py`)

Calculates training load balance and outputs a readiness recommendation.

**Core metric: Acute:Chronic Workload Ratio (ACWR)**
- Acute = rolling 7-day training load (distance × intensity factor)
- Chronic = rolling 28-day training load average
- Intensity factor: easy run = 1.0, tempo = 1.5, intervals = 2.0, gym = 0.8

**ACWR zones:**
| ACWR | Zone | Recommendation |
|------|------|----------------|
| < 0.8 | Detraining | Increase volume — losing fitness |
| 0.8–1.3 | Optimal | Push or maintain |
| 1.3–1.5 | Caution | Monitor closely, reduce if fatigued |
| > 1.5 | Danger | Back off — injury risk elevated |

**Recovery week override:** If the current week is a planned recovery week (`is_recovery: true` in plan.json), ACWR < 0.8 is reclassified as `expected_recovery` instead of `detraining`. No warning is generated.

**Additional fatigue signals:**
- HR drift trend (rising across weeks = accumulated fatigue)
- Resting HR elevation > 7% above baseline
- Gym session drop-off (planned but skipped)

**Output:** `ReadinessScore` (1-10) with recommendation: `push` / `maintain` / `back_off`

### 3. Plan Adjuster (`coach/adjustments.py`)

Generates modification recommendations when reality diverges from plan.

**Rules (priority order, based on Koop's hierarchy):**
1. If compliance < 60%: flag major deviation, suggest simplified catch-up week
2. If compliance 60-80%: identify which dimensions are lagging, suggest targeted adjustments
3. If compliance > 100% in any dimension: check for overtraining signals
4. If recovery week compliance > 80% of normal week: flag insufficient recovery
5. Phase transitions: explain what changes and why entering new phase

**Does NOT modify plan.json** — generates recommendations only. Athlete decides.

### 4. Nutrition Advisor (`coach/nutrition.py`)

Phase-appropriate fueling guidance based on training load and race timeline.

**Daily targets (from knowledge.json, scaled by athlete weight and training load):**

| Training Load | Carbs (g/kg/day) | Protein (g/kg/day) |
|---------------|-------------------|---------------------|
| Light (< 5km/day) | 5–7 | 1.2–1.4 |
| Moderate (5–15km/day) | 6–8 | 1.4–1.6 |
| Heavy (15–25km/day) | 8–10 | 1.6–1.8 |
| Extreme (25km+/day) | 10–12 | 1.8–2.0 |

**Load source:** Uses the planned weekly distance from plan.json divided by training days (typically 5-6) to determine the daily category. On days with actual Garmin data, uses the actual distance instead. This avoids depending on daily workout detail (only available for weeks 1-4).

**Race timeline triggers:**
- 16 weeks out: "Start gut training — practice eating during long runs at 30-40g carbs/hr"
- 8 weeks out: "Increase to 60-80g/hr with glucose:fructose mix"
- 1 week out: "Carb loading protocol: 8-12g/kg/day for 3 days"
- Race morning: "2-4g/kg carbs 3 hours before, sodium preload 1500mg"

**Altitude-specific (Toluca 2,600m):**
- Extra hydration: +500-1000ml/day
- Iron monitoring: ferritin should be > 40 ng/mL
- Increased caloric needs: ~5-10% above sea-level baseline

### 5. Race Pacer (`coach/pacing.py`)

Race simulation and finish time prediction.

**Inputs:**
- Race profile: 59km / 2,400m D+ (from athlete.json)
- Current fitness: recent long run pace, vert rate from activities
- Altitude adjustment: pace penalty per 1,000ft

**Outputs:**
- Predicted finish time range (optimistic / realistic / conservative)
- Overall effort targets by terrain type (climb, flat, descent) — not segment-by-segment
- Aid station timing with nutrition plan (when course data becomes available)
- Updated monthly as fitness data accumulates

**Note:** Segment-by-segment pacing requires course elevation profile data, which is not yet available. Initial implementation uses overall averages by terrain type. A `race_course.json` with segment data can be added later when course details are published.

### 6. Mental Coach (`coach/mental.py`)

Phase-appropriate psychological guidance.

**Phase mapping:**
| Phase | Mental Focus |
|-------|-------------|
| Base (weeks 1-12) | Building consistency habits, process goals, training identity |
| Specific (weeks 13-27) | Race visualization, course familiarization, adversity rehearsal |
| Taper (weeks 28-30) | Confidence building, anxiety management, race-day protocols |

**Trigger-based coaching:**
- After a bad week (compliance < 70%): perspective + trend context, not just the bad number
- After a great week: celebrate, reinforce what worked
- Milestone weeks: "Longest week ever," "Halfway to race day," "First 30km long run"
- Race week: pre-race visualization script, aid station mental protocol, mantra suggestions

---

## Data Layer

### Existing (unchanged)
- `plan.json` — 30-week training plan
- `data/activities/*.json` — cached Garmin activities
- `data/reports/*.md` — weekly metric reports

### New Files

**`athlete.json`** — swappable athlete profile
```json
{
  "name": "Emmanuel Diaz",
  "date_of_birth": "1995-12-15",
  "weight_kg": 70,
  "altitude_m": 2600,
  "hr_zones": {
    "z1": [0, 125], "z2": [125, 145],
    "z3": [145, 160], "z4": [160, 175], "z5": [175, 200]
  },
  "race": {
    "name": "Ultra Trail Tarahumara",
    "date": "2026-10-02",
    "distance_km": 59,
    "vert_m": 2400
  },
  "history": {
    "recent_race": {
      "distance_km": 33.3, "vert_m": 1184,
      "time": "4:38:00", "avg_hr": 149
    },
    "baseline_weekly_km": 21
  },
  "nutrition": {
    "gut_training_start": null,
    "target_carb_per_hr": null,
    "caffeine_sensitivity": "normal"
  }
}
```

**`knowledge.json`** — coaching thresholds and rules (tunable without touching code)

**Threshold ownership:** The existing `tracker/config.py` owns alert thresholds (HR drift, volume spike, etc.) used by the tracker's alert engine. `knowledge.json` owns coaching-specific thresholds (ACWR zones, nutrition targets, trend analysis). Where values overlap (e.g., HR drift = 10bpm), `knowledge.json` imports from `config.py` at load time to maintain a single source of truth. The coach never hardcodes a value that `config.py` already defines.
```json
{
  "acwr_zones": {
    "optimal": [0.8, 1.3],
    "caution": [1.3, 1.5],
    "danger": [1.5, null]
  },
  "volume_progression": {
    "max_weekly_increase_pct": 10,
    "recovery_reduction_pct": [25, 30]
  },
  "nutrition_targets": {
    "carbs_g_per_kg": {
      "light": [5, 7], "moderate": [6, 8],
      "heavy": [8, 10], "extreme": [10, 12]
    },
    "protein_g_per_kg": [1.4, 1.8],
    "race_carb_per_hr_g": [60, 90]
  },
  "altitude_adjustments": {
    "extra_hydration_ml": [500, 1000],
    "pace_penalty_pct_per_1000ft": [1.5, 3.0]
  },
  "fatigue_signals": {
    "hr_drift_warning_bpm": 10,
    "resting_hr_elevation_pct": 7
  },
  "trends": {
    "lookback_weeks": 4,
    "min_weeks_for_trend": 3
  }
}
```

**`data/coaching/`** — persisted coaching outputs
```
data/coaching/week_01_coaching.json   # rule engine structured output
data/coaching/week_01_narrative.md    # LLM-generated coaching narrative
```

---

## LLM Narrator

### Role

The narrator is the **only** component that calls the Claude API. It does not make coaching decisions — it translates structured rule engine output into natural language.

### Coach Persona

- Experienced trail/ultra coach familiar with the Copper Canyons and Tarahumara culture
- Direct and honest — doesn't sugarcoat bad weeks, frames constructively
- Data-informed but not data-obsessed — leads with insight, backs with numbers
- Knows when to push and when to hold back
- Uses trail running language naturally (vert, bonk, negative split, power hike)
- Bilingual awareness — athlete is in Mexico

### Narrator Constraints

- **NEVER** contradicts rule engine output
- **NEVER** invents data or metrics not present in the coaching JSON
- **NEVER** gives medical advice — flags issues with "see a physio/doctor"
- **CAN** add motivational context, race perspective, connect dots between weeks
- **CAN** ask follow-up questions to clarify ambiguous user input

### Question Classification

User input is classified before routing:

| Type | Example | Route |
|------|---------|-------|
| Data question | "What was my vert last week?" | Rule engine → minimal LLM |
| Coaching question | "Should I push harder?" | Readiness + trends + adjustments → LLM narrates |
| Knowledge question | "What to eat at aid stations?" | Nutrition module + knowledge.json → LLM narrates |
| Off-topic | "Weather in Chihuahua?" | LLM responds naturally, stays in coaching lane |

**Classification method:** Keyword matching with fallback. The classifier uses keyword patterns (e.g., "last week" / "this week" + metric name → data question; "should I" / "can I" → coaching question; nutrition/food/eat/drink keywords → knowledge question). Unmatched queries fall through to the LLM with full coaching context — the narrator handles them as general coaching questions. This keeps the classifier deterministic and avoids a second API call.

**Note:** This means the narrator IS the only Claude API caller. The classifier is pure Python pattern matching.

---

## Project Structure

```
personal_health/running/
├── tracker/                    # Existing (unchanged)
│   ├── config.py
│   ├── models.py
│   ├── plan_data.py
│   ├── garmin_sync.py
│   ├── analysis.py
│   ├── alerts.py
│   └── report.py
├── coach/                      # New package
│   ├── __init__.py
│   ├── engine.py               # Orchestrator — runs modules, assembles coaching JSON
│   ├── trends.py               # Multi-week trend analysis
│   ├── readiness.py            # ACWR, fatigue scoring
│   ├── adjustments.py          # Plan modification recommendations
│   ├── nutrition.py            # Phase-appropriate fueling guidance
│   ├── pacing.py               # Race simulation, finish prediction
│   ├── mental.py               # Phase-appropriate mental coaching
│   ├── narrator.py             # Claude API wrapper
│   ├── classifier.py           # Routes user questions to modules
│   └── models.py               # Dataclasses for coaching outputs
├── api/                        # New — FastAPI backend
│   ├── __init__.py
│   ├── app.py                  # /chat, /report, /status endpoints
│   └── schemas.py              # Request/response models
├── web/                        # New — chat frontend
│   └── index.html              # Single-file chat UI
├── coach.py                    # New — CLI entry point
├── athlete.json                # New — athlete profile
├── knowledge.json              # New — coaching thresholds
├── data/
│   ├── activities/             # Existing
│   ├── reports/                # Existing
│   └── coaching/               # New — weekly coaching outputs
└── plan.json                   # Existing
```

### Dependencies (additions to existing venv)

- `anthropic` — Claude API SDK
- `fastapi` + `uvicorn` — web backend
- No frontend build tools — single HTML file

### Environment

- New `.env` entry: `ANTHROPIC_API_KEY`
- Same Python 3.9 venv
- Same `from __future__ import annotations` pattern

---

## Interfaces

### CLI

```bash
# Conversational
python coach.py "how's my week looking?"
python coach.py "should I do my long run tomorrow or Sunday?"

# Structured commands
python coach.py status          # readiness score + today's focus
python coach.py report          # weekly coaching narrative
python coach.py report --week 3 # specific week
python coach.py pacing          # race simulation

# Post-sync workflow
python scripts/sync.py --week 4 && python coach.py report --week 4
```

### Web API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Conversational coaching (question + context → response) |
| `/api/report` | GET | Weekly coaching narrative (query param: `?week=N`) |
| `/api/status` | GET | Quick readiness snapshot |

### Automated Weekly Reports

Post-sync flow:
1. `sync.py` pulls Garmin data
2. Rule engine runs all 6 modules
3. Outputs `data/coaching/week_NN_coaching.json`
4. LLM narrator generates `data/coaching/week_NN_narrative.md`

**Trigger mechanism:** Manual CLI chaining: `python scripts/sync.py --week N && python coach.py report --week N`. The coach does NOT modify `sync.py` — the two commands are independent and composable. A combined convenience script (`scripts/sync_and_coach.py`) can be added later if desired. The FastAPI `/api/sync` endpoint (Phase 3) can optionally chain the coach report after sync completes.

**LLM failure fallback:** If the Claude API call fails (rate limit, network error), the structured coaching JSON is still saved. The CLI outputs the raw JSON to terminal. The narrative can be regenerated later with `python coach.py report --week N --regenerate`.

---

## Implementation Phases

### Phase 1 — Rule Engine Core
- `trends.py`, `readiness.py`, `adjustments.py`
- `engine.py` orchestrator
- `coach.py` CLI with `status` and `report` commands
- Works without LLM — structured output to terminal
- `athlete.json` and `knowledge.json`

### Phase 2 — LLM Narrator
- `narrator.py` wrapping Claude API
- System prompt with coach persona and coaching knowledge
- `coach.py` conversational mode
- Weekly narrative generation after sync

### Phase 3 — Web Interface
- FastAPI backend replaces the existing `dashboard/serve.py` (built-in `http.server`)
- Migrates existing dashboard endpoints (`/api/weeks`, `/api/sync`) to FastAPI
- Adds coach endpoints (`/chat`, `/report`, `/status`)
- Single-file chat UI (same pattern as dashboard)
- Single Railway deployment serves both dashboard and coach

### Phase 4 — Domain Modules
- `nutrition.py`, `pacing.py`, `mental.py`
- Full `knowledge.json` with compiled research
- `classifier.py` for question routing

### Phase 5 — RAG Enhancement (future)
- Vector store for books/research
- Narrator retrieves relevant passages for knowledge questions

---

## Research References

Detailed research compiled by 4 parallel research agents is stored in:
- `docs/trail_running_coach_knowledge_base.md` — injury prevention, strength, recovery, altitude
- `docs/mental_psychology_research.md` — race psychology, visualization, motivation, Tarahumara culture
- Research agent outputs (coaching methodologies, nutrition science) to be distilled into `knowledge.json` during implementation
