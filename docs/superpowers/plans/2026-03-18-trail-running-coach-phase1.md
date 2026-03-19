# Trail Running Coach — Phase 1: Rule Engine Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic rule engine that analyzes training data across multiple weeks and produces structured coaching JSON — trends, readiness scores, and plan adjustment recommendations.

**Architecture:** Six new modules (2 in tracker, 4 in coach) extending the existing Tarahumara Ultra Tracker. The tracker gains an activity classifier and multi-week data loader. The coach package contains trend analysis, readiness scoring, plan adjustments, and an orchestrating engine. A CLI entry point (`coach.py`) outputs structured coaching JSON to the terminal.

**Tech Stack:** Python 3.9, pytest, existing tracker package (models, config, analysis, alerts, plan_data, garmin_sync)

**Important:** All Python files MUST start with `from __future__ import annotations` (Python 3.9 requirement for 3.10+ type hints). Follow existing patterns: dataclasses for data objects, pure functions, defensive null checks, `| None` union syntax.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `athlete.json` | Athlete profile (weight, HR zones, race, history) |
| Create | `knowledge.json` | Coaching thresholds (ACWR zones, nutrition, trends) |
| Create | `tracker/classify.py` | Activity intensity classification (easy/tempo/intervals/gym) |
| Create | `tracker/data_loader.py` | Load & merge activities across multiple weeks |
| Create | `coach/__init__.py` | Package init |
| Create | `coach/models.py` | Coaching output dataclasses |
| Create | `coach/trends.py` | Multi-week trend analysis |
| Create | `coach/readiness.py` | ACWR calculation and fatigue scoring |
| Create | `coach/adjustments.py` | Plan adjustment recommendations |
| Create | `coach/engine.py` | Orchestrator — runs all modules, assembles coaching JSON |
| Create | `coach.py` | CLI entry point |
| Create | `tests/conftest.py` | Shared test fixtures (fake activities, plans) |
| Create | `tests/test_classify.py` | Tests for intensity classifier |
| Create | `tests/test_data_loader.py` | Tests for multi-week loader |
| Create | `tests/test_trends.py` | Tests for trend analyzer |
| Create | `tests/test_readiness.py` | Tests for readiness scorer |
| Create | `tests/test_adjustments.py` | Tests for plan adjuster |
| Create | `tests/test_engine.py` | Tests for engine orchestrator |
| Modify | `requirements.txt` | Add pytest |

---

## Task 1: Test Infrastructure & Data Files

**Files:**
- Modify: `requirements.txt`
- Create: `pytest.ini`
- Create: `athlete.json`
- Create: `knowledge.json`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add pytest to requirements and install**

Add `pytest>=7.0.0` to `requirements.txt` and install:

```
Run: source venv/bin/activate && pip install pytest>=7.0.0
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: Create athlete.json**

```json
{
  "name": "Emmanuel Diaz",
  "date_of_birth": "1995-12-15",
  "weight_kg": 70,
  "altitude_m": 2600,
  "hr_zones": {
    "z1": [0, 125],
    "z2": [125, 145],
    "z3": [145, 160],
    "z4": [160, 175],
    "z5": [175, 200]
  },
  "race": {
    "name": "Ultra Trail Tarahumara",
    "date": "2026-10-02",
    "distance_km": 59,
    "vert_m": 2400
  },
  "history": {
    "recent_race": {
      "distance_km": 33.3,
      "vert_m": 1184,
      "time": "4:38:00",
      "avg_hr": 149
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

- [ ] **Step 4: Create knowledge.json**

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
      "light": [5, 7],
      "moderate": [6, 8],
      "heavy": [8, 10],
      "extreme": [10, 12]
    },
    "protein_g_per_kg": [1.4, 1.8],
    "race_carb_per_hr_g": [60, 90]
  },
  "altitude_adjustments": {
    "extra_hydration_ml": [500, 1000],
    "pace_penalty_pct_per_1000ft": [1.5, 3.0]
  },
  "fatigue_signals": {
    "resting_hr_elevation_pct": 7
  },
  "trends": {
    "lookback_weeks": 4,
    "min_weeks_for_trend": 3
  }
}
```

- [ ] **Step 5: Create tests/__init__.py and tests/conftest.py with shared fixtures**

`tests/__init__.py`: empty file.

`tests/conftest.py`:

```python
from __future__ import annotations

import pytest
from datetime import date
from tracker.models import GarminActivity, WeekPlan, WeekActual, Alert


@pytest.fixture
def make_activity():
    """Factory fixture for creating GarminActivity with sensible defaults."""
    def _make(
        activity_type: str = "running",
        distance_km: float = 5.0,
        avg_hr: int = 140,
        max_hr: int = 155,
        elevation_gain_m: int = 50,
        duration_seconds: int = 1800,
        dt: date | None = None,
    ) -> GarminActivity:
        return GarminActivity(
            activity_id="1",
            date=(dt or date(2026, 3, 2)).isoformat(),
            activity_type=activity_type,
            name="Test Run",
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            avg_hr=avg_hr,
            max_hr=max_hr,
            avg_pace_min_km=duration_seconds / 60 / distance_km if distance_km else 0,
            elevation_gain_m=elevation_gain_m,
            calories=300,
        )
    return _make


@pytest.fixture
def make_week_plan():
    """Factory fixture for creating WeekPlan."""
    def _make(
        week_number: int = 1,
        phase: str = "base",
        is_recovery: bool = False,
        distance_km: float = 27.0,
        vert_m: float = 400.0,
        long_run_km: float = 14.0,
        gym_sessions: int = 3,
        series_type: str | None = "tempo",
    ) -> WeekPlan:
        start = date(2026, 3, 2)
        from datetime import timedelta
        start_dt = start + timedelta(weeks=week_number - 1)
        end_dt = start_dt + timedelta(days=6)
        return WeekPlan(
            week_number=week_number,
            start_date=start_dt.isoformat(),
            end_date=end_dt.isoformat(),
            phase=phase,
            is_recovery=is_recovery,
            distance_km=distance_km,
            vert_m=vert_m,
            long_run_km=long_run_km,
            gym_sessions=gym_sessions,
            series_type=series_type,
            workouts=[],
        )
    return _make


