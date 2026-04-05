from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime

import pytest

from api.conversation import save_message, load_history, clear_history


@pytest.fixture
def conv_dir(tmp_path):
    """Use a temp directory for conversations, then clean up."""
    d = tmp_path / "conversations"
    d.mkdir()
    original = os.environ.get("CONVERSATIONS_DIR")
    os.environ["CONVERSATIONS_DIR"] = str(d)
    yield d
    if original is None:
        os.environ.pop("CONVERSATIONS_DIR", None)
    else:
        os.environ["CONVERSATIONS_DIR"] = original


def test_save_and_load(conv_dir):
    save_message("How's my week?", "coaching", "Looks rough.", 5)
    save_message("What should I eat?", "knowledge", "Carbs before long runs.", 5)

    result = load_history(limit=50)
    assert len(result["messages"]) == 2
    assert result["messages"][0]["question"] == "How's my week?"
    assert result["messages"][1]["question"] == "What should I eat?"
    assert result["has_more"] is False


def test_load_respects_limit(conv_dir):
    for i in range(5):
        save_message(f"Q{i}", "general", f"A{i}", 5)

    result = load_history(limit=3)
    assert len(result["messages"]) == 3
    assert result["has_more"] is True


def test_clear_history(conv_dir):
    save_message("test", "general", "response", 5)
    assert len(list(conv_dir.iterdir())) > 0

    clear_history()
    json_files = list(conv_dir.glob("*.json"))
    assert len(json_files) == 0

    result = load_history(limit=50)
    assert len(result["messages"]) == 0


def test_load_empty(conv_dir):
    result = load_history(limit=50)
    assert result["messages"] == []
    assert result["has_more"] is False


def test_pagination_with_before(conv_dir):
    save_message("Q1", "general", "A1", 5)
    msgs = load_history(limit=50)["messages"]
    ts = msgs[0]["timestamp"]

    save_message("Q2", "general", "A2", 5)

    result = load_history(limit=50)
    assert len(result["messages"]) == 2
