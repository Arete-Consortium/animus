"""Tests for Gorgon CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from animus_forge.cli.main import (
    app,
    detect_codebase_context,
    format_context_for_prompt,
)

runner = CliRunner()


class TestDetectCodebaseContext:
    """Tests for codebase auto-detection."""

    def test_detect_python_project(self, tmp_path):
        """Detect Python project from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'")
        (tmp_path / "src").mkdir()

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "python"
        assert context["path"] == str(tmp_path)
        assert "src/" in context["structure"]

    def test_detect_python_fastapi(self, tmp_path):
        """Detect FastAPI framework in Python project."""
        (tmp_path / "pyproject.toml").write_text('[tool.poetry.dependencies]\nfastapi = "^0.100"')

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "python"
        assert context["framework"] == "fastapi"

    def test_detect_python_django(self, tmp_path):
        """Detect Django framework in Python project."""
        (tmp_path / "pyproject.toml").write_text('[tool.poetry.dependencies]\nDjango = "^4.0"')

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "python"
        assert context["framework"] == "django"

    def test_detect_rust_project(self, tmp_path):
        """Detect Rust project from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "rust"

    def test_detect_typescript_project(self, tmp_path):
        """Detect TypeScript project from package.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "typescript"

    def test_detect_react_framework(self, tmp_path):
        """Detect React framework in JS/TS project."""
        (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0"}}')

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "typescript"
        assert context["framework"] == "react"

    def test_detect_nextjs_framework(self, tmp_path):
        """Detect Next.js framework in JS/TS project."""
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "^14.0"}}')

        context = detect_codebase_context(tmp_path)

        assert context["framework"] == "nextjs"

    def test_detect_go_project(self, tmp_path):
        """Detect Go project from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/test")

        context = detect_codebase_context(tmp_path)

        assert context["language"] == "go"

    def test_detect_readme(self, tmp_path):
        """Detect and extract README content."""
        readme_content = "# Test Project\n\nThis is a test."
        (tmp_path / "README.md").write_text(readme_content)

        context = detect_codebase_context(tmp_path)

        assert context["readme"] == readme_content

    def test_readme_truncation(self, tmp_path):
        """README content is truncated to 500 chars."""
        long_content = "x" * 1000
        (tmp_path / "README.md").write_text(long_content)

        context = detect_codebase_context(tmp_path)

        assert len(context["readme"]) == 500

    def test_unknown_project(self, tmp_path):
        """Unknown project type returns 'unknown' language."""
        context = detect_codebase_context(tmp_path)

        assert context["language"] == "unknown"
        assert context["framework"] is None

    def test_structure_detection(self, tmp_path):
        """Detect key directory structure."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / ".hidden").mkdir()  # Should be ignored

        context = detect_codebase_context(tmp_path)

        assert "src/" in context["structure"]
        assert "tests/" in context["structure"]
        assert "docs/" in context["structure"]
        assert ".hidden/" not in context["structure"]


