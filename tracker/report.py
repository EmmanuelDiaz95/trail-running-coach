from __future__ import annotations

from tabulate import tabulate

from .config import REPORTS_DIR
from .models import WeekPlan, WeekActual, Alert
from .analysis import compute_deltas, compliance_score, classify_activity


def _format_delta(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "-"
    sign = "+" if delta_pct >= 0 else ""
    return f"{sign}{delta_pct:.1f}%"


def generate_report(plan: WeekPlan, actual: WeekActual, alerts: list[Alert]) -> str:
    """Generate a markdown weekly report."""
    deltas = compute_deltas(plan, actual)
    score = compliance_score(plan, actual)

    lines = []
    lines.append(f"# Week {plan.week_number} Report ({plan.start_date} to {plan.end_date})")
    lines.append(f"Phase: {plan.phase.title()} | Recovery: {'Yes' if plan.is_recovery else 'No'}")
    lines.append("")

    # Metrics table
    table_data = [
        ["Distance (km)", plan.distance_km, actual.total_distance_km,
         _format_delta(deltas["distance_km"]["delta_pct"])],
        ["Vert (m)", plan.vert_m, actual.total_vert_m,
         _format_delta(deltas["vert_m"]["delta_pct"])],
        ["Long Run (km)", plan.long_run_km, actual.longest_run_km,
         _format_delta(deltas["long_run_km"]["delta_pct"])],
        ["Gym Sessions", plan.gym_sessions, actual.gym_count,
         f"{deltas['gym_sessions']['delta_abs']:+d}"],
    ]

    if plan.series_type:
        series_actual = "Yes" if actual.series_detected else "No"
        table_data.append(["Series", plan.series_type.title(), series_actual, ""])

    table = tabulate(table_data, headers=["Metric", "Planned", "Actual", "Delta"],
                     tablefmt="pipe")
    lines.append(table)
    lines.append("")
    lines.append(f"**Compliance Score: {score}%**")
    lines.append("")

    # Activities detail
    lines.append("## Activities")
    for a in actual.activities:
        cat = classify_activity(a)
        if cat == "run":
            pace_str = ""
            if a.avg_pace_min_km:
                mins = int(a.avg_pace_min_km)
                secs = int((a.avg_pace_min_km - mins) * 60)
                pace_str = f" | Pace: {mins}:{secs:02d}/km"
            hr_str = f" | HR: {a.avg_hr}" if a.avg_hr else ""
            vert_str = f" | ↑{a.elevation_gain_m}m" if a.elevation_gain_m else ""
            lines.append(f"- **{a.date}** {a.name}: {a.distance_km}km{pace_str}{hr_str}{vert_str}")
        elif cat == "gym":
            dur_min = round(a.duration_seconds / 60)
            lines.append(f"- **{a.date}** {a.name}: {dur_min}min")
        else:
            lines.append(f"- **{a.date}** {a.name}: {a.activity_type}")
    lines.append("")

    # Alerts
    if alerts:
        lines.append("## Alerts")
        for alert in alerts:
            lines.append(f"- [{alert.level}] {alert.message}")
        lines.append("")
    else:
        lines.append("## Alerts")
        lines.append("No alerts this week.")
        lines.append("")

    return "\n".join(lines)


def save_report(report: str, week_number: int) -> str:
    """Save report to data/reports/ and return the file path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"week_{week_number:02d}.md"
    with open(filepath, "w") as f:
        f.write(report)
    return str(filepath)
