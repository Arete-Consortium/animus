"""Edge-case coverage tests for the workflow executor subsystem.

Targets:
  - executor_core.py: __init__, _emit_log, _emit_progress, _validate_workflow_inputs, _check_budget_exceeded
  - executor_patterns.py: _record_sub_step_metrics, _execute_sub_step_attempt, _execute_with_retries
  - executor_integrations.py: _execute_shell, _execute_checkpoint, _execute_github
"""

import subprocess
import sys

import pytest

sys.path.insert(0, "src")

from unittest.mock import MagicMock, patch

from animus_forge.workflow.executor_core import WorkflowExecutor
from animus_forge.workflow.executor_results import ExecutionResult
from animus_forge.workflow.loader import StepConfig, WorkflowConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_executor(**overrides) -> WorkflowExecutor:
    """Create a WorkflowExecutor bypassing __init__ and setting only the
    attributes needed for the method under test."""
    exe = WorkflowExecutor.__new__(WorkflowExecutor)
    # Sensible defaults that individual tests can override
    exe.checkpoint_manager = None
    exe.contract_validator = None
    exe.budget_manager = None
    exe.dry_run = False
    exe.error_callback = None
    exe.fallback_callbacks = {}
    exe.memory_manager = None
    exe.memory_config = None
    exe.feedback_engine = None
    exe.execution_manager = None
    exe._execution_id = None
    exe._handlers = {}
    exe._context = {}
    exe._current_workflow_id = None
    for k, v in overrides.items():
        setattr(exe, k, v)
    return exe


def _make_step(step_id="s1", step_type="shell", params=None, **kwargs) -> StepConfig:
    """Convenience factory for StepConfig with relaxed type checking."""
    return StepConfig(id=step_id, type=step_type, params=params or {}, **kwargs)


# ===================================================================
# 1. TestWorkflowExecutorInit
# ===================================================================


class TestWorkflowExecutorInit:
    """WorkflowExecutor.__init__ wiring."""

    def test_init_all_none(self):
        exe = WorkflowExecutor()
        assert exe.checkpoint_manager is None
        assert exe.contract_validator is None
        assert exe.budget_manager is None
        assert exe.dry_run is False
        assert exe.fallback_callbacks == {}
        assert exe.execution_manager is None
        assert exe._execution_id is None

    def test_init_with_managers(self):
        cp = MagicMock(name="checkpoint")
        bm = MagicMock(name="budget")
        em = MagicMock(name="execution")
        exe = WorkflowExecutor(
            checkpoint_manager=cp, budget_manager=bm, execution_manager=em, dry_run=True
        )
        assert exe.checkpoint_manager is cp
        assert exe.budget_manager is bm
        assert exe.execution_manager is em
        assert exe.dry_run is True

    def test_handler_registry_populated(self):
        exe = WorkflowExecutor()
        expected_types = {
            "shell",
            "checkpoint",
            "parallel",
            "claude_code",
            "openai",
            "fan_out",
            "fan_in",
            "map_reduce",
            "mcp_tool",
            "github",
            "notion",
            "gmail",
            "slack",
            "calendar",
            "browser",
        }
        assert expected_types.issubset(set(exe._handlers.keys()))

    def test_register_custom_handler(self):
        exe = WorkflowExecutor()
        handler = MagicMock()
        exe.register_handler("custom_type", handler)
        assert exe._handlers["custom_type"] is handler


# ===================================================================
# 2. TestEmitLog
# ===================================================================


class TestEmitLog:
    """_emit_log: non-fatal log emission to execution_manager."""

    def test_emit_log_with_execution_manager(self):
        em = MagicMock()
        exe = _bare_executor(execution_manager=em, _execution_id="exec-1")
        exe._emit_log("info", "hello", step_id="s1")
        em.add_log.assert_called_once()
        call_args = em.add_log.call_args
        assert call_args[0][0] == "exec-1"
        assert call_args[1]["step_id"] == "s1"

    def test_emit_log_no_manager_no_crash(self):
        exe = _bare_executor(execution_manager=None, _execution_id=None)
        # Should return silently
        exe._emit_log("info", "should not crash")

    def test_emit_log_no_execution_id_no_crash(self):
        em = MagicMock()
        exe = _bare_executor(execution_manager=em, _execution_id=None)
        exe._emit_log("warning", "no exec id")
        em.add_log.assert_not_called()

    def test_emit_log_exception_caught(self):
        em = MagicMock()
        em.add_log.side_effect = RuntimeError("boom")
        exe = _bare_executor(execution_manager=em, _execution_id="exec-1")
        # Must not propagate
        exe._emit_log("error", "will fail internally")


