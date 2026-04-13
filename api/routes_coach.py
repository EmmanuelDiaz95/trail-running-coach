from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from tracker.plan_data import get_current_week, get_week, get_week_dates, days_to_race, load_plan
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual, compliance_score
from tracker.data_loader import load_week_range
from coach.engine import run_coaching
from coach.classifier import classify_question
from coach.narrator import Narrator
from api.conversation import save_message, load_history, clear_history

router = APIRouter(prefix="/api/coach")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_KEY = os.environ.get("API_KEY", "")
CHAT_COOLDOWN_SECONDS = 10
PLAN_UPDATE_COOLDOWN_SECONDS = 5
_last_chat_time: dict[str, float] = {}


def _check_auth(authorization: Optional[str]) -> None:
    """Require Bearer token if API_KEY is configured."""
    if not API_KEY:
        return
    if not authorization or authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _get_narrator() -> Optional[Narrator]:
    """Create a Narrator if ANTHROPIC_API_KEY is set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    athlete_path = PROJECT_ROOT / "athlete.json"
    try:
        with open(athlete_path) as f:
            athlete = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return Narrator(api_key=api_key, athlete=athlete)


def _build_training_history(current_week: int) -> list[dict]:
    """Build a summary of all completed weeks for full training context."""
    summary = []
    for wn in range(1, current_week + 1):
        plan = get_week(wn)
        if plan is None:
            continue
        start, end = get_week_dates(wn)
        acts = load_cached_activities(start, end)
        entry = {
            "week": wn,
            "phase": plan.phase,
            "is_recovery": plan.is_recovery,
            "plan": {
                "distance_km": plan.distance_km,
                "vert_m": plan.vert_m,
                "long_run_km": plan.long_run_km,
                "gym": plan.gym_sessions,
                "series": plan.series_type,
            },
        }
        if acts:
            actual = build_week_actual(acts, wn)
            score = compliance_score(plan, actual)
            entry["actual"] = {
                "distance_km": round(actual.total_distance_km, 1),
                "vert_m": actual.total_vert_m,
                "long_run_km": round(actual.longest_run_km, 1),
                "gym": actual.gym_count,
                "series": actual.series_detected,
            }
            entry["compliance"] = score
        else:
            entry["actual"] = None
            entry["compliance"] = None
        summary.append(entry)
    return summary


def _build_upcoming_plan(current_week: int, lookahead: int = 4) -> list[dict]:
    """Build plan targets for upcoming weeks."""
    upcoming = []
    for wn in range(current_week + 1, min(current_week + lookahead + 1, 31)):
        plan = get_week(wn)
        if plan is None:
            continue
        upcoming.append({
            "week": wn,
            "phase": plan.phase,
            "is_recovery": plan.is_recovery,
            "distance_km": plan.distance_km,
            "vert_m": plan.vert_m,
            "long_run_km": plan.long_run_km,
            "gym": plan.gym_sessions,
            "series": plan.series_type,
        })
    return upcoming


def _build_coaching_data() -> Optional[dict]:
    """Build full coaching context: current week analysis + training history + health + plan changes."""
    week_num = get_current_week()
    if week_num is None:
        return None
    plan = get_week(week_num)
    if plan is None:
        return None
    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if not activities:
        # Try DB snapshots as fallback context
        try:
            from tracker import db
            snapshots = db.get_week_snapshots()
            if snapshots:
                data = {"training_history": [], "upcoming_plan": _build_upcoming_plan(week_num)}
                for s in snapshots:
                    w = s["data"]
                    data["training_history"].append({
                        "week": w.get("number"), "phase": w.get("phase"),
                        "is_recovery": w.get("recovery", False),
                        "plan": w.get("plan", {}), "actual": w.get("actual"),
                        "compliance": w.get("compliance"),
                    })
                data["week_number"] = week_num
                data["phase"] = plan.phase
                data["days_to_race"] = days_to_race()
                _enrich_with_health(data)
                _enrich_with_plan_changes(data, week_num)
                return data
        except Exception:
            pass
        return None

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)

    data = output.to_dict()
    data["training_history"] = _build_training_history(week_num)
    data["upcoming_plan"] = _build_upcoming_plan(week_num)

    # Load knowledge base for domain context
    knowledge_path = PROJECT_ROOT / "knowledge.json"
    if knowledge_path.exists():
        try:
            data["knowledge"] = json.loads(knowledge_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    _enrich_with_health(data)
    _enrich_with_plan_changes(data, week_num)

    return data


def _enrich_with_health(data: dict):
    """Add recent daily health data to coaching context."""
    try:
        from tracker import db
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=7)
        health = db.get_daily_health(start, end)
        if health:
            data["daily_health"] = health
    except Exception:
        pass


def _enrich_with_plan_changes(data: dict, week_num: int):
    """Add recent plan changes to coaching context."""
    try:
        from tracker import db
        changes = db.get_plan_changes(week_num)
        if changes:
            data["plan_changes"] = changes
    except Exception:
        pass


@router.get("/status")
def coach_status():
    week_num = get_current_week()
    if week_num is None:
        raise HTTPException(status_code=400, detail="Not in training window")

    plan = get_week(week_num)
    if plan is None:
        raise HTTPException(status_code=400, detail=f"Week {week_num} not in plan")

    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        return {
            "week": week_num,
            "phase": plan.phase,
            "days_to_race": days_to_race(),
            "compliance": None,
            "readiness": None,
        }

    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)

    readiness_data = None
    if output.readiness:
        readiness_data = {
            "score": output.readiness.score,
            "acwr": output.readiness.acwr,
            "zone": output.readiness.acwr_zone,
            "recommendation": output.readiness.recommendation,
        }

    return {
        "week": week_num,
        "phase": plan.phase,
        "days_to_race": days_to_race(),
        "compliance": output.compliance_score,
        "readiness": readiness_data,
    }


@router.get("/history")
def get_history(limit: int = Query(50)):
    return load_history(limit=limit)


@router.delete("/history")
def delete_history(authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    clear_history()
    return {"status": "ok"}


@router.post("/chat")
def coach_chat(request_body: dict):
    question = request_body.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    narrator = _get_narrator()
    if narrator is None:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    # Rate limiting
    rate_key = "chat"
    now = time.time()
    last = _last_chat_time.get(rate_key, 0)
    if now - last < CHAT_COOLDOWN_SECONDS:
        remaining = int(CHAT_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429, detail=f"Please wait {remaining}s")

    week_num = get_current_week()
    category = classify_question(question)
    coaching_data = _build_coaching_data()
    if coaching_data is None:
        coaching_data = {"note": "No training data available yet."}

    _last_chat_time[rate_key] = time.time()

    # Load recent conversation history for continuity
    recent = load_history(limit=20)
    chat_history = recent.get("messages", [])

    def event_stream():
        full_response = []
        for token in narrator.stream_answer(question, category, coaching_data, history=chat_history):
            full_response.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        yield f"data: {json.dumps({'meta': {'category': category, 'week': week_num}})}\n\n"
        yield "data: [DONE]\n\n"

        # Save to conversation history after streaming completes
        response_text = "".join(full_response)
        save_message(question, category, response_text, week_num or 0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/plan/update")
def update_plan(request_body: dict, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    from tracker import db

    week = request_body.get("week")
    field = request_body.get("field")
    new_value = request_body.get("new_value")
    reason = request_body.get("reason", "")

    # Input validation
    if not isinstance(week, int) or week < 1 or week > 30:
        raise HTTPException(status_code=400, detail="week must be an integer between 1 and 30")
    if not isinstance(field, str) or not field:
        raise HTTPException(status_code=400, detail="field must be a non-empty string")
    if new_value is None:
        raise HTTPException(status_code=400, detail="new_value is required")

    # Rate limiting
    rate_key = "plan_update"
    now = time.time()
    last = _last_chat_time.get(rate_key, 0)
    if now - last < PLAN_UPDATE_COOLDOWN_SECONDS:
        remaining = int(PLAN_UPDATE_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429, detail=f"Please wait {remaining}s")
    _last_chat_time[rate_key] = now

    current = db.get_week_plan(week)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Week {week} not found in plan")

    old_value = str(current.get(field, ""))
    db.update_plan_field(week, "default", field, old_value, str(new_value), reason, "manual")

    return {"status": "ok", "week": week, "field": field, "old_value": old_value, "new_value": str(new_value)}
