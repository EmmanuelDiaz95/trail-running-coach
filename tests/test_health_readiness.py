from __future__ import annotations

from datetime import date, timedelta

from coach.health_readiness import compute_health_readiness, HealthReadiness


def _row(d, **kw):
    base = {"date": d.isoformat(), "resting_hr": None, "hrv_last_night": None,
            "training_readiness": None, "sleep_hours": None, "body_battery_am": None}
    base.update(kw)
    return base


def test_no_data_returns_has_data_false():
    r = compute_health_readiness([], date(2026, 7, 5))
    assert isinstance(r, HealthReadiness)
    assert r.has_data is False
    assert r.level == 0
    assert "datos" in r.advice.lower()


def test_all_green_returns_adelante():
    today = date(2026, 7, 5)
    rows = []
    # 30-day baseline: RHR 53, HRV 45
    for i in range(8, 38):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=53, hrv_last_night=45))
    # last 7 days: healthy — RHR 54 (<=53*1.05), HRV 45 (>=45*0.97), good absolutes
    for i in range(0, 7):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=54, hrv_last_night=45,
                         training_readiness=70, sleep_hours=7.5, body_battery_am=60))
    r = compute_health_readiness(rows, today)
    assert r.has_data is True
    assert r.level == 0
    assert "ADELANTE" in r.verdict


def test_two_reds_returns_bajar():
    today = date(2026, 7, 5)
    rows = []
    for i in range(8, 38):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=50, hrv_last_night=50))
    # last 7: RHR way up (>1.10 -> red), HRV way down (<0.90 -> red)
    for i in range(0, 7):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=60, hrv_last_night=40,
                         training_readiness=70, sleep_hours=7.5, body_battery_am=60))
    r = compute_health_readiness(rows, today)
    assert r.level == 2
    assert "BAJAR" in r.verdict


def test_one_yellow_pair_returns_mantener():
    today = date(2026, 7, 5)
    rows = []
    for i in range(8, 38):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=50, hrv_last_night=50))
    # last 7: two yellow absolutes (sleep 6.5 -> yellow, body battery 40 -> yellow)
    for i in range(0, 7):
        d = today - timedelta(days=i)
        rows.append(_row(d, resting_hr=50, hrv_last_night=50,
                         training_readiness=70, sleep_hours=6.5, body_battery_am=40))
    r = compute_health_readiness(rows, today)
    assert r.level == 1
    assert "MANTENER" in r.verdict


from types import SimpleNamespace

from coach.health_readiness import merge_verdict


def _health(level):
    return HealthReadiness(level=level, verdict="v", advice="a", has_data=True)


def _coaching(rec):
    return SimpleNamespace(readiness=SimpleNamespace(recommendation=rec))


def test_merge_takes_max_severity_health_wins():
    verdict, advice, level = merge_verdict(_health(2), _coaching("push"))
    assert level == 2
    assert "BAJAR" in verdict


def test_merge_back_off_raises_from_green():
    verdict, advice, level = merge_verdict(_health(0), _coaching("back_off"))
    assert level == 2
    assert "BAJAR" in verdict


def test_merge_maintain_does_not_raise():
    verdict, advice, level = merge_verdict(_health(0), _coaching("maintain"))
    assert level == 0
    assert "ADELANTE" in verdict


def test_merge_handles_missing_coaching():
    verdict, advice, level = merge_verdict(_health(1), None)
    assert level == 1
    assert "MANTENER" in verdict


def test_merge_handles_null_readiness_attribute():
    coaching_no_readiness = SimpleNamespace(readiness=None)
    verdict, advice, level = merge_verdict(_health(1), coaching_no_readiness)
    assert level == 1
    assert "MANTENER" in verdict
