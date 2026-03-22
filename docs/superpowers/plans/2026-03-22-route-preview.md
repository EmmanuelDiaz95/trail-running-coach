# Route Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a subtle SVG route watermark on running activity cards in the dashboard.

**Architecture:** During Garmin sync, fetch GPS polyline per running activity, convert to an SVG path string via equirectangular projection + RDP simplification, store in cached JSON. Dashboard renders the SVG as an 8%-opacity background behind card content.

**Tech Stack:** Python 3.9, garminconnect library, single-file HTML/JS dashboard

**Spec:** `docs/superpowers/specs/2026-03-22-route-preview-design.md`

---

### Task 1: Add `route_svg` field to GarminActivity model

**Files:**
- Modify: `tracker/models.py:36-47`

- [ ] **Step 1: Add the field**

In `tracker/models.py`, add `route_svg` as the last field of the `GarminActivity` dataclass:

```python
@dataclass
class GarminActivity:
    activity_id: str
    date: str                   # "2026-03-03"
    activity_type: str          # "running", "trail_running", "strength_training"
    name: str
    distance_km: float
    duration_seconds: float
    avg_hr: Optional[int]
    max_hr: Optional[int]
    avg_pace_min_km: Optional[float]  # minutes per km as float
    elevation_gain_m: Optional[int]
    calories: Optional[int]
    route_svg: Optional[str] = None   # SVG path d-attribute for route trace
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: All existing tests pass (the new field has a default value so nothing breaks).

- [ ] **Step 3: Commit**

```bash
git add tracker/models.py
git commit -m "feat(models): add route_svg field to GarminActivity"
```

---

### Task 2: Implement `polyline_to_svg()` with inline RDP simplification

**Files:**
- Create: `tracker/route.py`
- Create: `tests/test_route.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_route.py`:

```python
from __future__ import annotations

import re

from tracker.route import polyline_to_svg


def test_returns_none_for_empty_input():
    assert polyline_to_svg([]) is None


def test_returns_none_for_single_point():
    assert polyline_to_svg([(19.3, -99.3)]) is None


def test_returns_none_for_identical_points():
    assert polyline_to_svg([(19.3, -99.3), (19.3, -99.3), (19.3, -99.3)]) is None


def test_simple_two_point_path():
    result = polyline_to_svg([(19.0, -99.0), (19.1, -99.1)])
    assert result is not None
    assert result.startswith("M")
    assert "L" in result


def test_output_matches_svg_path_grammar():
    """Output must only contain M, L, digits, dots, commas, spaces, and minus signs."""
    points = [
        (19.30, -99.30), (19.31, -99.29), (19.32, -99.28),
        (19.33, -99.27), (19.32, -99.26), (19.31, -99.27),
    ]
    result = polyline_to_svg(points)
    assert result is not None
    assert re.match(r'^[ML0-9., -]+$', result), f"Invalid SVG path chars: {result}"


def test_fits_within_viewbox():
    """All coordinates must be within 0-240 (x) and 0-200 (y)."""
    points = [
        (19.30, -99.30), (19.35, -99.25), (19.40, -99.20),
        (19.35, -99.15), (19.30, -99.20),
    ]
    result = polyline_to_svg(points)
    assert result is not None
    # Parse all numbers from the path
    nums = re.findall(r'-?[\d.]+', result)
    coords = [float(n) for n in nums]
    # X values (even indices after M/L parsing) should be 0-240
    # Y values (odd indices) should be 0-200
    # Simple check: all values should be within padded bounds
    for v in coords:
        assert 0 <= v <= 240, f"Coordinate {v} out of viewBox bounds"


def test_rdp_reduces_point_count():
    """A straight line with many collinear points should simplify heavily."""
    # 100 points along a straight line
    points = [(19.0 + i * 0.001, -99.0 + i * 0.001) for i in range(100)]
    result = polyline_to_svg(points)
    assert result is not None
    # A straight line should simplify to just 2 points (M + L)
    l_count = result.count("L")
    assert l_count <= 5, f"Expected heavy simplification, got {l_count} L commands"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -m pytest tests/test_route.py -v 2>&1 | tail -15`

Expected: FAIL — `ModuleNotFoundError: No module named 'tracker.route'`

- [ ] **Step 3: Implement `tracker/route.py`**

Create `tracker/route.py`:

```python
from __future__ import annotations

import math
import re
from typing import Optional

# Padding inside the 240x200 viewBox
_VIEWBOX_W = 240
_VIEWBOX_H = 200
_PAD = 10

