from __future__ import annotations

from datetime import date, timedelta

from coach.refresh import detect_week_gap, detect_health_gap


def _snap(n, dist):
    return {"week_number": n, "data": {"actual": {"distance_km": dist}}}


def test_week_gap_backfills_from_last_good_plus_one():
    snaps = [_snap(1, 20), _snap(2, 25), _snap(3, None)]
    frm, to, capped = detect_week_gap(snaps, current_week=6, max_weeks=8)
    assert (frm, to, capped) == (3, 6, False)  # wk3 has null actual -> resync from 3


def test_week_gap_no_snapshots_uses_window():
    frm, to, capped = detect_week_gap([], current_week=10, max_weeks=4)
    assert (frm, to) == (7, 10)
    assert capped is True


def test_week_gap_caps_large_gap():
    snaps = [_snap(1, 20)]
    frm, to, capped = detect_week_gap(snaps, current_week=18, max_weeks=8)
    assert frm == 11 and to == 18 and capped is True


def test_week_gap_steady_state_syncs_current_only():
    snaps = [_snap(1, 20), _snap(2, 25)]
    frm, to, capped = detect_week_gap(snaps, current_week=2, max_weeks=8)
    assert (frm, to, capped) == (2, 2, False)


def test_health_gap_backfills_missing_days():
    today = date(2026, 7, 5)
    rows = [{"date": (today - timedelta(days=3)).isoformat(), "resting_hr": 52}]
    frm, to, capped = detect_health_gap(rows, today, max_days=21)
    assert frm == today - timedelta(days=2)
    assert to == today
    assert capped is False


def test_health_gap_caps_and_ignores_empty_rows():
    today = date(2026, 7, 5)
    # a row exists but has no populated metric -> treated as no data
    rows = [{"date": (today - timedelta(days=40)).isoformat(), "resting_hr": None}]
    frm, to, capped = detect_health_gap(rows, today, max_days=14)
    assert frm == today - timedelta(days=13)
    assert to == today
    assert capped is True
