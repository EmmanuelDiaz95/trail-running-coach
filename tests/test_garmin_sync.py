from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tracker import garmin_sync
from tracker.garmin_sync import GarminRateLimited, _is_rate_limit_error, _backoff_seconds


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test gets a clean module-level cache and rate-limit state."""
    garmin_sync._client_cache.clear()
    garmin_sync._rate_limit_until.clear()
    yield
    garmin_sync._client_cache.clear()
    garmin_sync._rate_limit_until.clear()


def test_is_rate_limit_error_detects_429_and_too_many():
    assert _is_rate_limit_error(Exception("429 Client Error: Too Many Requests for url"))
    assert _is_rate_limit_error(Exception("connection failed: 429"))
    assert _is_rate_limit_error(RuntimeError("Garmin returned Too Many Requests"))
    assert not _is_rate_limit_error(Exception("connection refused"))
    assert not _is_rate_limit_error(Exception("invalid credentials"))


def test_check_rate_limit_raises_when_in_memory_cooldown_active():
    until = time.time() + 600
    garmin_sync._rate_limit_until["default"] = until

    with patch("tracker.db.get_garmin_rate_limit_until") as mock_get:
        with pytest.raises(GarminRateLimited) as exc_info:
            garmin_sync._check_rate_limit("default")
        # In-memory hit short-circuits — DB is not consulted
        mock_get.assert_not_called()

    assert exc_info.value.retry_after > 0
    assert exc_info.value.retry_after <= 600


def test_check_rate_limit_loads_from_db_when_memory_clear():
    """A different worker recorded a cooldown in the DB; this process should respect it."""
    db_until = datetime.now(timezone.utc) + timedelta(minutes=10)

    with patch("tracker.db.get_garmin_rate_limit_until", return_value=db_until):
        with pytest.raises(GarminRateLimited):
            garmin_sync._check_rate_limit("default")

    # In-memory cache was populated from DB so subsequent calls don't re-query DB
    assert garmin_sync._rate_limit_until["default"] == pytest.approx(db_until.timestamp(), abs=1.0)


def test_check_rate_limit_passes_when_db_cooldown_expired():
    db_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    with patch("tracker.db.get_garmin_rate_limit_until", return_value=db_until):
        garmin_sync._check_rate_limit("default")  # should not raise


def test_record_rate_limit_sets_memory_and_db():
    original = Exception("429 Too Many Requests")
    with patch("tracker.db.get_garmin_rate_limit_state", return_value={"until": None, "failures": 0}), \
         patch("tracker.db.set_garmin_rate_limit") as mock_set:
        exc = garmin_sync._record_rate_limit("default", original)

    assert isinstance(exc, GarminRateLimited)
    assert "default" in garmin_sync._rate_limit_until
    assert garmin_sync._rate_limit_until["default"] > time.time()
    mock_set.assert_called_once()
    args, _ = mock_set.call_args
    assert args[0] == "default"
    assert isinstance(args[1], datetime)
    assert args[2] == 1  # first failure


def test_record_rate_limit_increments_failure_count():
    """Each consecutive 429 increments the persisted failure count."""
    original = Exception("429")
    with patch("tracker.db.get_garmin_rate_limit_state", return_value={"until": None, "failures": 3}), \
         patch("tracker.db.set_garmin_rate_limit") as mock_set:
        garmin_sync._record_rate_limit("default", original)

    args, _ = mock_set.call_args
    assert args[2] == 4


def test_backoff_seconds_doubles_per_failure_then_caps():
    assert _backoff_seconds(1) == 15 * 60
    assert _backoff_seconds(2) == 30 * 60
    assert _backoff_seconds(3) == 60 * 60
    assert _backoff_seconds(4) == 2 * 3600
    assert _backoff_seconds(5) == 4 * 3600
    # Caps at 12h regardless of how high the failure count goes
    assert _backoff_seconds(20) == 12 * 3600


def test_clear_rate_limit_resets_memory_and_db():
    garmin_sync._rate_limit_until["default"] = time.time() + 600
    with patch("tracker.db.clear_garmin_rate_limit") as mock_clear:
        garmin_sync._clear_rate_limit("default")
    assert "default" not in garmin_sync._rate_limit_until
    mock_clear.assert_called_once_with("default")


def test_get_client_short_circuits_on_active_rate_limit():
    """_get_client must raise without invoking _build_client when cooldown is active."""
    garmin_sync._rate_limit_until["default"] = time.time() + 300

    with patch("tracker.garmin_sync._build_client") as mock_build, \
         patch("tracker.db.get_garmin_rate_limit_until", return_value=None):
        with pytest.raises(GarminRateLimited):
            garmin_sync._get_client("default")
        mock_build.assert_not_called()


def test_garmin_rate_limited_exception_carries_retry_after():
    exc = GarminRateLimited(time.time() + 120, original=Exception("429"))
    assert 119 <= exc.retry_after <= 120
    assert "retry in" in str(exc).lower()
