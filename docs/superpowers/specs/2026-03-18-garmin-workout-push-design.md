# Garmin Workout Push — Design Spec

**Date:** 2026-03-18
**Status:** Approved
**Scope:** Push structured series workouts (tempo, hills, fartlek) from plan.json to Garmin Connect, with scheduling and watch sync. Dashboard button for one-click push.

---

## Context

The Tarahumara Ultra Tracker has a 30-week training plan (`plan.json`) with series workouts (tempo, hills, fartlek) scheduled across all phases. Currently the user must manually create these workouts in Garmin Connect. This feature automates that process.

**In scope:** Series workouts with full `garmin_steps` detail in plan.json (currently weeks 2-4).
**Out of scope:** Easy runs, long runs, gym sessions, and series workouts without `garmin_steps` data.

---

## 1. Data Layer — `garmin_steps` in plan.json

Add a `garmin_steps` object to each series workout entry in plan.json. All series types (tempo, hills, fartlek) use the same schema:

```json
{
  "day": "friday", "date": "2026-03-13", "type": "series",
  "description": "Tempo 3x5min @ 6:30-6:45/km",
  "distance_km": 8, "vert_m": 110,
  "target_pace": "6:30-6:45", "target_hr": "155-165",
  "series_type": "tempo",
  "garmin_steps": {
    "warmup": {"end_condition": "distance", "value": 2.0, "hr_low": 115, "hr_high": 130},
    "repeat": 3,
    "work": {"end_condition": "time", "value_seconds": 300, "hr_low": 155, "hr_high": 165, "name": "Tempo 6:30-6:45/km"},
    "recovery": {"end_condition": "time", "value_seconds": 120, "hr_low": 0, "hr_high": 140, "name": "Easy jog recovery"},
    "cooldown": {"end_condition": "distance", "value": 1.5, "hr_low": 115, "hr_high": 130}
  }
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `warmup.end_condition` | `"distance"` or `"time"` | How warmup ends |
| `warmup.value` | float | km if distance (converted to meters by builder), seconds if time |
| `warmup.hr_low/hr_high` | int | HR target zone in BPM |
| `repeat` | int | Number of work+recovery iterations |
| `work.end_condition` | `"distance"` or `"time"` | How work interval ends |
| `work.value_seconds` | int | Duration in seconds (if time) |
| `work.value` | float | Distance in km if distance (converted to meters by builder) |
| `work.hr_low/hr_high` | int | HR target zone in BPM (hr_low=0 means no floor) |
| `work.name` | string | Step description shown on watch |
| `recovery.end_condition` | `"time"` | How recovery ends |
| `recovery.value_seconds` | int | Duration in seconds |
| `recovery.hr_low/hr_high` | int | HR target in BPM (hr_low=0 means no floor) |
| `recovery.name` | string | Step description shown on watch |
| `cooldown` | same as warmup | Cooldown step |

### Series to add (from PLAN_MARZO_2026_EXPORT_COMPLETO.md)

**Week 2 — Tempo 3x5min:**
- WU: 2.0km, HR 115-130
- 3x: 5min work HR 155-165 / 2min recovery HR <140
- CD: 1.5km, HR 115-130

**Week 3 — Hills 5x4min:**
- WU: 1.5km, HR 115-130
- 5x: 4min work HR 155-170 / 3min recovery HR <145
- CD: 1.5km, HR 115-130

**Week 4 — Fartlek 6x1min:**
- WU: 2.0km, HR 115-130
- 6x: 1min work HR 160-170 / 2min recovery HR <140
- CD: 2.0km, HR 115-130

---

## 2. Module — `tracker/workout_builder.py`

### Approach: Raw JSON + direct API calls (no library upgrade)

garminconnect >= 0.2.39 requires Python 3.10+ (project uses 3.9.6). Additionally, the library's Pydantic workout models have known bugs (`targetValueOne`/`targetValueTwo` not defined, `TargetType.HEART_RATE` mapped to wrong ID).

Instead: keep garminconnect 0.2.8 for auth, build workout JSON as raw dicts, and POST directly to the Garmin Connect workout API using the authenticated `garth` session.

### Functions

**`build_garmin_workout(workout: dict, week_num: int) -> dict`**
- Input: A series workout dict from plan.json (must have `garmin_steps`)
- Output: Garmin Connect workout JSON (raw dict)
- Converts: distances km to meters, builds RepeatGroupDTO for intervals
- Workout name format: `"{description} W{week_num}"` (e.g., "Tempo 3x5min @ 6:30-6:45/km W2")
- Estimates total duration for `estimatedDurationInSecs`

**`push_workout(week_num: int, profile_id: str) -> dict`**
- Finds the series workout for the given week by reading plan.json directly (not via model layer)
- Validates it has `garmin_steps`
- Calls `build_garmin_workout()` to create Garmin JSON
- Authenticates using existing `garmin_sync.py` pattern (garth tokens)
- Checks for existing workout with same name via `GET /workout-service/workouts` (idempotency)
- Uploads via `POST /proxy/workout-service/workout` with headers `{"Referer": "https://connect.garmin.com/modern/workouts", "nk": "NT"}`
- Schedules to the workout's date via `POST /proxy/workout-service/schedule/{workout_id}` with body `{"date": "YYYY-MM-DD"}`
- Returns `{"ok": True, "workout_id": "...", "scheduled_date": "...", "name": "..."}` or `{"error": "..."}`

### Garmin Connect Workout JSON Structure

The module produces this format. Key corrections from review:
- `conditionTypeId` for distance is **1** (not 3)
- `workoutTargetTypeId` for HR is **4** (known library bug maps it to 2)
- Includes `displayOrder` and `displayable` fields for API compatibility

```json
{
  "workoutName": "Tempo 3x5min @ 6:30-6:45/km W2",
  "sportType": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
  "estimatedDurationInSecs": 1920,
  "workoutSegments": [{
    "segmentOrder": 1,
    "sportType": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "workoutSteps": [
      {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
        "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "distance", "displayOrder": 1, "displayable": true},
        "endConditionValue": 2000,
        "description": "Warm Up",
        "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
        "targetValueOne": 115,
        "targetValueTwo": 130
      },
      {
        "type": "RepeatGroupDTO",
        "stepOrder": 2,
        "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
        "numberOfIterations": 3,
        "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": false},
        "endConditionValue": 3,
        "smartRepeat": false,
        "workoutSteps": [
          {
            "type": "ExecutableStepDTO",
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": true},
            "endConditionValue": 300,
            "description": "Tempo 6:30-6:45/km",
            "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
            "targetValueOne": 155,
            "targetValueTwo": 165
          },
          {
            "type": "ExecutableStepDTO",
            "stepOrder": 2,
            "stepType": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": true},
            "endConditionValue": 120,
            "description": "Easy jog recovery",
            "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
            "targetValueOne": 0,
            "targetValueTwo": 140
          }
        ]
      },
      {
        "type": "ExecutableStepDTO",
        "stepOrder": 3,
        "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
        "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "distance", "displayOrder": 1, "displayable": true},
        "endConditionValue": 1500,
        "description": "Cool Down",
        "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
        "targetValueOne": 115,
        "targetValueTwo": 130
      }
    ]
  }]
}
```

### Garmin Auth

Reuses existing auth pattern from `garmin_sync.py`:
- `_load_env()` for credentials
- `garth` token persistence at `~/.garminconnect/`
- Profile-based env vars for multi-athlete support
- Uses `garth` session directly for HTTP requests to workout endpoints

---

## 3. API Endpoint — `POST /api/push-workout` in serve.py

### Request
```
POST /api/push-workout?week=3&profile=default
Authorization: Bearer <API_KEY>
```

### Response (success)
```json
{"ok": true, "workout_id": "12345", "scheduled_date": "2026-03-20", "name": "Hills 5x4min W3"}
```

### Response (error)
```json
{"error": "Week 3 has no series workout with garmin_steps"}
```

### Error cases
- 401: Missing/invalid API key
- 400: Invalid week number, week has no series, series has no `garmin_steps`
- 429: Rate limited (reuses SYNC_COOLDOWN_SECONDS)
- 500: Garmin upload/schedule failed

---

## 4. Dashboard UI — "Push to Garmin" Button

### Where it appears
On weeks that have a series workout with `garmin_steps` data. The button appears in the week detail view near the series activity info.

### States
1. **Idle** — "Push to Garmin" button visible
2. **Pushing** — Button disabled, shows spinner/loading text
3. **Success** — Button replaced with "Sent to watch!" indicator
4. **Error** — Shows error message, button returns to idle for retry

### Data flow
- `build_week_json()` in serve.py adds `has_garmin_workout: true/false` to each week's JSON by checking if any workout in that week has `type == "series"` and a `garmin_steps` key in plan.json
- `/api/weeks` response carries this flag so the dashboard knows when to show the button
- Button calls `POST /api/push-workout?week=N`
- On success, stores pushed state in localStorage to persist the "Sent" indicator

---

## 5. Dependencies

- **No library upgrade needed.** Keep garminconnect 0.2.8 for auth. Workout JSON is built as raw dicts and POSTed via `garth` session directly.
- No new pip dependencies required.

---

## 6. Files Changed

| File | Change |
|------|--------|
| `plan.json` | Add `garmin_steps` to series workouts in weeks 2-4 |
| `tracker/workout_builder.py` | **New** — build Garmin workout JSON + push/schedule via garth HTTP |
| `dashboard/serve.py` | Add `POST /api/push-workout` endpoint, add `has_garmin_workout` to week JSON in `build_week_json()` |
| `dashboard/dashboard.html` | Add "Push to Garmin" button with idle/pushing/success/error states |
