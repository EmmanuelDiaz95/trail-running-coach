# Garmin Workout Push Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push structured series workouts from plan.json to Garmin Connect so they sync to the watch, with a dashboard button for one-click push.

**Architecture:** Raw Garmin workout JSON built from `garmin_steps` data in plan.json, POSTed via `garth.connectapi()` (the authenticated HTTP client already used by garminconnect 0.2.8). No library upgrade needed. New `tracker/workout_builder.py` module, new `POST /api/push-workout` endpoint in serve.py, new button in dashboard.html.

**Tech Stack:** Python 3.9, garth (via garminconnect 0.2.8), vanilla JS dashboard

**Spec:** `docs/superpowers/specs/2026-03-18-garmin-workout-push-design.md`

**Important:** Do NOT commit to git. All changes are local-only until manually verified.

---

## Chunk 1: Data Layer + Workout Builder

### Task 1: Add `garmin_steps` to plan.json series workouts

**Files:**
- Modify: `plan.json` (weeks 2, 3, 4 series workout entries)

- [ ] **Step 1: Add garmin_steps to Week 2 Tempo series**

In `plan.json`, find the week 2 series workout (day "friday", date "2026-03-13") and add the `garmin_steps` field:

```json
{"day": "friday", "date": "2026-03-13", "type": "series", "description": "Tempo 3x5min @ 6:30-6:45/km", "distance_km": 8, "vert_m": 110, "target_pace": "6:30-6:45", "target_hr": "155-165", "series_type": "tempo",
  "garmin_steps": {
    "warmup": {"end_condition": "distance", "value": 2.0, "hr_low": 115, "hr_high": 130},
    "repeat": 3,
    "work": {"end_condition": "time", "value_seconds": 300, "hr_low": 155, "hr_high": 165, "name": "Tempo 6:30-6:45/km"},
    "recovery": {"end_condition": "time", "value_seconds": 120, "hr_low": 0, "hr_high": 140, "name": "Easy jog recovery"},
    "cooldown": {"end_condition": "distance", "value": 1.5, "hr_low": 115, "hr_high": 130}
  }
}
```

- [ ] **Step 2: Add garmin_steps to Week 3 Hills series**

Find week 3 series workout (day "friday", date "2026-03-20") and add:

```json
"garmin_steps": {
  "warmup": {"end_condition": "distance", "value": 1.5, "hr_low": 115, "hr_high": 130},
  "repeat": 5,
  "work": {"end_condition": "time", "value_seconds": 240, "hr_low": 155, "hr_high": 170, "name": "UPHILL 5-7%, strong push"},
  "recovery": {"end_condition": "time", "value_seconds": 180, "hr_low": 0, "hr_high": 145, "name": "Jog/walk down, full recovery"},
  "cooldown": {"end_condition": "distance", "value": 1.5, "hr_low": 115, "hr_high": 130}
}
```

- [ ] **Step 3: Add garmin_steps to Week 4 Fartlek series**

Find week 4 series workout (day "friday", date "2026-03-27") and add:

```json
"garmin_steps": {
  "warmup": {"end_condition": "distance", "value": 2.0, "hr_low": 115, "hr_high": 130},
  "repeat": 6,
  "work": {"end_condition": "time", "value_seconds": 60, "hr_low": 160, "hr_high": 170, "name": "Fast 6:15-6:30, fun effort"},
  "recovery": {"end_condition": "time", "value_seconds": 120, "hr_low": 0, "hr_high": 140, "name": "Easy jog recovery"},
  "cooldown": {"end_condition": "distance", "value": 2.0, "hr_low": 115, "hr_high": 130}
}
```

- [ ] **Step 4: Validate plan.json is still valid JSON**

Run: `cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running && python3 -c "import json; json.load(open('plan.json')); print('OK')"`
Expected: `OK`

---

### Task 2: Create `tracker/workout_builder.py` — JSON builder

**Files:**
- Create: `tracker/workout_builder.py`

- [ ] **Step 1: Create the module with `build_garmin_workout()`**

