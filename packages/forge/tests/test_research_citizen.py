"""Tests for ResearchCitizen and CitizenCommissioner."""

from unittest.mock import MagicMock

import pytest

from animus_forge.citizens.commissioner import CitizenCommissioner
from animus_forge.citizens.mission import MissionConfig, MissionState
from animus_forge.citizens.research_citizen import ResearchCitizen
from animus_forge.citizens.store import MissionStore
from animus_forge.evaluation.base import EvalCase, EvalResult, EvalStatus, EvalSuite
from animus_forge.evaluation.runner import SuiteResult
from animus_forge.intelligence.evidence_bridge import MissionEvidence


@pytest.fixture()
def memory_backend():
    """Create an in-memory SQLite backend for tests."""
    from animus_forge.state.backends import SQLiteBackend

    backend = SQLiteBackend(":memory:")
    # Initialise citizen schema via MissionStore
    MissionStore(backend)
    return backend


@pytest.fixture()
def mission_store(memory_backend):
    return MissionStore(memory_backend)


@pytest.fixture()
def mock_workflow_engine():
    engine = MagicMock()
    wf = MagicMock()
    wf.workflow_id = "wf-1"
    wf.status = "success"
    wf.outputs = {"result": "ok"}
    engine.load_workflow.return_value = wf
    engine.execute_workflow.return_value = wf
    return engine


@pytest.fixture()
def mock_eval_runner():
    runner = MagicMock()
    runner.run.return_value = _make_suite_result(passed=3, failed=0, total_score=1.0)
    return runner


@pytest.fixture()
def mock_eval_loader():
    loader = MagicMock()
    suite = EvalSuite(name="test_suite", threshold=0.5)
    loader.load_suite.return_value = suite
    return loader


@pytest.fixture()
def mock_evidence_bridge():
    bridge = MagicMock()
    bridge.on_eval_complete.return_value = MissionEvidence(
        mission_id="m-1",
        workflow_id="wf-1",
        run_id="run-1",
        suite_name="test_suite",
        pass_rate=1.0,
        score_variance=0.0,
        total_cases=3,
        failed_cases=0,
    )
    return bridge


@pytest.fixture()
def citizen(
    mission_store,
    mock_workflow_engine,
    mock_eval_runner,
    mock_eval_loader,
    mock_evidence_bridge,
):
    return ResearchCitizen(
        mission_store=mission_store,
        workflow_engine=mock_workflow_engine,
        eval_runner=mock_eval_runner,
        eval_loader=mock_eval_loader,
        evidence_bridge=mock_evidence_bridge,
    )


def _make_suite_result(
    passed: int = 2,
    failed: int = 0,
    errors: int = 0,
    total_score: float = 1.0,
    score_variance: float = 0.0,
) -> SuiteResult:
    suite = EvalSuite(name="test_suite", threshold=0.5)
    results = []
    for i in range(passed):
        results.append(
            EvalResult(
                case=EvalCase(input=f"p{i}", name=f"pass_{i}"),
                status=EvalStatus.PASSED,
                score=1.0,
                output="ok",
            )
        )
    for i in range(failed):
        results.append(
            EvalResult(
                case=EvalCase(input=f"f{i}", name=f"fail_{i}"),
                status=EvalStatus.FAILED,
                score=0.0,
                output="bad",
            )
        )
    for i in range(errors):
        results.append(
            EvalResult(
                case=EvalCase(input=f"e{i}", name=f"err_{i}"),
                status=EvalStatus.ERROR,
                score=0.0,
                output=None,
                error="boom",
            )
        )
    return SuiteResult(
        suite=suite,
        results=results,
        passed=passed,
        failed=failed,
        errors=errors,
        total_score=total_score,
        score_variance=score_variance,
    )


