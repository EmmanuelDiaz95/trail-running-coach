from __future__ import annotations

import pytest

from tracker.csv_import import (
    map_activity_type,
    parse_duration_to_minutes,
    parse_number,
    synthetic_garmin_id,
)


def test_parse_number():
    assert parse_number("8.68") == pytest.approx(8.68)
    assert parse_number("10,860") == pytest.approx(10860.0)  # thousands separator
    assert parse_number('"124"') == pytest.approx(124.0)     # stray quotes
    assert parse_number("") is None
    assert parse_number("--") is None
    assert parse_number(None) is None


def test_parse_duration_to_minutes():
    assert parse_duration_to_minutes("01:06:47") == pytest.approx(66.7833, abs=1e-3)
    assert parse_duration_to_minutes("00:05:56.0") == pytest.approx(5.9333, abs=1e-3)
    assert parse_duration_to_minutes("07:42") == pytest.approx(7.7, abs=1e-3)  # MM:SS
    assert parse_duration_to_minutes("") is None
    assert parse_duration_to_minutes(None) is None


def test_map_activity_type():
    assert map_activity_type("Carrera") == "running"
    assert map_activity_type("Entrenamiento de fuerza") == "strength_training"
    assert map_activity_type("Algo Raro") == "algo_raro"  # unknown fallback
    assert map_activity_type(None) == ""


def test_synthetic_garmin_id_stable_and_offset():
    gid = synthetic_garmin_id("2026-07-11 06:30:54")
    assert gid == 9_000_000_000_000_000 + 20260711063054
    # deterministic
    assert synthetic_garmin_id("2026-07-11 06:30:54") == gid
    # distinct timestamps -> distinct ids
    assert synthetic_garmin_id("2026-07-10 06:29:18") != gid