Create `tracker/workout_builder.py` with the function that converts a plan.json series workout dict into a Garmin Connect workout JSON dict:

```python
from __future__ import annotations

import json
from pathlib import Path
from .config import PROJECT_ROOT

SPORT_TYPE_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

# Garmin step type IDs
STEP_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}
STEP_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_RECOVERY = {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4}
STEP_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}

# End condition IDs
COND_DISTANCE = {"conditionTypeId": 1, "conditionTypeKey": "distance", "displayOrder": 1, "displayable": True}
COND_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
COND_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}

# Target type for HR
TARGET_HR = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
TARGET_NONE = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}


def _end_condition(step_data: dict) -> tuple[dict, int]:
    """Return (endCondition dict, endConditionValue) from a garmin_steps entry."""
    if step_data["end_condition"] == "distance":
        return COND_DISTANCE, int(step_data["value"] * 1000)  # km to meters
    else:
        return COND_TIME, int(step_data.get("value_seconds", step_data.get("value", 0)))


def _hr_target(step_data: dict) -> tuple[dict, int, int]:
    """Return (targetType, targetValueOne, targetValueTwo) for HR zone."""
    hr_low = step_data.get("hr_low", 0)
    hr_high = step_data.get("hr_high", 0)
    if hr_low == 0 and hr_high == 0:
        return TARGET_NONE, None, None
    return TARGET_HR, hr_low, hr_high


def _estimate_duration(steps: dict) -> int:
    """Estimate total workout duration in seconds from garmin_steps."""
    total = 0
    # Warmup: assume 6:00/km for distance, or seconds for time
    wu = steps["warmup"]
    if wu["end_condition"] == "distance":
        total += int(wu["value"] * 360)  # ~6 min/km
    else:
        total += wu.get("value_seconds", 0)
    # Repeats
    repeats = steps["repeat"]
    work = steps["work"]
    recovery = steps["recovery"]
    work_secs = work.get("value_seconds", 0) if work["end_condition"] == "time" else int(work.get("value", 0) * 360)
    rec_secs = recovery.get("value_seconds", 0) if recovery["end_condition"] == "time" else int(recovery.get("value", 0) * 360)
    total += repeats * (work_secs + rec_secs)
    # Cooldown
    cd = steps["cooldown"]
    if cd["end_condition"] == "distance":
        total += int(cd["value"] * 360)
    else:
        total += cd.get("value_seconds", 0)
    return total


def build_garmin_workout(workout: dict, week_num: int) -> dict:
    """Convert a plan.json series workout with garmin_steps to Garmin API format."""
    gs = workout["garmin_steps"]
    name = f"{workout['description']} W{week_num}"

    # Warmup step
    wu_cond, wu_val = _end_condition(gs["warmup"])
    wu_target, wu_v1, wu_v2 = _hr_target(gs["warmup"])
    warmup_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": dict(STEP_WARMUP),
        "endCondition": dict(wu_cond),
        "endConditionValue": wu_val,
        "description": "Warm Up",
        "targetType": dict(wu_target),
    }
    if wu_v1 is not None:
        warmup_step["targetValueOne"] = wu_v1
        warmup_step["targetValueTwo"] = wu_v2

    # Work step (inside repeat)
    w_cond, w_val = _end_condition(gs["work"])
    w_target, w_v1, w_v2 = _hr_target(gs["work"])
    work_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": dict(STEP_INTERVAL),
        "endCondition": dict(w_cond),
        "endConditionValue": w_val,
        "description": gs["work"].get("name", "Work"),
        "targetType": dict(w_target),
    }
    if w_v1 is not None:
        work_step["targetValueOne"] = w_v1
        work_step["targetValueTwo"] = w_v2

    # Recovery step (inside repeat)
    r_cond, r_val = _end_condition(gs["recovery"])
    r_target, r_v1, r_v2 = _hr_target(gs["recovery"])
    recovery_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 2,
        "stepType": dict(STEP_RECOVERY),
        "endCondition": dict(r_cond),
        "endConditionValue": r_val,
        "description": gs["recovery"].get("name", "Recovery"),
        "targetType": dict(r_target),
    }
    if r_v1 is not None:
        recovery_step["targetValueOne"] = r_v1
        recovery_step["targetValueTwo"] = r_v2

    # Repeat group
    repeat_count = gs["repeat"]
    repeat_group = {
        "type": "RepeatGroupDTO",
        "stepOrder": 2,
        "stepType": dict(STEP_REPEAT),
        "numberOfIterations": repeat_count,
        "endCondition": dict(COND_ITERATIONS),
        "endConditionValue": repeat_count,
        "smartRepeat": False,
        "workoutSteps": [work_step, recovery_step],
    }

    # Cooldown step
    cd_cond, cd_val = _end_condition(gs["cooldown"])
    cd_target, cd_v1, cd_v2 = _hr_target(gs["cooldown"])
    cooldown_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 3,
        "stepType": dict(STEP_COOLDOWN),
        "endCondition": dict(cd_cond),
        "endConditionValue": cd_val,
        "description": "Cool Down",
        "targetType": dict(cd_target),
    }
    if cd_v1 is not None:
        cooldown_step["targetValueOne"] = cd_v1
        cooldown_step["targetValueTwo"] = cd_v2

    return {
        "workoutName": name,
        "sportType": dict(SPORT_TYPE_RUNNING),
        "estimatedDurationInSecs": _estimate_duration(gs),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": dict(SPORT_TYPE_RUNNING),
            "workoutSteps": [warmup_step, repeat_group, cooldown_step],
        }],
    }
```