@pytest.fixture
def make_week_actual():
    """Factory fixture for creating WeekActual."""
    def _make(
        week_number: int = 1,
        total_distance_km: float = 26.0,
        total_vert_m: int = 700,
        longest_run_km: float = 14.0,
        gym_count: int = 3,
        series_detected: bool = True,
        activities: list | None = None,
    ) -> WeekActual:
        return WeekActual(
            week_number=week_number,
            total_distance_km=total_distance_km,
            total_vert_m=total_vert_m,
            longest_run_km=longest_run_km,
            gym_count=gym_count,
            series_detected=series_detected,
            activities=activities or [],
        )
    return _make
```

- [ ] **Step 6: Verify test infrastructure works**

Run: `source venv/bin/activate && python -m pytest tests/ -v --co`

Expected: pytest collects 0 tests, no import errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini athlete.json knowledge.json tests/
git commit -m "chore: add test infrastructure, athlete profile, and knowledge config"
```

---

## Task 2: Activity Intensity Classifier

**Files:**
- Create: `tracker/classify.py`
- Create: `tests/test_classify.py`

The classifier extends the existing `_is_series()` heuristic from `alerts.py` into a full intensity classification. It reuses that logic for consistency.

- [ ] **Step 1: Write failing tests**

`tests/test_classify.py`:

```python
from __future__ import annotations

from tracker.classify import classify_intensity


def test_easy_run(make_activity):
    """Run with low HR, not series -> easy."""
    act = make_activity(activity_type="running", distance_km=8.0, avg_hr=135, max_hr=148)
    assert classify_intensity(act) == "easy"


def test_tempo_run(make_activity):
    """Run with avg HR in Z3 range, duration > 20min, not series."""
    act = make_activity(
        activity_type="running", distance_km=10.0,
        avg_hr=150, max_hr=158, duration_seconds=3000,
    )
    assert classify_intensity(act) == "tempo"


def test_interval_run(make_activity):
    """Run matching _is_series heuristic -> intervals."""
    act = make_activity(
        activity_type="running", distance_km=8.0,
        avg_hr=145, max_hr=175,  # gap=30, max>=160
    )
    assert classify_intensity(act) == "intervals"


def test_interval_short_high_hr(make_activity):
    """Short run with high avg HR -> intervals."""
    act = make_activity(
        activity_type="running", distance_km=6.0,
        avg_hr=160, max_hr=178,
    )
    assert classify_intensity(act) == "intervals"


def test_gym_activity(make_activity):
    """Strength training -> gym."""
    act = make_activity(activity_type="strength_training", distance_km=0)
    assert classify_intensity(act) == "gym"


def test_other_activity(make_activity):
    """Non-run, non-gym -> other."""
    act = make_activity(activity_type="cycling", distance_km=30.0)
    assert classify_intensity(act) == "other"


def test_trail_run_easy(make_activity):
    """trail_running type with low HR -> easy."""
    act = make_activity(activity_type="trail_running", distance_km=12.0, avg_hr=138, max_hr=150)
    assert classify_intensity(act) == "easy"


def test_long_run(make_activity):
    """Long easy run -> long_run (uses threshold param)."""
    act = make_activity(
        activity_type="running", distance_km=16.0,
        avg_hr=140, max_hr=152,
    )
    assert classify_intensity(act, long_run_threshold_km=14.0) == "long_run"


def test_intensity_factor_mapping(make_activity):
    """Verify intensity factors for ACWR calculation."""
    from tracker.classify import INTENSITY_FACTORS

    assert INTENSITY_FACTORS["easy"] == 1.0
    assert INTENSITY_FACTORS["tempo"] == 1.5
    assert INTENSITY_FACTORS["intervals"] == 2.0
    assert INTENSITY_FACTORS["long_run"] == 1.2
    assert INTENSITY_FACTORS["gym"] == 0.8
    assert INTENSITY_FACTORS["other"] == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classify.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'tracker.classify'`

- [ ] **Step 3: Implement classifier**

`tracker/classify.py`:

```python
from __future__ import annotations

from tracker.models import GarminActivity
from tracker.analysis import _is_series
from tracker import config


INTENSITY_FACTORS: dict[str, float] = {
    "easy": 1.0,
    "tempo": 1.5,
    "intervals": 2.0,
    "long_run": 1.2,
    "gym": 0.8,
    "other": 0.5,
}


def classify_intensity(
    activity: GarminActivity,
    long_run_threshold_km: float | None = None,
) -> str:
    """Classify a GarminActivity into an intensity type.

    Reuses the _is_series() heuristic from analysis.py for consistency
    with the existing alert engine.

    Args:
        activity: The activity to classify.
        long_run_threshold_km: If set, easy runs above this distance
            are classified as long_run instead.

    Returns:
        One of: easy, tempo, intervals, long_run, gym, other
    """
    # Gym
    if activity.activity_type in config.GYM_TYPES:
        return "gym"

    # Not a run
    if activity.activity_type not in config.RUNNING_TYPES:
        return "other"

    # Intervals (reuses existing series heuristic from analysis.py)
    if _is_series(activity):
        return "intervals"

    # Tempo: avg HR in upper range, sustained effort (> 20 min)
    if (activity.avg_hr is not None
            and activity.avg_hr >= 145
            and activity.duration_seconds > 1200):
        return "tempo"

    # Long run
    if long_run_threshold_km is not None and activity.distance_km >= long_run_threshold_km:
        return "long_run"

    # Default: easy
    return "easy"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_classify.py -v`

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tracker/classify.py tests/test_classify.py
git commit -m "feat(coach): add activity intensity classifier with tests"
```

---

## Task 3: Multi-Week Data Loader

**Files:**
- Create: `tracker/data_loader.py`
- Create: `tests/test_data_loader.py`

- [ ] **Step 1: Write failing tests**

`tests/test_data_loader.py`:

```python
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tracker.data_loader import load_week_range
from tracker.models import WeekActual


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary activities directory with cached data."""
    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    return activities_dir


def _write_cache(cache_dir: Path, start: date, end: date, activities: list[dict]):
    """Write a fake cache file matching garmin_sync naming convention."""
    filename = f"{start.isoformat()}_{end.isoformat()}.json"
    (cache_dir / filename).write_text(json.dumps(activities))


def _make_raw_activity(activity_type="running", distance_m=5000, avg_hr=140, max_hr=155, elevation=50):
    """Create a raw Garmin API activity dict (pre-normalization)."""
    return {
        "activityId": 1,
        "startTimeLocal": "2026-03-02 08:00:00",
        "activityType": {"typeKey": activity_type},
        "activityName": "Test",
        "distance": distance_m,
        "duration": 1800,
        "averageHR": avg_hr,
        "maxHR": max_hr,
        "averageRunningCadenceInStepsPerMinute": 170,
        "averageSpeed": 2.78,
        "elevationGain": elevation,
        "calories": 300,
    }


def _patch_activities_dir(monkeypatch, cache_dir):
    """Monkeypatch garmin_sync to use temp cache directory.

    load_week_range calls garmin_sync.load_cached_activities, which
    internally calls _get_activities_dir. We patch the config constant
    that _get_activities_dir reads from.
    """
    monkeypatch.setattr("tracker.config.ACTIVITIES_DIR", cache_dir)


def test_load_single_week(cache_dir, monkeypatch):
    """Load one week of cached data."""
    _patch_activities_dir(monkeypatch, cache_dir)
    _write_cache(cache_dir, date(2026, 3, 2), date(2026, 3, 8), [
        _make_raw_activity(distance_m=10000),
        _make_raw_activity(activity_type="strength_training", distance_m=0),
    ])
    results = load_week_range(1, 1)
    assert len(results) == 1
    assert results[0].week_number == 1
    assert results[0].total_distance_km == pytest.approx(10.0, abs=0.1)
    assert results[0].gym_count == 1


def test_load_multiple_weeks(cache_dir, monkeypatch):
    """Load 3 weeks of cached data."""
    _patch_activities_dir(monkeypatch, cache_dir)
    for week in range(1, 4):
        start = date(2026, 3, 2 + (week - 1) * 7)
        end = date(2026, 3, 8 + (week - 1) * 7)
        _write_cache(cache_dir, start, end, [_make_raw_activity(distance_m=week * 5000)])
    results = load_week_range(1, 3)
    assert len(results) == 3
    assert results[0].week_number == 1
    assert results[2].week_number == 3


def test_missing_week_skipped(cache_dir, monkeypatch):
    """Missing weeks are skipped, not errored."""
    _patch_activities_dir(monkeypatch, cache_dir)
    # Only cache week 1 and 3, skip 2
    _write_cache(cache_dir, date(2026, 3, 2), date(2026, 3, 8), [_make_raw_activity()])
    _write_cache(cache_dir, date(2026, 3, 16), date(2026, 3, 22), [_make_raw_activity()])
    results = load_week_range(1, 3)
    assert len(results) == 2
    assert results[0].week_number == 1
    assert results[1].week_number == 3


def test_empty_range(cache_dir, monkeypatch):
    """No cached data returns empty list."""
    _patch_activities_dir(monkeypatch, cache_dir)
    results = load_week_range(1, 4)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_data_loader.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'tracker.data_loader'`

- [ ] **Step 3: Implement data loader**

`tracker/data_loader.py`:

```python
from __future__ import annotations

from tracker.plan_data import get_week_dates
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
from tracker.models import WeekActual


def load_week_range(start_week: int, end_week: int) -> list[WeekActual]:
    """Load and merge activity data across a range of weeks.

    Gracefully handles missing weeks — returns only weeks that have
    cached data. Callers check len(results) >= min_weeks before
    computing trends.

    Args:
        start_week: First week number (inclusive).
        end_week: Last week number (inclusive).

    Returns:
        List of WeekActual for weeks that have cached data,
        ordered by week number.
    """
    results: list[WeekActual] = []
    for week_num in range(start_week, end_week + 1):
        start_date, end_date = get_week_dates(week_num)
        activities = load_cached_activities(start_date, end_date)
        if activities is None:
            continue
        week_actual = build_week_actual(activities, week_num)
        results.append(week_actual)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_data_loader.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tracker/data_loader.py tests/test_data_loader.py
git commit -m "feat(coach): add multi-week data loader with tests"
```

---

## Task 4: Coach Models

**Files:**
- Create: `coach/__init__.py`
- Create: `coach/models.py`

- [ ] **Step 1: Create coach package**

`coach/__init__.py`: empty file.

`coach/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrendResult:
    """Result of analyzing a single metric across multiple weeks."""
    metric: str
    trend: str  # improving, plateauing, declining, erratic, insufficient_data
    values: list[float]
    delta: str  # human-readable delta (e.g., "-0:22/km over 4 weeks")
    significance: str  # on_track, watch, concern


@dataclass
class ReadinessScore:
    """Fatigue and readiness assessment."""
    score: int  # 1-10
    acwr: float
    acwr_zone: str  # optimal, caution, danger, expected_recovery, detraining
    recommendation: str  # push, maintain, back_off
    signals: list[str] = field(default_factory=list)


@dataclass
class Adjustment:
    """A plan adjustment recommendation."""
    category: str  # volume, intensity, gym, series, recovery, phase_transition
    priority: str  # high, medium, low
    message: str


@dataclass
class ComplianceBreakdown:
    """Detailed compliance for one metric."""
    planned: float | None
    actual: float | None
    pct: int | None


@dataclass
class CoachingOutput:
    """Complete coaching output for one week — the contract between
    the rule engine and the LLM narrator."""
    week_number: int
    generated_at: str
    phase: str
    is_recovery_week: bool
    days_to_race: int

    compliance_score: int
    compliance_breakdown: dict[str, ComplianceBreakdown]

    readiness: ReadinessScore | None
    trends: list[TrendResult]
    adjustments: list[Adjustment]
    alerts: list[dict]  # reuses existing Alert as dict

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for the narrator."""
        from dataclasses import asdict
        return asdict(self)
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from coach.models import CoachingOutput, TrendResult, ReadinessScore, Adjustment; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add coach/__init__.py coach/models.py
git commit -m "feat(coach): add coaching output dataclasses"
```

---

## Task 5: Trend Analyzer

**Files:**
- Create: `coach/trends.py`
- Create: `tests/test_trends.py`

- [ ] **Step 1: Write failing tests**

`tests/test_trends.py`:

```python
from __future__ import annotations

