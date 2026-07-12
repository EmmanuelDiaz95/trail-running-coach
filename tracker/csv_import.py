from __future__ import annotations

import re

# Spanish Garmin activity labels -> canonical tracker types.
TYPE_MAP = {
    "carrera": "running",
    "carrera de trail": "trail_running",
    "carrera por senderos": "trail_running",
    "ciclismo": "cycling",
    "entrenamiento de fuerza": "strength_training",
    "natación": "swimming",
    "caminata": "walking",
}

_GARMIN_ID_OFFSET = 9_000_000_000_000_000


def parse_number(v: str | None) -> float | None:
    """Parse a numeric CSV cell; thousands ',' stripped, blanks/'--' -> None."""
    if v is None:
        return None
    s = str(v).strip().strip('"').replace(",", "")
    if s in ("", "--", "None"):
        return None
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