- [ ] **Step 2: Verify the builder produces correct JSON for all 3 series**

Run:
```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python3 -c "
import json
from pathlib import Path
plan = json.load(open('plan.json'))
from tracker.workout_builder import build_garmin_workout
for w in plan['weeks']:
    for wo in w.get('workouts', []):
        if wo.get('garmin_steps'):
            result = build_garmin_workout(wo, w['week_number'])
            steps = result['workoutSegments'][0]['workoutSteps']
            repeat = steps[1]
            print(f'W{w[\"week_number\"]} {result[\"workoutName\"]}')
            print(f'  Steps: warmup + {repeat[\"numberOfIterations\"]}x(work+recovery) + cooldown')
            print(f'  Duration: {result[\"estimatedDurationInSecs\"]}s')
            print(f'  Warmup endVal: {steps[0][\"endConditionValue\"]}')
            print(f'  Work endVal: {repeat[\"workoutSteps\"][0][\"endConditionValue\"]}')
            print(f'  Recovery endVal: {repeat[\"workoutSteps\"][1][\"endConditionValue\"]}')
            print()
"
```

Expected output:
```
W2 Tempo 3x5min @ 6:30-6:45/km W2
  Steps: warmup + 3x(work+recovery) + cooldown
  Duration: 2520s
  Warmup endVal: 2000
  Work endVal: 300
  Recovery endVal: 120

W3 Hill repeats 5x4min uphill W3
  Steps: warmup + 5x(work+recovery) + cooldown
  Duration: 3180s
  Warmup endVal: 1500
  Work endVal: 240
  Recovery endVal: 180

W4 Fartlek 6x1min @ 6:15-6:30 W4
  Steps: warmup + 6x(work+recovery) + cooldown
  Duration: 2520s
  Warmup endVal: 2000
  Work endVal: 60
  Recovery endVal: 120
```

---

### Task 3: Add `push_workout()` — Garmin API integration

**Files:**
- Modify: `tracker/workout_builder.py`

- [ ] **Step 1: Add helper to find series workout from plan.json**

Add this function to `tracker/workout_builder.py`:

```python
def _load_series_workout(week_num: int) -> dict | None:
    """Load the series workout with garmin_steps for a given week from plan.json."""
    plan_path = PROJECT_ROOT / "plan.json"
    with open(plan_path) as f:
        plan = json.load(f)
    for w in plan["weeks"]:
        if w["week_number"] == week_num:
            for wo in w.get("workouts", []):
                if wo.get("type") == "series" and wo.get("garmin_steps"):
                    return wo
            return None
    return None


def has_garmin_workout(week_num: int) -> bool:
    """Check if a week has a series workout with garmin_steps data."""
    return _load_series_workout(week_num) is not None
```

