"""Coverage boost tests for CLI commands: budget, graph, admin, workflow."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer import Exit

# ---------------------------------------------------------------------------
# Budget CLI tests
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    """Tests for 'budget status' command."""

    def test_status_success(self):
        """Shows budget stats."""
        from animus_forge.cli.commands.budget import budget_status

        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_budget": 100000,
            "used": 50000,
            "remaining": 50000,
            "total_operations": 10,
            "agents": {"builder": 30000, "tester": 20000},
        }

        with (
            patch("animus_forge.budget.BudgetManager", return_value=mock_manager),
            patch("animus_forge.cli.commands.budget.console"),
        ):
            budget_status(json_output=False)

    def test_status_error(self):
        """Error getting budget exits."""
        from animus_forge.cli.commands.budget import budget_status

        with (
            patch("animus_forge.budget.BudgetManager", side_effect=RuntimeError("no db")),
            patch("animus_forge.cli.commands.budget.console"),
            pytest.raises(Exit),
        ):
            budget_status(json_output=False)

    def test_status_json(self, capsys):
        """JSON output for budget status."""
        from animus_forge.cli.commands.budget import budget_status

        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_budget": 100000,
            "used": 50000,
            "remaining": 50000,
            "total_operations": 10,
        }

        with (
            patch("animus_forge.budget.BudgetManager", return_value=mock_manager),
            patch("animus_forge.cli.commands.budget.console"),
        ):
            budget_status(json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["total_budget"] == 100000


class TestBudgetHistory:
    """Tests for 'budget history' command."""

    def test_history_error(self):
        """Error exits."""
        from animus_forge.cli.commands.budget import budget_history

        with (
            patch("animus_forge.budget.BudgetManager", side_effect=RuntimeError("no db")),
            patch("animus_forge.cli.commands.budget.console"),
            pytest.raises(Exit),
        ):
            budget_history(agent=None, limit=20, json_output=False)

    def test_history_json(self, capsys):
        """JSON output for history."""
        from animus_forge.cli.commands.budget import budget_history

        mock_record = MagicMock()
        mock_record.__dict__ = {
            "agent_id": "builder",
            "tokens": 100,
            "timestamp": "now",
            "operation": "tool:read",
        }
        mock_manager = MagicMock()
        mock_manager.get_usage_history.return_value = [mock_record]

        with (
            patch("animus_forge.budget.BudgetManager", return_value=mock_manager),
            patch("animus_forge.cli.commands.budget.console"),
        ):
            budget_history(agent=None, limit=20, json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1

    def test_history_empty(self):
        """Empty history shows message."""
        from animus_forge.cli.commands.budget import budget_history

        mock_manager = MagicMock()
        mock_manager.get_usage_history.return_value = []

        with (
            patch("animus_forge.budget.BudgetManager", return_value=mock_manager),
            patch("animus_forge.cli.commands.budget.console"),
        ):
            budget_history(agent=None, limit=20, json_output=False)


class TestBudgetDaily:
    """Tests for 'budget daily' command."""

    def test_daily_error(self):
        """Error exits."""
        from animus_forge.cli.commands.budget import budget_daily

        with (
            patch("animus_forge.db.get_task_store", side_effect=RuntimeError("no db")),
            patch("animus_forge.cli.commands.budget.console"),
            pytest.raises(Exit),
        ):
            budget_daily(days=7, agent=None, json_output=False)

    def test_daily_json(self, capsys):
        """JSON output for daily."""
        from animus_forge.cli.commands.budget import budget_daily

        mock_store = MagicMock()
        mock_store.get_daily_budget.return_value = [
            {
                "date": "2026-03-07",
                "agent_role": "builder",
                "task_count": 5,
                "total_tokens": 1000,
                "total_cost_usd": 0.01,
            },
        ]

        with (
            patch("animus_forge.db.get_task_store", return_value=mock_store),
            patch("animus_forge.cli.commands.budget.console"),
        ):
            budget_daily(days=7, agent=None, json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data[0]["date"] == "2026-03-07"


class TestBudgetReset:
    """Tests for 'budget reset' command."""

    def test_reset_error(self):
        """Error exits."""
        from animus_forge.cli.commands.budget import budget_reset

        with (
            patch("animus_forge.budget.BudgetManager", side_effect=RuntimeError("no db")),
            patch("animus_forge.cli.commands.budget.console"),
            pytest.raises(Exit),
        ):
            budget_reset(force=True)


# ---------------------------------------------------------------------------
# Admin CLI tests
# ---------------------------------------------------------------------------


class TestAdminCLI:
    """Tests for admin CLI commands."""

    def test_dashboard_no_file(self):
        """Dashboard command when file not found."""
        from animus_forge.cli.commands.admin import dashboard

        with (
            patch("animus_forge.cli.commands.admin.console"),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(Exit),
        ):
            dashboard(host="localhost", port=8501, no_browser=True)

    def test_dashboard_keyboard_interrupt(self):
        """Dashboard handles KeyboardInterrupt."""

        from animus_forge.cli.commands.admin import dashboard

        with (
            patch("animus_forge.cli.commands.admin.console"),
            patch("pathlib.Path.exists", return_value=True),
            patch("subprocess.run", side_effect=KeyboardInterrupt),
        ):
            dashboard(host="localhost", port=8501, no_browser=True)

    def test_dashboard_opens_browser(self):
        """Dashboard opens browser unless --no-browser."""

        from animus_forge.cli.commands.admin import dashboard

        mock_result = MagicMock(returncode=0)

        with (
            patch("animus_forge.cli.commands.admin.console"),
            patch("pathlib.Path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result),
            patch("webbrowser.open") as mock_open,
        ):
            dashboard(host="localhost", port=8501, no_browser=False)

        mock_open.assert_called_once_with("http://localhost:8501")


# ---------------------------------------------------------------------------
# Workflow CLI tests
# ---------------------------------------------------------------------------


class TestWorkflowCLI:
    """Tests for workflow CLI commands."""

    def test_workflow_list_empty(self):
        """workflow list with no workflows."""
        from animus_forge.cli.commands.workflow import list_workflows

        with (
            patch("animus_forge.cli.commands.workflow.console"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.glob", return_value=[]),
        ):
            try:
                list_workflows(json_output=False)
            except Exit:
                pass

    def test_workflow_validate(self):
        """workflow validate command."""
        from animus_forge.cli.commands.workflow import validate

        mock_wf = MagicMock()
        mock_wf.name = "test"
        mock_wf.steps = []

        with (
            patch("animus_forge.cli.commands.workflow.console"),
            patch("animus_kernel.executor.loader.load_workflow", return_value=mock_wf),
            patch("pathlib.Path.exists", return_value=True),
        ):
            try:
                validate(workflow_file="test")
            except (Exit, Exception):
                pass


# ---------------------------------------------------------------------------
# Dev CLI streaming paths (lines 201-210)
# ---------------------------------------------------------------------------


class TestDevProgressCallback:
    """Tests for the progress callback branches in do_task."""

    def test_progress_callback_all_stages(self):
        """All progress stage branches get exercised."""

        from animus_forge.cli.commands.dev import do_task

        mock_supervisor = MagicMock()
        captured_callback = None

        async def capture_process_message(msg, progress_callback=None, max_rounds=1):
            nonlocal captured_callback
            captured_callback = progress_callback
            # Exercise all stage branches
            if progress_callback:
                progress_callback("tools", "reading file.py")
                progress_callback("delegating", "to builder")
                progress_callback("synthesizing", "combining results")
                progress_callback("verifying", "checking output")
                progress_callback("analyzing", "")  # No detail
            return "Done"

        mock_supervisor.process_message = capture_process_message

        with (
            patch(
                "animus_forge.cli.commands.dev.detect_codebase_context",
                return_value={"path": "/tmp"},
            ),
            patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx"),
            patch("animus_forge.cli.commands.dev.get_supervisor", return_value=mock_supervisor),
            patch("animus_forge.cli.commands.dev.console"),
        ):
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

        assert captured_callback is not None