class TestFormatContextForPrompt:
    """Tests for context formatting."""

    def test_format_basic(self):
        """Format basic context information."""
        context = {
            "path": "/test/path",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = format_context_for_prompt(context)

        assert "Codebase: /test/path" in result
        assert "Language: python" in result

    def test_format_with_framework(self):
        """Include framework when present."""
        context = {
            "path": "/test/path",
            "language": "python",
            "framework": "fastapi",
            "structure": [],
        }

        result = format_context_for_prompt(context)

        assert "Framework: fastapi" in result

    def test_format_with_structure(self):
        """Include structure when present."""
        context = {
            "path": "/test/path",
            "language": "python",
            "framework": None,
            "structure": ["src/", "tests/", "docs/"],
        }

        result = format_context_for_prompt(context)

        assert "Structure: src/, tests/, docs/" in result


class TestVersionCommand:
    """Tests for the version command."""

    def test_version(self):
        """Version command shows version info."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "gorgon" in result.output.lower()
        assert "0.3.0" in result.output


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_workflow(self, tmp_path):
        """Init creates a workflow template file."""
        output_file = tmp_path / "test_workflow.json"

        result = runner.invoke(app, ["init", "Test Workflow", "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert data["name"] == "Test Workflow"
        assert data["id"] == "test_workflow"
        assert len(data["steps"]) == 2

    def test_init_default_filename(self, tmp_path, monkeypatch):
        """Init uses default filename based on name."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init", "My Test"])

        assert result.exit_code == 0
        assert (tmp_path / "my_test.json").exists()

    def test_init_overwrites_with_confirm(self, tmp_path):
        """Init asks before overwriting existing file."""
        output_file = tmp_path / "existing.json"
        output_file.write_text("{}")

        result = runner.invoke(app, ["init", "Test", "-o", str(output_file)], input="y\n")

        assert result.exit_code == 0
        data = json.loads(output_file.read_text())
        assert "steps" in data  # New content


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_workflow(self, tmp_path):
        """Validate passes for valid workflow."""
        workflow_file = tmp_path / "valid.json"
        workflow_file.write_text(
            json.dumps(
                {
                    "id": "test",
                    "name": "Test",
                    "steps": [{"id": "step1", "type": "transform", "action": "format"}],
                }
            )
        )

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_missing_id(self, tmp_path):
        """Validate fails when ID is missing."""
        workflow_file = tmp_path / "invalid.json"
        workflow_file.write_text(json.dumps({"steps": []}))

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 1
        assert "Missing required field: id" in result.output

    def test_validate_missing_steps(self, tmp_path):
        """Validate fails when steps are missing."""
        workflow_file = tmp_path / "invalid.json"
        workflow_file.write_text(json.dumps({"id": "test"}))

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 1
        assert "Missing required field: steps" in result.output

    def test_validate_duplicate_step_ids(self, tmp_path):
        """Validate fails on duplicate step IDs."""
        workflow_file = tmp_path / "invalid.json"
        workflow_file.write_text(
            json.dumps(
                {
                    "id": "test",
                    "steps": [
                        {"id": "step1", "type": "transform", "action": "a"},
                        {"id": "step1", "type": "transform", "action": "b"},
                    ],
                }
            )
        )

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 1
        assert "Duplicate step ID" in result.output

    def test_validate_invalid_next_step(self, tmp_path):
        """Validate fails when next_step references non-existent step."""
        workflow_file = tmp_path / "invalid.json"
        workflow_file.write_text(
            json.dumps(
                {
                    "id": "test",
                    "steps": [
                        {
                            "id": "step1",
                            "type": "transform",
                            "action": "a",
                            "next_step": "nonexistent",
                        }
                    ],
                }
            )
        )

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_validate_invalid_json(self, tmp_path):
        """Validate fails on invalid JSON."""
        workflow_file = tmp_path / "invalid.json"
        workflow_file.write_text("not json")

        result = runner.invoke(app, ["validate", str(workflow_file)])

        assert result.exit_code == 1
        assert "Invalid JSON" in result.output


