from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from tracker.plan_data import get_current_week, get_week, get_week_dates, days_to_race
from tracker.garmin_sync import load_cached_activities
from tracker.analysis import build_week_actual
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


def _build_coaching_data() -> Optional[dict]:
    """Build coaching data for the current week. Returns None if unavailable."""
    week_num = get_current_week()
    if week_num is None:
        return None
    plan = get_week(week_num)
    if plan is None:
        return None
    start, end = get_week_dates(week_num)
    activities = load_cached_activities(start, end)
    if activities is None:
        return None
    current = build_week_actual(activities, week_num)
    lookback_start = max(1, week_num - 3)
    history = load_week_range(lookback_start, week_num)
    output = run_coaching(plan, current, history)
    return output.to_dict()


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

    def event_stream():
        full_response = []
        for token in narrator.stream_answer(question, category, coaching_data):
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
