"""Coverage push tests: dashboard, workflows, executions, coordination,
calendar, notion, marketplace, and executor_step.

Targets ~350 lines of new coverage to push forge from 90% → 93%.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_forge.auth import create_access_token
from animus_forge.state.backends import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_api_routes_coverage.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        be = SQLiteBackend(db_path=db_path)
        be.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "description TEXT);"
        )
        yield be
        be.close()


@pytest.fixture
def client(backend, monkeypatch):
    monkeypatch.setenv("ALLOW_DEMO_AUTH", "true")
    from animus_forge.config.settings import get_settings

    get_settings.cache_clear()

    with patch("animus_forge.api.get_database", return_value=backend):
        with patch("animus_forge.api.run_migrations", return_value=[]):
            import animus_forge.api_state as api_state
            from animus_forge.api import app
            from animus_forge.security.brute_force import get_brute_force_protection

            api_state.limiter.enabled = False
            protection = get_brute_force_protection()
            protection._attempts.clear()
            protection._total_blocked = 0
            protection._total_allowed = 0

            test_client = TestClient(app)
            api_state._app_state["shutting_down"] = False
            api_state._app_state["ready"] = True
            test_client._api_state = api_state
            yield test_client


@pytest.fixture
def auth_headers():
    token = create_access_token("test-user")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_execution(execution_id="exec-1", status_value="running", workflow_id="wf-1"):
    from animus_forge.executions import ExecutionStatus

    mock = MagicMock()
    mock.id = execution_id
    mock.workflow_id = workflow_id
    mock.workflow_name = "Test Workflow"
    mock.status = ExecutionStatus(status_value)
    mock.started_at = datetime.now()
    mock.completed_at = None
    mock.current_step = "step-1"
    mock.progress = 50
    mock.variables = {}
    mock.error = None
    mock.created_at = datetime.now()
    mock.logs = []
    mock.metrics = None
    mock.model_dump.return_value = {
        "id": execution_id,
        "workflow_id": workflow_id,
        "workflow_name": "Test Workflow",
        "status": status_value,
    }
    return mock


def _make_paginated(data, total=1, page=1, page_size=20, total_pages=1):
    mock = MagicMock()
    mock.data = data
    mock.total = total
    mock.page = page
    mock.page_size = page_size
    mock.total_pages = total_pages
    return mock


def _mock_db_backend():
    """Build a mock database backend with fetchone/fetchall/execute."""
    be = MagicMock()
    be.fetchone.return_value = None
    be.fetchall.return_value = []
    be.execute.return_value = []
    return be


# ===========================================================================
# 1. Dashboard route tests
# ===========================================================================


class TestAgentEndpoints:
    """Tests for /v1/agents endpoints."""

    def test_list_agents(self, client, auth_headers):
        resp = client.get("/v1/agents", headers=auth_headers)
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) > 0
        assert "id" in agents[0]
        assert "name" in agents[0]
        assert "capabilities" in agents[0]

    def test_get_agent_success(self, client, auth_headers):
        from animus_forge.contracts.base import AgentRole

        role = list(AgentRole)[0]
        resp = client.get(f"/v1/agents/{role.value}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == role.value

    def test_get_agent_not_found(self, client, auth_headers):
        resp = client.get("/v1/agents/nonexistent_role", headers=auth_headers)
        assert resp.status_code == 404


class TestDashboardStatsEndpoint:
    """Tests for /v1/dashboard/* endpoints."""

    def test_dashboard_stats_success(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.list_workflows.return_value = [{"id": "wf-1"}]
        client._api_state.workflow_engine = mock_engine

        mock_be = _mock_db_backend()
        mock_be.fetchone.side_effect = [
            {"count": 2},  # active
            {"count": 5},  # completed
            {"count": 1},  # failed
            {"tokens": 5000, "cost_cents": 150},  # tokens
        ]
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalWorkflows"] == 1
        assert data["activeExecutions"] == 2
        assert data["completedToday"] == 5
        assert data["failedToday"] == 1
        assert data["totalTokensToday"] == 5000
        assert data["totalCostToday"] == 1.5

    def test_dashboard_stats_empty(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.list_workflows.return_value = None
        client._api_state.workflow_engine = mock_engine

        mock_be = _mock_db_backend()
        # All queries return None (no rows)
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalWorkflows"] == 0
        assert data["activeExecutions"] == 0
        assert data["totalTokensToday"] == 0

    def test_recent_executions_time_formatting(self, client, auth_headers):
        """Test human-readable time strings for various deltas."""
        from animus_forge.executions import ExecutionStatus

        now = datetime.now()

        def _exec(eid, started_at):
            m = MagicMock()
            m.id = eid
            m.workflow_name = "wf"
            m.status = ExecutionStatus.COMPLETED
            m.started_at = started_at
            return m

        execs = [
            _exec("e1", now - timedelta(seconds=10)),  # just now
            _exec("e2", now - timedelta(minutes=5)),  # 5 min ago
            _exec("e3", now - timedelta(hours=3)),  # 3 hours ago
            _exec("e4", now - timedelta(days=2)),  # 2 days ago
            _exec("e5", None),  # pending
        ]

        mock_mgr = MagicMock()
        mock_mgr.list_executions.return_value = _make_paginated(execs, total=5)
        client._api_state.execution_manager = mock_mgr

        resp = client.get("/v1/dashboard/recent-executions?limit=10", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 5
        assert items[0]["time"] == "just now"
        assert "min ago" in items[1]["time"]
        assert "hour" in items[2]["time"]
        assert "day" in items[3]["time"]
        assert items[4]["time"] == "pending"

    def test_recent_executions_1_hour_no_plural(self, client, auth_headers):
        from animus_forge.executions import ExecutionStatus

        m = MagicMock()
        m.id = "e1"
        m.workflow_name = "wf"
        m.status = ExecutionStatus.COMPLETED
        m.started_at = datetime.now() - timedelta(hours=1, minutes=5)

        mock_mgr = MagicMock()
        mock_mgr.list_executions.return_value = _make_paginated([m])
        client._api_state.execution_manager = mock_mgr

        resp = client.get("/v1/dashboard/recent-executions", headers=auth_headers)
        assert resp.status_code == 200
        assert "hours" not in resp.json()[0]["time"]
        assert "hour ago" in resp.json()[0]["time"]

    def test_daily_usage(self, client, auth_headers):
        mock_be = _mock_db_backend()
        mock_be.fetchone.return_value = {"tokens": 1000, "cost_cents": 50}

        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/usage/daily?days=3", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["tokens"] == 1000

    def test_daily_usage_no_data(self, client, auth_headers):
        mock_be = _mock_db_backend()
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/usage/daily", headers=auth_headers)
        assert resp.status_code == 200
        for item in resp.json():
            assert item["tokens"] == 0

    def test_agent_usage_keyword_mapping(self, client, auth_headers):
        mock_be = _mock_db_backend()
        mock_be.fetchall.return_value = [
            {"workflow_name": "Plan analysis tasks", "tokens": 100},
            {"workflow_name": "Build feature", "tokens": 200},
            {"workflow_name": "Review merge request", "tokens": 300},
            {"workflow_name": "Test suite runner", "tokens": 150},
            {"workflow_name": "Doc generator", "tokens": 50},
            {"workflow_name": "Some random workflow", "tokens": 75},
        ]
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/usage/by-agent", headers=auth_headers)
        assert resp.status_code == 200
        data = {item["agent"]: item["tokens"] for item in resp.json()}
        assert data["Planner"] == 100
        assert data["Builder"] == 275  # 200 build + 75 unknown (fallback)
        assert data["Reviewer"] == 300
        assert data["Tester"] == 150
        assert data["Documenter"] == 50

    def test_agent_usage_empty(self, client, auth_headers):
        mock_be = _mock_db_backend()
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/usage/by-agent", headers=auth_headers)
        assert resp.status_code == 200
        agents = {item["agent"] for item in resp.json()}
        assert agents == {"Planner", "Builder", "Tester", "Reviewer", "Documenter"}

    def test_budget_with_alert(self, client, auth_headers):
        mock_be = _mock_db_backend()
        # Return cost that will trigger alert (>80% of Builder's $40 limit)
        mock_be.fetchall.return_value = [
            {"workflow_name": "Build project", "cost_cents": 3500},
        ]
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/budget", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert"] is not None
        assert "Builder" in data["alert"]

    def test_budget_no_alert(self, client, auth_headers):
        mock_be = _mock_db_backend()
        mock_be.fetchall.return_value = [
            {"workflow_name": "Build project", "cost_cents": 100},
        ]
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/budget", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert"] is None

    def test_budget_empty(self, client, auth_headers):
        mock_be = _mock_db_backend()
        with patch("animus_forge.api_routes.dashboard.get_database", return_value=mock_be):
            resp = client.get("/v1/dashboard/budget", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalUsed"] == 0


# ===========================================================================
# 2. Workflow route tests
# ===========================================================================


class TestWorkflowCRUDCoverage:
    """Tests for JSON workflow CRUD endpoints."""

    def test_create_workflow_success(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.save_workflow.return_value = True
        client._api_state.workflow_engine = mock_engine

        resp = client.post(
            "/v1/workflows",
            json={"id": "wf-1", "name": "Test", "description": "A test workflow", "steps": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_create_workflow_failure(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.save_workflow.return_value = False
        client._api_state.workflow_engine = mock_engine

        resp = client.post(
            "/v1/workflows",
            json={"id": "wf-1", "name": "Test", "description": "A test workflow", "steps": []},
            headers=auth_headers,
        )
        assert resp.status_code == 500

    def test_execute_workflow_success(self, client, auth_headers):
        mock_wf = MagicMock()
        mock_wf.variables = {}

        mock_engine = MagicMock()
        mock_engine.load_workflow.return_value = mock_wf
        mock_engine.execute_workflow.return_value = {"result": "done"}
        client._api_state.workflow_engine = mock_engine

        resp = client.post(
            "/v1/workflows/execute",
            json={"workflow_id": "wf-1", "variables": {"key": "val"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_execute_workflow_not_found(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.load_workflow.return_value = None
        client._api_state.workflow_engine = mock_engine

        resp = client.post(
            "/v1/workflows/execute",
            json={"workflow_id": "nope"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestWorkflowRoutesCoverage:
    """Tests for YAML workflows, versioning, and start execution."""

    def test_list_yaml_workflows_success(self, client, auth_headers):
        with patch(
            "animus_forge.api_routes.workflows.list_yaml_workflows",
            return_value=[
                {"name": "Deploy", "description": "Deploy app", "version": "1.0", "path": "/a.yaml"}
            ],
        ):
            resp = client.get("/v1/yaml-workflows", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["workflows"]) == 1
        assert resp.json()["workflows"][0]["id"] == "deploy"

    def test_list_yaml_workflows_exception(self, client, auth_headers):
        with patch(
            "animus_forge.api_routes.workflows.list_yaml_workflows",
            side_effect=RuntimeError("disk error"),
        ):
            resp = client.get("/v1/yaml-workflows", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["workflows"] == []

    def test_get_yaml_workflow_not_found(self, client, auth_headers):
        mock_dir = MagicMock()
        mock_yaml = MagicMock()
        mock_yaml.exists.return_value = False
        mock_yml = MagicMock()
        mock_yml.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_yaml if key.endswith(".yaml") else mock_yml
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        resp = client.get("/v1/yaml-workflows/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_yaml_workflow_success(self, client, auth_headers):
        mock_dir = MagicMock()
        mock_yaml = MagicMock()
        mock_yaml.exists.return_value = True
        mock_yml = MagicMock()
        mock_yml.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_yaml if key.endswith(".yaml") else mock_yml
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        mock_step = MagicMock()
        mock_step.id = "step-1"
        mock_step.type = "shell"
        mock_step.params = {"cmd": "echo hi"}

        mock_wf = MagicMock()
        mock_wf.name = "Deploy"
        mock_wf.description = "Deploy app"
        mock_wf.version = "1.0"
        mock_wf.inputs = {"env": "prod"}
        mock_wf.outputs = ["result"]
        mock_wf.steps = [mock_step]

        with patch(
            "animus_forge.api_routes.workflows.load_yaml_workflow",
            return_value=mock_wf,
        ):
            resp = client.get("/v1/yaml-workflows/deploy", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Deploy"
        assert len(data["steps"]) == 1

    def test_execute_yaml_workflow_success(self, client, auth_headers):
        mock_dir = MagicMock()
        mock_yaml = MagicMock()
        mock_yaml.exists.return_value = True
        mock_yml = MagicMock()
        mock_yml.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_yaml if key.endswith(".yaml") else mock_yml
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        mock_step_result = MagicMock()
        mock_step_result.step_id = "s1"
        mock_step_result.status.value = "success"
        mock_step_result.duration_ms = 100
        mock_step_result.tokens_used = 50

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.started_at = datetime.now()
        mock_result.completed_at = datetime.now()
        mock_result.total_duration_ms = 100
        mock_result.total_tokens = 50
        mock_result.outputs = {"out": "done"}
        mock_result.steps = [mock_step_result]
        mock_result.error = None

        mock_wf = MagicMock()
        mock_wf.name = "Deploy"

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        client._api_state.yaml_workflow_executor = mock_executor

        with patch(
            "animus_forge.api_routes.workflows.load_yaml_workflow",
            return_value=mock_wf,
        ):
            resp = client.post(
                "/v1/yaml-workflows/execute",
                json={"workflow_id": "deploy", "inputs": {"env": "prod"}},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_execute_yaml_workflow_not_found(self, client, auth_headers):
        mock_dir = MagicMock()
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_path
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        resp = client.post(
            "/v1/yaml-workflows/execute",
            json={"workflow_id": "nope"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_get_yaml_workflow_sanitized_empty(self, client, auth_headers):
        """Workflow ID that sanitizes to empty string."""
        resp = client.get("/v1/yaml-workflows/!!!!", headers=auth_headers)
        assert resp.status_code == 404

    def test_compare_versions(self, client, auth_headers):
        mock_diff = MagicMock()
        mock_diff.from_version = "1.0"
        mock_diff.to_version = "2.0"
        mock_diff.has_changes = True
        mock_diff.added_lines = 5
        mock_diff.removed_lines = 2
        mock_diff.changed_sections = ["steps"]
        mock_diff.unified_diff = "+line1\n-line2"

        mock_vm = MagicMock()
        mock_vm.compare_versions.return_value = mock_diff
        client._api_state.version_manager = mock_vm

        resp = client.get(
            "/v1/workflows/my-wf/versions/compare?from_version=1.0&to_version=2.0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_changes"] is True
        assert data["added_lines"] == 5

    def test_compare_versions_error(self, client, auth_headers):
        mock_vm = MagicMock()
        mock_vm.compare_versions.side_effect = ValueError("Version not found")
        client._api_state.version_manager = mock_vm

        resp = client.get(
            "/v1/workflows/my-wf/versions/compare?from_version=1.0&to_version=2.0",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_activate_version_success(self, client, auth_headers):
        mock_vm = MagicMock()
        client._api_state.version_manager = mock_vm

        resp = client.post("/v1/workflows/my-wf/versions/2.0/activate", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["active_version"] == "2.0"

    def test_activate_version_not_found(self, client, auth_headers):
        mock_vm = MagicMock()
        mock_vm.set_active.side_effect = ValueError("not found")
        client._api_state.version_manager = mock_vm

        resp = client.post("/v1/workflows/my-wf/versions/9.9/activate", headers=auth_headers)
        assert resp.status_code == 404

    def test_rollback_success(self, client, auth_headers):
        mock_ver = MagicMock()
        mock_ver.version = "1.0"
        mock_vm = MagicMock()
        mock_vm.rollback.return_value = mock_ver
        client._api_state.version_manager = mock_vm

        resp = client.post("/v1/workflows/my-wf/rollback", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["rolled_back_to"] == "1.0"

    def test_rollback_no_previous(self, client, auth_headers):
        mock_vm = MagicMock()
        mock_vm.rollback.return_value = None
        client._api_state.version_manager = mock_vm

        resp = client.post("/v1/workflows/my-wf/rollback", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_version(self, client, auth_headers):
        mock_vm = MagicMock()
        client._api_state.version_manager = mock_vm

        resp = client.delete("/v1/workflows/my-wf/versions/1.0", headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_version_active(self, client, auth_headers):
        mock_vm = MagicMock()
        mock_vm.delete_version.side_effect = ValueError("Cannot delete active version")
        client._api_state.version_manager = mock_vm

        resp = client.delete("/v1/workflows/my-wf/versions/1.0", headers=auth_headers)
        assert resp.status_code == 400

    def test_list_versioned_workflows(self, client, auth_headers):
        mock_vm = MagicMock()
        mock_vm.list_workflows.return_value = [{"name": "wf", "active_version": "1.0"}]
        client._api_state.version_manager = mock_vm

        resp = client.get("/v1/workflow-versions", headers=auth_headers)
        assert resp.status_code == 200

    def test_start_execution_yaml_fallback(self, client, auth_headers):
        """When JSON load returns None, falls back to YAML lookup."""
        mock_engine = MagicMock()
        mock_engine.load_workflow.return_value = None
        client._api_state.workflow_engine = mock_engine

        # YAML path exists
        mock_dir = MagicMock()
        mock_yaml = MagicMock()
        mock_yaml.exists.return_value = True
        mock_yml = MagicMock()
        mock_yml.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_yaml if key.endswith(".yaml") else mock_yml
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        mock_wf = MagicMock()
        mock_wf.name = "YAML Workflow"

        mock_exec = MagicMock()
        mock_exec.id = "exec-1"

        mock_mgr = MagicMock()
        mock_mgr.create_execution.return_value = mock_exec
        client._api_state.execution_manager = mock_mgr

        with patch(
            "animus_forge.api_routes.workflows.load_yaml_workflow",
            return_value=mock_wf,
        ):
            resp = client.post(
                "/v1/workflows/my-yaml-wf/execute",
                json={"variables": {}},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["workflow_name"] == "YAML Workflow"

    def test_start_execution_not_found(self, client, auth_headers):
        mock_engine = MagicMock()
        mock_engine.load_workflow.return_value = None
        client._api_state.workflow_engine = mock_engine

        mock_dir = MagicMock()
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_dir.__truediv__ = lambda self, key: mock_path
        client._api_state.YAML_WORKFLOWS_DIR = mock_dir

        resp = client.post(
            "/v1/workflows/nope/execute",
            json={"variables": {}},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# 3. Execution route tests (pause/resume/cancel/delete/cleanup/approval)
# ===========================================================================


class TestExecutionActionsCoverage:
    """Tests for pause, resume, cancel, delete, cleanup, approval endpoints."""

    def test_pause_success(self, client, auth_headers):
        exec_mock = _make_execution(status_value="running")
        updated = _make_execution(status_value="paused")

        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.pause_execution.return_value = updated
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/pause", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_pause_not_running(self, client, auth_headers):
        exec_mock = _make_execution(status_value="completed")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/pause", headers=auth_headers)
        assert resp.status_code == 400

    def test_resume_paused(self, client, auth_headers):
        exec_mock = _make_execution(status_value="paused")
        updated = _make_execution(status_value="running")

        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.resume_execution.return_value = updated
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/resume", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_resume_not_paused(self, client, auth_headers):
        exec_mock = _make_execution(status_value="completed")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/resume", headers=auth_headers)
        assert resp.status_code == 400

    def test_resume_approval_approved(self, client, auth_headers):
        exec_mock = _make_execution(status_value="awaiting_approval")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        mock_store = MagicMock()
        mock_store.get_by_token.return_value = {
            "execution_id": "exec-1",
            "context": {"key": "val"},
            "next_step_id": "step-2",
        }

        with patch(
            "animus_forge.workflow.approval_store.get_approval_store",
            return_value=mock_store,
        ):
            resp = client.post(
                "/v1/executions/exec-1/resume",
                json={"token": "abc", "approve": True},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        assert resp.json()["resume_from"] == "step-2"

    def test_resume_approval_rejected(self, client, auth_headers):
        exec_mock = _make_execution(status_value="awaiting_approval")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        mock_store = MagicMock()
        mock_store.get_by_token.return_value = {
            "execution_id": "exec-1",
            "context": {},
            "next_step_id": "step-2",
        }

        with patch(
            "animus_forge.workflow.approval_store.get_approval_store",
            return_value=mock_store,
        ):
            resp = client.post(
                "/v1/executions/exec-1/resume",
                json={"token": "abc", "approve": False, "reason": "bad step"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_resume_approval_no_token(self, client, auth_headers):
        exec_mock = _make_execution(status_value="awaiting_approval")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        resp = client.post(
            "/v1/executions/exec-1/resume",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_resume_approval_invalid_token(self, client, auth_headers):
        exec_mock = _make_execution(status_value="awaiting_approval")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        mock_store = MagicMock()
        mock_store.get_by_token.return_value = None

        with patch(
            "animus_forge.workflow.approval_store.get_approval_store",
            return_value=mock_store,
        ):
            resp = client.post(
                "/v1/executions/exec-1/resume",
                json={"token": "bad"},
                headers=auth_headers,
            )
        assert resp.status_code == 400

    def test_cancel_success(self, client, auth_headers):
        exec_mock = _make_execution(status_value="running")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.cancel_execution.return_value = True
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/cancel", headers=auth_headers)
        assert resp.status_code == 200

    def test_cancel_fails(self, client, auth_headers):
        exec_mock = _make_execution(status_value="completed")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.cancel_execution.return_value = False
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/exec-1/cancel", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_completed(self, client, auth_headers):
        exec_mock = _make_execution(status_value="completed")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.delete_execution.return_value = True
        client._api_state.execution_manager = mock_mgr

        resp = client.delete("/v1/executions/exec-1", headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_running_rejected(self, client, auth_headers):
        exec_mock = _make_execution(status_value="running")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        resp = client.delete("/v1/executions/exec-1", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_pending_rejected(self, client, auth_headers):
        exec_mock = _make_execution(status_value="pending")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        resp = client.delete("/v1/executions/exec-1", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_failed_internal_error(self, client, auth_headers):
        exec_mock = _make_execution(status_value="failed")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        mock_mgr.delete_execution.return_value = False
        client._api_state.execution_manager = mock_mgr

        resp = client.delete("/v1/executions/exec-1", headers=auth_headers)
        assert resp.status_code == 500

    def test_get_approval_status(self, client, auth_headers):
        exec_mock = _make_execution(status_value="awaiting_approval")
        mock_mgr = MagicMock()
        mock_mgr.get_execution.return_value = exec_mock
        client._api_state.execution_manager = mock_mgr

        mock_store = MagicMock()
        mock_store.get_by_execution.return_value = [
            {
                "token": "tok-1",
                "step_id": "step-1",
                "prompt": "Approve?",
                "preview": {},
                "timeout_at": None,
                "created_at": datetime.now().isoformat(),
                "status": "pending",
            },
            {
                "token": "tok-2",
                "step_id": "step-0",
                "status": "approved",
            },
        ]

        with patch(
            "animus_forge.workflow.approval_store.get_approval_store",
            return_value=mock_store,
        ):
            resp = client.get("/v1/executions/exec-1/approval", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 2
        assert len(data["pending_approvals"]) == 1

    def test_cleanup_executions(self, client, auth_headers):
        mock_mgr = MagicMock()
        mock_mgr.cleanup_old_executions.return_value = 3
        client._api_state.execution_manager = mock_mgr

        resp = client.post("/v1/executions/cleanup?max_age_hours=48", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 3


# ===========================================================================
# 4. Coordination route tests
# ===========================================================================


class TestCoordinationRoutesCoverage:
    """Tests for /v1/coordination/* endpoints."""

    def test_health_convergent_available(self, client):
        mock_bridge = MagicMock()
        client._api_state.coordination_bridge = mock_bridge

        health_data = {"grade": "A", "components": {"intent_graph": "healthy"}}
        with patch(
            "animus_forge.agents.convergence.HAS_QUORUM",
            True,
        ):
            with patch(
                "animus_forge.agents.convergence.get_coordination_health",
                return_value=health_data,
            ):
                resp = client.get("/v1/coordination/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["grade"] == "A"

    def test_health_no_bridge(self, client):
        client._api_state.coordination_bridge = None

        with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
            resp = client.get("/v1/coordination/health")
        assert resp.status_code == 200
        assert resp.json()["reason"] == "no active coordination bridge"

    def test_health_convergent_unavailable(self, client):
        with patch("animus_forge.agents.convergence.HAS_QUORUM", False):
            resp = client.get("/v1/coordination/health")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_health_exception(self, client):
        client._api_state.coordination_bridge = MagicMock()

        with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
            with patch(
                "animus_forge.agents.convergence.get_coordination_health",
                side_effect=RuntimeError("boom"),
            ):
                resp = client.get("/v1/coordination/health")
        assert resp.status_code == 200
        assert resp.json()["error"] == "internal error"

    def test_health_empty_report(self, client):
        client._api_state.coordination_bridge = MagicMock()

        with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
            with patch(
                "animus_forge.agents.convergence.get_coordination_health",
                return_value=None,
            ):
                resp = client.get("/v1/coordination/health")
        assert resp.status_code == 200
        assert resp.json()["reason"] == "health check returned no data"

    def _fake_convergent(self):
        """Create a fake convergent module in sys.modules for lazy imports."""
        import types

        fake = types.ModuleType("animus_quorum")
        fake.IntentResolver = MagicMock()
        fake.PythonGraphBackend = MagicMock()
        fake.EventType = MagicMock(side_effect=lambda v: v)
        return fake

    def test_cycles_success(self, client):
        import sys

        fake = self._fake_convergent()
        with patch.dict(sys.modules, {"animus_quorum": fake}):
            with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
                with patch(
                    "animus_forge.agents.convergence.check_dependency_cycles",
                    return_value=[["a", "b", "a"]],
                ):
                    resp = client.get("/v1/coordination/cycles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cycle_count"] == 1

    def test_cycles_no_convergent(self, client):
        with patch("animus_forge.agents.convergence.HAS_QUORUM", False):
            resp = client.get("/v1/coordination/cycles")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_cycles_exception(self, client):
        import sys

        fake = self._fake_convergent()
        fake.IntentResolver = MagicMock(side_effect=RuntimeError("fail"))
        with patch.dict(sys.modules, {"animus_quorum": fake}):
            with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
                resp = client.get("/v1/coordination/cycles")
        assert resp.status_code == 200
        assert resp.json()["error"] == "internal error"

    def test_events_with_filter(self, client):
        import sys

        mock_event = MagicMock()
        mock_event.event_id = "ev-1"
        mock_event.event_type.value = "intent_published"
        mock_event.agent_id = "agent-1"
        mock_event.timestamp = datetime.now().isoformat()
        mock_event.payload = {"key": "val"}
        mock_event.correlation_id = "corr-1"

        mock_log = MagicMock()
        mock_log.query.return_value = [mock_event]
        client._api_state.coordination_event_log = mock_log

        fake = self._fake_convergent()
        with patch.dict(sys.modules, {"animus_quorum": fake}):
            with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
                resp = client.get(
                    "/v1/coordination/events?event_type=intent_published&agent=agent-1&limit=10"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_events_no_log(self, client):
        import sys

        client._api_state.coordination_event_log = None
        fake = self._fake_convergent()
        with patch.dict(sys.modules, {"animus_quorum": fake}):
            with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
                resp = client.get("/v1/coordination/events")
        assert resp.status_code == 200
        assert resp.json()["reason"] == "no active event log"

    def test_events_invalid_type(self, client):
        import sys

        mock_log = MagicMock()
        client._api_state.coordination_event_log = mock_log

        fake = self._fake_convergent()
        fake.EventType = MagicMock(side_effect=ValueError("bad"))
        with patch.dict(sys.modules, {"animus_quorum": fake}):
            with patch("animus_forge.agents.convergence.HAS_QUORUM", True):
                resp = client.get("/v1/coordination/events?event_type=bogus")
        assert resp.status_code == 200
        assert "Unknown event type" in resp.json()["error"]


# ===========================================================================
# 5. Calendar client tests
# ===========================================================================


class TestCalendarClientCoverage:
    """Tests for CalendarClient authenticate, list, check, quick_add, etc."""

    def test_authenticate_not_configured(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path=None)
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            assert c.authenticate() is False

    def test_authenticate_existing_valid_token(self, tmp_path):
        token_path = str(tmp_path / "token.json")
        # Create a dummy token file
        (tmp_path / "token.json").write_text("{}")

        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake/creds.json")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient(credentials_path="/fake/creds.json")

        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch("googleapiclient.discovery.build"),
        ):
            result = c.authenticate(token_path=token_path)

        assert result is True
        assert c._authenticated is True

    def test_authenticate_refresh_token(self, tmp_path):
        token_path = str(tmp_path / "token.json")
        (tmp_path / "token.json").write_text("{}")

        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake/creds.json")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient(credentials_path="/fake/creds.json")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh"
        mock_creds.to_json.return_value = '{"token": "new"}'

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch("googleapiclient.discovery.build"),
        ):
            result = c.authenticate(token_path=token_path)

        assert result is True
        mock_creds.refresh.assert_called_once()

    def test_authenticate_new_flow(self, tmp_path):
        token_path = str(tmp_path / "token.json")

        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake/creds.json")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient(credentials_path="/fake/creds.json")

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = '{"token": "fresh"}'

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        with (
            patch("os.path.exists", return_value=False),
            patch(
                "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
                return_value=mock_flow,
            ),
            patch("googleapiclient.discovery.build"),
        ):
            result = c.authenticate(token_path=token_path)

        assert result is True

    def test_authenticate_exception(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake/creds.json")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient(credentials_path="/fake/creds.json")

        with patch("os.path.exists", side_effect=RuntimeError("boom")):
            result = c.authenticate()

        assert result is False

    def test_list_events_no_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path=None)
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            assert c.list_events() == []

    def test_check_availability_no_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path=None)
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            assert c.check_availability(datetime.now(), datetime.now()) == []

    def test_list_calendars_no_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path=None)
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            assert c.list_calendars() == []

    def test_quick_add_no_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path=None)
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            assert c.quick_add("lunch tomorrow") is None

    def test_get_upcoming_today(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            c.service = MagicMock()
            c._authenticated = True

        with patch.object(c, "list_events", return_value=[]) as mock_le:
            result = c.get_upcoming_today()
            assert result == []
            call_args = mock_le.call_args
            assert call_args.kwargs["max_results"] == 50

    def test_list_events_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "ev1",
                    "summary": "Meeting",
                    "start": {"dateTime": "2025-01-01T10:00:00Z"},
                    "end": {"dateTime": "2025-01-01T11:00:00Z"},
                }
            ]
        }
        c.service = mock_service

        events = c.list_events(max_results=5, query="meeting")
        assert len(events) == 1
        assert events[0].summary == "Meeting"

    def test_list_events_exception(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.list.return_value.execute.side_effect = RuntimeError(
            "API error"
        )
        c.service = mock_service
        assert c.list_events() == []

    def test_get_event_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.get.return_value.execute.return_value = {
            "id": "ev1",
            "summary": "Standup",
            "start": {"dateTime": "2025-01-01T09:00:00Z"},
            "end": {"dateTime": "2025-01-01T09:30:00Z"},
        }
        c.service = mock_service
        event = c.get_event("ev1")
        assert event is not None
        assert event.summary == "Standup"

    def test_create_event_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient, CalendarEvent

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "new-1",
            "summary": "Lunch",
            "start": {"dateTime": "2025-01-01T12:00:00Z"},
            "end": {"dateTime": "2025-01-01T13:00:00Z"},
        }
        c.service = mock_service

        event = CalendarEvent(summary="Lunch", start=datetime.now(), end=datetime.now())
        created = c.create_event(event)
        assert created is not None
        assert created.id == "new-1"

    def test_update_event_no_id(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient, CalendarEvent

            c = CalendarClient()
            c.service = MagicMock()

        event = CalendarEvent(summary="No ID")
        assert c.update_event(event) is None

    def test_update_event_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient, CalendarEvent

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.update.return_value.execute.return_value = {
            "id": "ev1",
            "summary": "Updated",
            "start": {"dateTime": "2025-01-01T12:00:00Z"},
            "end": {"dateTime": "2025-01-01T13:00:00Z"},
        }
        c.service = mock_service

        event = CalendarEvent(id="ev1", summary="Updated", start=datetime.now(), end=datetime.now())
        updated = c.update_event(event)
        assert updated is not None
        assert updated.summary == "Updated"

    def test_delete_event_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        c.service = mock_service
        assert c.delete_event("ev1") is True

    def test_check_availability_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [{"start": "2025-01-01T10:00:00Z", "end": "2025-01-01T11:00:00Z"}]
                }
            }
        }
        c.service = mock_service
        busy = c.check_availability(datetime.now(), datetime.now() + timedelta(hours=8))
        assert len(busy) == 1
        assert busy[0]["calendar_id"] == "primary"

    def test_list_calendars_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.calendarList.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "primary", "summary": "Main", "primary": True, "accessRole": "owner"}]
        }
        c.service = mock_service
        cals = c.list_calendars()
        assert len(cals) == 1
        assert cals[0]["primary"] is True

    def test_quick_add_with_service(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()

        mock_service = MagicMock()
        mock_service.events.return_value.quickAdd.return_value.execute.return_value = {
            "id": "qa-1",
            "summary": "Lunch tomorrow at noon",
            "start": {"dateTime": "2025-01-02T12:00:00Z"},
            "end": {"dateTime": "2025-01-02T13:00:00Z"},
        }
        c.service = mock_service
        event = c.quick_add("Lunch tomorrow at noon")
        assert event is not None
        assert event.id == "qa-1"

    def test_get_tomorrow(self):
        with patch("animus_forge.api_clients.calendar_client.get_settings") as ms:
            ms.return_value = MagicMock(gmail_credentials_path="/fake")
            from animus_forge.api_clients.calendar_client import CalendarClient

            c = CalendarClient()
            c.service = MagicMock()
            c._authenticated = True

        with patch.object(c, "list_events", return_value=[]) as mock_le:
            result = c.get_tomorrow()
            assert result == []
            call_args = mock_le.call_args
            assert call_args.kwargs["time_min"].day != datetime.now(UTC).day


# ===========================================================================
# 6. Notion client tests
# ===========================================================================


class TestNotionClientCoverage:
    """Tests for NotionClientWrapper property extraction and search."""

    def _make_client(self):
        with patch("animus_forge.api_clients.notion_client.get_settings") as ms:
            ms.return_value = MagicMock(notion_token="fake-token")
            with patch("animus_forge.api_clients.notion_client.NotionClient"):
                from animus_forge.api_clients.notion_client import NotionClientWrapper

                return NotionClientWrapper()

    def test_extract_number(self):
        c = self._make_client()
        assert c._extract_property_value({"type": "number", "number": 42}) == 42

    def test_extract_checkbox(self):
        c = self._make_client()
        assert c._extract_property_value({"type": "checkbox", "checkbox": True}) is True

    def test_extract_url(self):
        c = self._make_client()
        assert c._extract_property_value({"type": "url", "url": "https://x.com"}) == "https://x.com"

    def test_extract_rich_text(self):
        c = self._make_client()
        prop = {
            "type": "rich_text",
            "rich_text": [{"text": {"content": "hello "}}, {"text": {"content": "world"}}],
        }
        assert c._extract_property_value(prop) == "hello world"

    def test_extract_title(self):
        c = self._make_client()
        prop = {"type": "title", "title": [{"text": {"content": "My Title"}}]}
        assert c._extract_property_value(prop) == "My Title"

    def test_extract_select(self):
        c = self._make_client()
        prop = {"type": "select", "select": {"name": "High"}}
        assert c._extract_property_value(prop) == "High"

    def test_extract_select_none(self):
        c = self._make_client()
        prop = {"type": "select", "select": None}
        assert c._extract_property_value(prop) is None

    def test_extract_status(self):
        c = self._make_client()
        prop = {"type": "status", "status": {"name": "In Progress"}}
        assert c._extract_property_value(prop) == "In Progress"

    def test_extract_multi_select(self):
        c = self._make_client()
        prop = {
            "type": "multi_select",
            "multi_select": [{"name": "Tag1"}, {"name": "Tag2"}],
        }
        assert c._extract_property_value(prop) == ["Tag1", "Tag2"]

    def test_extract_relation(self):
        c = self._make_client()
        prop = {"type": "relation", "relation": [{"id": "r1"}, {"id": "r2"}]}
        assert c._extract_property_value(prop) == ["r1", "r2"]

    def test_extract_date(self):
        c = self._make_client()
        prop = {"type": "date", "date": {"start": "2025-01-01"}}
        assert c._extract_property_value(prop) == "2025-01-01"

    def test_extract_date_none(self):
        c = self._make_client()
        prop = {"type": "date", "date": None}
        assert c._extract_property_value(prop) is None

    def test_extract_formula(self):
        c = self._make_client()
        prop = {"type": "formula", "formula": {"type": "number", "number": 99}}
        assert c._extract_property_value(prop) == 99

    def test_extract_unknown_type(self):
        c = self._make_client()
        assert c._extract_property_value({"type": "rollup"}) is None

    def test_search_pages(self):
        c = self._make_client()
        c.client.search.return_value = {
            "results": [
                {
                    "id": "p1",
                    "properties": {"Name": {"title": [{"text": {"content": "Page One"}}]}},
                    "url": "https://notion.so/p1",
                }
            ]
        }
        results = c.search_pages("test")
        assert len(results) == 1
        assert results[0]["title"] == "Page One"

    def test_search_pages_empty(self):
        c = self._make_client()
        c.client.search.return_value = {"results": []}
        assert c.search_pages("nothing") == []

    def test_search_pages_not_configured(self):
        with patch("animus_forge.api_clients.notion_client.get_settings") as ms:
            ms.return_value = MagicMock(notion_token=None)
            from animus_forge.api_clients.notion_client import NotionClientWrapper

            c = NotionClientWrapper()
            assert c.search_pages("q") == []

    def test_query_database_async(self):
        from unittest.mock import AsyncMock

        c = self._make_client()
        mock_async = MagicMock()
        mock_async.databases.query = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "row-1",
                        "url": "https://notion.so/row-1",
                        "created_time": "",
                        "last_edited_time": "",
                        "properties": {},
                    }
                ]
            }
        )
        c._async_client = mock_async

        async def run():
            return await c.query_database_async("db-1")

        results = asyncio.run(run())
        assert len(results) == 1
        assert results[0]["id"] == "row-1"


# ===========================================================================
# 7. Marketplace tests
# ===========================================================================


class TestMarketplaceCoverage:
    """Tests for PluginMarketplace search, CRUD, and edge cases."""

    def _make_marketplace(self):
        from animus_forge.plugins.marketplace import PluginMarketplace

        mock_be = MagicMock()
        mock_be.transaction.return_value.__enter__ = MagicMock()
        mock_be.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_be.execute.return_value = []

        mp = PluginMarketplace.__new__(PluginMarketplace)
        mp.backend = mock_be
        return mp

    def test_search_with_tags(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = [
            [(5,)],  # count query
            [],  # select query
        ]
        result = mp.search("test", tags=["ml", "data"])
        assert result.total == 5
        # Verify tag filtering was included in the SQL
        calls = mp.backend.execute.call_args_list
        assert any('"%ml%"' in str(c) or "ml" in str(c) for c in calls)

    def test_search_verified_only(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = [
            [(2,)],  # count
            [],  # select
        ]
        result = mp.search("q", verified_only=True)
        assert result.total == 2

    def test_search_count_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = [
            RuntimeError("db error"),  # count fails
            [],  # select still runs after count
        ]
        result = mp.search("q")
        assert result.total == 0

    def test_search_select_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = [
            [(1,)],  # count succeeds
            RuntimeError("db error"),  # select fails
        ]
        result = mp.search("q")
        assert result.total == 1
        assert result.results == []

    def test_get_plugin_with_releases(self):
        mp = self._make_marketplace()
        row = (
            "id-1",
            "my-plugin",
            "My Plugin",
            "desc",
            "long desc",
            "author",
            "other",
            '["tag1"]',
            100,
            4.5,
            10,
            "1.0.0",
            "2025-01-01T00:00:00",
            "2025-01-01T00:00:00",
            True,
            False,
            "https://gh.com",
        )
        mp.backend.execute.side_effect = [
            [row],  # get_plugin query
            [],  # get_releases query
        ]
        plugin = mp.get_plugin("my-plugin")
        assert plugin is not None
        assert plugin.name == "my-plugin"
        assert plugin.verified is True

    def test_get_plugin_not_found(self):
        mp = self._make_marketplace()
        mp.backend.execute.return_value = []
        assert mp.get_plugin("nope") is None

    def test_get_release_not_found(self):
        mp = self._make_marketplace()
        mp.backend.execute.return_value = []
        assert mp.get_release("plugin", "1.0") is None

    def test_add_plugin_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = RuntimeError("unique constraint")

        from animus_forge.plugins.models import PluginCategory, PluginListing

        listing = PluginListing(
            id="id-1",
            name="test",
            display_name="Test",
            latest_version="1.0",
            category=PluginCategory.OTHER,
        )
        assert mp.add_plugin(listing) is False

    def test_add_release_with_metadata(self):
        mp = self._make_marketplace()

        from animus_forge.plugins.models import PluginMetadata, PluginRelease

        release = PluginRelease(
            id="rel-1",
            plugin_name="test",
            version="1.0",
            download_url="https://example.com/test-1.0.tar.gz",
            checksum="abc123",
            metadata=PluginMetadata(name="test", version="1.0"),
        )
        assert mp.add_release(release) is True

    def test_add_release_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = RuntimeError("db error")

        from animus_forge.plugins.models import PluginRelease

        release = PluginRelease(
            id="rel-1",
            plugin_name="test",
            version="1.0",
            download_url="https://example.com/test-1.0.tar.gz",
            checksum="abc123",
        )
        assert mp.add_release(release) is False

    def test_update_plugin_tags(self):
        mp = self._make_marketplace()
        assert mp.update_plugin("test", tags=["a", "b"]) is True
        call_args = mp.backend.execute.call_args
        # Tags should be JSON-serialized
        assert '["a", "b"]' in str(call_args)

    def test_update_plugin_no_fields(self):
        mp = self._make_marketplace()
        assert mp.update_plugin("test", invalid_field="x") is False

    def test_update_plugin_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = RuntimeError("db")
        assert mp.update_plugin("test", description="new") is False

    def test_increment_downloads(self):
        mp = self._make_marketplace()
        assert mp.increment_downloads("test") is True

    def test_increment_downloads_exception(self):
        mp = self._make_marketplace()
        mp.backend.execute.side_effect = RuntimeError("db")
        assert mp.increment_downloads("test") is False

    def test_row_to_release_bad_json(self):
        mp = self._make_marketplace()
        # Row with invalid metadata JSON at index 10
        row = (
            "id-1",
            "plugin",
            "1.0",
            "2025-01-01T00:00:00",
            "https://dl.com/p.tar.gz",
            "abc",
            None,
            "changelog",
            1024,
            '["1.0"]',
            "not valid json{{{",
        )
        release = mp._row_to_release(row)
        assert release.metadata is None
        assert release.version == "1.0"

    def test_get_categories(self):
        mp = self._make_marketplace()
        mp.backend.execute.return_value = [("integration", 3), ("other", 7)]
        cats = mp.get_categories()
        assert cats["integration"] == 3
        assert cats["other"] == 7

    def test_update_plugin_category_enum(self):
        from animus_forge.plugins.models import PluginCategory

        mp = self._make_marketplace()
        assert mp.update_plugin("test", category=PluginCategory.SECURITY) is True


# ===========================================================================
# 8. Executor step tests
# ===========================================================================


class TestExecutorStepCoverage:
    """Tests for StepExecutionMixin preconditions, fallbacks, and error paths."""

    def _make_executor(self):
        from animus_forge.workflow.executor_step import StepExecutionMixin

        class FakeExecutor(StepExecutionMixin):
            pass

        ex = FakeExecutor()
        ex._handlers = {}
        ex._context = {}
        ex.contract_validator = None
        ex.checkpoint_manager = None
        ex.fallback_callbacks = {}
        return ex

    def _make_step(self, step_id="step-1", step_type="shell", **kwargs):
        from animus_forge.workflow.loader import StepConfig

        return StepConfig(id=step_id, type=step_type, **kwargs)

    def test_input_validation_failure(self):
        from animus_forge.workflow.executor_results import StepResult, StepStatus

        ex = self._make_executor()
        ex.contract_validator = MagicMock()
        ex.contract_validator.validate_input.side_effect = ValueError("bad input")

        step = self._make_step(params={"role": "builder", "input": {}})
        result = StepResult(step_id="step-1", status=StepStatus.PENDING)

        handler, cb, error = ex._check_step_preconditions(step, result)
        assert handler is None
        assert "Input validation failed" in error

    def test_unknown_handler_type(self):
        from animus_forge.workflow.executor_results import StepResult, StepStatus

        ex = self._make_executor()
        step = self._make_step(step_type="nonexistent")
        result = StepResult(step_id="step-1", status=StepStatus.PENDING)

        handler, cb, error = ex._check_step_preconditions(step, result)
        assert handler is None
        assert "Unknown step type" in error

    def test_circuit_breaker_open(self):
        from animus_forge.workflow.executor_results import StepResult, StepStatus

        ex = self._make_executor()
        ex._handlers["shell"] = MagicMock()

        mock_cb = MagicMock()
        mock_cb.is_open = True

        step = self._make_step()
        result = StepResult(step_id="step-1", status=StepStatus.PENDING)

        with patch(
            "animus_kernel.executor.executor_step.get_circuit_breaker",
            return_value=mock_cb,
        ):
            handler, cb, error = ex._check_step_preconditions(step, result)
        assert handler is None
        assert "Circuit breaker open" in error

    def test_execute_step_circuit_breaker_error(self):
        from animus_forge.utils.circuit_breaker import CircuitBreakerError
        from animus_forge.workflow.executor_results import StepStatus

        ex = self._make_executor()
        ex._handlers["shell"] = MagicMock(side_effect=CircuitBreakerError("open"))

        step = self._make_step(max_retries=0)

        with patch(
            "animus_kernel.executor.executor_step.get_circuit_breaker",
            return_value=None,
        ):
            result = ex._execute_step(step)
        assert result.status == StepStatus.FAILED
        assert "open" in result.error

    def test_execute_step_output_validation_failure(self):
        from animus_forge.workflow.executor_results import StepStatus

        ex = self._make_executor()
        ex._handlers["shell"] = MagicMock(return_value={"tokens_used": 10})
        ex.contract_validator = MagicMock()
        ex.contract_validator.validate_input.return_value = None
        ex.contract_validator.validate_output.side_effect = ValueError("bad output")

        step = self._make_step(params={"role": "builder"}, max_retries=0)

        with patch(
            "animus_kernel.executor.executor_step.get_circuit_breaker",
            return_value=None,
        ):
            result = ex._execute_step(step)
        assert result.status == StepStatus.FAILED
        assert "bad output" in result.error

    def test_execute_step_async_circuit_breaker_error(self):
        from animus_forge.utils.circuit_breaker import CircuitBreakerError
        from animus_forge.workflow.executor_results import StepStatus

        ex = self._make_executor()
        ex._handlers["shell"] = MagicMock(side_effect=CircuitBreakerError("open"))

        step = self._make_step(max_retries=0)

        async def run():
            with patch(
                "animus_kernel.executor.executor_step.get_circuit_breaker",
                return_value=None,
            ):
                return await ex._execute_step_async(step)

        result = asyncio.run(run())
        assert result.status == StepStatus.FAILED

    def test_fallback_none(self):
        ex = self._make_executor()
        step = self._make_step()
        assert ex._execute_fallback(step, "error", None) is None

    def test_fallback_default_value(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        step = self._make_step()
        step.fallback = FallbackConfig(type="default_value", value=42)

        result = ex._execute_fallback(step, "error", None)
        assert result["fallback_value"] == 42
        assert result["fallback_used"] is True

    def test_fallback_alternate_step_success(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        ex._handlers["shell"] = MagicMock(return_value={"result": "ok", "tokens_used": 0})

        step = self._make_step()
        step.fallback = FallbackConfig(
            type="alternate_step",
            step={"id": "alt-1", "type": "shell", "params": {}},
        )

        with patch(
            "animus_kernel.executor.executor_step.get_circuit_breaker",
            return_value=None,
        ):
            result = ex._execute_fallback(step, "error", "wf-1")
        assert result is not None
        assert result.get("result") == "ok"

    def test_fallback_callback(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        ex.fallback_callbacks["my_cb"] = MagicMock(return_value={"recovered": True})

        step = self._make_step()
        step.fallback = FallbackConfig(type="callback", callback="my_cb")

        result = ex._execute_fallback(step, "err", None)
        assert result["recovered"] is True

    def test_fallback_callback_not_registered(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        step = self._make_step()
        step.fallback = FallbackConfig(type="callback", callback="missing_cb")

        result = ex._execute_fallback(step, "err", None)
        assert result is None

    def test_fallback_callback_exception(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        ex.fallback_callbacks["bad_cb"] = MagicMock(side_effect=RuntimeError("boom"))

        step = self._make_step()
        step.fallback = FallbackConfig(type="callback", callback="bad_cb")

        result = ex._execute_fallback(step, "err", None)
        assert result is None

    def test_fallback_async_none(self):
        ex = self._make_executor()
        step = self._make_step()
        result = asyncio.run(ex._execute_fallback_async(step, "err", None))
        assert result is None

    def test_fallback_async_default_value(self):
        from animus_forge.workflow.loader import FallbackConfig

        ex = self._make_executor()
        step = self._make_step()
        step.fallback = FallbackConfig(type="default_value", value="fallback")

        result = asyncio.run(ex._execute_fallback_async(step, "err", None))
        assert result["fallback_value"] == "fallback"

    def test_condition_skip(self):
        from animus_forge.workflow.executor_results import StepResult, StepStatus
        from animus_forge.workflow.loader import ConditionConfig

        ex = self._make_executor()
        step = self._make_step()
        step.condition = ConditionConfig(field="enabled", operator="equals", value=True)
        ex._context = {"enabled": False}

        result = StepResult(step_id="step-1", status=StepStatus.PENDING)
        handler, cb, error = ex._check_step_preconditions(step, result)
        assert result.status == StepStatus.SKIPPED
        assert handler is None
        assert error is None