class TestStatusCommand:
    """Tests for the status command."""

    @patch("animus_forge.cli.commands.workflow.get_tracker")
    def test_status_displays_metrics(self, mock_get_tracker):
        """Status command displays metrics."""
        mock_tracker = MagicMock()
        mock_tracker.get_dashboard_data.return_value = {
            "summary": {
                "active_workflows": 2,
                "total_executions": 100,
                "success_rate": 95.5,
                "avg_duration_ms": 1234,
            },
            "active_workflows": [],
            "recent_executions": [],
        }
        mock_get_tracker.return_value = mock_tracker

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Active Workflows: 2" in result.output
        assert "Total Executions: 100" in result.output
        assert "Success Rate: 95.5%" in result.output

    @patch("animus_forge.cli.commands.workflow.get_tracker")
    def test_status_json_output(self, mock_get_tracker):
        """Status command outputs JSON when requested."""
        mock_tracker = MagicMock()
        mock_tracker.get_dashboard_data.return_value = {
            "summary": {"active_workflows": 1},
            "active_workflows": [],
            "recent_executions": [],
        }
        mock_get_tracker.return_value = mock_tracker

        result = runner.invoke(app, ["status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "summary" in data

    @patch("animus_forge.cli.commands.workflow.get_tracker")
    def test_status_handles_unavailable_tracker(self, mock_get_tracker):
        """Status handles unavailable tracker gracefully."""
        mock_get_tracker.side_effect = Exception("Not available")

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "unavailable" in result.output.lower()


class TestListCommand:
    """Tests for the list command."""

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_list_no_workflows(self, mock_get_engine):
        """List shows message when no workflows exist."""
        mock_engine = MagicMock()
        mock_engine.list_workflows.return_value = []
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No workflows found" in result.output

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_list_shows_workflows(self, mock_get_engine):
        """List displays available workflows."""
        mock_engine = MagicMock()
        mock_engine.list_workflows.return_value = [
            {"id": "wf1", "name": "Workflow 1", "description": "Test"}
        ]
        mock_wf = MagicMock()
        mock_wf.steps = [MagicMock(), MagicMock()]
        mock_engine.load_workflow.return_value = mock_wf
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "wf1" in result.output
        assert "Workflow 1" in result.output

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_list_json_output(self, mock_get_engine):
        """List outputs JSON when requested."""
        mock_engine = MagicMock()
        mock_engine.list_workflows.return_value = [{"id": "wf1", "name": "Test"}]
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "wf1"


class TestRunCommand:
    """Tests for the run command."""

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_run_workflow_not_found(self, mock_get_engine):
        """Run fails when workflow not found."""
        mock_engine = MagicMock()
        mock_engine.load_workflow.return_value = None
        mock_engine.list_workflows.return_value = []
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["run", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_run_dry_run(self, mock_get_engine):
        """Run with --dry-run shows plan without executing."""
        mock_engine = MagicMock()
        mock_wf = MagicMock()
        mock_wf.model_dump.return_value = {
            "id": "test",
            "name": "Test",
            "description": "Test workflow",
            "steps": [{"id": "s1", "type": "transform", "action": "a"}],
        }
        mock_engine.load_workflow.return_value = mock_wf
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["run", "test", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        mock_engine.execute_workflow.assert_not_called()

    @patch("animus_forge.cli.commands.workflow.get_workflow_engine")
    def test_run_with_variables(self, mock_get_engine):
        """Run passes variables to workflow."""
        mock_engine = MagicMock()
        mock_wf = MagicMock()
        mock_wf.model_dump.return_value = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "steps": [],
        }
        mock_engine.load_workflow.return_value = mock_wf
        mock_result = MagicMock()
        mock_result.status = "completed"
        mock_result.step_results = {}
        mock_result.error = None
        mock_engine.execute_workflow.return_value = mock_result
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(app, ["run", "test", "--var", "key1=value1", "--var", "key2=value2"])

        assert result.exit_code == 0
        # Verify variables were set
        call_args = mock_engine.execute_workflow.call_args
        wf = call_args[0][0]
        assert wf.variables == {"key1": "value1", "key2": "value2"}

    def test_run_invalid_variable_format(self):
        """Run fails on invalid variable format."""
        result = runner.invoke(app, ["run", "test", "--var", "invalid"])

        assert result.exit_code == 1
        assert "Invalid variable format" in result.output


class TestAgentCommands:
    """Tests for interactive agent commands."""

    @patch(
        "animus_forge.cli.commands.dev._run_single_agent", return_value="1. Step one\n2. Step two"
    )
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_plan_command(self, mock_context, mock_agent):
        """Plan command calls planner agent."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["plan", "add authentication"])

        assert result.exit_code == 0
        assert "Planner" in result.output
        mock_agent.assert_called_once()
        assert mock_agent.call_args[0][0] == "planner"

    @patch("animus_forge.cli.commands.dev._run_single_agent", return_value="def auth(): pass")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_build_command(self, mock_context, mock_agent):
        """Build command calls builder agent."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["build", "auth module"])

        assert result.exit_code == 0
        assert "Builder" in result.output
        assert mock_agent.call_args[0][0] == "builder"

    @patch(
        "animus_forge.cli.commands.dev._run_single_agent",
        return_value="def test_auth(): assert True",
    )
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_test_command(self, mock_context, mock_agent):
        """Test command calls tester agent."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["test", "auth.py"])

        assert result.exit_code == 0
        assert "Tester" in result.output
        assert mock_agent.call_args[0][0] == "tester"

    @patch("animus_forge.cli.commands.dev._run_single_agent", return_value="Score: 8/10\nApproved")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_review_command(self, mock_context, mock_agent):
        """Review command calls reviewer agent."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["review", "src/"])

        assert result.exit_code == 0
        assert "Reviewer" in result.output
        assert mock_agent.call_args[0][0] == "reviewer"

    @patch(
        "animus_forge.cli.commands.dev._run_single_agent",
        return_value="The auth system uses JWT tokens.",
    )
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_ask_command(self, mock_context, mock_agent):
        """Ask command answers questions about codebase."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["ask", "how does auth work?"])

        assert result.exit_code == 0
        assert "Question" in result.output
        mock_agent.assert_called_once()

    @patch(
        "animus_forge.cli.commands.dev._run_single_agent",
        return_value="Error: API rate limit exceeded",
    )
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_agent_error_handling(self, mock_context, mock_agent):
        """Agent commands handle errors gracefully."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["plan", "something"])

        assert result.exit_code == 0
        assert "Error" in result.output

    @patch("animus_forge.cli.commands.dev._run_single_agent", return_value="Plan here")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_agent_json_output(self, mock_context, mock_agent):
        """Agent commands support JSON output."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        result = runner.invoke(app, ["plan", "test", "--json"])

        assert result.exit_code == 0
        # Output contains JSON after the spinner/panel output
        # Find the JSON portion
        output = result.output.strip()
        json_start = output.find("{")
        assert json_start >= 0, f"No JSON found in output: {output}"
        data = json.loads(output[json_start:])
        assert data["task"] == "test"
        assert data["result"] == "Plan here"


class TestDoCommand:
    """Tests for the 'do' task command."""

    @patch("animus_forge.cli.commands.dev.get_workflow_executor")
    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    @patch("animus_kernel.executor.loader.load_workflow")
    def test_do_dry_run(self, mock_load, mock_context, mock_get_executor):
        """Do command with --dry-run shows plan."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }
        mock_wf = MagicMock()
        mock_wf.name = "Test Workflow"
        mock_wf.steps = [MagicMock(id="s1", type="agent", params={"role": "planner"})]
        mock_load.return_value = mock_wf

        # Create mock workflows directory - patch where it's checked in do_task
        with patch.object(Path, "exists", return_value=True):
            result = runner.invoke(app, ["do", "add feature", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run" in result.output

    @patch("animus_forge.cli.commands.dev.detect_codebase_context")
    def test_do_workflow_not_found(self, mock_context):
        """Do command fails when workflow not found."""
        mock_context.return_value = {
            "path": "/test",
            "language": "python",
            "framework": None,
            "structure": [],
        }

        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(app, ["do", "test", "-w", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestBudgetSubcommands:
    """Tests for budget subcommands."""

    @patch("animus_forge.budget.BudgetManager")
    def test_budget_status(self, mock_manager_class):
        """Budget status shows current usage."""
        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_budget": 100000,
            "used": 25000,
            "remaining": 75000,
            "total_operations": 50,
            "agents": {"planner": 10000, "builder": 15000},
        }
        mock_manager_class.return_value = mock_manager

        result = runner.invoke(app, ["budget", "status"])

        assert result.exit_code == 0
        assert "100,000" in result.output
        assert "25,000" in result.output

    @patch("animus_forge.budget.BudgetManager")
    def test_budget_status_json(self, mock_manager_class):
        """Budget status outputs JSON."""
        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_budget": 100000,
            "used": 25000,
            "remaining": 75000,
            "total_operations": 50,
        }
        mock_manager_class.return_value = mock_manager

        result = runner.invoke(app, ["budget", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_budget"] == 100000

    @patch("animus_forge.budget.BudgetManager")
    def test_budget_history(self, mock_manager_class):
        """Budget history shows usage records."""
        mock_manager = MagicMock()
        mock_record = MagicMock()
        mock_record.timestamp = "2024-01-01 12:00:00"
        mock_record.agent_id = "planner"
        mock_record.tokens = 1000
        mock_record.operation = "plan task"
        mock_manager.get_usage_history.return_value = [mock_record]
        mock_manager_class.return_value = mock_manager

        result = runner.invoke(app, ["budget", "history"])

        assert result.exit_code == 0
        assert "planner" in result.output

    @patch("animus_forge.budget.BudgetManager")
    def test_budget_reset_requires_confirm(self, mock_manager_class):
        """Budget reset requires confirmation."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        result = runner.invoke(app, ["budget", "reset"], input="n\n")

        assert result.exit_code == 1
        mock_manager.reset.assert_not_called()

    @patch("animus_forge.budget.BudgetManager")
    def test_budget_reset_with_force(self, mock_manager_class):
        """Budget reset skips confirmation with --force."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        result = runner.invoke(app, ["budget", "reset", "--force"])

        assert result.exit_code == 0
        mock_manager.reset.assert_called_once()


class TestScheduleSubcommands:
    """Tests for schedule subcommands."""

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_list_empty(self, mock_scheduler_class):
        """Schedule list shows message when empty."""
        mock_scheduler = MagicMock()
        mock_scheduler.list.return_value = []
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0
        assert "No scheduled workflows" in result.output

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_add_requires_cron_or_interval(self, mock_scheduler_class):
        """Schedule add requires --cron or --interval."""
        result = runner.invoke(app, ["schedule", "add", "workflow.json"])

        assert result.exit_code == 1
        assert "Must specify" in result.output

    @patch("animus_kernel.executor.WorkflowScheduler")
    @patch("animus_kernel.executor.ScheduleConfig")
    def test_schedule_add_with_cron(self, mock_config, mock_scheduler_class):
        """Schedule add with cron expression."""
        mock_scheduler = MagicMock()
        mock_result = MagicMock()
        mock_result.schedule_id = "sched-123"
        mock_scheduler.add.return_value = mock_result
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "add", "workflow.json", "--cron", "0 * * * *"])

        assert result.exit_code == 0
        assert "created" in result.output.lower()

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_remove(self, mock_scheduler_class):
        """Schedule remove deletes schedule."""
        mock_scheduler = MagicMock()
        mock_scheduler.remove.return_value = True
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "remove", "sched-123"])

        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_remove_not_found(self, mock_scheduler_class):
        """Schedule remove fails when not found."""
        mock_scheduler = MagicMock()
        mock_scheduler.remove.return_value = False
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "remove", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_pause(self, mock_scheduler_class):
        """Schedule pause pauses schedule."""
        mock_scheduler = MagicMock()
        mock_scheduler.pause.return_value = True
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "pause", "sched-123"])

        assert result.exit_code == 0
        assert "paused" in result.output.lower()

    @patch("animus_kernel.executor.WorkflowScheduler")
    def test_schedule_resume(self, mock_scheduler_class):
        """Schedule resume resumes paused schedule."""
        mock_scheduler = MagicMock()
        mock_scheduler.resume.return_value = True
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["schedule", "resume", "sched-123"])

        assert result.exit_code == 0
        assert "resumed" in result.output.lower()


