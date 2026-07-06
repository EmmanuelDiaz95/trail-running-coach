from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean


@dataclass
class HealthReadiness:
    checks: list = field(default_factory=list)   # list[tuple[str, str]]
    verdict: str = "—"
    advice: str = ""
    level: int = 0        # 0 green, 1 yellow, 2 red
    days: int = 0
    has_data: bool = False


def _avg(rows, field_name):
    vals = [r.get(field_name) for r in rows if isinstance(r.get(field_name), (int, float))]
    return mean(vals) if vals else None


def _score(label, cur, base, kind):
    """kind: 'low_bad' (HRV), 'high_bad' (RHR), or absolute (green_min, yellow_min)."""
    if cur is None:
        return ("—", f"{label}: sin datos")
    if kind == "high_bad":
        if base is None:
            base = cur
        s = "🟢" if cur <= base * 1.05 else "🟡" if cur <= base * 1.10 else "🔴"
        return (s, f"{label}: {cur:.0f} (base {base:.0f})")
    if kind == "low_bad":
        if base is None:
            base = cur
        s = "🟢" if cur >= base * 0.97 else "🟡" if cur >= base * 0.90 else "🔴"
        return (s, f"{label}: {cur:.0f} (base {base:.0f})")
    g, y = kind
    s = "🟢" if cur >= g else "🟡" if cur >= y else "🔴"
    return (s, f"{label}: {cur:.1f}")


def compute_health_readiness(rows: list, today: date) -> HealthReadiness:
    rows = [r for r in rows if r.get("date")]
    rows.sort(key=lambda r: str(r["date"]))
    if not rows:
        return HealthReadiness(
            checks=[], verdict="—",
            advice="No hay datos de salud. Sincroniza Garmin primero.",
            level=0, days=0, has_data=False,
        )

    cutoff = str(today - timedelta(days=7))
    last7 = [r for r in rows if str(r["date"]) >= cutoff]
    base = [r for r in rows if str(r["date"]) < cutoff]

    checks = [
        _score("Resting HR", _avg(last7, "resting_hr"), _avg(base, "resting_hr"), "high_bad"),
        _score("HRV noche", _avg(last7, "hrv_last_night"), _avg(base, "hrv_last_night"), "low_bad"),
        _score("Readiness", _avg(last7, "training_readiness"), None, (55, 40)),
        _score("Sueño (h)", _avg(last7, "sleep_hours"), None, (7, 6)),
        _score("Body Battery AM", _avg(last7, "body_battery_am"), None, (50, 35)),
    ]
    reds = sum(1 for s, _ in checks if s == "🔴")
    yels = sum(1 for s, _ in checks if s == "🟡")

    if reds >= 2:
        level, verdict, advice = 2, "🔴 BAJAR", "Reduce volumen / recuperación extra esta semana."
    elif reds >= 1 or yels >= 2:
        level, verdict, advice = 1, "🟡 MANTENER", "Repite el volumen de esta semana; NO subas. Prioriza dormir."
    else:
        level, verdict, advice = 0, "🟢 ADELANTE", "Procede con el aumento planeado."

    return HealthReadiness(
        checks=checks, verdict=verdict, advice=advice,
        level=level, days=len(rows), has_data=True,
    )
