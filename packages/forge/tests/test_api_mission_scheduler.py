"""Tests for mission scheduler API routes."""

import asyncio
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_forge.state.backends import SQLiteBackend


@pytest.fixture
def memory_backend():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        backend = SQLiteBackend(db_path=db_path)
        yield backend
        backend.close()


@pytest.fixture
def test_client(memory_backend):
    import animus_forge.api_state as api_state
    from animus_forge.api import app
    from animus_forge.api_state import limiter
    from animus_forge.security.brute_force import get_brute_force_protection

    limiter.enabled = False
    protection = get_brute_force_protection()
    protection._attempts.clear()
    protection._total_blocked = 0
    protection._total_allowed = 0

    with patch("animus_forge.api.get_database", return_value=memory_backend):
        with patch("animus_forge.api.run_migrations", return_value=[]):
            client = TestClient(app)

    api_state._app_state["shutting_down"] = False

    # Wire up a minimal mission scheduler mock
    scheduler_mock = MagicMock()
    scheduler_mock.is_running = False  # Start as "stopped"
    scheduler_mock.start = MagicMock(return_value=asyncio.Future())
    scheduler_mock.start.return_value.set_result(None)
    scheduler_mock.stop = MagicMock(return_value=asyncio.Future())
    scheduler_mock.stop.return_value.set_result(None)
    scheduler_mock.status.return_value = {
        "is_running": True,
        "active_workers": 1,
        "free_slots": 3,
        "global_spend_usd": "0.50",
        "global_cap_usd": "100.00",
    }

    api_state.mission_scheduler = scheduler_mock

    yield client

    api_state.mission_scheduler = None


@pytest.fixture
def auth_headers():
    from animus_forge.api_routes.auth import create_access_token

    token = create_access_token("test-user")
    return {"Authorization": f"Bearer {token}"}


class TestSchedulerEndpoints:
    def test_start_scheduler(self, test_client, auth_headers):
        response = test_client.post("/v1/scheduler/start", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

    def test_start_already_running(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        # Mark as already running
        api_state.mission_scheduler.is_running = True
        response = test_client.post("/v1/scheduler/start", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_running"

        # Reset for other tests
        api_state.mission_scheduler.is_running = False

    def test_stop_scheduler(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        # Mark as running
        api_state.mission_scheduler.is_running = True
        response = test_client.post("/v1/scheduler/stop", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

        # Reset
        api_state.mission_scheduler.is_running = False

    def test_stop_already_stopped(self, test_client, auth_headers):
        response = test_client.post("/v1/scheduler/stop", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_stopped"

    def test_get_status(self, test_client, auth_headers):
        response = test_client.get("/v1/scheduler/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "active_workers" in data
        assert "free_slots" in data
        assert data["global_spend_usd"] == "0.50"

    def test_start_without_scheduler(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        api_state.mission_scheduler = None
        response = test_client.post("/v1/scheduler/start", headers=auth_headers)
        assert response.status_code == 400
        data = response.json()
        assert "not initialized" in data["error"]["message"]

    def test_stop_without_scheduler(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        api_state.mission_scheduler = None
        response = test_client.post("/v1/scheduler/stop", headers=auth_headers)
        assert response.status_code == 400
        data = response.json()
        assert "not initialized" in data["error"]["message"]

    def test_status_without_scheduler(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        api_state.mission_scheduler = None
        response = test_client.get("/v1/scheduler/status", headers=auth_headers)
        assert response.status_code == 400
        data = response.json()
        assert "not initialized" in data["error"]["message"]

    def test_get_metrics(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        # Wire a mock metrics object
        metrics_mock = MagicMock()
        metrics_mock.summary.return_value = {
            "task_dispatched": 5,
            "result_processed": 4,
            "mission_completed": 2,
        }
        api_state.mission_scheduler.metrics = metrics_mock

        response = test_client.get("/v1/scheduler/metrics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["task_dispatched"] == 5
        assert data["mission_completed"] == 2

    def test_get_metrics_by_mission(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        metrics_mock = MagicMock()
        metrics_mock.by_mission.return_value = [
            {
                "event_type": "task_dispatched",
                "task_id": "t1",
                "value": None,
                "recorded_at": "2026-07-27T00:00:00",
            }
        ]
        api_state.mission_scheduler.metrics = metrics_mock

        response = test_client.get("/v1/scheduler/metrics?mission_id=m1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["mission_id"] == "m1"
        assert len(data["events"]) == 1

    def test_get_metrics_without_scheduler(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        api_state.mission_scheduler = None
        response = test_client.get("/v1/scheduler/metrics", headers=auth_headers)
        assert response.status_code == 400

    def test_get_metrics_without_metrics(self, test_client, auth_headers):
        import animus_forge.api_state as api_state

        api_state.mission_scheduler.metrics = None
        response = test_client.get("/v1/scheduler/metrics", headers=auth_headers)
        assert response.status_code == 400