class TestResearchCitizen:
    """Core ResearchCitizen behaviour."""

    def test_commission_creates_mission(self, citizen, mission_store):
        config = MissionConfig(
            objective="test objective",
            eval_suite="test_suite",
            workflow_template="echo_test",
        )
        mid = citizen.commission(config)
        assert mid
        mission = mission_store.get(mid)
        assert mission is not None
        assert mission.config.objective == "test objective"
        assert mission.state == MissionState.PENDING

    def test_run_iteration_completes_when_passing(self, citizen, mock_evidence_bridge):
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
            min_pass_rate=0.9,
            max_variance=0.1,
        )
        mid = citizen.commission(config)
        result = citizen.run_iteration(mid)
        assert result.state == MissionState.COMPLETED
        assert result.current_iteration == 1
        assert result.last_pass_rate == 1.0

    def test_run_iteration_retries_when_failing(
        self, citizen, mock_evidence_bridge, mock_eval_runner
    ):
        # First eval fails
        mock_eval_runner.run.return_value = _make_suite_result(
            passed=1, failed=2, total_score=0.3, score_variance=0.05
        )
        mock_evidence_bridge.on_eval_complete.return_value = MissionEvidence(
            mission_id="m-1",
            workflow_id="wf-1",
            run_id="run-1",
            suite_name="test_suite",
            pass_rate=0.33,
            score_variance=0.05,
            total_cases=3,
            failed_cases=2,
        )
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
            max_iterations=3,
            min_pass_rate=0.9,
        )
        mid = citizen.commission(config)
        result = citizen.run_iteration(mid)
        assert result.state == MissionState.NEEDS_RETRY
        assert result.current_iteration == 1
        assert result.metadata.get("temperature") == 0.8  # escalated from 0.7

    def test_run_iteration_fails_at_max_iterations(
        self, citizen, mock_evidence_bridge, mock_eval_runner
    ):
        mock_eval_runner.run.return_value = _make_suite_result(
            passed=0, failed=3, total_score=0.0, score_variance=0.0
        )
        mock_evidence_bridge.on_eval_complete.return_value = MissionEvidence(
            mission_id="m-1",
            workflow_id="wf-1",
            run_id="run-1",
            suite_name="test_suite",
            pass_rate=0.0,
            score_variance=0.0,
            total_cases=3,
            failed_cases=3,
        )
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
            max_iterations=2,
            min_pass_rate=0.9,
        )
        mid = citizen.commission(config)
        citizen.run_iteration(mid)
        citizen.run_iteration(mid)
        final = citizen.run_iteration(mid)
        assert final.state == MissionState.FAILED
        assert "Max iterations" in (final.error or "")

    def test_run_mission_loops_to_completion(self, citizen, mock_evidence_bridge, mock_eval_runner):
        # First fails, second passes
        def side_effect(*args, **kwargs):
            # Return failing on first call, passing on second
            if mock_eval_runner.run.call_count == 1:
                mock_evidence_bridge.on_eval_complete.return_value = MissionEvidence(
                    mission_id="m-1",
                    workflow_id="wf-1",
                    run_id="run-1",
                    suite_name="test_suite",
                    pass_rate=0.5,
                    score_variance=0.05,
                    total_cases=2,
                    failed_cases=1,
                )
                return _make_suite_result(passed=1, failed=1, total_score=0.5, score_variance=0.25)
            mock_evidence_bridge.on_eval_complete.return_value = MissionEvidence(
                mission_id="m-1",
                workflow_id="wf-1",
                run_id="run-2",
                suite_name="test_suite",
                pass_rate=1.0,
                score_variance=0.0,
                total_cases=2,
                failed_cases=0,
            )
            return _make_suite_result(passed=2, failed=0, total_score=1.0, score_variance=0.0)

        mock_eval_runner.run.side_effect = side_effect
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
            max_iterations=3,
            min_pass_rate=0.9,
            max_variance=0.1,
        )
        mid = citizen.commission(config)
        final = citizen.run_mission(mid)
        assert final.state == MissionState.COMPLETED
        assert final.current_iteration == 2

    def test_workflow_not_found_raises(self, citizen, mock_workflow_engine):
        mock_workflow_engine.load_workflow.return_value = None
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="missing_wf",
        )
        mid = citizen.commission(config)
        result = citizen.run_iteration(mid)
        assert result.state == MissionState.FAILED
        assert "not found" in (result.error or "")

    def test_get_mission(self, citizen):
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
        )
        mid = citizen.commission(config)
        fetched = citizen.get_mission(mid)
        assert fetched is not None
        assert fetched.id == mid

    def test_list_missions(self, citizen):
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
        )
        citizen.commission(config)
        citizen.commission(config)
        assert len(citizen.list_missions()) == 2
        assert len(citizen.list_missions(state=MissionState.PENDING)) == 2


class TestCitizenCommissioner:
    """Commissioner API layer."""

    def test_commission_and_status(self, citizen):
        commissioner = CitizenCommissioner(citizen)
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
        )
        mid = commissioner.commission(config)
        status = commissioner.status(mid)
        assert status is not None
        assert status["state"] == "pending"
        assert status["objective"] == "test"

    def test_run_iteration(self, citizen, mock_evidence_bridge):
        commissioner = CitizenCommissioner(citizen)
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
        )
        mid = commissioner.commission(config)
        result = commissioner.run(mid)
        assert result["state"] == "completed"

    def test_list_missions(self, citizen):
        commissioner = CitizenCommissioner(citizen)
        config = MissionConfig(
            objective="test",
            eval_suite="suite",
            workflow_template="wf",
        )
        commissioner.commission(config)
        commissioner.commission(config)
        missions = commissioner.list()
        assert len(missions) == 2