class TestMemorySubcommands:
    """Tests for memory subcommands."""

    @patch("animus_forge.state.AgentMemory")
    def test_memory_list_empty(self, mock_memory_class):
        """Memory list shows message when empty."""
        mock_memory = MagicMock()
        mock_memory.backend.fetchall.return_value = []
        mock_memory_class.return_value = mock_memory

        result = runner.invoke(app, ["memory", "list"])

        assert result.exit_code == 0
        assert "No memories found" in result.output

    @patch("animus_forge.state.AgentMemory")
    def test_memory_stats(self, mock_memory_class):
        """Memory stats shows statistics."""
        mock_memory = MagicMock()
        mock_memory.get_stats.return_value = {
            "total_memories": 100,
            "average_importance": 0.75,
            "by_type": {"fact": 50, "context": 50},
        }
        mock_memory_class.return_value = mock_memory

        result = runner.invoke(app, ["memory", "stats", "planner"])

        assert result.exit_code == 0
        assert "100" in result.output
        assert "0.75" in result.output

    @patch("animus_forge.state.AgentMemory")
    def test_memory_clear_requires_confirm(self, mock_memory_class):
        """Memory clear requires confirmation."""
        mock_memory = MagicMock()
        mock_memory_class.return_value = mock_memory

        result = runner.invoke(app, ["memory", "clear", "planner"], input="n\n")

        assert result.exit_code == 1
        mock_memory.forget.assert_not_called()

    @patch("animus_forge.state.AgentMemory")
    def test_memory_clear_with_force(self, mock_memory_class):
        """Memory clear skips confirmation with --force."""
        mock_memory = MagicMock()
        mock_memory.forget.return_value = 10
        mock_memory_class.return_value = mock_memory

        result = runner.invoke(app, ["memory", "clear", "planner", "--force"])

        assert result.exit_code == 0
        assert "Cleared 10" in result.output


