from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
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
CHAT_COOLDOWN_SECONDS = 10
_last_chat_time: dict[str, float] = {}


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


def _build_coaching_data_from_cache(week_num: int) -> Optional[dict]:
    """Fallback: build coaching context from weeks_cache.json when raw activities aren't available."""
    cache_path = PROJECT_ROOT / "dashboard" / "weeks_cache.json"
    if not cache_path.exists():
        return None
    try:
        weeks = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if not weeks:
        return None

    # Find current week in cache
    current = None
    for w in weeks:
        if w.get("number") == week_num:
            current = w
            break

    plan = get_week(week_num)

    # Build a coaching-data-shaped dict from the cache
    data = {
        "week_number": week_num,
        "generated_at": "from cache",
        "phase": current["phase"] if current else (plan.phase if plan else "unknown"),
        "is_recovery_week": current.get("recovery", False) if current else False,
        "days_to_race": days_to_race(),
        "compliance_score": current.get("compliance") if current else None,
        "compliance_breakdown": {},
        "readiness": None,
        "trends": [],
        "adjustments": [],
        "alerts": current.get("alerts", []) if current else [],
    }

    if current and current.get("actual"):
        data["compliance_breakdown"] = {
            "plan": current.get("plan", {}),
            "actual": current["actual"],
        }

    # Full training history from cache
    data["training_history"] = []
    for w in weeks:
        entry = {
            "week": w["number"],
            "phase": w.get("phase", ""),
            "is_recovery": w.get("recovery", False),
            "plan": w.get("plan", {}),
            "actual": w.get("actual"),
            "compliance": w.get("compliance"),
        }
        data["training_history"].append(entry)

    data["upcoming_plan"] = _build_upcoming_plan(week_num)

    # Load knowledge base
    knowledge_path = PROJECT_ROOT / "knowledge.json"
    if knowledge_path.exists():
        try:
            data["knowledge"] = json.loads(knowledge_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    return data


def _build_coaching_data() -> Optional[dict]:
    """Build full coaching context: current week analysis + training history + upcoming plan."""
    week_num = get_current_week()
    if week_num is None:
        return None
    plan = get_week(week_num)
    if plan is None:
        return None
    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if not activities:
        # Fallback to weeks_cache.json (e.g. on Railway where raw activities aren't available)
        return _build_coaching_data_from_cache(week_num)
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

    return data


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
def get_history(limit: int = Query(50), before: Optional[str] = Query(None)):
    return load_history(limit=limit, before=before)


@router.delete("/history")
def delete_history():
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
