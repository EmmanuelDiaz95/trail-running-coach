from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import patch

from coach.refresh import RefreshSummary
from coach.health_readiness import HealthReadiness

_COACH_PATH = Path(__file__).resolve().parent.parent / "coach.py"


def _load_coach_module():
    spec = importlib.util.spec_from_file_location("coach_script", _COACH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cmd_refresh_prints_summary(capsys):
    mod = _load_coach_module()
    summary = RefreshSummary(weeks_synced=[17, 18], health_days_synced=["2026-07-04"])
    with patch.object(mod, "refresh", lambda **k: summary):
        mod.cmd_refresh()
    out = capsys.readouterr().out
    assert "18" in out
    assert "1" in out  # one health day


def test_cmd_checkin_merges_and_prints(capsys):
    mod = _load_coach_module()
    summary = RefreshSummary(weeks_synced=[18], health_days_synced=[])
    health = HealthReadiness(checks=[("🟢", "Resting HR: 55")], verdict="🟢 ADELANTE",
                             advice="go", level=0, days=30, has_data=True)
    with patch.object(mod, "refresh", lambda **k: summary), \
         patch.object(mod, "get_current_week", lambda: 18), \
         patch.object(mod, "load_cached_activities", lambda s, e: None), \
         patch.object(mod, "get_daily_health", lambda a, b: []), \
         patch.object(mod, "compute_health_readiness", lambda rows, today: health), \
         patch.object(mod, "merge_verdict", lambda h, c: ("🟢 ADELANTE", "go", 0)):
        mod.cmd_checkin()
    out = capsys.readouterr().out
    assert "ADELANTE" in out
