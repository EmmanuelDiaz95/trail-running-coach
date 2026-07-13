from __future__ import annotations

import csv
import re
from datetime import date

from .plan_data import week_for_date

# Spanish Garmin activity labels -> canonical tracker types.
TYPE_MAP = {
    "carrera": "running",
    "carrera de trail": "trail_running",
    "carrera por senderos": "trail_running",
    "ciclismo": "cycling",
    "entrenamiento de fuerza": "strength_training",
    "natación": "swimming",
    "caminata": "walking",
    "senderismo": "hiking",
    "entrenamiento en pista": "running",   # track session (intervals) — counts as running
    "entrenamiento en cinta": "running",   # treadmill run — counts as running
}

_GARMIN_ID_OFFSET = 9_000_000_000_000_000


def parse_number(v: str | None, comma_decimal: bool = False) -> float | None:
    """Parse a numeric CSV cell, locale-robust; blanks/'--' -> None.

    Garmin exports MIX number formats across rows: US (dot decimal, comma
    thousands, e.g. '38.07' / '1,274') and European (comma decimal, e.g.
    '8,670' == 8.670). A lone comma is therefore ambiguous and must be
    resolved by COLUMN semantics, which the caller signals via ``comma_decimal``:

      - both '.' and ',': the RIGHTMOST separator is the decimal point, the
        other is a thousands separator (handles '1.234,56' and '1,234.56').
      - only ',':
          * comma_decimal=True  (distance): decimal   -> '8,670'  = 8.670 km
          * comma_decimal=False (elevation, calories): thousands -> '1,274' = 1274 m
      - only '.' or none: parsed as-is.

    Rationale: distances are never >=1000 km (so a lone comma is a European
    decimal), whereas elevation/calories cross 1000 (so a lone comma is a US
    thousands separator). Set comma_decimal=True only for the distance column.
    """
    if v is None:
        return None
    s = str(v).strip().strip('"')
    if s in ("", "--", "None"):
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):        # European: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                                    # US: 1,234.56
            s = s.replace(",", "")
    elif has_comma:
        s = s.replace(",", ".") if comma_decimal else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_duration_to_minutes(t: str | None) -> float | None:
    """Parse 'HH:MM:SS(.s)' or 'MM:SS' into minutes; blank/'--' -> None."""
    if t is None:
        return None
    s = str(t).strip().strip('"')
    if s in ("", "--"):
        return None
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        h, m, sec = parts
    elif len(parts) == 2:
        h, m, sec = 0.0, parts[0], parts[1]
    else:
        return None
    return h * 60 + m + sec / 60


def map_activity_type(raw: str | None) -> str:
    """Map a Spanish Garmin activity label to a canonical type."""
    key = (raw or "").strip().lower()
    return TYPE_MAP.get(key, key.replace(" ", "_"))


def synthetic_garmin_id(fecha: str) -> int:
    """Deterministic BIGINT id from the activity start timestamp.

    Offset sits above real Garmin ids (~1e10) and under BIGINT max (~9.2e18)."""
    digits = re.sub(r"\D", "", str(fecha).strip())
    if len(digits) < 8:
        raise ValueError(f"Unparseable Fecha timestamp: {fecha!r}")
    return _GARMIN_ID_OFFSET + int(digits)


def parse_activity_row(row: dict) -> dict:
    """Normalize one Garmin CSV DictReader row into a db.save_activities dict."""
    fecha = (row.get("Fecha") or "").strip()
    activity_date = fecha.split(" ")[0]
    week_number = week_for_date(date.fromisoformat(activity_date))
    return {
        "garmin_id": synthetic_garmin_id(fecha),
        "activity_date": activity_date,
        "week_number": week_number,
        "activity_type": map_activity_type(row.get("Tipo de actividad")),
        "activity_name": (row.get("Título") or "").strip() or None,
        "distance_km": parse_number(row.get("Distancia"), comma_decimal=True),
        "elevation_m": parse_number(row.get("Ascenso total")),
        "duration_min": parse_duration_to_minutes(row.get("Tiempo")),
        "avg_hr": parse_number(row.get("Frecuencia cardiaca media")),
        "avg_pace": (row.get("Ritmo medio") or "").strip() or None,
        "calories": parse_number(row.get("Calorías")),
        "sets": None,
        "reps": None,
        "route_svg": None,
        "raw_json": dict(row),
    }


def parse_csv(path: str) -> tuple[list[dict], list[tuple[int, str]]]:
    """Read a Garmin CSV export. Returns (normalized_rows, errors[(line_no, msg)])."""
    rows: list[dict] = []
    errors: list[tuple[int, str]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # line 1 is the header
            try:
                rows.append(parse_activity_row(row))
            except Exception as e:  # noqa: BLE001 - record & continue, never abort import
                errors.append((i, str(e)))
    return rows, errors


def group_by_week(rows: list[dict]) -> dict[int, list[dict]]:
    """Group normalized rows by their precomputed plan week (week 0 = outside the plan window)."""
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["week_number"], []).append(r)
    return grouped
