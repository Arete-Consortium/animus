"""Tests for AreteToolsHandlerMixin step handlers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.executor_core import WorkflowExecutor
from animus_forge.workflow.loader import StepConfig, WorkflowConfig

# ─── Helpers ───────────────────────────────────────────────────────────


def _make_workflow(step_type: str, params: dict) -> WorkflowConfig:
    """Build a minimal workflow with one step."""
    return WorkflowConfig(
        name="Test Workflow",
        version="1.0",
        description="",
        steps=[StepConfig(id="test_step", type=step_type, params=params)],
    )


def _make_executor(dry_run: bool = False) -> WorkflowExecutor:
    return WorkflowExecutor(dry_run=dry_run)


# ─── Signal Audit ──────────────────────────────────────────────────────


class TestSignalAudit:
    """Tests for _execute_signal_audit handler."""

    def test_dry_run_returns_mock(self):
        executor = _make_executor(dry_run=True)
        workflow = _make_workflow("signal_audit", {"file": "test.py"})
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["dry_run"] is True
        assert output["score"] == 85
        assert output["grade"] == "B"
        assert output["file"] == "test.py"

    def test_missing_file_param_raises(self):
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {})
        result = executor.execute(workflow)
        assert result.status == "failed"

    def test_empty_file_param_raises(self):
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": ""})
        result = executor.execute(workflow)
        assert result.status == "failed"

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", True)
    @patch("animus_kernel.executor.executor_arete.run_quality_audit", create=True)
    def test_direct_import_path(self, mock_audit):
        mock_audit.return_value = {
            "score": 92,
            "grade": "A",
            "dimensions": {"clarity": 95},
            "flags": [],
        }
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": "src/main.py"})
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["score"] == 92
        assert output["grade"] == "A"
        assert output["dimensions"] == {"clarity": 95}
        mock_audit.assert_called_once_with("src/main.py")

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", True)
    @patch("animus_kernel.executor.executor_arete.run_quality_audit", create=True)
    def test_min_score_pass(self, mock_audit):
        mock_audit.return_value = {"score": 80, "grade": "B", "dimensions": {}, "flags": []}
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": "x.py", "min_score": 70})
        result = executor.execute(workflow)
        assert result.status == "success"
        assert result.steps[0].output["score"] == 80

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", True)
    @patch("animus_kernel.executor.executor_arete.run_quality_audit", create=True)
    def test_min_score_fail(self, mock_audit):
        mock_audit.return_value = {"score": 50, "grade": "F", "dimensions": {}, "flags": []}
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": "x.py", "min_score": 70})
        result = executor.execute(workflow)
        assert result.status == "failed"

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", False)
    @patch("animus_kernel.executor.executor_arete._run_subprocess")
    def test_subprocess_fallback(self, mock_sub):
        mock_sub.return_value = {
            "score": 75,
            "grade": "C",
            "dimensions": {},
            "flags": ["verbose"],
        }
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": "app.py"})
        result = executor.execute(workflow)
        assert result.status == "success"
        assert result.steps[0].output["score"] == 75
        mock_sub.assert_called_once()

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", False)
    @patch("animus_kernel.executor.executor_arete._run_subprocess")
    def test_subprocess_failure_propagates(self, mock_sub):
        mock_sub.side_effect = RuntimeError("Subprocess signal-audit failed (exit 1): error")
        executor = _make_executor()
        workflow = _make_workflow("signal_audit", {"file": "app.py"})
        result = executor.execute(workflow)
        assert result.status == "failed"

    def test_context_variable_substitution(self):
        executor = _make_executor(dry_run=True)
        step = StepConfig(id="s1", type="signal_audit", params={"file": "${target_file}"})
        context = {"target_file": "resolved.py"}
        output = executor._execute_signal_audit(step, context)
        assert output["file"] == "resolved.py"

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", True)
    @patch("animus_kernel.executor.executor_arete.run_quality_audit", create=True)
    def test_output_includes_all_fields(self, mock_audit):
        mock_audit.return_value = {
            "score": 88,
            "grade": "B+",
            "dimensions": {"a": 1, "b": 2},
            "flags": ["x", "y"],
        }
        executor = _make_executor()
        step = StepConfig(id="s1", type="signal_audit", params={"file": "f.py"})
        output = executor._execute_signal_audit(step, {})
        assert set(output.keys()) == {"score", "grade", "dimensions", "flags", "file"}

    @patch("animus_kernel.executor.executor_arete.HAS_SIGNAL", True)
    @patch("animus_kernel.executor.executor_arete.run_quality_audit", create=True)
    def test_missing_keys_in_result_default_gracefully(self, mock_audit):
        mock_audit.return_value = {}  # no keys
        executor = _make_executor()
        step = StepConfig(id="s1", type="signal_audit", params={"file": "f.py"})
        output = executor._execute_signal_audit(step, {})
        assert output["score"] == 0
        assert output["grade"] == ""
        assert output["dimensions"] == {}
        assert output["flags"] == []


# ─── Autopsy Analyze ───────────────────────────────────────────────────


class TestAutopsyAnalyze:
    """Tests for _execute_autopsy_analyze handler."""

    def test_dry_run_returns_mock(self):
        executor = _make_executor(dry_run=True)
        workflow = _make_workflow("autopsy_analyze", {"error_text": "KeyError: 'x'"})
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["dry_run"] is True
        assert output["failure_type"] == "unknown"

    def test_missing_error_text_raises(self):
        executor = _make_executor()
        workflow = _make_workflow("autopsy_analyze", {})
        result = executor.execute(workflow)
        assert result.status == "failed"

    @patch("animus_kernel.executor.executor_arete.HAS_AUTOPSY", True)
    @patch("animus_kernel.executor.executor_arete.analyze_failure", create=True)
    def test_direct_import_path(self, mock_analyze):
        mock_analyze.return_value = {
            "failure_type": "tool_loop",
            "error_chain": ["step1 failed", "retry exhausted"],
            "recommendations": ["Add circuit breaker"],
            "loops_detected": True,
        }
        executor = _make_executor()
        workflow = _make_workflow(
            "autopsy_analyze",
            {"error_text": "RuntimeError: max retries", "workflow_id": "wf-123"},
        )
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["failure_type"] == "tool_loop"
        assert output["loops_detected"] is True
        assert output["workflow_id"] == "wf-123"
        mock_analyze.assert_called_once_with("RuntimeError: max retries", workflow_id="wf-123")

    @patch("animus_kernel.executor.executor_arete.HAS_AUTOPSY", False)
    @patch("animus_kernel.executor.executor_arete.subprocess")
    def test_subprocess_fallback(self, mock_subprocess):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps(
            {
                "failure_type": "overconfidence",
                "error_chain": ["bad prediction"],
                "recommendations": ["Lower confidence"],
                "loops_detected": False,
            }
        )
        mock_subprocess.run.return_value = mock_proc
        executor = _make_executor()
        workflow = _make_workflow("autopsy_analyze", {"error_text": "Wrong answer"})
        result = executor.execute(workflow)
        assert result.status == "success"
        assert result.steps[0].output["failure_type"] == "overconfidence"

    @patch("animus_kernel.executor.executor_arete.HAS_AUTOPSY", False)
    @patch("animus_kernel.executor.executor_arete.subprocess")
    def test_subprocess_nonzero_exit(self, mock_subprocess):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "fatal error"
        mock_subprocess.run.return_value = mock_proc
        executor = _make_executor()
        workflow = _make_workflow("autopsy_analyze", {"error_text": "crash"})
        result = executor.execute(workflow)
        assert result.status == "failed"

    def test_context_substitution_in_error_text(self):
        executor = _make_executor(dry_run=True)
        step = StepConfig(
            id="s1",
            type="autopsy_analyze",
            params={"error_text": "Failed in ${step_name}"},
        )
        context = {"step_name": "build_step"}
        output = executor._execute_autopsy_analyze(step, context)
        assert "build_step" in output["error_chain"][0]

    @patch("animus_kernel.executor.executor_arete.HAS_AUTOPSY", True)
    @patch("animus_kernel.executor.executor_arete.analyze_failure", create=True)
    def test_default_workflow_id_empty(self, mock_analyze):
        mock_analyze.return_value = {
            "failure_type": "unknown",
            "error_chain": [],
            "recommendations": [],
            "loops_detected": False,
        }
        executor = _make_executor()
        step = StepConfig(id="s1", type="autopsy_analyze", params={"error_text": "err"})
        output = executor._execute_autopsy_analyze(step, {})
        assert output["workflow_id"] == ""

    @patch("animus_kernel.executor.executor_arete.HAS_AUTOPSY", True)
    @patch("animus_kernel.executor.executor_arete.analyze_failure", create=True)
    def test_output_fields(self, mock_analyze):
        mock_analyze.return_value = {
            "failure_type": "goal_necrosis",
            "error_chain": ["a"],
            "recommendations": ["b"],
            "loops_detected": False,
        }
        executor = _make_executor()
        step = StepConfig(id="s1", type="autopsy_analyze", params={"error_text": "err"})
        output = executor._execute_autopsy_analyze(step, {})
        assert set(output.keys()) == {
            "failure_type",
            "error_chain",
            "recommendations",
            "loops_detected",
            "workflow_id",
        }


# ─── Verdict Capture ──────────────────────────────────────────────────


class TestVerdictCapture:
    """Tests for _execute_verdict_capture handler."""

    def test_dry_run_returns_mock(self):
        executor = _make_executor(dry_run=True)
        workflow = _make_workflow(
            "verdict_capture",
            {"title": "Use PostgreSQL", "reasoning": "Better for our scale"},
        )
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["dry_run"] is True
        assert output["title"] == "Use PostgreSQL"
        assert output["category"] == "general"

    def test_missing_title_raises(self):
        executor = _make_executor()
        workflow = _make_workflow("verdict_capture", {"reasoning": "no title"})
        result = executor.execute(workflow)
        assert result.status == "failed"

    @patch("animus_kernel.executor.executor_arete.HAS_VERDICT", True)
    @patch("animus_kernel.executor.executor_arete.DecisionStore", create=True)
    def test_direct_import_path(self, mock_store_cls):
        mock_store = MagicMock()
        mock_store.record.return_value = {
            "id": "dec-001",
            "review_date": "2026-04-05",
        }
        mock_store_cls.return_value = mock_store
        executor = _make_executor()
        workflow = _make_workflow(
            "verdict_capture",
            {
                "title": "Switch to Rust",
                "reasoning": "Performance",
                "alternatives": ["Go", "C++"],
                "category": "architecture",
            },
        )
        result = executor.execute(workflow)
        assert result.status == "success"
        output = result.steps[0].output
        assert output["decision_id"] == "dec-001"
        assert output["category"] == "architecture"
        mock_store.record.assert_called_once_with(
            title="Switch to Rust",
            reasoning="Performance",
            alternatives=["Go", "C++"],
            category="architecture",
        )

    @patch("animus_kernel.executor.executor_arete.HAS_VERDICT", False)
    @patch("animus_kernel.executor.executor_arete._run_subprocess")
    def test_subprocess_fallback(self, mock_sub):
        mock_sub.return_value = {"id": "dec-002", "review_date": "2026-05-01"}
        executor = _make_executor()
        workflow = _make_workflow(
            "verdict_capture",
            {"title": "Use Redis", "reasoning": "Caching needs"},
        )
        result = executor.execute(workflow)
        assert result.status == "success"
        assert result.steps[0].output["decision_id"] == "dec-002"

    def test_context_substitution_in_title(self):
        executor = _make_executor(dry_run=True)
        step = StepConfig(
            id="s1",
            type="verdict_capture",
            params={"title": "Deploy ${service_name}", "reasoning": "needed"},
        )
        context = {"service_name": "auth-api"}
        output = executor._execute_verdict_capture(step, context)
        assert output["title"] == "Deploy auth-api"

    def test_default_category_is_general(self):
        executor = _make_executor(dry_run=True)
        step = StepConfig(
            id="s1",
            type="verdict_capture",
            params={"title": "Test", "reasoning": "r"},
        )
        output = executor._execute_verdict_capture(step, {})
        assert output["category"] == "general"

    def test_default_alternatives_empty(self):
        executor = _make_executor(dry_run=True)
        step = StepConfig(
            id="s1",
            type="verdict_capture",
            params={"title": "Test", "reasoning": "r"},
        )
        # Just verify it doesn't crash with no alternatives
        output = executor._execute_verdict_capture(step, {})
        assert output["title"] == "Test"

    @patch("animus_kernel.executor.executor_arete.HAS_VERDICT", False)
    @patch("animus_kernel.executor.executor_arete._run_subprocess")
    def test_subprocess_failure_propagates(self, mock_sub):
        mock_sub.side_effect = RuntimeError("Subprocess verdict failed")
        executor = _make_executor()
        workflow = _make_workflow("verdict_capture", {"title": "X", "reasoning": "Y"})
        result = executor.execute(workflow)
        assert result.status == "failed"


# ─── Handler Registration ─────────────────────────────────────────────


class TestHandlerRegistration:
    """Verify handlers are registered in WorkflowExecutor."""

    def test_signal_audit_registered(self):
        executor = _make_executor()
        assert "signal_audit" in executor._handlers

    def test_autopsy_analyze_registered(self):
        executor = _make_executor()
        assert "autopsy_analyze" in executor._handlers

    def test_verdict_capture_registered(self):
        executor = _make_executor()
        assert "verdict_capture" in executor._handlers

    def test_handlers_are_callable(self):
        executor = _make_executor()
        for name in ("signal_audit", "autopsy_analyze", "verdict_capture"):
            assert callable(executor._handlers[name])


# ─── _substitute_context ──────────────────────────────────────────────


class TestSubstituteContext:
    """Tests for the context variable substitution helper."""

    def test_basic_substitution(self):
        from animus_forge.workflow.executor_arete import _substitute_context

        result = _substitute_context("hello ${name}", {"name": "world"})
        assert result == "hello world"

    def test_multiple_substitutions(self):
        from animus_forge.workflow.executor_arete import _substitute_context

        result = _substitute_context("${a} and ${b}", {"a": "foo", "b": "bar"})
        assert result == "foo and bar"

    def test_non_string_context_values_skipped(self):
        from animus_forge.workflow.executor_arete import _substitute_context

        result = _substitute_context("${num}", {"num": 42})
        assert result == "${num}"

    def test_missing_key_unchanged(self):
        from animus_forge.workflow.executor_arete import _substitute_context

        result = _substitute_context("${missing}", {})
        assert result == "${missing}"


# ─── _run_subprocess ──────────────────────────────────────────────────


class TestRunSubprocess:
    """Tests for the subprocess fallback helper."""

    @patch("animus_kernel.executor.executor_arete.subprocess.run")
    def test_success_parses_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"key": "value"}', stderr="")
        from animus_forge.workflow.executor_arete import _run_subprocess

        result = _run_subprocess(["test-cmd", "arg"])
        assert result == {"key": "value"}

    @patch("animus_kernel.executor.executor_arete.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
        from animus_forge.workflow.executor_arete import _run_subprocess

        with pytest.raises(RuntimeError, match="exit 1"):
            _run_subprocess(["test-cmd"])

    @patch("animus_kernel.executor.executor_arete.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        from animus_forge.workflow.executor_arete import _run_subprocess

        with pytest.raises(json.JSONDecodeError):
            _run_subprocess(["test-cmd"])
