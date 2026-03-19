from __future__ import annotations

from coach.trends import analyze_trends
from coach.models import TrendResult


def test_improving_distance(make_week_actual):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=23),
        make_week_actual(week_number=3, total_distance_km=25),
        make_week_actual(week_number=4, total_distance_km=28),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "improving"
    assert dist.values == [20, 23, 25, 28]


def test_declining_distance(make_week_actual):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=30),
        make_week_actual(week_number=2, total_distance_km=27),
        make_week_actual(week_number=3, total_distance_km=24),
        make_week_actual(week_number=4, total_distance_km=20),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "declining"


def test_plateauing_distance(make_week_actual):
    weeks = [
        make_week_actual(week_number=i, total_distance_km=25)
        for i in range(1, 5)
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "plateauing"


def test_insufficient_data(make_week_actual):
    weeks = [make_week_actual(week_number=1, total_distance_km=20)]
    results = analyze_trends(weeks, min_weeks=3)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "insufficient_data"


def test_erratic_distance(make_week_actual):
    weeks = [
        make_week_actual(week_number=1, total_distance_km=20),
        make_week_actual(week_number=2, total_distance_km=30),
        make_week_actual(week_number=3, total_distance_km=18),
        make_week_actual(week_number=4, total_distance_km=32),
    ]
    results = analyze_trends(weeks)
    dist = next(t for t in results if t.metric == "weekly_distance")
    assert dist.trend == "erratic"


def test_multiple_metrics_returned(make_week_actual):
    weeks = [
        make_week_actual(week_number=i, total_distance_km=20 + i, total_vert_m=300 + i * 50)
        for i in range(1, 5)
    ]
    results = analyze_trends(weeks)
    metrics = {t.metric for t in results}
    assert "weekly_distance" in metrics
    assert "weekly_vert" in metrics
    assert "longest_run" in metrics
    assert "gym_frequency" in metrics
    assert "easy_run_avg_hr" in metrics
    assert "easy_run_avg_pace" in metrics


def test_empty_weeks():
    results = analyze_trends([])
    assert all(t.trend == "insufficient_data" for t in results)


def test_easy_run_hr_with_activities(make_week_actual, make_activity):
    weeks = []
    for i in range(1, 5):
        activities = [
            make_activity(activity_type="running", distance_km=8, avg_hr=150 - i * 2, max_hr=158),
        ]
        weeks.append(make_week_actual(week_number=i, activities=activities))
    results = analyze_trends(weeks)
    hr_trend = next(t for t in results if t.metric == "easy_run_avg_hr")
    assert hr_trend.trend in ("improving", "declining")