# ===================================================================
# 3. TestEmitProgress
# ===================================================================


class TestEmitProgress:
    """_emit_progress: calculates percentage, handles missing manager."""

    def test_emit_progress_percentage(self):
        em = MagicMock()
        exe = _bare_executor(execution_manager=em, _execution_id="exec-1")
        exe._emit_progress(2, 10, "step-2")
        em.update_progress.assert_called_once_with("exec-1", 20, current_step="step-2")

    def test_emit_progress_zero_total(self):
        em = MagicMock()
        exe = _bare_executor(execution_manager=em, _execution_id="exec-1")
        exe._emit_progress(0, 0, "step-0")
        em.update_progress.assert_called_once_with("exec-1", 0, current_step="step-0")

    def test_emit_progress_no_manager(self):
        exe = _bare_executor(execution_manager=None, _execution_id=None)
        # Should not raise
        exe._emit_progress(1, 5, "step-1")


# ===================================================================
# 4. TestValidateWorkflowInputs
# ===================================================================


class TestValidateWorkflowInputs:
    """_validate_workflow_inputs: defaults, required, missing."""

    def test_no_input_spec_passes(self):
        wf = WorkflowConfig(name="wf", version="1", description="", steps=[], inputs={})
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor()
        assert exe._validate_workflow_inputs(wf, result) is True

    def test_applies_default(self):
        wf = WorkflowConfig(
            name="wf",
            version="1",
            description="",
            steps=[],
            inputs={"repo": {"required": True, "default": "owner/repo"}},
        )
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor()
        exe._context = {}
        assert exe._validate_workflow_inputs(wf, result) is True
        assert exe._context["repo"] == "owner/repo"

    def test_missing_required_fails(self):
        wf = WorkflowConfig(
            name="wf",
            version="1",
            description="",
            steps=[],
            inputs={"token": {"required": True}},
        )
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor()
        exe._context = {}
        assert exe._validate_workflow_inputs(wf, result) is False
        assert result.status == "failed"
        assert "Missing required input: token" in result.error

    def test_optional_input_not_provided_passes(self):
        wf = WorkflowConfig(
            name="wf",
            version="1",
            description="",
            steps=[],
            inputs={"debug": {"required": False}},
        )
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor()
        exe._context = {}
        assert exe._validate_workflow_inputs(wf, result) is True


# ===================================================================
# 5. TestCheckBudgetExceeded
# ===================================================================


class TestCheckBudgetExceeded:
    """_check_budget_exceeded: token allocation and daily limit checks."""

    def test_no_budget_manager_passes(self):
        step = _make_step()
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor(budget_manager=None)
        assert exe._check_budget_exceeded(step, result) is False

    def test_under_budget_passes(self):
        bm = MagicMock()
        bm.can_allocate.return_value = True
        bm.config.daily_token_limit = 0  # disabled
        step = _make_step(params={"estimated_tokens": 500})
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor(budget_manager=bm)
        assert exe._check_budget_exceeded(step, result) is False
        bm.can_allocate.assert_called_once_with(500)

    def test_over_budget_fails(self):
        bm = MagicMock()
        bm.can_allocate.return_value = False
        step = _make_step(params={"estimated_tokens": 99999})
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor(budget_manager=bm)
        assert exe._check_budget_exceeded(step, result) is True
        assert result.status == "failed"
        assert result.error == "Token budget exceeded"

    @patch("animus_forge.workflow.executor_core.get_task_store", create=True)
    def test_daily_limit_exceeded(self, mock_get_store):
        """When daily token usage meets or exceeds daily_token_limit."""
        bm = MagicMock()
        bm.can_allocate.return_value = True
        bm.config.daily_token_limit = 5000
        step = _make_step()
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor(budget_manager=bm)

        # Patch the lazy import inside the method
        store = MagicMock()
        store.get_daily_budget.return_value = [{"total_tokens": 6000}]
        with patch("animus_forge.db.get_task_store", return_value=store):
            exceeded = exe._check_budget_exceeded(step, result)
        assert exceeded is True
        assert result.error == "Daily token budget exceeded"

    def test_default_estimated_tokens_used_when_param_missing(self):
        """When step.params has no estimated_tokens, default 1000 is used."""
        bm = MagicMock()
        bm.can_allocate.return_value = True
        bm.config.daily_token_limit = 0
        step = _make_step(params={})  # no estimated_tokens key
        result = ExecutionResult(workflow_name="wf")
        exe = _bare_executor(budget_manager=bm)
        exe._check_budget_exceeded(step, result)
        bm.can_allocate.assert_called_once_with(1000)