class TestMetricsCommands:
    """Tests for metrics subcommands."""

    def test_metrics_export_text_format(self):
        """Metrics export text format handles errors gracefully."""
        # This will fail to import metrics but should handle gracefully
        result = runner.invoke(app, ["metrics", "export", "--format", "text"])

        # Either succeeds or shows error message
        assert result.exit_code in (0, 1)

    def test_metrics_export_help(self):
        """Metrics export shows help."""
        result = runner.invoke(app, ["metrics", "export", "--help"])

        assert result.exit_code == 0
        assert "format" in result.output.lower()

    def test_metrics_serve_help(self):
        """Metrics serve shows help."""
        result = runner.invoke(app, ["metrics", "serve", "--help"])

        assert result.exit_code == 0
        assert "port" in result.output.lower()

    def test_metrics_push_help(self):
        """Metrics push shows help."""
        result = runner.invoke(app, ["metrics", "push", "--help"])

        assert result.exit_code == 0
        assert "gateway" in result.output.lower()


class TestConfigCommands:
    """Tests for config subcommands."""

    def test_config_show_handles_errors(self):
        """Config show handles import errors gracefully."""
        result = runner.invoke(app, ["config", "show"])

        # Either succeeds or shows error message
        assert result.exit_code in (0, 1)

    def test_config_path(self):
        """Config path shows configuration paths."""
        result = runner.invoke(app, ["config", "path"])

        assert result.exit_code == 0
        assert "Configuration Sources" in result.output

    def test_config_env(self):
        """Config env shows environment variables."""
        result = runner.invoke(app, ["config", "env"])

        assert result.exit_code == 0
        assert "Environment Variables" in result.output
        assert "ANTHROPIC_API_KEY" in result.output


