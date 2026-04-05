from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data" / "conversations"


def _conv_dir() -> Path:
    override = os.environ.get("CONVERSATIONS_DIR")
    if override:
        return Path(override)
    return DEFAULT_DIR


def save_message(question: str, category: str, response: str, week: int) -> dict:
    """Append a chat exchange to today's conversation file. Returns the saved entry."""
    d = _conv_dir()
    d.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    entry = {
        "timestamp": now.isoformat(timespec="seconds"),
        "question": question,
        "category": category,
        "response": response,
        "week": week,
    }

    day_file = d / f"{now.strftime('%Y-%m-%d')}.json"
    messages = []
    if day_file.exists():
        messages = json.loads(day_file.read_text())
    messages.append(entry)
    day_file.write_text(json.dumps(messages, indent=2))
    return entry


def load_history(limit: int = 50, before: str | None = None) -> dict:
    """Load conversation history across day files, newest last.

    Returns {"messages": [...], "has_more": bool}.
    """
    d = _conv_dir()
    if not d.exists():
        return {"messages": [], "has_more": False}

    day_files = sorted(d.glob("*.json"))

    all_messages: list[dict] = []
    for f in day_files:
        try:
            msgs = json.loads(f.read_text())
            all_messages.extend(msgs)
        except (json.JSONDecodeError, OSError):
            continue

    if before:
        all_messages = [m for m in all_messages if m["timestamp"] < before]

    has_more = len(all_messages) > limit
    if has_more:
        all_messages = all_messages[-limit:]

    return {"messages": all_messages, "has_more": has_more}


def clear_history():
    """Remove all conversation JSON files."""
    d = _conv_dir()
    if not d.exists():
        return
    for f in d.glob("*.json"):
        f.unlink()
