"""Tests for the EvidenceBridge that closes eval → memory loop."""

from unittest.mock import MagicMock

import pytest

from animus_forge.evaluation.base import EvalCase, EvalResult, EvalStatus, EvalSuite
from animus_forge.evaluation.runner import SuiteResult
from animus_forge.intelligence.evidence_bridge import EvidenceBridge, MissionEvidence


@pytest.fixture()
def mock_eval_store():
    store = MagicMock()
    store.record_run.return_value = "run-uuid-1234"
    return store


@pytest.fixture()
def mock_outcome_tracker():
    return MagicMock()


@pytest.fixture()
def mock_cross_memory():
    return MagicMock()


@pytest.fixture()
def bridge(mock_eval_store, mock_outcome_tracker, mock_cross_memory):
    return EvidenceBridge(
        eval_store=mock_eval_store,
        outcome_tracker=mock_outcome_tracker,
        cross_memory=mock_cross_memory,
        auto_learn=True,
    )


def _make_suite_result(
    passed: int = 2,
    failed: int = 1,
    errors: int = 0,
    total_score: float = 0.7,
    score_variance: float = 0.05,
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
                score=0.1,
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


class TestEvidenceBridge:
    """Core bridge behaviour."""

    def test_on_eval_complete_returns_mission_evidence(self, bridge):
        result = _make_suite_result(passed=3, failed=0, total_score=1.0, score_variance=0.0)
        evidence = bridge.on_eval_complete(
            result, workflow_id="wf-1", mission_id="m-1", agent_role="tester"
        )
        assert isinstance(evidence, MissionEvidence)
        assert evidence.mission_id == "m-1"
        assert evidence.workflow_id == "wf-1"
        assert evidence.run_id == "run-uuid-1234"
        assert evidence.pass_rate == 1.0

    def test_records_eval_run_with_metadata(self, bridge, mock_eval_store):
        result = _make_suite_result()
        bridge.on_eval_complete(result, workflow_id="wf-1", mission_id="m-1")
        call = mock_eval_store.record_run.call_args
        assert call.kwargs["metadata"]["mission_id"] == "m-1"
        assert call.kwargs["metadata"]["source"] == "evidence_bridge"

    def test_feeds_outcomes(self, bridge, mock_outcome_tracker):
        result = _make_suite_result(passed=1, failed=1)
        bridge.on_eval_complete(result, workflow_id="wf-1", mission_id="m-1")
        assert mock_outcome_tracker.record_many.called
        records = mock_outcome_tracker.record_many.call_args[0][0]
        assert len(records) == 2
        assert records[0].workflow_id == "wf-1"
        assert records[0].metadata["run_id"] == "run-uuid-1234"

    def test_auto_learn_when_low_pass_rate(self, bridge, mock_cross_memory):
        result = _make_suite_result(passed=1, failed=2, total_score=0.3, score_variance=0.1)
        evidence = bridge.on_eval_complete(
            result, workflow_id="wf-1", mission_id="m-1", agent_role="tester"
        )
        mock_cross_memory.record_learning.assert_called_once()
        call = mock_cross_memory.record_learning.call_args
        assert call.kwargs["agent_role"] == "tester"
        assert "regression" in call.kwargs["tags"]
        assert call.kwargs["importance"] > 0.2
        assert len(evidence.learned_insights) == 1

    def test_auto_learn_when_high_variance(self, bridge, mock_cross_memory):
        result = _make_suite_result(passed=2, failed=1, total_score=0.7, score_variance=0.25)
        bridge.on_eval_complete(result, workflow_id="wf-1", mission_id="m-1")
        mock_cross_memory.record_learning.assert_called_once()

    def test_no_learn_when_passing_and_low_variance(self, bridge, mock_cross_memory):
        result = _make_suite_result(passed=3, failed=0, total_score=1.0, score_variance=0.0)
        bridge.on_eval_complete(result, workflow_id="wf-1", mission_id="m-1")
        mock_cross_memory.record_learning.assert_not_called()

    def test_auto_learn_disabled(self, mock_eval_store, mock_outcome_tracker, mock_cross_memory):
        bridge_no_learn = EvidenceBridge(
            eval_store=mock_eval_store,
            outcome_tracker=mock_outcome_tracker,
            cross_memory=mock_cross_memory,
            auto_learn=False,
        )
        result = _make_suite_result(passed=0, failed=3, total_score=0.0)
        bridge_no_learn.on_eval_complete(result)
        mock_cross_memory.record_learning.assert_not_called()

    def test_build_insight_includes_failed_case_names(self, bridge):
        result = _make_suite_result(passed=1, failed=2, errors=1)
        insight = bridge._build_insight(result, "my_suite")
        assert "my_suite" in insight
        assert "fail_0" in insight
        assert "err_0" in insight

    def test_mission_evidence_to_dict(self):
        ev = MissionEvidence(
            mission_id="m-1",
            workflow_id="wf-1",
            run_id="r-1",
            suite_name="s",
            pass_rate=0.5,
            score_variance=0.1,
            total_cases=10,
            failed_cases=2,
        )
        d = ev.to_dict()
        assert d["mission_id"] == "m-1"
        assert d["pass_rate"] == 0.5
        assert "timestamp" in d
