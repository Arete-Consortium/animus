"""Tests for CLI --live flag on do_task command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from animus_forge.cli.main import app

runner = CliRunner()


class TestDoTaskLiveFlag:
    """Verify --live flag behavior on do_task command."""

    @patch("animus_forge.cli.commands.dev.get_workflow_executor")
    @patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    @patch("animus_kernel.executor.loader.load_workflow")
    def test_live_flag_accepted(self, mock_load, mock_ctx, mock_fmt, mock_exec):
        """--live flag is accepted without error."""
        mock_ctx.return_value = {"path": "/tmp", "language": "python"}
        mock_wf = MagicMock()
        mock_wf.name = "Test WF"
        mock_wf.steps = []
        mock_load.return_value = mock_wf

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.steps = []
        mock_result.error = None
        mock_result.total_tokens = 0
        mock_exec.return_value.execute.return_value = mock_result

        with patch.object(Path, "exists", return_value=True):
            result = runner.invoke(app, ["do", "test task", "--live", "-w", "feature-build"])

        assert result.exit_code == 0

    @patch("animus_forge.cli.commands.dev.get_workflow_executor")
    @patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    @patch("animus_kernel.executor.loader.load_workflow")
    def test_live_creates_execution_manager(self, mock_load, mock_ctx, mock_fmt, mock_exec):
        """--live creates an execution manager and attaches it to executor."""
        mock_ctx.return_value = {"path": "/tmp", "language": "python"}
        mock_wf = MagicMock()
        mock_wf.name = "Test WF"
        mock_wf.steps = []
        mock_load.return_value = mock_wf

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.steps = []
        mock_result.error = None
        mock_result.total_tokens = 0

        executor_instance = MagicMock()
        executor_instance.execute.return_value = mock_result
        mock_exec.return_value = executor_instance

        with patch.object(Path, "exists", return_value=True):
            with patch("animus_forge.cli.helpers._create_cli_execution_manager") as mock_create_em:
                mock_em = MagicMock()
                mock_create_em.return_value = mock_em
                result = runner.invoke(app, ["do", "test task", "--live", "-w", "feature-build"])

        assert result.exit_code == 0
        # Verify execution_manager was set on the executor
        assert executor_instance.execution_manager == mock_em
        mock_em.register_callback.assert_called_once()

    @patch("animus_forge.cli.commands.dev.get_workflow_executor")
    @patch("animus_forge.cli.commands.dev.format_context_for_prompt", return_value="ctx")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    @patch("animus_kernel.executor.loader.load_workflow")
    def test_without_live_uses_status_spinner(self, mock_load, mock_ctx, mock_fmt, mock_exec):
        """Without --live, uses the traditional console.status spinner."""
        mock_ctx.return_value = {"path": "/tmp", "language": "python"}
        mock_wf = MagicMock()
        mock_wf.name = "Test WF"
        mock_wf.steps = []
        mock_load.return_value = mock_wf

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.steps = []
        mock_result.error = None
        mock_result.total_tokens = 0
        mock_exec.return_value.execute.return_value = mock_result

        with patch.object(Path, "exists", return_value=True):
            result = runner.invoke(app, ["do", "test task", "-w", "feature-build"])

        assert result.exit_code == 0


class TestCreateCliExecutionManager:
    """Verify _create_cli_execution_manager helper."""

    def test_creates_in_memory_manager(self):
        """Creates an in-memory ExecutionManager."""
        from animus_forge.cli.helpers import _create_cli_execution_manager

        em = _create_cli_execution_manager()
        assert em is not None

        # Verify it's functional
        execution = em.create_execution("wf-1", "Test WF")
        assert execution.id is not None
        assert execution.workflow_name == "Test WF"

    def test_returns_none_on_failure(self):
        """Returns None if ExecutionManager creation fails."""
        with patch(
            "animus_forge.state.backends.SQLiteBackend",
            side_effect=Exception("No SQLite"),
        ):
            from animus_forge.cli.helpers import _create_cli_execution_manager

            em = _create_cli_execution_manager()
            assert em is None
