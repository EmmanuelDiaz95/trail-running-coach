from __future__ import annotations

from tracker import db


def save_message(question: str, category: str, response: str, week: int) -> dict:
    """Save a chat exchange to the database. Returns the saved entry."""
    return db.save_conversation(question, category, response, week)


def load_history(limit: int = 50, before: str | None = None) -> dict:
    """Load conversation history from the database.

    Returns {"messages": [...], "has_more": bool}.
    """
    messages = db.get_conversations(limit=limit + 1)
    has_more = len(messages) > limit
    if has_more:
        messages = messages[-limit:]
    return {"messages": messages, "has_more": has_more}


def clear_history():
    """Remove all conversation history."""
    db.clear_conversations()