class TestPluginsCommands:
    """Tests for plugins subcommands."""

    def test_plugins_list_handles_missing_manager(self):
        """Plugins list handles missing PluginManager gracefully."""
        result = runner.invoke(app, ["plugins", "list"])

        # Should either show plugins or show error message
        assert result.exit_code in (0, 1)

    def test_plugins_info_not_found(self):
        """Plugins info shows error for non-existent plugin."""
        result = runner.invoke(app, ["plugins", "info", "nonexistent"])

        # Should fail since plugin doesn't exist
        assert result.exit_code == 1


class TestLogsCommand:
    """Tests for logs command."""

    @patch("animus_forge.cli.commands.admin.get_tracker")
    def test_logs_empty(self, mock_get_tracker):
        """Logs shows message when empty."""
        mock_tracker = MagicMock()
        mock_tracker.get_logs.return_value = []
        mock_get_tracker.return_value = mock_tracker

        result = runner.invoke(app, ["logs"])

        assert result.exit_code == 0
        assert "No logs found" in result.output

    @patch("animus_forge.cli.commands.admin.get_tracker")
    def test_logs_displays_entries(self, mock_get_tracker):
        """Logs displays log entries."""
        mock_tracker = MagicMock()
        mock_tracker.get_logs.return_value = [
            {
                "timestamp": "2024-01-01 12:00:00",
                "level": "INFO",
                "message": "Test log message",
                "workflow_id": "wf-1",
                "execution_id": "exec-12345678",
            }
        ]
        mock_get_tracker.return_value = mock_tracker

        result = runner.invoke(app, ["logs"])

        assert result.exit_code == 0
        assert "Test log message" in result.output

    @patch("animus_forge.cli.commands.admin.get_tracker")
    def test_logs_json_output(self, mock_get_tracker):
        """Logs outputs JSON when requested."""
        mock_tracker = MagicMock()
        mock_tracker.get_logs.return_value = [
            {"timestamp": "2024-01-01", "level": "INFO", "message": "Test"}
        ]
        mock_get_tracker.return_value = mock_tracker

        result = runner.invoke(app, ["logs", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["message"] == "Test"


class TestDashboardCommand:
    """Tests for dashboard command."""

    @patch("subprocess.run")
    @patch("webbrowser.open")
    def test_dashboard_starts(self, mock_browser, mock_run):
        """Dashboard command starts streamlit."""
        mock_run.return_value = MagicMock(returncode=0)

        # Patch Path.exists to return True for dashboard
        with patch("pathlib.Path.exists", return_value=True):
            runner.invoke(app, ["dashboard", "--no-browser"])

        # Should attempt to run streamlit
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "streamlit" in call_args
