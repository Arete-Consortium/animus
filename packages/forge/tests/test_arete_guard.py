"""Tests for AreteGuard and eval baseline regression detection."""

import pytest

from animus_forge.evaluation.base import EvalCase, EvalResult, EvalStatus, EvalSuite
from animus_forge.evaluation.runner import SuiteResult
from animus_forge.evaluation.store import EvalStore
from animus_forge.security.arete_guard import AreteGuard, AreteGuardError
from animus_forge.state.backends import SQLiteBackend


@pytest.fixture
def backend(tmp_path):
    from animus_forge.state.migrations import run_migrations

    backend = SQLiteBackend(str(tmp_path / "eval.db"))
    run_migrations(backend)
    yield backend
    backend.close()


@pytest.fixture
def eval_store(backend):
    return EvalStore(backend)


def _make_suite_result(pass_rate: float) -> SuiteResult:
    suite = EvalSuite(name="suite_a", threshold=0.5)
    total = 4
    passed = int(total * pass_rate)
    failed = total - passed
    results = []
    for _ in range(passed):
        results.append(
            EvalResult(case=EvalCase(input="x"), status=EvalStatus.PASSED, score=1.0, output="ok")
        )
    for _ in range(failed):
        results.append(
            EvalResult(case=EvalCase(input="x"), status=EvalStatus.FAILED, score=0.0, output="bad")
        )
    return SuiteResult(
        suite=suite,
        results=results,
        passed=passed,
        failed=failed,
        errors=0,
        total_score=pass_rate,
    )


class TestAreteGuard:
    """AreteGuard behaviour across modes."""

    def test_no_evidence_allows_execution(self, eval_store):
        guard = AreteGuard(eval_store, mode="block")
        assert guard.check("wf-1") is True

    def test_passing_evidence_allows_execution(self, eval_store):
        eval_store.record_run(
            "suite_a",
            _make_suite_result(0.8),
            agent_role="research_citizen",
            metadata={"workflow_id": "wf-1"},
        )
        guard = AreteGuard(eval_store, mode="block")
        assert guard.check("wf-1") is True

    def test_block_mode_raises_on_poor_evidence(self, eval_store):
        eval_store.record_run(
            "suite_a",
            _make_suite_result(0.2),
            agent_role="research_citizen",
            metadata={"workflow_id": "wf-1"},
        )
        guard = AreteGuard(eval_store, mode="block")
        with pytest.raises(AreteGuardError):
            guard.check("wf-1")

    def test_warn_mode_does_not_raise(self, eval_store):
        eval_store.record_run(
            "suite_a",
            _make_suite_result(0.2),
            agent_role="research_citizen",
            metadata={"workflow_id": "wf-1"},
        )
        guard = AreteGuard(eval_store, mode="warn")
        assert guard.check("wf-1") is True

    def test_log_mode_does_not_raise(self, eval_store):
        eval_store.record_run(
            "suite_a",
            _make_suite_result(0.2),
            agent_role="research_citizen",
            metadata={"workflow_id": "wf-1"},
        )
        guard = AreteGuard(eval_store, mode="log")
        assert guard.check("wf-1") is True

    def test_env_mode_override(self, eval_store, monkeypatch):
        monkeypatch.setenv("ARETE_GUARD_MODE", "block")
        eval_store.record_run(
            "suite_a",
            _make_suite_result(0.2),
            agent_role="research_citizen",
            metadata={"workflow_id": "wf-1"},
        )
        guard = AreteGuard(eval_store)
        with pytest.raises(AreteGuardError):
            guard.check("wf-1")


class TestEvalBaseline:
    """Baseline storage and regression detection."""

    def test_set_and_get_baseline(self, eval_store):
        run_id = eval_store.record_run("suite_a", _make_suite_result(1.0))
        eval_store.set_baseline("suite_a", run_id)
        baseline = eval_store.get_baseline("suite_a")
        assert baseline is not None
        assert baseline["id"] == run_id
        assert baseline["pass_rate"] == 1.0

    def test_set_baseline_replaces_previous(self, eval_store):
        run1 = eval_store.record_run("suite_a", _make_suite_result(0.9))
        run2 = eval_store.record_run("suite_a", _make_suite_result(0.95))
        eval_store.set_baseline("suite_a", run1)
        eval_store.set_baseline("suite_a", run2)
        baseline = eval_store.get_baseline("suite_a")
        assert baseline["id"] == run2

    def test_check_regression_no_baseline(self, eval_store):
        result = eval_store.check_regression("suite_a", 0.8)
        assert result["regression_detected"] is False
        assert result["reason"] == "no_baseline"

    def test_check_regression_within_tolerance(self, eval_store):
        run_id = eval_store.record_run("suite_a", _make_suite_result(1.0))
        eval_store.set_baseline("suite_a", run_id)
        result = eval_store.check_regression("suite_a", 0.85, delta_threshold=0.2)
        assert result["regression_detected"] is False
        assert result["reason"] == "within_tolerance"
        assert result["delta"] == 0.15

    def test_check_regression_detected(self, eval_store):
        run_id = eval_store.record_run("suite_a", _make_suite_result(1.0))
        eval_store.set_baseline("suite_a", run_id)
        result = eval_store.check_regression("suite_a", 0.7, delta_threshold=0.2)
        assert result["regression_detected"] is True
        assert result["reason"] == "regression"
        assert result["delta"] == 0.3
