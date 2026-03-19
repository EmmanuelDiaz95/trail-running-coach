from __future__ import annotations

from tracker.classify import classify_intensity


def test_easy_run(make_activity):
    """Run with low HR, not series -> easy."""
    act = make_activity(activity_type="running", distance_km=8.0, avg_hr=135, max_hr=148)
    assert classify_intensity(act) == "easy"


def test_tempo_run(make_activity):
    """Run with avg HR in Z3 range, duration > 20min, not series."""
    act = make_activity(
        activity_type="running", distance_km=10.0,
        avg_hr=150, max_hr=158, duration_seconds=3000,
    )
    assert classify_intensity(act) == "tempo"


def test_interval_run(make_activity):
    """Run matching _is_series heuristic -> intervals."""
    act = make_activity(
        activity_type="running", distance_km=8.0,
        avg_hr=145, max_hr=175,  # gap=30, max>=160
    )
    assert classify_intensity(act) == "intervals"


def test_interval_short_high_hr(make_activity):
    """Short run with high avg HR -> intervals."""
    act = make_activity(
        activity_type="running", distance_km=6.0,
        avg_hr=160, max_hr=178,
    )
    assert classify_intensity(act) == "intervals"


def test_gym_activity(make_activity):
    """Strength training -> gym."""
    act = make_activity(activity_type="strength_training", distance_km=0)
    assert classify_intensity(act) == "gym"


def test_other_activity(make_activity):
    """Non-run, non-gym -> other."""
    act = make_activity(activity_type="cycling", distance_km=30.0)
    assert classify_intensity(act) == "other"


def test_trail_run_easy(make_activity):
    """trail_running type with low HR -> easy."""
    act = make_activity(activity_type="trail_running", distance_km=12.0, avg_hr=138, max_hr=150)
    assert classify_intensity(act) == "easy"


def test_long_run(make_activity):
    """Long easy run -> long_run (uses threshold param)."""
    act = make_activity(
        activity_type="running", distance_km=16.0,
        avg_hr=140, max_hr=152,
    )
    assert classify_intensity(act, long_run_threshold_km=14.0) == "long_run"


def test_intensity_factor_mapping(make_activity):
    """Verify intensity factors for ACWR calculation."""
    from tracker.classify import INTENSITY_FACTORS

    assert INTENSITY_FACTORS["easy"] == 1.0
    assert INTENSITY_FACTORS["tempo"] == 1.5
    assert INTENSITY_FACTORS["intervals"] == 2.0
    assert INTENSITY_FACTORS["long_run"] == 1.2
    assert INTENSITY_FACTORS["gym"] == 0.8
    assert INTENSITY_FACTORS["other"] == 0.5