_SVG_PATH_RE = re.compile(r'^[ML0-9., -]+$')


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker line simplification."""
    if len(points) <= 2:
        return list(points)

    # Find the point with max distance from the line between first and last
    start, end = points[0], points[-1]
    max_dist = 0.0
    max_idx = 0

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    line_len_sq = dx * dx + dy * dy

    for i in range(1, len(points) - 1):
        if line_len_sq == 0:
            dist = math.hypot(points[i][0] - start[0], points[i][1] - start[1])
        else:
            t = max(0, min(1, ((points[i][0] - start[0]) * dx + (points[i][1] - start[1]) * dy) / line_len_sq))
            proj_x = start[0] + t * dx
            proj_y = start[1] + t * dy
            dist = math.hypot(points[i][0] - proj_x, points[i][1] - proj_y)
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > epsilon:
        left = _rdp(points[:max_idx + 1], epsilon)
        right = _rdp(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]


def polyline_to_svg(points: list[tuple[float, float]], epsilon: float = 1.5) -> Optional[str]:
    """Convert GPS (lat, lon) points to an SVG path d-attribute string.

    Returns None if fewer than 2 distinct points.
    Projection: equirectangular with cos(mid_lat) correction.
    Output fits within a 240x200 viewBox with 10px padding.
    """
    if len(points) < 2:
        return None

    # Deduplicate consecutive identical points
    deduped = [points[0]]
    for p in points[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    if len(deduped) < 2:
        return None

    # Equirectangular projection: correct longitude by cos(mid_latitude)
    mid_lat = sum(p[0] for p in deduped) / len(deduped)
    cos_lat = math.cos(math.radians(mid_lat))

    projected = [(p[1] * cos_lat, -p[0]) for p in deduped]  # lon→x, -lat→y (north up)

    # Normalize to viewBox
    min_x = min(p[0] for p in projected)
    max_x = max(p[0] for p in projected)
    min_y = min(p[1] for p in projected)
    max_y = max(p[1] for p in projected)

    range_x = max_x - min_x
    range_y = max_y - min_y

    if range_x == 0 and range_y == 0:
        return None

    draw_w = _VIEWBOX_W - 2 * _PAD
    draw_h = _VIEWBOX_H - 2 * _PAD

    # Scale preserving aspect ratio
    if range_x == 0:
        scale = draw_h / range_y
    elif range_y == 0:
        scale = draw_w / range_x
    else:
        scale = min(draw_w / range_x, draw_h / range_y)

    # Center within viewBox
    scaled_w = range_x * scale
    scaled_h = range_y * scale
    offset_x = _PAD + (draw_w - scaled_w) / 2
    offset_y = _PAD + (draw_h - scaled_h) / 2

    normalized = [
        ((p[0] - min_x) * scale + offset_x, (p[1] - min_y) * scale + offset_y)
        for p in projected
    ]

    # RDP simplification (epsilon is in viewBox coordinate space)
    simplified = _rdp(normalized, epsilon)

    if len(simplified) < 2:
        return None

    # Build SVG path
    parts = [f"M{simplified[0][0]:.1f},{simplified[0][1]:.1f}"]
    for p in simplified[1:]:
        parts.append(f"L{p[0]:.1f},{p[1]:.1f}")

    path = " ".join(parts)

    # Validate output
    if not _SVG_PATH_RE.match(path):
        return None

    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -m pytest tests/test_route.py -v 2>&1 | tail -15`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tracker/route.py tests/test_route.py
git commit -m "feat(route): add polyline-to-SVG conversion with RDP simplification"
```

---

### Task 3: Fetch GPS polyline during sync and populate `route_svg`

**Files:**
- Modify: `tracker/garmin_sync.py:1-174`

- [ ] **Step 1: Add imports at top of `garmin_sync.py`**

Add `import time` after `import sys` (line 5, among the stdlib imports).

Add after the existing `.config` import (line 12):

```python
from .config import ACTIVITIES_DIR, PROJECT_ROOT, RUNNING_TYPES
```

And add the route import after the models import (after line 13):

```python
from .route import polyline_to_svg
```

- [ ] **Step 2: Add `_fetch_route_svg()` helper**

Add this function after `_normalize_activity()` (after line 139):

```python
def _fetch_route_svg(client: Garmin, activity_id: str) -> str | None:
    """Fetch GPS polyline from Garmin and convert to SVG path."""
    try:
        details = client.get_activity_details(activity_id, maxpoly=500)
        poly_dto = details.get("geoPolylineDTO") or {}
        raw_points = poly_dto.get("polyline", [])
        points = [(p["lat"], p["lon"]) for p in raw_points if "lat" in p and "lon" in p]
        return polyline_to_svg(points)
    except Exception as e:
        print(f"[garmin] Warning: failed to fetch route for {activity_id}: {e}")
        return None
```

- [ ] **Step 3: Update `sync_activities()` to fetch routes and inject into raw JSON**

Replace `sync_activities()` (lines 142-160) with:

```python
def sync_activities(start_date: date, end_date: date, profile_id: str = DEFAULT_PROFILE) -> list[GarminActivity]:
    """Pull activities from Garmin Connect for a date range and cache them."""
    client = _get_client(profile_id)

    raw_activities = client.get_activities_by_date(
        start_date.isoformat(),
        end_date.isoformat(),
    )

    # Fetch route SVG for running activities
    for raw in raw_activities:
        activity_type = (raw.get("activityType", {}).get("typeKey", "") or "").lower()
        if activity_type in RUNNING_TYPES and raw.get("hasPolyline"):
            activity_id = str(raw.get("activityId", ""))
            raw["route_svg"] = _fetch_route_svg(client, activity_id)
            time.sleep(0.5)  # Rate limit
        else:
            raw["route_svg"] = None

    activities = [_normalize_activity(a) for a in raw_activities]

    # Cache raw JSON
    act_dir = _get_activities_dir(profile_id)
    act_dir.mkdir(parents=True, exist_ok=True)
    cache_file = act_dir / f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    with open(cache_file, "w") as f:
        json.dump(raw_activities, f, indent=2, default=str)

    return activities
```

- [ ] **Step 4: Update `_normalize_activity()` to read `route_svg`**

In the `return GarminActivity(...)` block (line 127-139), add `route_svg` as the last field:

```python
    return GarminActivity(
        activity_id=str(raw.get("activityId", "")),
        date=activity_date,
        activity_type=activity_type,
        name=raw.get("activityName", ""),
        distance_km=distance_km,
        duration_seconds=round(duration, 1),
        avg_hr=raw.get("averageHR"),
        max_hr=raw.get("maxHR"),
        avg_pace_min_km=avg_pace,
        elevation_gain_m=raw.get("elevationGain"),
        calories=raw.get("calories"),
        route_svg=raw.get("route_svg"),
    )
```

- [ ] **Step 5: Verify tests pass**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add tracker/garmin_sync.py
git commit -m "feat(sync): fetch GPS polyline and generate route_svg during sync"
```

---

### Task 4: Pass `route` field through serve.py

**Files:**
- Modify: `dashboard/serve.py:199-211`

- [ ] **Step 1: Add `route` to the activity entry dict**

In `dashboard/serve.py`, after the `"reps": None,` line (line 210), add:

```python
            "route": a.route_svg,
```

So the entry dict becomes:

```python
        entry = {
            "date": format_activity_date(a.date),
            "name": html_mod.escape(sanitize_activity_name(a.name)),
            "type": dtype,
            "dist": round(a.distance_km, 2) if a.distance_km > 0.1 else None,
            "pace": pace_str(a.duration_seconds, a.distance_km),
            "hr": a.avg_hr,
            "elev": a.elevation_gain_m if a.elevation_gain_m and a.elevation_gain_m > 0 else None,
            "cal": a.calories,
            "dur": round(a.duration_seconds / 60),
            "sets": None,
            "reps": None,
            "route": a.route_svg,
        }
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/serve.py
git commit -m "feat(serve): pass route_svg field to dashboard API"
```

---

### Task 5: Render route SVG background on activity cards

**Files:**
- Modify: `dashboard/dashboard.html:463-467` (CSS)
- Modify: `dashboard/dashboard.html:1319-1324` (JS)

- [ ] **Step 1: Add `position: relative; overflow: hidden;` to `.activity-card` CSS**

In `dashboard/dashboard.html`, change line 463-467 from:

```css
  .activity-card {
    min-width: 300px; max-width: 300px; background: var(--bg-card);
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 24px; scroll-snap-align: start;
    transition: border-color 0.3s ease, transform 0.25s ease; flex-shrink: 0;
  }
```

to:

```css
  .activity-card {
    min-width: 300px; max-width: 300px; background: var(--bg-card);
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 24px; scroll-snap-align: start;
    transition: border-color 0.3s ease, transform 0.25s ease; flex-shrink: 0;
    position: relative; overflow: hidden;
  }
```

- [ ] **Step 2: Add route SVG rendering in the activity card JS**

In `dashboard/dashboard.html`, replace lines 1319-1324:

```javascript
    html += '<div class="activity-card">'
      + '<div class="activity-card__date">' + a.date + '</div>'
      + '<div class="activity-card__name">' + a.name + '</div>'
      + '<div class="activity-card__type"><span class="activity-card__type-dot ' + dotClass(a.type) + '"></span>'
      + typeLabel(a.type) + durLabel + '</div>'
      + '<div class="activity-card__stats">' + stats + '</div></div>';
```

with:

```javascript
    let routeSvg = '';
    if (isRun && a.route) {
      routeSvg = '<svg viewBox="0 0 240 200" preserveAspectRatio="xMidYMid meet"'
        + ' style="position:absolute;inset:10px;width:calc(100% - 20px);'
        + 'height:calc(100% - 20px);opacity:0.08;z-index:0;" fill="none"'
        + ' stroke="var(--copper)" stroke-width="2.5"'
        + ' stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="' + a.route + '"/></svg>';
    }

    html += '<div class="activity-card">' + routeSvg
      + '<div style="position:relative;z-index:1;">'
      + '<div class="activity-card__date">' + a.date + '</div>'
      + '<div class="activity-card__name">' + a.name + '</div>'
      + '<div class="activity-card__type"><span class="activity-card__type-dot ' + dotClass(a.type) + '"></span>'
      + typeLabel(a.type) + durLabel + '</div>'
      + '<div class="activity-card__stats">' + stats + '</div>'
      + '</div></div>';
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/dashboard.html
git commit -m "feat(dashboard): render route SVG watermark on running activity cards"
```

---

### Task 6: Sync week 3 with route data and update cache

- [ ] **Step 1: Re-sync week 3 to fetch route polylines**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python scripts/sync.py --week 3`

Expected: Output shows activities synced. Route fetching logs may appear for running activities.

- [ ] **Step 2: Verify route_svg is in the cached JSON**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -c "
import json
data = json.load(open('data/activities/2026-03-16_2026-03-22.json'))
for a in data:
    name = a.get('activityName','')
    route = a.get('route_svg')
    print(f'{name}: route_svg={'yes (' + str(len(route)) + ' chars)' if route else 'null'}')
"`

Expected: Trail running and running activities show `route_svg=yes (300-600 chars)`. Strength activities show `route_svg=null`.

- [ ] **Step 3: Update `weeks_cache.json` with route data**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && source venv/bin/activate && python -c "
import json
from datetime import date, datetime
from tracker.plan_data import get_week
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual, compliance_score
from tracker.alerts import generate_alerts

wp = get_week(3)
activities = load_cached_activities(date.fromisoformat(wp.start_date), date.fromisoformat(wp.end_date))
actual = build_week_actual(activities, 3)
score = compliance_score(wp, actual)

wp2 = get_week(2)
acts2 = load_cached_activities(date.fromisoformat(wp2.start_date), date.fromisoformat(wp2.end_date))
prev_actual = build_week_actual(acts2, 2) if acts2 else None
alerts = generate_alerts(wp, actual, prev_actual)

cache = json.load(open('dashboard/weeks_cache.json'))
for i, w in enumerate(cache):
    if w.get('number') == 3:
        cache[i]['actual'] = {
            'distance_km': actual.total_distance_km,
            'vert_m': actual.total_vert_m,
            'long_run_km': actual.longest_run_km,
            'gym': actual.gym_count,
            'series': actual.series_detected
        }
        cache[i]['compliance'] = score
        cache[i]['activities'] = [
            {
                'date': datetime.strptime(a.date, '%Y-%m-%d').strftime('%a, %b %d').replace(' 0', ' '),
                'name': a.name,
                'type': 'trail' if a.activity_type in ('running','trail_running','treadmill_running') else ('strength' if a.activity_type in ('strength_training','indoor_cardio') else 'cycling'),
                'dist': a.distance_km if a.distance_km > 0.1 else None,
                'pace': (str(int(a.avg_pace_min_km)) + ':' + str(int((a.avg_pace_min_km - int(a.avg_pace_min_km)) * 60)).zfill(2)) if a.avg_pace_min_km else None,
                'hr': a.avg_hr,
                'elev': a.elevation_gain_m if a.elevation_gain_m and a.elevation_gain_m > 0 else None,
                'cal': a.calories,
                'dur': int(a.duration_seconds / 60) if a.duration_seconds else None,
                'sets': None,
                'reps': None,
                'route': a.route_svg,
            }
            for a in activities
        ]
        cache[i]['alerts'] = [
            {'level': a.level, 'message': a.message}
            for a in alerts
        ]
        print(f'Updated week 3: compliance={score}%')
        routes = sum(1 for a in activities if a.route_svg)
        print(f'Activities with routes: {routes}')
        break

with open('dashboard/weeks_cache.json', 'w') as f:
    json.dump(cache, f, indent=2)
print('Cache saved.')
"
`

Expected: Shows activities with routes count > 0.

- [ ] **Step 4: Commit and push**

```bash
git add dashboard/weeks_cache.json
git commit -m "data: update week 3 cache with route SVG data"
git push origin main
```

---

### Task 7: Verify on Railway

- [ ] **Step 1: Wait for Railway deploy**

Wait ~2 minutes for Railway auto-deploy after push.

- [ ] **Step 2: Verify visually**

Open `https://personal-web-production-140b.up.railway.app` and check Week 3 activity cards. Running/trail cards should show the subtle copper route watermark behind the stats. Strength cards should show no watermark.
