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
COND_DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
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
            "/workout-service/workouts",
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
            "/workout-service/workout",
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
                f"/workout-service/schedule/{workout_id}",
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