from coach.trends import analyze_trends
from coach.models import TrendResult


def test_improving_distance(make_week_actual):
    """Increasing distance across weeks -> improving."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=23),
        make_week_actual(week_number=3, total_distance_km=25),
        make_week_actual(week_number=4, total_distance_km=28),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "improving"
    assert dist.values == [20, 23, 25, 28]


def test_declining_distance(make_week_actual):
    """Decreasing distance across weeks -> declining."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=27),
        make_week_actual(week_number=3, total_distance_km=24),
        make_week_actual(week_number=4, total_distance_km=20),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "declining"


def test_plateauing_distance(make_week_actual):
    """Stable distance -> plateauing."""
    weeks = [
        make_week_actual(week_number=i, total_distance_km=25)
        for i in range(1, 5)
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "plateauing"


def test_insufficient_data(make_week_actual):
    """Fewer than min_weeks -> insufficient_data."""
    weeks = [make_week_actual(week_number=1, total_distance_km=20)]
    results = analyze_trends(weeks, min_weeks=3)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "insufficient_data"


def test_erratic_distance(make_week_actual):
    """Zigzag pattern -> erratic."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=18),
        make_week_actual(week_number=4, total_distance_km=32),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "erratic"


def test_multiple_metrics_returned(make_week_actual):
    """Should return trends for all 6 tracked metrics."""
    weeks = [
        make_week_actual(week_number=i, total_distance_km=20 + i, total_vert_m=300 + i * 50)
        for i in range(1, 5)
    ]
    results = analyze_trends(weeks)
    metrics = {t.metric for t in results}
    assert "weekly_distance" in metrics
    assert "weekly_vert" in metrics
    assert "longest_run" in metrics
    assert "gym_frequency" in metrics
    assert "easy_run_avg_hr" in metrics
    assert "easy_run_avg_pace" in metrics


def test_empty_weeks():
    """Empty list -> all insufficient_data."""
    results = analyze_trends([])
    assert all(t.trend == "insufficient_data" for t in results)


def test_easy_run_hr_with_activities(make_week_actual, make_activity):
    """Easy run HR trend extracted from activity data."""
    weeks = []
    for i in range(1, 5):
        activities = [
            make_activity(activity_type="running", distance_km=8, avg_hr=150 - i * 2, max_hr=158),
        ]
        weeks.append(make_week_actual(week_number=i, activities=activities))
    results = analyze_trends(weeks)
    hr_trend = next(t for t in results if t.metric == "easy_run_avg_hr")
    # HR decreasing = improving aerobic fitness
    assert hr_trend.trend in ("improving", "declining")  # declining values = improving fitness
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trends.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'coach.trends'`

- [ ] **Step 3: Implement trend analyzer**

`coach/trends.py`:

```python
from __future__ import annotations

from tracker.models import WeekActual
from tracker.analysis import _is_series, classify_activity
from coach.models import TrendResult


def _easy_run_avg_hr(week: WeekActual) -> float:
    """Average HR across easy runs (non-series runs) in a week."""
    easy_hrs = [
        a.avg_hr for a in week.activities
        if classify_activity(a) == "run"
        and not _is_series(a)
        and a.avg_hr is not None
    ]
    return sum(easy_hrs) / len(easy_hrs) if easy_hrs else 0.0


def _easy_run_avg_pace(week: WeekActual) -> float:
    """Average pace (min/km) across easy runs in a week."""
    easy_paces = [
        a.avg_pace_min_km for a in week.activities
        if classify_activity(a) == "run"
        and not _is_series(a)
        and a.avg_pace_min_km is not None
        and a.avg_pace_min_km > 0
    ]
    return sum(easy_paces) / len(easy_paces) if easy_paces else 0.0


def _classify_trend(values: list[float], threshold_pct: float = 5.0) -> str:
    """Classify a series of values into a trend category.

    Args:
        values: Ordered list of metric values (oldest first).
        threshold_pct: Minimum percentage change to count as
            improving or declining.

    Returns:
        One of: improving, declining, plateauing, erratic
    """
    if len(values) < 2:
        return "plateauing"

    # Count direction changes
    increases = 0
    decreases = 0
    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            increases += 1
        elif values[i] < values[i - 1]:
            decreases += 1

    total_changes = increases + decreases
    if total_changes == 0:
        return "plateauing"

    # Erratic: direction changes frequently (neither mostly up nor mostly down)
    consistency = max(increases, decreases) / total_changes
    if consistency < 0.7 and total_changes >= 3:
        return "erratic"

    # Overall change
    first, last = values[0], values[-1]
    if first == 0:
        pct_change = 100.0 if last > 0 else 0.0
    else:
        pct_change = ((last - first) / abs(first)) * 100

    if pct_change > threshold_pct and increases >= decreases:
        return "improving"
    elif pct_change < -threshold_pct and decreases >= increases:
        return "declining"
    else:
        return "plateauing"


def _format_delta(values: list[float], unit: str = "") -> str:
    """Format the overall change as a human-readable string."""
    if len(values) < 2:
        return "no data"
    first, last = values[0], values[-1]
    diff = last - first
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}{unit} over {len(values)} weeks"


def _significance(trend: str) -> str:
    """Map trend to significance level."""
    if trend == "improving":
        return "on_track"
    elif trend in ("declining", "erratic"):
        return "concern"
    elif trend == "plateauing":
        return "watch"
    return "watch"


def analyze_trends(
    weeks: list[WeekActual],
    min_weeks: int = 3,
) -> list[TrendResult]:
    """Analyze trends across multiple weeks of training data.

    Args:
        weeks: List of WeekActual ordered by week_number.
        min_weeks: Minimum weeks required to compute a trend.

    Returns:
        List of TrendResult, one per tracked metric.
    """
    metrics = [
        ("weekly_distance", lambda w: w.total_distance_km, "km"),
        ("weekly_vert", lambda w: w.total_vert_m, "m"),
        ("longest_run", lambda w: w.longest_run_km, "km"),
        ("gym_frequency", lambda w: float(w.gym_count), ""),
        ("easy_run_avg_hr", lambda w: _easy_run_avg_hr(w), "bpm"),
        ("easy_run_avg_pace", lambda w: _easy_run_avg_pace(w), "min/km"),
    ]

    results: list[TrendResult] = []
    for metric_name, extractor, unit in metrics:
        if len(weeks) < min_weeks:
            results.append(TrendResult(
                metric=metric_name,
                trend="insufficient_data",
                values=[],
                delta="insufficient data",
                significance="watch",
            ))
            continue

        values = [extractor(w) for w in weeks]
        trend = _classify_trend(values)
        delta = _format_delta(values, unit)
        sig = _significance(trend)

        results.append(TrendResult(
            metric=metric_name,
            trend=trend,
            values=values,
            delta=delta,
            significance=sig,
        ))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_trends.py -v`

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add coach/trends.py tests/test_trends.py
git commit -m "feat(coach): add multi-week trend analyzer with tests"
```

---

## Task 6: Readiness Scorer

**Files:**
- Create: `coach/readiness.py`
- Create: `tests/test_readiness.py`

- [ ] **Step 1: Write failing tests**

`tests/test_readiness.py`:

```python
from __future__ import annotations

from coach.readiness import compute_readiness
from tracker.models import WeekPlan


def test_optimal_acwr(make_week_actual, make_week_plan):
    """ACWR in optimal range -> push/maintain."""
    # 4 weeks of consistent ~25km -> chronic ~25, acute ~25, ACWR ~1.0
    weeks = [make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 5)]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "optimal"
    assert result.recommendation in ("push", "maintain")
    assert 0.8 <= result.acwr <= 1.3


def test_high_acwr_danger(make_week_actual, make_week_plan):
    """Sudden volume spike -> danger zone."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=20),
        make_week_actual(week_number=3, total_distance_km=20),
        make_week_actual(week_number=4, total_distance_km=45),  # huge spike
    ]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone in ("caution", "danger")
    assert result.recommendation == "back_off"


