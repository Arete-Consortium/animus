"""Tests for new dev.py features: streaming progress, verify flag, task persistence."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer import Exit


class TestDoTaskStreamingProgress:
    """Tests for the streaming progress callback in do_task."""

    def _invoke_do_task(self, **kwargs):
        """Helper to invoke do_task with all mocks."""
        from animus_forge.cli.commands.dev import do_task

        defaults = {
            "task": "test task",
            "workflow": None,
            "dry_run": False,
            "json_output": False,
            "live": False,
            "verify": False,
            "runner": False,
            "role": "builder",
        }
        defaults.update(kwargs)

        mock_supervisor = MagicMock()
        mock_supervisor.process_message = AsyncMock(return_value="Done")

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp", "language": "python"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            do_task(**defaults)

        return mock_supervisor

    def test_verify_flag_sets_max_rounds_2(self):
        """--verify sets max_rounds=2."""
        supervisor = self._invoke_do_task(verify=True)
        call_kwargs = supervisor.process_message.call_args
        assert call_kwargs.kwargs.get("max_rounds") == 2 or call_kwargs[1].get("max_rounds") == 2

    def test_no_verify_sets_max_rounds_1(self):
        """Without --verify, max_rounds=1."""
        supervisor = self._invoke_do_task(verify=False)
        call_kwargs = supervisor.process_message.call_args
        assert call_kwargs.kwargs.get("max_rounds") == 1 or call_kwargs[1].get("max_rounds") == 1

    def test_progress_callback_passed(self):
        """A progress_callback is passed to process_message."""
        supervisor = self._invoke_do_task()
        call_kwargs = supervisor.process_message.call_args
        assert "progress_callback" in call_kwargs.kwargs or len(call_kwargs[0]) > 1

    def test_json_output_includes_task_id(self, capsys):
        """JSON output includes task_id and duration_ms."""
        from animus_forge.cli.commands.dev import do_task

        mock_supervisor = MagicMock()
        mock_supervisor.process_message = AsyncMock(return_value="Done")

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp", "language": "python"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            do_task(
                task="test",
                workflow=None,
                dry_run=False,
                json_output=True,
                live=False,
                verify=False,
                runner=False,
                role="builder",
            )

        output = capsys.readouterr().out
        data = json.loads(output)
        assert "task_id" in data
        assert "duration_ms" in data
        assert data["result"] == "Done"

    def test_dry_run_exits(self):
        """--dry-run shows plan and exits."""
        from typer import Exit

        from animus_forge.cli.commands.dev import do_task

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.console"),
            pytest.raises(Exit),
        ):
            do_task(
                task="test",
                workflow=None,
                dry_run=True,
                json_output=False,
                live=False,
                verify=False,
                runner=False,
                role="builder",
            )


class TestDoTaskPersistence:
    """Tests for task result persistence in do_task."""

    def test_task_persisted_to_store(self):
        """Task result is saved to TaskStore."""
        from animus_forge.cli.commands.dev import do_task

        mock_supervisor = MagicMock()
        mock_supervisor.process_message = AsyncMock(return_value="Built it")
        mock_store = MagicMock()

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor),
            patch("animus_forge.cli.commands.dev.console"),
            patch("animus_forge.db.get_task_store", return_value=mock_store),
        ):
            do_task(
                task="build feature",
                workflow=None,
                dry_run=False,
                json_output=False,
                live=False,
                verify=False,
                runner=False,
                role="builder",
            )

        mock_store.record_task.assert_called_once()
        call_kwargs = mock_store.record_task.call_args
        assert (
            call_kwargs.kwargs.get("workflow_id") == "supervisor"
            or call_kwargs[1].get("workflow_id") == "supervisor"
        )

    def test_persistence_failure_is_silent(self):
        """If TaskStore raises, do_task still completes."""
        from animus_forge.cli.commands.dev import do_task

        mock_supervisor = MagicMock()
        mock_supervisor.process_message = AsyncMock(return_value="Done")

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor),
            patch("animus_forge.cli.commands.dev.console"),
            patch("animus_forge.db.get_task_store", side_effect=ImportError("no db")),
        ):
            # Should not raise
            do_task(
                task="test",
                workflow=None,
                dry_run=False,
                json_output=False,
                live=False,
                verify=False,
                runner=False,
                role="builder",
            )


class TestRunSingleAgent:
    """Tests for _run_single_agent helper."""

    def test_uses_supervisor_run_agent(self):
        """_run_single_agent calls supervisor._run_agent."""
        from animus_forge.cli.commands.dev import _run_single_agent

        mock_supervisor = MagicMock()
        mock_supervisor._run_agent = AsyncMock(return_value="agent result")

        with patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor):
            result = _run_single_agent("planner", "make a plan")

        assert result == "agent result"

    def test_fallback_to_claude_client(self):
        """Falls back to ClaudeCodeClient if supervisor fails."""
        from animus_forge.cli.commands.dev import _run_single_agent

        mock_client = MagicMock()
        mock_client.execute_agent.return_value = {"success": True, "output": "client result"}

        with (
            patch(
                "animus_forge.cli.commands.dev.get_supervisor",
                side_effect=RuntimeError("no supervisor"),
            ),
            patch("animus_forge.cli.commands.dev.get_claude_client", return_value=mock_client),
        ):
            result = _run_single_agent("builder", "build it")

        assert result == "client result"

    def test_fallback_client_error(self):
        """Falls back to error message when client returns failure."""
        from animus_forge.cli.commands.dev import _run_single_agent

        mock_client = MagicMock()
        mock_client.execute_agent.return_value = {"success": False, "error": "rate limit"}

        with (
            patch(
                "animus_forge.cli.commands.dev.get_supervisor", side_effect=RuntimeError("no sup")
            ),
            patch("animus_forge.cli.commands.dev.get_claude_client", return_value=mock_client),
        ):
            result = _run_single_agent("builder", "build it")

        assert "rate limit" in result

    def test_no_provider_available(self):
        """Returns error when no LLM provider available."""
        from animus_forge.cli.commands.dev import _run_single_agent

        with (
            patch(
                "animus_forge.cli.commands.dev.get_supervisor", side_effect=RuntimeError("no sup")
            ),
            patch(
                "animus_forge.cli.commands.dev.get_claude_client",
                side_effect=RuntimeError("no client"),
            ),
        ):
            result = _run_single_agent("builder", "build it")

        assert "No LLM provider" in result


class TestDevCommandHelpers:
    """Tests for dev.py helper functions."""

    def test_get_git_diff_context_success(self, tmp_path):
        """_get_git_diff_context returns diff on success."""
        from animus_forge.cli.commands.dev import _get_git_diff_context

        mock_result = MagicMock(returncode=0, stdout="diff --git a/file.py")
        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff_context("HEAD~1", tmp_path)
        assert "diff" in result

    def test_get_git_diff_context_failure(self, tmp_path):
        """_get_git_diff_context returns empty on failure."""
        from animus_forge.cli.commands.dev import _get_git_diff_context

        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff_context("HEAD~1", tmp_path)
        assert result == ""

    def test_get_git_diff_context_exception(self, tmp_path):
        """_get_git_diff_context returns empty on exception."""
        from animus_forge.cli.commands.dev import _get_git_diff_context

        with patch("subprocess.run", side_effect=OSError("no git")):
            result = _get_git_diff_context("HEAD~1", tmp_path)
        assert result == ""

    def test_get_file_context(self, tmp_path):
        """_get_file_context reads file content."""
        from animus_forge.cli.commands.dev import _get_file_context

        f = tmp_path / "test.py"
        f.write_text("def hello(): pass")
        result = _get_file_context(f)
        assert "def hello" in result

    def test_get_file_context_unreadable(self, tmp_path):
        """_get_file_context returns empty for unreadable files."""
        from animus_forge.cli.commands.dev import _get_file_context

        result = _get_file_context(tmp_path / "nonexistent.py")
        assert result == ""

    def test_get_directory_context(self, tmp_path):
        """_get_directory_context reads python files."""
        from animus_forge.cli.commands.dev import _get_directory_context

        (tmp_path / "a.py").write_text("# file a")
        result = _get_directory_context(tmp_path)
        assert "file a" in result

    def test_get_directory_context_empty(self, tmp_path):
        """_get_directory_context returns empty for dirs with no .py files."""
        from animus_forge.cli.commands.dev import _get_directory_context

        result = _get_directory_context(tmp_path)
        assert result == ""

    def test_gather_review_code_context_git_ref(self, tmp_path):
        """_gather_review_code_context detects git refs."""
        from animus_forge.cli.commands.dev import _gather_review_code_context

        mock_result = MagicMock(returncode=0, stdout="diff content")
        with patch("subprocess.run", return_value=mock_result):
            result = _gather_review_code_context("HEAD~1", {"path": tmp_path})
        assert "diff" in result

    def test_gather_review_code_context_origin_ref(self, tmp_path):
        """_gather_review_code_context detects origin/ refs."""
        from animus_forge.cli.commands.dev import _gather_review_code_context

        mock_result = MagicMock(returncode=0, stdout="diff content")
        with patch("subprocess.run", return_value=mock_result):
            result = _gather_review_code_context("origin/main", {"path": tmp_path})
        assert "diff" in result

    def test_gather_review_code_context_nonexistent(self):
        """_gather_review_code_context returns empty for nonexistent paths."""
        from animus_forge.cli.commands.dev import _gather_review_code_context

        result = _gather_review_code_context("/nonexistent/path", {"path": "."})
        assert result == ""


class TestDevCommands:
    """Tests for plan, build, test, review, ask commands."""

    def test_plan_json_output(self, capsys):
        """plan --json outputs JSON."""
        from animus_forge.cli.commands.dev import plan

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev._run_single_agent", return_value="Step 1\nStep 2"),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            plan(task="add auth", json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["task"] == "add auth"
        assert "Step 1" in data["result"]

    def test_build_with_plan_file(self, tmp_path):
        """build --plan loads plan from file."""
        from animus_forge.cli.commands.dev import build

        plan_file = tmp_path / "plan.txt"
        plan_file.write_text("1. Create module\n2. Add tests")

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": str(tmp_path)},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch(
                "animus_forge.cli.commands.dev._run_single_agent", return_value="Built"
            ) as mock_agent,
            patch("animus_forge.cli.commands.dev.console"),
        ):
            build(description="auth module", plan=str(plan_file), json_output=False)

        # Plan text should be included in the prompt
        prompt = mock_agent.call_args[0][1]
        assert "Create module" in prompt

    def test_build_with_inline_plan(self):
        """build --plan with inline text."""
        from animus_forge.cli.commands.dev import build

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch(
                "animus_forge.cli.commands.dev._run_single_agent", return_value="Built"
            ) as mock_agent,
            patch("animus_forge.cli.commands.dev.console"),
        ):
            build(description="auth", plan="step 1: create", json_output=False)

        prompt = mock_agent.call_args[0][1]
        assert "step 1: create" in prompt

    def test_build_json_output(self, capsys):
        """build --json outputs JSON."""
        from animus_forge.cli.commands.dev import build

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch(
                "animus_forge.cli.commands.dev._run_single_agent", return_value="def auth(): pass"
            ),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            build(description="auth", plan=None, json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert "auth" in data["result"]

    def test_test_with_file_target(self, tmp_path):
        """test command reads source file for context."""
        from animus_forge.cli.commands.dev import test

        src = tmp_path / "auth.py"
        src.write_text("def login(): pass")

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": str(tmp_path)},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch(
                "animus_forge.cli.commands.dev._run_single_agent",
                return_value="def test_login(): assert True",
            ) as mock_agent,
            patch("animus_forge.cli.commands.dev.console"),
        ):
            test(target=str(src), json_output=False)

        prompt = mock_agent.call_args[0][1]
        assert "def login" in prompt

    def test_test_json_output(self, capsys):
        """test --json outputs JSON."""
        from animus_forge.cli.commands.dev import test

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev._run_single_agent", return_value="tests"),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            test(target="src/auth.py", json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["target"] == "src/auth.py"

    def test_review_json_output(self, capsys):
        """review --json outputs JSON."""
        from animus_forge.cli.commands.dev import review

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev._run_single_agent", return_value="Score: 9"),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            review(target="src/", json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert "Score" in data["result"]

    def test_ask_json_output(self, capsys):
        """ask --json outputs JSON."""
        from animus_forge.cli.commands.dev import ask

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev._run_single_agent", return_value="It uses JWT"),
            patch("animus_forge.cli.commands.dev.console"),
        ):
            ask(question="how does auth work?", json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["question"] == "how does auth work?"
        assert "JWT" in data["answer"]


class TestRunYamlWorkflow:
    """Tests for _run_yaml_workflow."""

    def test_workflow_dry_run_shows_steps(self):
        """--dry-run lists workflow steps."""
        from animus_forge.cli.commands.dev import do_task

        mock_wf = MagicMock()
        mock_wf.name = "test_workflow"
        mock_step = MagicMock()
        mock_step.type = "ai"
        mock_step.id = "step1"
        mock_step.params = {"role": "builder"}
        mock_wf.steps = [mock_step]

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.console"),
            patch("animus_kernel.executor.loader.load_workflow", return_value=mock_wf),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(Exit),
        ):
            do_task(
                task="test",
                workflow="my_workflow",
                dry_run=True,
                json_output=False,
                live=False,
                verify=False,
            )

    def test_workflow_json_output(self, capsys):
        """Workflow execution with --json outputs results."""
        from animus_forge.cli.commands.dev import do_task

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"status": "success"}
        mock_result.status = "success"
        mock_result.steps = []
        mock_result.error = None
        mock_result.total_tokens = 100

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result

        mock_wf = MagicMock()
        mock_wf.name = "test_wf"
        mock_wf.steps = []

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.console"),
            patch("animus_kernel.executor.loader.load_workflow", return_value=mock_wf),
            patch(
                "animus_forge.cli.commands.dev.get_workflow_executor", return_value=mock_executor
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            do_task(
                task="test",
                workflow="my_wf",
                dry_run=False,
                json_output=True,
                live=False,
                verify=False,
            )

        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "success"

    def test_workflow_displays_steps_and_error(self):
        """Workflow results show step details and errors."""
        from animus_forge.cli.commands.dev import do_task

        mock_step = MagicMock()
        mock_step.status.value = "success"
        mock_step.output = {"role": "builder"}
        mock_step.tokens_used = 500
        mock_step.step_id = "build_step"

        mock_result = MagicMock()
        mock_result.status = "failed"
        mock_result.steps = [mock_step]
        mock_result.error = "Build failed"
        mock_result.total_tokens = 500

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result

        mock_wf = MagicMock()
        mock_wf.name = "test_wf"
        mock_wf.steps = []

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.console") as mock_console,
            patch("animus_kernel.executor.loader.load_workflow", return_value=mock_wf),
            patch(
                "animus_forge.cli.commands.dev.get_workflow_executor", return_value=mock_executor
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            do_task(
                task="test",
                workflow="wf",
                dry_run=False,
                json_output=False,
                live=False,
                verify=False,
            )

        # Verify error was printed
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "Build failed" in printed or "Error" in printed