- [ ] **Step 2: Add push_workout() function**

Add the main push function that authenticates via garth and calls the Garmin workout API:

```python
def push_workout(week_num: int, profile_id: str = "default") -> dict:
    """Build, upload, and schedule a series workout to Garmin Connect."""
    from .garmin_sync import _get_client

    # Find the series workout
    workout = _load_series_workout(week_num)
    if workout is None:
        return {"error": f"Week {week_num} has no series workout with garmin_steps"}

    # Build the Garmin JSON
    garmin_json = build_garmin_workout(workout, week_num)
    workout_name = garmin_json["workoutName"]

    # Authenticate
    try:
        client = _get_client(profile_id)
    except Exception as e:
        return {"error": f"Garmin auth failed: {str(e)}"}

    WORKOUT_HEADERS = {
        "Referer": "https://connect.garmin.com/modern/workouts",
        "nk": "NT",
    }

    # Check for existing workout with same name (idempotency)
    try:
        existing = client.garth.connectapi(
            "/proxy/workout-service/workouts",
            params={"start": 0, "limit": 100},
            headers=WORKOUT_HEADERS,
        )
        for w in existing:
            if w.get("workoutName") == workout_name:
                return {
                    "ok": True,
                    "workout_id": str(w["workoutId"]),
                    "scheduled_date": workout.get("date"),
                    "name": workout_name,
                    "already_existed": True,
                }
    except Exception:
        pass  # If listing fails, proceed with upload

    # Upload workout
    try:
        result = client.garth.connectapi(
            "/proxy/workout-service/workout",
            method="POST",
            json=garmin_json,
            headers=WORKOUT_HEADERS,
        )
        workout_id = str(result.get("workoutId", ""))
    except Exception as e:
        return {"error": f"Workout upload failed: {str(e)}"}

    # Schedule to date
    scheduled_date = workout.get("date")
    if scheduled_date and workout_id:
        try:
            client.garth.connectapi(
                f"/proxy/workout-service/schedule/{workout_id}",
                method="POST",
                json={"date": scheduled_date},
                headers=WORKOUT_HEADERS,
            )
        except Exception as e:
            return {
                "ok": True,
                "workout_id": workout_id,
                "scheduled_date": None,
                "name": workout_name,
                "warning": f"Uploaded but scheduling failed: {str(e)}",
            }

    return {
        "ok": True,
        "workout_id": workout_id,
        "scheduled_date": scheduled_date,
        "name": workout_name,
    }
```

- [ ] **Step 3: Test push_workout locally with a dry run**

First verify auth works and the workout JSON is valid by testing against Garmin:

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python3 -c "
from tracker.workout_builder import push_workout
result = push_workout(3)  # Week 3 hills — past week, safe to test
print(result)
"
```

Expected: Either `{"ok": True, "workout_id": "...", ...}` or an error message we can debug. If auth fails, check `.env` credentials and token state.

---

## Chunk 2: Server Endpoint + Dashboard Button

### Task 4: Add `has_garmin_workout` flag to week JSON

**Files:**
- Modify: `dashboard/serve.py:90-127` (`build_week_json` function)
- Modify: `dashboard/serve.py:19` (imports)

- [ ] **Step 1: Import has_garmin_workout in serve.py**

Add to the imports block in `serve.py` after the existing tracker imports (around line 21):

```python
from tracker.workout_builder import has_garmin_workout
```

- [ ] **Step 2: Add flag to build_week_json result**

In `build_week_json()`, after the `result = { ... }` dict is built (around line 127, before the `if activities is None` check), add:

```python
    result["has_garmin_workout"] = has_garmin_workout(week_num)
```

- [ ] **Step 3: Add flag to future weeks in build_all_weeks_json**

In `build_all_weeks_json()`, in the future week dict (around line 235), add `has_garmin_workout` key:

```python
                "has_garmin_workout": has_garmin_workout(wn),