def test_recovery_week_low_acwr_expected(make_week_actual, make_week_plan):
    """Low ACWR during recovery week -> expected_recovery, not detraining."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=30),
        make_week_actual(week_number=4, total_distance_km=15),  # recovery
    ]
    plan = make_week_plan(week_number=4, is_recovery=True)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "expected_recovery"
    assert result.recommendation == "maintain"


def test_detraining_non_recovery(make_week_actual, make_week_plan):
    """Low ACWR on non-recovery week -> detraining."""
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=30),
        make_week_actual(week_number=4, total_distance_km=10),  # unplanned drop
    ]
    plan = make_week_plan(week_number=4, is_recovery=False)
    result = compute_readiness(weeks, plan)
    assert result.acwr_zone == "detraining"
    assert result.recommendation == "push"


def test_insufficient_data(make_week_actual, make_week_plan):
    """Single week -> still produces a score with warning signal."""
    weeks = [make_week_actual(week_number=1, total_distance_km=25)]
    plan = make_week_plan(week_number=1)
    result = compute_readiness(weeks, plan)
    assert result.score > 0
    assert any("insufficient" in s.lower() or "limited" in s.lower() for s in result.signals)


def test_score_range(make_week_actual, make_week_plan):
    """Score is always 1-10."""
    weeks = [make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 5)]
    plan = make_week_plan(week_number=4)
    result = compute_readiness(weeks, plan)
    assert 1 <= result.score <= 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_readiness.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'coach.readiness'`

- [ ] **Step 3: Implement readiness scorer**

`coach/readiness.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from tracker.models import WeekActual, WeekPlan
from coach.models import ReadinessScore
from tracker import config


def _load_acwr_zones() -> dict:
    """Load ACWR zone thresholds from knowledge.json."""
    knowledge_path = config.PROJECT_ROOT / "knowledge.json"
    if knowledge_path.exists():
        with open(knowledge_path) as f:
            data = json.load(f)
        return data.get("acwr_zones", {})
    return {"optimal": [0.8, 1.3], "caution": [1.3, 1.5], "danger": [1.5, None]}


def _compute_training_load(week: WeekActual) -> float:
    """Compute a simplified training load for a week.

    Uses distance as the primary load metric. A more sophisticated
    version would weight by intensity (from classify.py), but this
    provides a useful baseline without requiring per-activity
    classification of historical data.
    """
    return week.total_distance_km + (week.total_vert_m / 100) + (week.gym_count * 3)


def _compute_acwr(weeks: list[WeekActual]) -> float | None:
    """Compute Acute:Chronic Workload Ratio.

    Acute = most recent week's load.
    Chronic = average load over all provided weeks.

    Returns None if insufficient data.
    """
    if not weeks:
        return None

    loads = [_compute_training_load(w) for w in weeks]
    acute = loads[-1]
    chronic = sum(loads) / len(loads)

    if chronic == 0:
        return None

    return round(acute / chronic, 2)


def _classify_acwr(acwr: float, is_recovery: bool, zones: dict) -> tuple[str, str]:
    """Classify ACWR into zone and recommendation.

    Returns (zone_name, recommendation).
    """
    optimal = zones.get("optimal", [0.8, 1.3])
    caution = zones.get("caution", [1.3, 1.5])

    if acwr < optimal[0]:
        if is_recovery:
            return "expected_recovery", "maintain"
        return "detraining", "push"
    elif acwr <= optimal[1]:
        return "optimal", "maintain" if acwr > 1.1 else "push"
    elif acwr <= (caution[1] or 1.5):
        return "caution", "back_off"
    else:
        return "danger", "back_off"


def compute_readiness(
    weeks: list[WeekActual],
    plan: WeekPlan,
) -> ReadinessScore:
    """Compute readiness score from training history.

    Args:
        weeks: Training history ordered by week_number (oldest first).
            Ideally 4 weeks, but works with fewer.
        plan: Current week's plan (for recovery week detection).

    Returns:
        ReadinessScore with ACWR, zone classification, and recommendation.
    """
    zones = _load_acwr_zones()
    signals: list[str] = []

    acwr = _compute_acwr(weeks)
    if acwr is None:
        return ReadinessScore(
            score=5, acwr=0.0, acwr_zone="unknown",
            recommendation="maintain",
            signals=["No training data available"],
        )

    if len(weeks) < 4:
        signals.append(f"Limited data ({len(weeks)} weeks) — ACWR accuracy improves with 4+ weeks")

    zone, recommendation = _classify_acwr(acwr, plan.is_recovery, zones)

    # Build signals
    if zone == "expected_recovery":
        signals.append("Recovery week — low ACWR is expected and healthy")
    elif zone == "detraining":
        signals.append("Volume has dropped significantly — consider increasing if not intentional")
    elif zone == "caution":
        signals.append("Training load is elevated — monitor fatigue closely")
    elif zone == "danger":
        signals.append("Training load spike detected — high injury risk, reduce volume")

    # Score: map ACWR zone to 1-10 score
    if zone == "optimal":
        score = 8 if acwr <= 1.1 else 7
    elif zone in ("expected_recovery", "detraining"):
        score = 6
    elif zone == "caution":
        score = 4
    elif zone == "danger":
        score = 2
    else:
        score = 5

    return ReadinessScore(
        score=score,
        acwr=acwr,
        acwr_zone=zone,
        recommendation=recommendation,
        signals=signals,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_readiness.py -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add coach/readiness.py tests/test_readiness.py
git commit -m "feat(coach): add ACWR readiness scorer with tests"
```

---

## Task 7: Plan Adjuster

**Files:**
- Create: `coach/adjustments.py`
- Create: `tests/test_adjustments.py`

- [ ] **Step 1: Write failing tests**

`tests/test_adjustments.py`:

```python
from __future__ import annotations

from coach.adjustments import generate_adjustments
from coach.models import Adjustment


def test_no_adjustments_high_compliance(make_week_plan, make_week_actual):
    """Compliance > 80% and no issues -> no adjustments."""
    plan = make_week_plan(distance_km=25, gym_sessions=3)
    actual = make_week_actual(total_distance_km=24, gym_count=3)
    result = generate_adjustments(plan, actual, compliance_score=92)
    assert len(result) == 0


def test_major_deviation(make_week_plan, make_week_actual):
    """Compliance < 60% -> high priority adjustment."""
    plan = make_week_plan(distance_km=30, gym_sessions=3)
    actual = make_week_actual(total_distance_km=12, gym_count=1)
    result = generate_adjustments(plan, actual, compliance_score=45)
    assert len(result) > 0
    assert any(a.priority == "high" for a in result)
    assert any("major" in a.message.lower() or "significant" in a.message.lower() for a in result)


def test_moderate_deviation(make_week_plan, make_week_actual):
    """Compliance 60-80% -> medium priority with specific suggestions."""
    plan = make_week_plan(distance_km=30, gym_sessions=3)
    actual = make_week_actual(total_distance_km=20, gym_count=2)
    result = generate_adjustments(plan, actual, compliance_score=70)
    assert len(result) > 0
    assert any(a.priority == "medium" for a in result)


def test_overtraining_flag(make_week_plan, make_week_actual):
    """Actual >> planned -> overtraining check adjustment."""
    plan = make_week_plan(distance_km=25)
    actual = make_week_actual(total_distance_km=38)  # 52% over
    result = generate_adjustments(plan, actual, compliance_score=100)
    assert any(a.category == "volume" for a in result)


def test_insufficient_recovery(make_week_plan, make_week_actual):
    """Recovery week with high volume -> flag."""
    plan = make_week_plan(distance_km=20, is_recovery=True)
    actual = make_week_actual(total_distance_km=28)
    prev = make_week_actual(week_number=0, total_distance_km=30)
    result = generate_adjustments(plan, actual, compliance_score=85, prev_actual=prev)
    assert any(a.category == "recovery" for a in result)


def test_gym_lagging(make_week_plan, make_week_actual):
    """Missed gym sessions specifically flagged."""
    plan = make_week_plan(gym_sessions=3)
    actual = make_week_actual(gym_count=1)
    result = generate_adjustments(plan, actual, compliance_score=75)
    assert any(a.category == "gym" for a in result)


def test_phase_transition(make_week_plan, make_week_actual):
    """First week of new phase -> phase transition adjustment."""
    plan = make_week_plan(week_number=13, phase="specific")
    actual = make_week_actual(week_number=13)
    prev_plan = make_week_plan(week_number=12, phase="base")
    result = generate_adjustments(plan, actual, compliance_score=90, prev_plan=prev_plan)
    assert any(a.category == "phase_transition" for a in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_adjustments.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'coach.adjustments'`

- [ ] **Step 3: Implement plan adjuster**

`coach/adjustments.py`:

```python
from __future__ import annotations

from tracker.models import WeekPlan, WeekActual
from coach.models import Adjustment


_PHASE_DESCRIPTIONS = {
    "base": "aerobic base building — focus on consistent volume and easy effort",
    "specific": "race-specific preparation — terrain, vert, and intensity increase",
    "taper": "taper phase — volume drops, maintain intensity, trust the training",
}


def generate_adjustments(
    plan: WeekPlan,
    actual: WeekActual,
    compliance_score: int,
    prev_actual: WeekActual | None = None,
    prev_plan: WeekPlan | None = None,
) -> list[Adjustment]:
    """Generate plan adjustment recommendations.

    Does NOT modify plan.json — generates recommendations only.

    Args:
        plan: Current week's plan.
        actual: Current week's actual data.
        compliance_score: Computed compliance (0-100).
        prev_actual: Previous week's actual (for recovery check).
        prev_plan: Previous week's plan (for phase transition detection).

    Returns:
        List of Adjustment recommendations, ordered by priority.
    """
    adjustments: list[Adjustment] = []

    # Phase transition detection
    if prev_plan is not None and prev_plan.phase != plan.phase:
        desc = _PHASE_DESCRIPTIONS.get(plan.phase, plan.phase)
        adjustments.append(Adjustment(
            category="phase_transition",
            priority="medium",
            message=f"Entering {plan.phase} phase — {desc}.",
        ))

    # Major deviation
    if compliance_score < 60:
        adjustments.append(Adjustment(
            category="volume",
            priority="high",
            message=(
                f"Significant deviation from plan (compliance {compliance_score}%). "
                f"Planned {plan.distance_km}km, actual {actual.total_distance_km:.1f}km. "
                f"Focus on the key sessions next week rather than trying to make up volume."
            ),
        ))

    # Moderate deviation — identify specific lagging dimensions
    elif compliance_score < 80:
        if plan.distance_km > 0 and actual.total_distance_km / plan.distance_km < 0.8:
            adjustments.append(Adjustment(
                category="volume",
                priority="medium",
                message=(
                    f"Distance behind target: {actual.total_distance_km:.1f}km vs "
                    f"{plan.distance_km}km planned. Add an easy mid-week run to close the gap."
                ),
            ))

        if plan.gym_sessions > 0 and actual.gym_count < plan.gym_sessions:
            adjustments.append(Adjustment(
                category="gym",
                priority="medium",
                message=(
                    f"Gym sessions behind: {actual.gym_count}/{plan.gym_sessions}. "
                    f"Strength work protects against injury — prioritize next week."
                ),
            ))

    # Gym specifically lagging even with OK overall compliance
    if (compliance_score >= 60
            and plan.gym_sessions > 0
            and actual.gym_count < plan.gym_sessions - 1):
        adjustments.append(Adjustment(
            category="gym",
            priority="medium",
            message=(
                f"Only {actual.gym_count}/{plan.gym_sessions} gym sessions. "
                f"Consistent strength work is critical for downhill protection."
            ),
        ))

    # Overtraining check: actual >> planned
    if plan.distance_km > 0 and actual.total_distance_km > plan.distance_km * 1.3:
        over_pct = ((actual.total_distance_km - plan.distance_km) / plan.distance_km) * 100
        adjustments.append(Adjustment(
            category="volume",
            priority="medium",
            message=(
                f"Volume {over_pct:.0f}% above plan ({actual.total_distance_km:.1f}km vs "
                f"{plan.distance_km}km). Exceeding plan increases injury risk — "
                f"check if the extra volume was intentional."
            ),
        ))

    # Insufficient recovery
    if plan.is_recovery and prev_actual is not None:
        if prev_actual.total_distance_km > 0:
            reduction = ((prev_actual.total_distance_km - actual.total_distance_km)
                         / prev_actual.total_distance_km * 100)
            if reduction < 20:
                adjustments.append(Adjustment(
                    category="recovery",
                    priority="high",
                    message=(
                        f"Recovery week volume only reduced {reduction:.0f}% "
                        f"(target: 25-30%). Your body needs this recovery to absorb "
                        f"the training — cut back more."
                    ),
                ))

    return adjustments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_adjustments.py -v`

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add coach/adjustments.py tests/test_adjustments.py
git commit -m "feat(coach): add plan adjustment recommendations with tests"
```

---

## Task 8: Engine Orchestrator

**Files:**
- Create: `coach/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/test_engine.py`:

```python
from __future__ import annotations

from unittest.mock import patch
from coach.engine import run_coaching
from coach.models import CoachingOutput


def test_run_coaching_produces_output(make_week_plan, make_week_actual):
    """Engine produces a CoachingOutput with all fields populated."""
    plan = make_week_plan(week_number=3, phase="base")
    current = make_week_actual(week_number=3, total_distance_km=25)
    history = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=23),
        current,
    ]
    result = run_coaching(plan, current, history)
    assert isinstance(result, CoachingOutput)
    assert result.week_number == 3
    assert result.phase == "base"
    assert result.compliance_score >= 0
    assert result.readiness is not None
    assert isinstance(result.trends, list)
    assert isinstance(result.adjustments, list)
    assert isinstance(result.alerts, list)


def test_run_coaching_with_minimal_data(make_week_plan, make_week_actual):
    """Works with just current week — no history."""
    plan = make_week_plan(week_number=1, phase="base")
    current = make_week_actual(week_number=1, total_distance_km=26)
    result = run_coaching(plan, current, [current])
    assert isinstance(result, CoachingOutput)
    assert result.week_number == 1


def test_run_coaching_recovery_week(make_week_plan, make_week_actual):
    """Recovery week is flagged in output."""
    plan = make_week_plan(week_number=4, phase="base", is_recovery=True)
    current = make_week_actual(week_number=4, total_distance_km=18)
    history = [
        make_week_actual(week_number=i, total_distance_km=25) for i in range(1, 4)
    ] + [current]
    result = run_coaching(plan, current, history)
    assert result.is_recovery_week is True


def test_to_dict(make_week_plan, make_week_actual):
    """CoachingOutput serializes to dict."""
    plan = make_week_plan(week_number=1)
    current = make_week_actual(week_number=1)
    result = run_coaching(plan, current, [current])
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "week_number" in d
    assert "readiness" in d
    assert "trends" in d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'coach.engine'`

- [ ] **Step 3: Implement engine**

`coach/engine.py`:

```python
from __future__ import annotations

from datetime import datetime

from tracker.models import WeekPlan, WeekActual, Alert
from tracker.analysis import compliance_score, compute_deltas
from tracker.alerts import generate_alerts
from tracker.plan_data import days_to_race
from coach.models import CoachingOutput, ComplianceBreakdown
from coach.trends import analyze_trends
from coach.readiness import compute_readiness
from coach.adjustments import generate_adjustments


def run_coaching(
    plan: WeekPlan,
    current: WeekActual,
    history: list[WeekActual],
    prev_plan: WeekPlan | None = None,
) -> CoachingOutput:
    """Run all coaching modules and assemble the coaching output.

    Args:
        plan: Current week's plan.
        current: Current week's actual data.
        history: All available weeks (including current), oldest first.
        prev_plan: Previous week's plan (for phase transition detection).

    Returns:
        CoachingOutput with all fields populated.
    """
    # Compliance
    score = compliance_score(plan, current)
    deltas = compute_deltas(plan, current)

    breakdown: dict[str, ComplianceBreakdown] = {}
    for key in ("distance_km", "vert_m", "long_run_km", "gym_sessions"):
        d = deltas.get(key, {})
        planned = d.get("planned")
        actual = d.get("actual")
        if planned is not None and planned > 0 and actual is not None:
            pct = round(actual / planned * 100)
        else:
            pct = None
        breakdown[key] = ComplianceBreakdown(planned=planned, actual=actual, pct=pct)

    # Series is boolean (planned: bool, actual: bool) — handle separately
    series_d = deltas.get("series", {})
    series_planned = series_d.get("planned")  # bool or None
    series_actual = series_d.get("actual")    # bool or None
    if series_planned:
        breakdown["series"] = ComplianceBreakdown(
            planned=1.0 if series_planned else 0.0,
            actual=1.0 if series_actual else 0.0,
            pct=100 if series_actual else 0,
        )
    else:
        breakdown["series"] = ComplianceBreakdown(planned=None, actual=None, pct=None)

    # Alerts
    prev_actual = None
    prev_weeks: list[WeekActual] = []
    for w in history:
        if w.week_number < current.week_number:
            prev_weeks.append(w)
    if prev_weeks:
        prev_actual = prev_weeks[-1]

    alerts = generate_alerts(plan, current, prev_actual, prev_weeks or None)
    alert_dicts = [{"level": a.level, "category": a.category, "message": a.message} for a in alerts]

    # Trends
    trends = analyze_trends(history)

    # Readiness
    readiness = compute_readiness(history, plan)

    # Adjustments
    adjustments = generate_adjustments(
        plan, current, score,
        prev_actual=prev_actual,
        prev_plan=prev_plan,
    )

    return CoachingOutput(
        week_number=current.week_number,
        generated_at=datetime.now().isoformat(),
        phase=plan.phase,
        is_recovery_week=plan.is_recovery,
        days_to_race=days_to_race(),
        compliance_score=score,
        compliance_breakdown=breakdown,
        readiness=readiness,
        trends=trends,
        adjustments=adjustments,
        alerts=alert_dicts,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add coach/engine.py tests/test_engine.py
git commit -m "feat(coach): add engine orchestrator with tests"
```

---

## Task 9: CLI Entry Point

**Files:**
- Create: `coach.py`

- [ ] **Step 1: Implement CLI**

`coach.py`:

```python
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

    # Load history for trends and readiness
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)

    # Load previous week's plan for phase transition detection
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
```

- [ ] **Step 2: Verify CLI runs**

Run: `python coach.py --help`

Expected: Shows help with `status` and `report` subcommands.

Run: `python coach.py status`

Expected: Either shows coaching status for current week or "No synced data" message.

- [ ] **Step 3: Commit**

```bash
git add coach.py
git commit -m "feat(coach): add CLI entry point with status and report commands"
```

---

## Task 10: Full Test Suite Verification

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All tests pass (classify: 9, data_loader: 4, trends: 9, readiness: 6, adjustments: 7, engine: 4 = ~39 tests).

- [ ] **Step 2: Test with real data (if available)**

Run: `python coach.py report --week 1`

Expected: Prints coaching JSON for week 1 (if synced). Saves to `data/coaching/week_01_coaching.json`.

- [ ] **Step 3: Final commit with any fixes**

```bash
git add -A
git commit -m "chore: phase 1 complete — rule engine core with tests"
```

---

## Summary

After completing all tasks, the coach has:
- **6 new modules:** classify, data_loader, trends, readiness, adjustments, engine
- **~39 tests** covering all coaching logic
- **CLI** with `status` (quick view) and `report` (full JSON) commands
- **Data files:** athlete.json and knowledge.json for configuration
- **Zero LLM dependency** — Phase 1 is pure Python, no API calls needed

**Next phase:** Phase 2 adds the LLM narrator (Claude API) to turn the structured JSON into natural coaching language.