# ===================================================================
# 6. TestExecuteShell
# ===================================================================


class TestExecuteShell:
    """_execute_shell: subprocess delegation with safety checks."""

    def _settings_mock(self, **overrides):
        s = MagicMock()
        s.shell_timeout_seconds = 300
        s.shell_max_output_bytes = 10 * 1024 * 1024
        s.shell_allowed_commands = None
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_successful_command(self, mock_sub, mock_val, mock_settings, mock_run):
        mock_settings.return_value = self._settings_mock()
        mock_val.return_value = "echo hi"
        mock_sub.return_value = "echo hi"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "hi\n"
        proc.stderr = ""
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "echo hi"})
        out = exe._execute_shell(step, {})
        assert out["stdout"] == "hi\n"
        assert out["returncode"] == 0

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_failed_command_raises(self, mock_sub, mock_val, mock_settings, mock_run):
        mock_settings.return_value = self._settings_mock()
        mock_val.return_value = "false"
        mock_sub.return_value = "false"
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "err"
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "false"})
        with pytest.raises(RuntimeError, match="Command failed with code 1"):
            exe._execute_shell(step, {})

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_timeout_raises(self, mock_sub, mock_val, mock_settings, mock_run):
        mock_settings.return_value = self._settings_mock()
        mock_val.return_value = "sleep 999"
        mock_sub.return_value = "sleep 999"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 999", timeout=300)

        exe = _bare_executor()
        step = _make_step(params={"command": "sleep 999"})
        with pytest.raises(RuntimeError, match="timed out"):
            exe._execute_shell(step, {})

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_output_truncation(self, mock_sub, mock_val, mock_settings, mock_run):
        mock_settings.return_value = self._settings_mock(shell_max_output_bytes=20)
        mock_val.return_value = "big"
        mock_sub.return_value = "big"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "A" * 100  # exceeds 20 bytes
        proc.stderr = ""
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "big"})
        out = exe._execute_shell(step, {})
        assert "[OUTPUT TRUNCATED]" in out["stdout"]

    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    def test_dangerous_command_rejected(self, mock_val, mock_settings):
        from animus_forge.errors import ValidationError

        mock_settings.return_value = self._settings_mock()
        mock_val.side_effect = ValidationError("dangerous pattern detected")

        exe = _bare_executor()
        step = _make_step(params={"command": "sudo rm -rf /"})
        with pytest.raises(ValidationError, match="dangerous"):
            exe._execute_shell(step, {})


# ===================================================================
# 7. TestCheckSubStepBudget
# ===================================================================


# NOTE: `_check_sub_step_budget` was removed in roadmap A2. The per-attempt
# `can_allocate` gate was racy (concurrent sub-steps could collectively
# overspend); the gate is now an atomic `allocate()`/`release()` reservation in
# the parallel handler. The reservation contract (incl. per-agent limits and
# thread-safety) is covered by tests/test_budget_reservation.py.


# ===================================================================
# 8. TestExecuteWithRetries
# ===================================================================