```

- [ ] **Step 4: Verify the flag appears in /api/weeks response**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python3 -c "
from dashboard.serve import build_week_json
for wn in [1, 2, 3, 4, 5]:
    result = build_week_json(wn)
    print(f'Week {wn}: has_garmin_workout={result.get(\"has_garmin_workout\", \"MISSING\")}')
"
```

Expected:
```
Week 1: has_garmin_workout=False
Week 2: has_garmin_workout=True
Week 3: has_garmin_workout=True
Week 4: has_garmin_workout=True
Week 5: has_garmin_workout=False
```

---

### Task 5: Add `POST /api/push-workout` endpoint

**Files:**
- Modify: `dashboard/serve.py:19` (imports — add `push_workout`)
- Modify: `dashboard/serve.py:291-297` (`do_POST` method)
- Modify: `dashboard/serve.py` (add `_handle_push_workout` method to DashboardHandler)

- [ ] **Step 1: Update import to include push_workout**

Update the import line (added in Task 4) to also import `push_workout`:

```python
from tracker.workout_builder import has_garmin_workout, push_workout
```

- [ ] **Step 2: Add routing in do_POST**

Modify `do_POST()` to route the new endpoint:

```python
    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/sync':
            self._handle_sync(parsed)
        elif parsed.path == '/api/push-workout':
            self._handle_push_workout(parsed)
        else:
            self.send_error(405, "Method not allowed")
```

- [ ] **Step 3: Add _handle_push_workout method**

Add this method to `DashboardHandler`, after `_handle_sync`:

```python
    def _handle_push_workout(self, parsed):
        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        params = parse_qs(parsed.query)
        profile_id = self._validate_profile(params)
        week_str = params.get('week', [None])[0]

        if not week_str:
            self._send_json({"error": "week parameter required"}, 400)
            return
        try:
            week_num = int(week_str)
        except ValueError:
            self._send_json({"error": "Invalid week number"}, 400)
            return
        if week_num < 1 or week_num > 30:
            self._send_json({"error": "Week must be between 1 and 30"}, 400)
            return

        # Rate limiting
        rate_key = f"push:{profile_id}:{week_num}"
        now = time.time()
        last = _last_sync_time.get(rate_key, 0)
        if now - last < SYNC_COOLDOWN_SECONDS:
            remaining = int(SYNC_COOLDOWN_SECONDS - (now - last))
            self._send_json({"error": f"Please wait {remaining}s"}, 429)
            return

        print(f"[push] Pushing workout for week {week_num}, profile '{profile_id}'...")
        result = push_workout(week_num, profile_id)

        if result.get("error"):
            print(f"[push] Failed: {result['error']}")
            self._send_json(result, 500)
        else:
            _last_sync_time[rate_key] = time.time()
            print(f"[push] Success: {result.get('name')} -> workout_id={result.get('workout_id')}")
            self._send_json(result)
```

- [ ] **Step 4: Test the endpoint locally**

Start the server and test:
```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python dashboard/serve.py &
sleep 2
curl -X POST "http://127.0.0.1:8000/api/push-workout?week=3"
kill %1
```

Expected: JSON response with `ok: true` or a descriptive error.

---

### Task 6: Add "Push to Garmin" button in dashboard.html

**Files:**
- Modify: `dashboard/dashboard.html` (CSS + JS sections)

- [ ] **Step 1: Add CSS for the push button**

Find the sync button CSS (search for `.sync-btn`) and add after it:

```css
/* Push to Garmin button */
.push-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border: 1px solid var(--copper); border-radius: 8px;
  background: transparent; color: var(--copper); cursor: pointer;
  font-size: 0.85rem; font-family: inherit; transition: all 0.2s;
  margin-top: 8px;
}
.push-btn:hover { background: var(--copper); color: var(--bg-deep); }
.push-btn--pushing { opacity: 0.6; pointer-events: none; }
.push-btn--sent { border-color: var(--forest); color: var(--forest); pointer-events: none; }
.push-btn__icon { width: 16px; height: 16px; }
```

