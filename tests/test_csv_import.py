from __future__ import annotations

import pytest

from tracker.csv_import import (
    group_by_week,
    map_activity_type,
    parse_activity_row,
    parse_csv,
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


SAMPLE_ROW = {
    "Tipo de actividad": "Carrera",
    "Fecha": "2026-07-11 06:30:54",
    "Título": "Metepec Carrera",
    "Distancia": "8.68",
    "Calorías": "630",
    "Tiempo": "01:06:47",
    "Frecuencia cardiaca media": "124",
    "Ritmo medio": "7:42",
    "Ascenso total": "230",
}


def test_parse_activity_row_maps_all_fields():
    r = parse_activity_row(SAMPLE_ROW)
    assert r["garmin_id"] == 9_000_000_000_000_000 + 20260711063054
    assert r["activity_date"] == "2026-07-11"
    assert r["activity_type"] == "running"
    assert r["activity_name"] == "Metepec Carrera"
    assert r["distance_km"] == 8.68
    assert r["elevation_m"] == 230.0
    assert round(r["duration_min"], 2) == 66.78
    assert r["avg_hr"] == 124.0
    assert r["avg_pace"] == "7:42"
    assert r["calories"] == 630.0
    assert r["sets"] is None and r["reps"] is None and r["route_svg"] is None
    assert r["raw_json"]["Título"] == "Metepec Carrera"  # full row preserved


def test_parse_csv_reads_file(tmp_path):
    csv_text = (
        "Tipo de actividad,Fecha,Título,Distancia,Calorías,Tiempo,"
        "Frecuencia cardiaca media,Ritmo medio,Ascenso total\n"
        'Carrera,2026-07-11 06:30:54,"Metepec Carrera","8.68","630","01:06:47","124","7:42","230"\n'
        'Carrera,2026-06-10 06:09:23,"Metepec Carrera","6.01","400","00:47:00","129","7:49","14"\n'
    )
    p = tmp_path / "sample.csv"
    p.write_text(csv_text, encoding="utf-8")
    rows, errors = parse_csv(str(p))
    assert errors == []
    assert len(rows) == 2
    assert {r["activity_date"] for r in rows} == {"2026-07-11", "2026-06-10"}


def test_group_by_week():
    rows = [parse_activity_row(SAMPLE_ROW)]  # 2026-07-11 -> week 19
    grouped = group_by_week(rows)
    assert list(grouped.keys()) == [19]
    assert len(grouped[19]) == 1
