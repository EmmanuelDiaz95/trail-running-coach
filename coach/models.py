from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrendResult:
    """Result of analyzing a single metric across multiple weeks."""
    metric: str
    trend: str  # improving, plateauing, declining, erratic, insufficient_data
    values: list[float]
    delta: str  # human-readable delta (e.g., "-0:22/km over 4 weeks")
    significance: str  # on_track, watch, concern


@dataclass
class ReadinessScore:
    """Fatigue and readiness assessment."""
    score: int  # 1-10
    acwr: float
    acwr_zone: str  # optimal, caution, danger, expected_recovery, detraining
    recommendation: str  # push, maintain, back_off
    signals: list[str] = field(default_factory=list)


@dataclass
class Adjustment:
    """A plan adjustment recommendation."""
    category: str  # volume, intensity, gym, series, recovery, phase_transition
    priority: str  # high, medium, low
    message: str


@dataclass
class ComplianceBreakdown:
    """Detailed compliance for one metric."""
    planned: float | None
    actual: float | None
    pct: int | None


@dataclass
class CoachingOutput:
    """Complete coaching output for one week — the contract between
    the rule engine and the LLM narrator."""
    week_number: int
    generated_at: str
    phase: str
    is_recovery_week: bool
    days_to_race: int

    compliance_score: int
    compliance_breakdown: dict[str, ComplianceBreakdown]

    readiness: ReadinessScore | None
    trends: list[TrendResult]
    adjustments: list[Adjustment]
    alerts: list[dict]  # reuses existing Alert as dict

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for the narrator."""
        from dataclasses import asdict
        return asdict(self)
