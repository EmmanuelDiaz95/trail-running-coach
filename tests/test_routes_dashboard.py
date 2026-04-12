from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_profiles(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "id" in data[0]
    assert "name" in data[0]


def test_get_weeks(client):
    with patch("api.routes_dashboard.build_all_weeks_json") as mock_build:
        mock_build.return_value = [{"number": 1, "actual": {"distance_km": 27}}]
        resp = client.get("/api/weeks")
        assert resp.status_code == 200
        data = resp.json()
        assert "weeks" in data
        assert isinstance(data["weeks"], list)
        assert data["weeks"][0]["number"] == 1
        assert "last_synced" in data


def test_sync_requires_auth_when_configured(client):
    with patch("api.routes_dashboard.API_KEY", "test-secret"):
        resp = client.post("/api/sync?week=1")
        assert resp.status_code == 401


def test_sync_with_valid_auth(client):
    with patch("api.routes_dashboard.API_KEY", "test-secret"), \
         patch("api.routes_dashboard.build_week_json") as mock_build, \
         patch("api.routes_dashboard._update_weeks_cache"):
        mock_build.return_value = {"number": 1, "compliance": 99, "activities": []}
        resp = client.post(
            "/api/sync?week=1",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 200
        assert resp.json()["compliance"] == 99
