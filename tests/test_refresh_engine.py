from __future__ import annotations

from datetime import date
from unittest.mock import patch

from coach.refresh import refresh, RefreshSummary
from tracker.garmin_sync import GarminRateLimited


def _patches(week_json_side_effect=None, health_side_effect=None,
             snapshots=None, health_rows=None, current_week=6):
    return [
        patch("tracker.garmin_sync._load_env", lambda: None),
        patch("tracker.db.init_db", lambda: None),
        patch("tracker.db.get_week_snapshots", lambda profile_id="default": snapshots or []),
        patch("tracker.db.get_daily_health", lambda a, b, profile_id="default": health_rows or []),
        patch("tracker.plan_data.get_current_week", lambda: current_week),
    ]


def test_refresh_syncs_weeks_and_health():
    calls = {"weeks": [], "health": []}

    def fake_week_json(w, do_sync=False, profile_id="default"):
        calls["weeks"].append(w)
        return {"activities": [1, 2], "compliance": 90}

    def fake_update(w, data, pid):
        pass

    def fake_health(d, profile_id="default"):
        calls["health"].append(d)

    ctx = _patches(current_week=6)
    with patch("dashboard.serve.build_week_json", fake_week_json), \
         patch("dashboard.serve._update_weeks_cache", fake_update), \
         patch("tracker.garmin_sync.sync_daily_health", fake_health):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5), max_weeks=8, max_health_days=3)
        finally:
            for p in ctx:
                p.stop()

    assert isinstance(summary, RefreshSummary)
    assert summary.weeks_synced == [1, 2, 3, 4, 5, 6]  # no snapshots -> window floor=1? capped
    assert summary.rate_limited is False
    assert len(summary.health_days_synced) == 3


def test_refresh_stops_on_rate_limit():
    def fake_week_json(w, do_sync=False, profile_id="default"):
        raise GarminRateLimited(__import__("time").time() + 300)

    ctx = _patches(current_week=6)
    with patch("dashboard.serve.build_week_json", fake_week_json), \
         patch("dashboard.serve._update_weeks_cache", lambda *a: None), \
         patch("tracker.garmin_sync.sync_daily_health", lambda *a, **k: None):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5))
        finally:
            for p in ctx:
                p.stop()

    assert summary.rate_limited is True
    assert summary.retry_after is not None and summary.retry_after > 0
    assert summary.weeks_synced == []


def test_refresh_stops_on_error_dict_rate_limit():
    def fake_week_json(w, do_sync=False, profile_id="default"):
        return {"error": "rate limit", "rate_limited": True}

    ctx = _patches(current_week=6)
    with patch("dashboard.serve.build_week_json", fake_week_json), \
         patch("dashboard.serve._update_weeks_cache", lambda *a: None), \
         patch("tracker.garmin_sync.sync_daily_health", lambda *a, **k: None):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5))
        finally:
            for p in ctx:
                p.stop()

    assert summary.rate_limited is True
    assert summary.weeks_synced == []


def test_refresh_stops_on_health_rate_limit():
    def fake_week_json(w, do_sync=False, profile_id="default"):
        return {"activities": [], "compliance": 90}

    def fake_health(d, profile_id="default"):
        raise GarminRateLimited(__import__("time").time() + 300)

    ctx = _patches(current_week=6)
    with patch("dashboard.serve.build_week_json", fake_week_json), \
         patch("dashboard.serve._update_weeks_cache", lambda *a: None), \
         patch("tracker.garmin_sync.sync_daily_health", fake_health):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5), max_weeks=8, max_health_days=3)
        finally:
            for p in ctx:
                p.stop()

    assert summary.rate_limited is True
    assert summary.retry_after is not None and summary.retry_after > 0
    assert summary.weeks_synced == [1, 2, 3, 4, 5, 6]
    assert summary.health_days_synced == []


def test_refresh_records_week_error_and_continues():
    def fake_week_json(w, do_sync=False, profile_id="default"):
        if w == 3:
            return {"error": "garmin 500"}
        return {"activities": [1], "compliance": 90}

    ctx = _patches(current_week=6)
    with patch("dashboard.serve.build_week_json", fake_week_json), \
         patch("dashboard.serve._update_weeks_cache", lambda *a: None), \
         patch("tracker.garmin_sync.sync_daily_health", lambda *a, **k: None):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5), max_weeks=8, max_health_days=3)
        finally:
            for p in ctx:
                p.stop()

    assert 3 not in summary.weeks_synced
    assert summary.weeks_synced == [1, 2, 4, 5, 6]
    assert any("week 3" in e for e in summary.errors)


def test_refresh_handles_no_current_week():
    health_calls = []

    def fake_health(d, profile_id="default"):
        health_calls.append(d)

    ctx = _patches(current_week=None)
    with patch("dashboard.serve.build_week_json", lambda *a, **k: None), \
         patch("dashboard.serve._update_weeks_cache", lambda *a: None), \
         patch("tracker.garmin_sync.sync_daily_health", fake_health):
        for p in ctx:
            p.start()
        try:
            summary = refresh(today=date(2026, 7, 5), max_health_days=3)
        finally:
            for p in ctx:
                p.stop()

    assert any("not in training window" in w for w in summary.warnings)
    assert len(summary.health_days_synced) == 3