class TestExecuteWithRetries:
    """_execute_with_retries: retry loop with backoff."""

    def test_success_first_attempt(self):
        handler = MagicMock(return_value={"response": "ok", "tokens_used": 10})
        exe = _bare_executor(budget_manager=None, _handlers={"shell": handler})
        step = _make_step(step_id="r1", max_retries=2)
        output, tokens, error_msg, retries = exe._execute_with_retries(step, "stage", {}, {})
        assert output is not None
        assert output["response"] == "ok"
        assert tokens == 10
        assert error_msg is None
        assert retries == 0

    @patch("animus_kernel.executor.executor_patterns.time.sleep")
    def test_success_after_retry(self, mock_sleep):
        call_count = 0

        def flaky_handler(step_cfg, ctx):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient failure")
            return {"response": "recovered", "tokens_used": 5}

        exe = _bare_executor(budget_manager=None, _handlers={"shell": flaky_handler})
        step = _make_step(step_id="r2", max_retries=3)
        output, tokens, error_msg, retries = exe._execute_with_retries(step, "stage", {}, {})
        assert output["response"] == "recovered"
        assert error_msg is None
        assert retries == 1  # one failed attempt before success
        mock_sleep.assert_called()

    @patch("animus_kernel.executor.executor_patterns.time.sleep")
    def test_all_retries_fail_raises(self, mock_sleep):
        handler = MagicMock(side_effect=RuntimeError("always fails"))
        exe = _bare_executor(budget_manager=None, _handlers={"shell": handler})
        step = _make_step(step_id="r3", max_retries=2)
        with pytest.raises(RuntimeError, match="always fails"):
            exe._execute_with_retries(step, "stage", {}, {})
        # handler called 1 initial + 2 retries = 3
        assert handler.call_count == 3


# ===================================================================
# 9. TestExecuteCheckpoint
# ===================================================================


class TestExecuteCheckpoint:
    """_execute_checkpoint: simple no-op that returns step id."""

    def test_returns_step_id(self):
        exe = _bare_executor()
        step = _make_step(step_id="cp1", step_type="checkpoint")
        out = exe._execute_checkpoint(step, {})
        assert out == {"checkpoint": "cp1"}

    def test_returns_different_id(self):
        exe = _bare_executor()
        step = _make_step(step_id="cp-save-state", step_type="checkpoint")
        out = exe._execute_checkpoint(step, {})
        assert out["checkpoint"] == "cp-save-state"


# ===================================================================
# 10. TestExecuteGitHub (dry_run + action dispatch)
# ===================================================================


class TestExecuteGitHub:
    """_execute_github: dry-run mode and action routing."""

    def test_dry_run_returns_marker(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="github",
            params={"action": "create_issue", "repo": "owner/repo"},
        )
        out = exe._execute_github(step, {})
        assert out["dry_run"] is True
        assert "DRY RUN" in out["result"]

    @patch("animus_forge.api_clients.GitHubClient")
    def test_create_issue(self, MockGH, monkeypatch):
        client = MagicMock()
        client.is_configured.return_value = True
        client.create_issue.return_value = {"number": 42, "url": "https://gh/42"}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={
                "action": "create_issue",
                "repo": "owner/repo",
                "title": "Bug",
                "body": "details",
                "labels": ["bug"],
            },
        )
        monkeypatch.setenv("ANIMUS_ALLOW_AUTONOMOUS_ISSUES", "1")
        out = exe._execute_github(step, {})
        assert out["issue_number"] == 42
        client.create_issue.assert_called_once()

    @patch("animus_forge.api_clients.GitHubClient")
    def test_create_issue_blocked_without_env_opt_in(self, MockGH, monkeypatch):
        """The autonomous-issue gate raises RuntimeError unless explicitly enabled."""
        client = MagicMock()
        client.is_configured.return_value = True
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={
                "action": "create_issue",
                "repo": "owner/repo",
                "title": "Bug",
                "body": "details",
                "labels": [],
            },
        )
        monkeypatch.delenv("ANIMUS_ALLOW_AUTONOMOUS_ISSUES", raising=False)
        with pytest.raises(RuntimeError, match="Autonomous gh issue create is blocked"):
            exe._execute_github(step, {})
        client.create_issue.assert_not_called()

    @patch("animus_forge.api_clients.GitHubClient")
    def test_unknown_action_raises(self, MockGH):
        client = MagicMock()
        client.is_configured.return_value = True
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={"action": "delete_everything", "repo": "owner/repo"},
        )
        with pytest.raises(ValueError, match="Unknown GitHub action"):
            exe._execute_github(step, {})

    @patch("animus_forge.api_clients.GitHubClient")
    def test_not_configured_raises(self, MockGH):
        client = MagicMock()
        client.is_configured.return_value = False
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={"action": "list_repos", "repo": ""},
        )
        with pytest.raises(RuntimeError, match="GitHub client not configured"):
            exe._execute_github(step, {})


