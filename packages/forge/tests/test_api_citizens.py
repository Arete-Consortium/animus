"""Tests for Research Citizen API routes."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_forge.citizens import CitizenCommissioner
from animus_forge.citizens.research_citizen import ResearchCitizen
from animus_forge.citizens.store import MissionStore
from animus_forge.state.backends import SQLiteBackend


@pytest.fixture
def memory_backend():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        backend = SQLiteBackend(db_path=db_path)
        # Initialise citizen schema via MissionStore
        MissionStore(backend)
        yield backend
        backend.close()


@pytest.fixture
def test_client(memory_backend):
    """Create a test client with citizen commissioner wired in."""
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
            test_client = TestClient(app)

    api_state._app_state["shutting_down"] = False

    # Wire up a minimal citizen commissioner using the test backend
    mission_store = MissionStore(memory_backend)
    mock_engine = MagicMock()
    mock_engine.load_workflow.return_value = MagicMock(
        workflow_id="wf-1", status="success", outputs={"result": "ok"}
    )
    mock_engine.execute_workflow.return_value = MagicMock(
        workflow_id="wf-1", status="success", outputs={"result": "ok"}
    )
    mock_eval_runner = MagicMock()
    mock_eval_runner.run.return_value = _make_suite_result(
        passed=3, failed=0, total_score=1.0, score_variance=0.0
    )
    mock_eval_loader = MagicMock()
    mock_evidence_bridge = MagicMock()
    mock_evidence_bridge.on_eval_complete.return_value = MagicMock(
        mission_id="m-1",
        workflow_id="wf-1",
        run_id="run-1",
        suite_name="test_suite",
        pass_rate=1.0,
        score_variance=0.0,
        total_cases=3,
        failed_cases=0,
    )

    citizen = ResearchCitizen(
        mission_store=mission_store,
        workflow_engine=mock_engine,
        eval_runner=mock_eval_runner,
        eval_loader=mock_eval_loader,
        evidence_bridge=mock_evidence_bridge,
    )
    api_state.citizen_commissioner = CitizenCommissioner(citizen)

    yield test_client

    api_state.citizen_commissioner = None


@pytest.fixture
def auth_headers():
    from animus_forge.api_routes.auth import create_access_token

    token = create_access_token("test-user")
    return {"Authorization": f"Bearer {token}"}


def _make_suite_result(passed=2, failed=0, total_score=1.0, score_variance=0.0):
    from animus_forge.evaluation.base import EvalCase, EvalResult, EvalStatus, EvalSuite
    from animus_forge.evaluation.runner import SuiteResult

    suite = EvalSuite(name="test_suite", threshold=0.5)
    results = []
    for i in range(passed):
        results.append(
            EvalResult(
                case=EvalCase(input=f"p{i}"), status=EvalStatus.PASSED, score=1.0, output="ok"
            )
        )
    for i in range(failed):
        results.append(
            EvalResult(
                case=EvalCase(input=f"f{i}"), status=EvalStatus.FAILED, score=0.0, output="bad"
            )
        )
    return SuiteResult(
        suite=suite,
        results=results,
        passed=passed,
        failed=failed,
        total_score=total_score,
        score_variance=score_variance,
    )


class TestCitizenEndpoints:
    def test_commission_mission(self, test_client, auth_headers):
        payload = {
            "objective": "test objective",
            "eval_suite": "test_suite",
            "workflow_template": "echo_test",
        }
        response = test_client.post(
            "/v1/citizens/research/commission", json=payload, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "commissioned"
        assert "mission_id" in data

    def test_get_mission(self, test_client, auth_headers):
        # Commission first
        payload = {"objective": "x", "eval_suite": "s", "workflow_template": "w"}
        resp = test_client.post(
            "/v1/citizens/research/commission", json=payload, headers=auth_headers
        )
        mid = resp.json()["mission_id"]

        response = test_client.get(f"/v1/citizens/research/{mid}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mid
        assert data["state"] == "pending"

    def test_run_mission_iteration(self, test_client, auth_headers):
        payload = {"objective": "x", "eval_suite": "s", "workflow_template": "w"}
        resp = test_client.post(
            "/v1/citizens/research/commission", json=payload, headers=auth_headers
        )
        mid = resp.json()["mission_id"]

        response = test_client.post(f"/v1/citizens/research/{mid}/run", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "completed"

    def test_list_missions(self, test_client, auth_headers):
        payload = {"objective": "x", "eval_suite": "s", "workflow_template": "w"}
        test_client.post("/v1/citizens/research/commission", json=payload, headers=auth_headers)
        test_client.post("/v1/citizens/research/commission", json=payload, headers=auth_headers)

        response = test_client.get("/v1/citizens/research", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["missions"]) == 2

    def test_commission_missing_fields(self, test_client, auth_headers):
        payload = {"objective": "x"}
        response = test_client.post(
            "/v1/citizens/research/commission", json=payload, headers=auth_headers
        )
        assert response.status_code == 400

    def test_get_nonexistent_mission(self, test_client, auth_headers):
        response = test_client.get("/v1/citizens/research/nonexistent", headers=auth_headers)
        assert response.status_code == 404