- [ ] **Step 2: Add push button rendering in renderActivities()**

In the `renderActivities()` function, add a helper function for the push button HTML, then insert it in two places:

**First**, add this helper at the top of `renderActivities()` (after `const section = ...`):

```javascript
  function pushBtnHtml() {
    if (!w.has_garmin_workout) return '';
    const pushKey = 'pushed_w' + w.number;
    const wasPushed = localStorage.getItem(pushKey);
    if (wasPushed) {
      return '<button class="push-btn push-btn--sent" disabled>'
        + '<svg class="push-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>'
        + 'Sent to watch</button>';
    }
    return '<button class="push-btn" data-week="' + w.number + '">'
      + '<svg class="push-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12l7-7 7 7"/></svg>'
      + 'Push to Garmin</button>';
  }
```

**Second**, in the empty-state branch (when `w.activities.length === 0`), add `pushBtnHtml()` before the `return`:

```javascript
    section.innerHTML = '<div class="section-title">Activities <span class="tag tag--pending">Pending</span></div>'
      + '<div class="empty-state">...'  // existing empty state
      + pushBtnHtml();
    return;
```

**Third**, AFTER `html += '</div>';` (which closes the `activities-scroll` div) and BEFORE `section.innerHTML = html;`, add:

```javascript
  html += pushBtnHtml();
```

- [ ] **Step 3: Add push button click handler**

Add after the sync button event listener block (after `syncBtn.classList.remove('sync-btn--syncing');`), before the service worker registration:

```javascript
// ═══════════════════════════════════════════════════════
// PUSH WORKOUT BUTTON — calls /api/push-workout
// ═══════════════════════════════════════════════════════
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.push-btn');
  if (!btn || btn.classList.contains('push-btn--pushing') || btn.classList.contains('push-btn--sent')) return;

  const weekNum = btn.dataset.week;
  btn.classList.add('push-btn--pushing');
  btn.textContent = 'Pushing...';

  try {
    const headers = {};
    const apiKey = localStorage.getItem('tarahumara_api_key');
    if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;
    const profileParam = activeProfile !== 'default' ? '&profile=' + activeProfile : '';
    const res = await fetch('/api/push-workout?week=' + weekNum + profileParam, { method: 'POST', headers });
    const data = await res.json();

    if (res.status === 401) {
      const key = prompt('Enter API key:');
      if (key) { localStorage.setItem('tarahumara_api_key', key); showToast('Key saved. Tap push again.', ''); }
      btn.classList.remove('push-btn--pushing');
      btn.textContent = 'Push to Garmin';
      return;
    }

    if (data.error) {
      showToast('<strong>Push failed:</strong> ' + data.error, 'error');
      btn.classList.remove('push-btn--pushing');
      btn.textContent = 'Push to Garmin';
      return;
    }

    // Success
    localStorage.setItem('pushed_w' + weekNum, '1');
    btn.classList.remove('push-btn--pushing');
    btn.classList.add('push-btn--sent');
    btn.disabled = true;
    btn.innerHTML = '<svg class="push-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg> Sent to watch';
    const name = data.name || 'Workout';
    showToast('<strong>Pushed!</strong> ' + name + (data.scheduled_date ? ' scheduled for ' + data.scheduled_date : ''), 'success');
  } catch (e) {
    showToast('<strong>Push failed:</strong> server not reachable', 'error');
    btn.classList.remove('push-btn--pushing');
    btn.textContent = 'Push to Garmin';
  }
});
```

- [ ] **Step 4: Test the full flow in browser**

```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python dashboard/serve.py
```

Open `http://127.0.0.1:8000` in the browser. Navigate to Week 2, 3, or 4. Verify:
1. "Push to Garmin" button appears on series weeks (2, 3, 4)
2. Button does NOT appear on week 1 or week 5
3. Click the button — it should show "Pushing..." then either "Sent to watch" (success) or a toast error
4. After success, refresh the page — button should still show "Sent to watch" (localStorage persistence)
5. Navigate to a non-series week — no button shown