# ===================================================================
# 11. TestRecordSubStepMetrics
# ===================================================================


class TestRecordSubStepMetrics:
    """_record_sub_step_metrics: budget recording and checkpoint."""

    def test_records_budget_usage(self):
        bm = MagicMock()
        exe = _bare_executor(budget_manager=bm, checkpoint_manager=None)
        sub_step = _make_step(step_id="sub1")
        exe._record_sub_step_metrics(
            stage_name="par.sub1",
            sub_step=sub_step,
            parent_step_id="par",
            tokens_used=100,
            duration_ms=50,
            retries_used=1,
            output={"response": "ok"},
            error_msg=None,
        )
        bm.record_usage.assert_called_once()
        call_kwargs = bm.record_usage.call_args[1]
        assert call_kwargs["agent_id"] == "par.sub1"
        assert call_kwargs["tokens"] == 100

    def test_records_checkpoint_on_success(self):
        cp = MagicMock()
        exe = _bare_executor(
            budget_manager=None,
            checkpoint_manager=cp,
            _current_workflow_id="wf-1",
        )
        sub_step = _make_step(step_id="sub2")
        exe._record_sub_step_metrics(
            stage_name="par.sub2",
            sub_step=sub_step,
            parent_step_id="par",
            tokens_used=0,
            duration_ms=10,
            retries_used=0,
            output={"result": "good"},
            error_msg=None,
        )
        cp.checkpoint_now.assert_called_once()
        call_kwargs = cp.checkpoint_now.call_args[1]
        assert call_kwargs["status"] == "success"

    def test_records_checkpoint_on_failure(self):
        cp = MagicMock()
        exe = _bare_executor(
            budget_manager=None,
            checkpoint_manager=cp,
            _current_workflow_id="wf-1",
        )
        sub_step = _make_step(step_id="sub3")
        exe._record_sub_step_metrics(
            stage_name="par.sub3",
            sub_step=sub_step,
            parent_step_id="par",
            tokens_used=0,
            duration_ms=10,
            retries_used=2,
            output=None,
            error_msg="something broke",
        )
        call_kwargs = cp.checkpoint_now.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["output_data"] == {"error": "something broke"}

    def test_skips_budget_when_zero_tokens(self):
        bm = MagicMock()
        exe = _bare_executor(budget_manager=bm, checkpoint_manager=None)
        sub_step = _make_step()
        exe._record_sub_step_metrics(
            "stage",
            sub_step,
            "par",
            tokens_used=0,
            duration_ms=5,
            retries_used=0,
            output={},
            error_msg=None,
        )
        bm.record_usage.assert_not_called()


# ===================================================================
# 12. TestExecuteSubStepAttempt
# ===================================================================


class TestExecuteSubStepAttempt:
    """_execute_sub_step_attempt: single attempt dispatch."""

    def test_dispatches_to_handler(self):
        handler = MagicMock(return_value={"tokens_used": 42, "data": "result"})
        exe = _bare_executor(budget_manager=None, _handlers={"shell": handler})
        sub_step = _make_step(step_id="a1", outputs=["data"])
        ctx_updates = {}
        output, tokens = exe._execute_sub_step_attempt(
            sub_step, "stage", {"key": "val"}, ctx_updates
        )
        assert tokens == 42
        assert ctx_updates["data"] == "result"
        handler.assert_called_once()

    def test_unknown_handler_raises(self):
        exe = _bare_executor(budget_manager=None, _handlers={})
        sub_step = _make_step(step_id="a2", step_type="shell")
        with pytest.raises(ValueError, match="Unknown step type"):
            exe._execute_sub_step_attempt(sub_step, "stage", {}, {})
