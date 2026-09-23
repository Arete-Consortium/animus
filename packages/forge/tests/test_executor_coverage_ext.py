"""Extended coverage tests for workflow executor subsystem.

Targets:
  - executor_integrations.py: _execute_shell (edge cases), _execute_notion,
    _execute_gmail, _execute_slack, _execute_calendar, _execute_browser,
    _execute_github (additional actions)
  - executor_parallel_exec.py: _execute_parallel_group (sync),
    _execute_parallel_group_async, _execute_with_auto_parallel,
    _execute_with_auto_parallel_async, error/tracking paths, rate limiting
"""

import asyncio
import subprocess
import sys

import pytest

sys.path.insert(0, "src")

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

from animus_forge.workflow.executor_core import WorkflowExecutor
from animus_forge.workflow.executor_results import ExecutionResult, StepResult, StepStatus
from animus_forge.workflow.loader import StepConfig, WorkflowConfig, WorkflowSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_executor(**overrides) -> WorkflowExecutor:
    """Create a WorkflowExecutor bypassing __init__ and setting only the
    attributes needed for the method under test."""
    exe = WorkflowExecutor.__new__(WorkflowExecutor)
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
    """Convenience factory for StepConfig."""
    return StepConfig(id=step_id, type=step_type, params=params or {}, **kwargs)


# ===================================================================
# INTEGRATION HANDLERS — executor_integrations.py
# ===================================================================


# -------------------------------------------------------------------
# _execute_shell — additional edge cases
# -------------------------------------------------------------------


class TestExecuteShellExtended:
    """Additional _execute_shell coverage: allowed commands, allow_failure,
    stderr truncation, step-level timeout, variable substitution."""

    def _settings_mock(self, **overrides):
        s = MagicMock()
        s.shell_timeout_seconds = 300
        s.shell_max_output_bytes = 10 * 1024 * 1024
        s.shell_allowed_commands = None
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def test_missing_command_raises(self):
        """Empty/missing command param raises ValueError."""
        with patch("animus_forge.config.get_settings") as mock_settings:
            mock_settings.return_value = self._settings_mock()
            exe = _bare_executor()
            step = _make_step(params={"command": ""})
            with pytest.raises(ValueError, match="requires 'command' parameter"):
                exe._execute_shell(step, {})

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_allowed_commands_whitelist_passes(self, mock_sub, mock_val, mock_settings, mock_run):
        """Command in whitelist is allowed."""
        mock_settings.return_value = self._settings_mock(shell_allowed_commands="echo,ls,cat")
        mock_val.return_value = None
        mock_sub.return_value = "echo hello"
        proc = MagicMock(returncode=0, stdout="hello\n", stderr="")
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "echo hello"})
        out = exe._execute_shell(step, {})
        assert out["returncode"] == 0

    @patch("animus_forge.config.get_settings")
    def test_allowed_commands_whitelist_blocks(self, mock_settings):
        """Command NOT in whitelist is rejected."""
        mock_settings.return_value = self._settings_mock(shell_allowed_commands="echo,ls")
        exe = _bare_executor()
        step = _make_step(params={"command": "curl http://evil.com"})
        with pytest.raises(ValueError, match="not in allowed list"):
            exe._execute_shell(step, {})

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_allow_failure_non_zero_exit(self, mock_sub, mock_val, mock_settings, mock_run):
        """Non-zero exit with allow_failure=True returns without raising."""
        mock_settings.return_value = self._settings_mock()
        mock_val.return_value = None
        mock_sub.return_value = "false"
        proc = MagicMock(returncode=1, stdout="", stderr="expected error")
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "false", "allow_failure": True})
        out = exe._execute_shell(step, {})
        assert out["returncode"] == 1
        assert out["stderr"] == "expected error"

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_stderr_truncation(self, mock_sub, mock_val, mock_settings, mock_run):
        """Stderr exceeding max_output_bytes is truncated."""
        mock_settings.return_value = self._settings_mock(shell_max_output_bytes=20)
        mock_val.return_value = None
        mock_sub.return_value = "cmd"
        proc = MagicMock(returncode=0, stdout="ok", stderr="E" * 100)
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "cmd"})
        out = exe._execute_shell(step, {})
        assert "[OUTPUT TRUNCATED]" in out["stderr"]

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_step_level_timeout_override(self, mock_sub, mock_val, mock_settings, mock_run):
        """Step-level timeout_seconds overrides global setting."""
        mock_settings.return_value = self._settings_mock(shell_timeout_seconds=300)
        mock_val.return_value = None
        mock_sub.return_value = "cmd"
        proc = MagicMock(returncode=0, stdout="ok", stderr="")
        mock_run.return_value = proc

        exe = _bare_executor()
        step = _make_step(params={"command": "cmd"}, timeout_seconds=60)
        exe._execute_shell(step, {})
        # Verify subprocess.run got the step-level timeout
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 60

    @patch("animus_kernel.executor.executor_integrations.subprocess.run")
    @patch("animus_forge.config.get_settings")
    @patch("animus_kernel.utils.validation.validate_shell_command")
    @patch("animus_kernel.utils.validation.substitute_shell_variables")
    def test_timeout_expired_with_partial_output(self, mock_sub, mock_val, mock_settings, mock_run):
        """TimeoutExpired error includes partial stdout/stderr when available."""
        mock_settings.return_value = self._settings_mock()
        mock_val.return_value = None
        mock_sub.return_value = "slow"
        err = subprocess.TimeoutExpired(cmd="slow", timeout=10)
        err.stdout = "partial out"
        err.stderr = "partial err"
        mock_run.side_effect = err

        exe = _bare_executor()
        step = _make_step(params={"command": "slow"})
        with pytest.raises(RuntimeError, match="timed out") as exc_info:
            exe._execute_shell(step, {})
        assert "partial out" in str(exc_info.value)
        assert "partial err" in str(exc_info.value)


# -------------------------------------------------------------------
# _execute_github — commit_file, list_repos, get_repo_info + context sub
# -------------------------------------------------------------------


class TestExecuteGitHubExtended:
    """Additional _execute_github paths: commit_file, list_repos,
    get_repo_info, context variable substitution."""

    @patch("animus_forge.api_clients.GitHubClient")
    def test_commit_file(self, MockGH):
        client = MagicMock()
        client.is_configured.return_value = True
        client.commit_file.return_value = {"commit_sha": "abc123"}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={
                "action": "commit_file",
                "repo": "owner/repo",
                "file_path": "README.md",
                "body": "# Hello",
                "message": "Update readme",
                "branch": "main",
            },
        )
        out = exe._execute_github(step, {})
        assert out["commit_sha"] == "abc123"
        assert out["action"] == "commit_file"
        client.commit_file.assert_called_once_with(
            "owner/repo", "README.md", "# Hello", "Update readme", "main"
        )

    @patch("animus_forge.api_clients.GitHubClient")
    def test_list_repos(self, MockGH):
        client = MagicMock()
        client.is_configured.return_value = True
        client.list_repositories.return_value = [
            {"name": "repo1"},
            {"name": "repo2"},
        ]
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={"action": "list_repos", "repo": ""},
        )
        out = exe._execute_github(step, {})
        assert out["action"] == "list_repos"
        assert out["count"] == 2

    @patch("animus_forge.api_clients.GitHubClient")
    def test_get_repo_info(self, MockGH):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_repo_info.return_value = {"full_name": "owner/repo", "stars": 42}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={"action": "get_repo_info", "repo": "owner/repo"},
        )
        out = exe._execute_github(step, {})
        assert out["action"] == "get_repo_info"
        assert out["result"]["stars"] == 42

    @patch("animus_forge.api_clients.GitHubClient")
    def test_context_variable_substitution_in_repo(self, MockGH):
        """Context variables are substituted in repo name."""
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_repo_info.return_value = {"full_name": "myorg/myrepo"}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={"action": "get_repo_info", "repo": "${org}/${name}"},
        )
        exe._execute_github(step, {"org": "myorg", "name": "myrepo"})
        client.get_repo_info.assert_called_once_with("myorg/myrepo")

    @patch("animus_forge.api_clients.GitHubClient")
    def test_commit_file_with_context_substitution(self, MockGH):
        """Context variables substituted in file_path, content, message."""
        client = MagicMock()
        client.is_configured.return_value = True
        client.commit_file.return_value = {"commit_sha": "def456"}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={
                "action": "commit_file",
                "repo": "owner/repo",
                "file_path": "docs/${module}.md",
                "body": "# ${module} docs",
                "message": "Update ${module} documentation",
                "branch": "main",
            },
        )
        out = exe._execute_github(step, {"module": "auth"})
        assert out["commit_sha"] == "def456"
        client.commit_file.assert_called_once_with(
            "owner/repo",
            "docs/auth.md",
            "# auth docs",
            "Update auth documentation",
            "main",
        )

    @patch("animus_forge.api_clients.GitHubClient")
    def test_create_issue_with_context_substitution(self, MockGH, monkeypatch):
        """Context variables substituted in title, body."""
        client = MagicMock()
        client.is_configured.return_value = True
        client.create_issue.return_value = {"number": 1, "url": "https://gh/1"}
        MockGH.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="github",
            params={
                "action": "create_issue",
                "repo": "owner/repo",
                "title": "Fix ${module}",
                "body": "Details about ${module}",
                "labels": [],
            },
        )
        monkeypatch.setenv("ANIMUS_ALLOW_AUTONOMOUS_ISSUES", "1")
        out = exe._execute_github(step, {"module": "auth"})
        assert out["issue_number"] == 1
        client.create_issue.assert_called_once_with(
            "owner/repo", "Fix auth", "Details about auth", []
        )

    def test_dry_run_context_substitution(self):
        """Dry run substitutes context vars in repo."""
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="github",
            params={"action": "create_issue", "repo": "${owner}/repo"},
        )
        out = exe._execute_github(step, {"owner": "acme"})
        assert out["repo"] == "acme/repo"
        assert out["dry_run"] is True


# -------------------------------------------------------------------
# _execute_notion — all 7 actions
# -------------------------------------------------------------------


class TestExecuteNotion:
    """_execute_notion: all actions + dry run + unconfigured client."""

    def test_dry_run(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(step_type="notion", params={"action": "search", "query": "test"})
        out = exe._execute_notion(step, {})
        assert out["dry_run"] is True
        assert "DRY RUN" in out["result"]

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_not_configured_raises(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = False
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="notion", params={"action": "search"})
        with pytest.raises(RuntimeError, match="Notion client not configured"):
            exe._execute_notion(step, {})

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_query_database(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.query_database.return_value = [{"id": "page1"}, {"id": "page2"}]
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={
                "action": "query_database",
                "database_id": "db123",
                "filter": {"property": "Status", "status": {"equals": "Done"}},
                "sorts": [{"property": "Date", "direction": "descending"}],
                "page_size": 50,
            },
        )
        out = exe._execute_notion(step, {})
        assert out["action"] == "query_database"
        assert out["count"] == 2
        client.query_database.assert_called_once_with(
            "db123",
            {"property": "Status", "status": {"equals": "Done"}},
            [{"property": "Date", "direction": "descending"}],
            50,
        )

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_create_page(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.create_page.return_value = {
            "id": "page123",
            "url": "https://notion.so/page123",
        }
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={
                "action": "create_page",
                "parent_id": "db456",
                "title": "Report for ${project}",
                "content": "Content about ${project}",
            },
        )
        out = exe._execute_notion(step, {"project": "Gorgon"})
        assert out["page_id"] == "page123"
        assert out["page_url"] == "https://notion.so/page123"
        client.create_page.assert_called_once_with(
            "db456", "Report for Gorgon", "Content about Gorgon"
        )

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_get_page(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_page.return_value = {"id": "p1", "title": "Test"}
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={"action": "get_page", "page_id": "p1"},
        )
        out = exe._execute_notion(step, {})
        assert out["page_id"] == "p1"
        client.get_page.assert_called_once_with("p1")

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_update_page(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.update_page.return_value = {"id": "p1", "status": "updated"}
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={
                "action": "update_page",
                "page_id": "p1",
                "properties": {"Status": {"status": {"name": "Done"}}},
            },
        )
        out = exe._execute_notion(step, {})
        assert out["page_id"] == "p1"
        client.update_page.assert_called_once_with("p1", {"Status": {"status": {"name": "Done"}}})

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_read_content(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.read_page_content.return_value = [
            {"type": "paragraph", "text": "hello"},
            {"type": "heading_1", "text": "Title"},
        ]
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={"action": "read_content", "page_id": "p2"},
        )
        out = exe._execute_notion(step, {})
        assert out["blocks"] == 2
        client.read_page_content.assert_called_once_with("p2")

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_append(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.append_to_page.return_value = {"ok": True}
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={
                "action": "append",
                "page_id": "p3",
                "content": "Note about ${topic}",
            },
        )
        out = exe._execute_notion(step, {"topic": "testing"})
        assert out["page_id"] == "p3"
        client.append_to_page.assert_called_once_with("p3", "Note about testing")

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_search(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        client.search_pages.return_value = [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}]
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="notion",
            params={"action": "search", "query": "Find ${keyword}"},
        )
        out = exe._execute_notion(step, {"keyword": "bugs"})
        assert out["count"] == 3
        assert out["query"] == "Find bugs"
        client.search_pages.assert_called_once_with("Find bugs")

    @patch("animus_forge.api_clients.NotionClientWrapper")
    def test_unknown_action_raises(self, MockNotion):
        client = MagicMock()
        client.is_configured.return_value = True
        MockNotion.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="notion", params={"action": "delete_everything"})
        with pytest.raises(ValueError, match="Unknown Notion action"):
            exe._execute_notion(step, {})


# -------------------------------------------------------------------
# _execute_gmail — list_messages, get_message, dry run, errors
# -------------------------------------------------------------------


class TestExecuteGmail:
    """_execute_gmail: all actions + dry run + auth failure."""

    def test_dry_run(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(step_type="gmail", params={"action": "list_messages"})
        out = exe._execute_gmail(step, {})
        assert out["dry_run"] is True
        assert "DRY RUN" in out["result"]

    @patch("animus_forge.api_clients.GmailClient")
    def test_not_configured_raises(self, MockGmail):
        client = MagicMock()
        client.is_configured.return_value = False
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="gmail", params={"action": "list_messages"})
        with pytest.raises(RuntimeError, match="Gmail client not configured"):
            exe._execute_gmail(step, {})

    @patch("animus_forge.api_clients.GmailClient")
    def test_auth_failure_raises(self, MockGmail):
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = False
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="gmail", params={"action": "list_messages"})
        with pytest.raises(RuntimeError, match="Gmail authentication failed"):
            exe._execute_gmail(step, {})

    @patch("animus_forge.api_clients.GmailClient")
    def test_list_messages(self, MockGmail):
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = True
        client.list_messages.return_value = [{"id": "m1"}, {"id": "m2"}]
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="gmail",
            params={
                "action": "list_messages",
                "max_results": 5,
                "query": "from:${sender}",
            },
        )
        out = exe._execute_gmail(step, {"sender": "alice@example.com"})
        assert out["count"] == 2
        client.list_messages.assert_called_once_with(5, "from:alice@example.com")

    @patch("animus_forge.api_clients.GmailClient")
    def test_list_messages_no_query(self, MockGmail):
        """list_messages with no query parameter."""
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = True
        client.list_messages.return_value = []
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="gmail",
            params={"action": "list_messages", "max_results": 10},
        )
        out = exe._execute_gmail(step, {"some_var": "value"})
        assert out["count"] == 0
        # query is None, context sub skipped because query is falsy
        client.list_messages.assert_called_once_with(10, None)

    @patch("animus_forge.api_clients.GmailClient")
    def test_get_message(self, MockGmail):
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = True
        client.get_message.return_value = {"id": "m42", "subject": "Hello"}
        client.extract_email_body.return_value = "Body text here"
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="gmail",
            params={"action": "get_message", "message_id": "m42"},
        )
        out = exe._execute_gmail(step, {})
        assert out["message_id"] == "m42"
        assert out["body"] == "Body text here"
        client.get_message.assert_called_once_with("m42")

    @patch("animus_forge.api_clients.GmailClient")
    def test_get_message_no_result(self, MockGmail):
        """get_message returns None/empty — body should be empty string."""
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = True
        client.get_message.return_value = None
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="gmail",
            params={"action": "get_message", "message_id": "missing"},
        )
        out = exe._execute_gmail(step, {})
        assert out["body"] == ""
        assert out["result"] is None

    @patch("animus_forge.api_clients.GmailClient")
    def test_unknown_action_raises(self, MockGmail):
        client = MagicMock()
        client.is_configured.return_value = True
        client.authenticate.return_value = True
        MockGmail.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="gmail", params={"action": "send_email"})
        with pytest.raises(ValueError, match="Unknown Gmail action"):
            exe._execute_gmail(step, {})


# -------------------------------------------------------------------
# _execute_slack — send_message, send_notification, send_approval,
#                  update_message, add_reaction, dry run, errors
# -------------------------------------------------------------------


class TestExecuteSlack:
    """_execute_slack: all 5 actions + dry run + missing token."""

    def _mock_settings(self, token="xoxb-test-token"):
        s = MagicMock()
        s.slack_token = token
        return s

    def test_dry_run(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="slack",
            params={
                "action": "send_message",
                "channel": "#general",
                "text": "Hello",
            },
        )
        out = exe._execute_slack(step, {})
        assert out["dry_run"] is True
        assert "#general" in out["result"]

    def test_dry_run_context_substitution(self):
        """Context vars substituted in channel even in dry run."""
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="slack",
            params={"action": "send_message", "channel": "${target_channel}"},
        )
        out = exe._execute_slack(step, {"target_channel": "#alerts"})
        assert out["channel"] == "#alerts"

    @patch("animus_forge.config.get_settings")
    def test_missing_token_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(slack_token=None)
        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={"action": "send_message", "channel": "#gen"},
        )
        with pytest.raises(RuntimeError, match="Slack client not configured"):
            exe._execute_slack(step, {})

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_client_not_configured_raises(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = False
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={"action": "send_message", "channel": "#gen"},
        )
        with pytest.raises(RuntimeError, match="initialization failed"):
            exe._execute_slack(step, {})

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.api_clients.slack_client.MessageType")
    @patch("animus_forge.config.get_settings")
    def test_send_message(self, mock_settings, MockMsgType, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        client.send_message.return_value = {
            "success": True,
            "ts": "1234567890.123456",
        }
        MockSlack.return_value = client
        MockMsgType.return_value = "info"

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={
                "action": "send_message",
                "channel": "#dev",
                "text": "Build ${status}",
                "message_type": "info",
                "thread_ts": None,
            },
        )
        out = exe._execute_slack(step, {"status": "passed"})
        assert out["success"] is True
        assert out["ts"] == "1234567890.123456"

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_send_notification(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        client.send_workflow_notification.return_value = {"success": True}
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={
                "action": "send_notification",
                "channel": "#ops",
                "workflow_name": "deploy",
                "status": "completed",
                "details": "All good",
            },
        )
        out = exe._execute_slack(step, {})
        assert out["success"] is True
        client.send_workflow_notification.assert_called_once()

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_send_approval(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        client.send_approval_request.return_value = {
            "success": True,
            "ts": "ts123",
        }
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={
                "action": "send_approval",
                "channel": "#approvals",
                "title": "Deploy ${env}?",
                "description": "Deploy to ${env}",
                "requester": "bot",
                "callback_id": "deploy_123",
            },
        )
        out = exe._execute_slack(step, {"env": "production"})
        assert out["success"] is True
        # Verify context substitution in title and description
        call_args = client.send_approval_request.call_args
        assert call_args[0][1] == "Deploy production?"
        assert call_args[0][2] == "Deploy to production"

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_update_message(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        client.update_message.return_value = {"success": True}
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={
                "action": "update_message",
                "channel": "#dev",
                "ts": "ts456",
                "text": "Updated: ${msg}",
            },
        )
        out = exe._execute_slack(step, {"msg": "done"})
        assert out["success"] is True
        client.update_message.assert_called_once_with("#dev", "ts456", "Updated: done")

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_add_reaction(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        client.add_reaction.return_value = {"success": True}
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="slack",
            params={
                "action": "add_reaction",
                "channel": "#dev",
                "ts": "ts789",
                "emoji": "rocket",
            },
        )
        out = exe._execute_slack(step, {})
        assert out["success"] is True
        assert out["emoji"] == "rocket"
        client.add_reaction.assert_called_once_with("#dev", "ts789", "rocket")

    @patch("animus_forge.api_clients.slack_client.SlackClient")
    @patch("animus_forge.config.get_settings")
    def test_unknown_action_raises(self, mock_settings, MockSlack):
        mock_settings.return_value = self._mock_settings()
        client = MagicMock()
        client.is_configured.return_value = True
        MockSlack.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="slack", params={"action": "delete_channel", "channel": "#dev"})
        with pytest.raises(ValueError, match="Unknown Slack action"):
            exe._execute_slack(step, {})


# -------------------------------------------------------------------
# _execute_calendar — list_events, create_event, get_event,
#                     delete_event, check_availability, quick_add
# -------------------------------------------------------------------


class TestExecuteCalendar:
    """_execute_calendar: all 6 actions + dry run + auth failure."""

    def test_dry_run(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="calendar",
            params={"action": "list_events", "calendar_id": "primary"},
        )
        out = exe._execute_calendar(step, {})
        assert out["dry_run"] is True
        assert "DRY RUN" in out["result"]

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_auth_failure_raises(self, MockCal):
        client = MagicMock()
        client.authenticate.return_value = False
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="calendar", params={"action": "list_events"})
        with pytest.raises(RuntimeError, match="authentication failed"):
            exe._execute_calendar(step, {})

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_list_events(self, MockCal):
        from datetime import datetime

        mock_event = MagicMock()
        mock_event.id = "ev1"
        mock_event.summary = "Team Standup"
        mock_event.start = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        mock_event.end = datetime(2025, 1, 1, 9, 30, tzinfo=UTC)
        mock_event.location = "Room A"
        mock_event.all_day = False

        client = MagicMock()
        client.authenticate.return_value = True
        client.list_events.return_value = [mock_event]
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "list_events", "days": 3, "max_results": 10},
        )
        out = exe._execute_calendar(step, {})
        assert out["count"] == 1
        assert out["result"][0]["summary"] == "Team Standup"
        assert out["result"][0]["location"] == "Room A"

    @patch("animus_forge.api_clients.calendar_client.CalendarEvent")
    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_create_event(self, MockCal, MockCalEvent):
        result_event = MagicMock()
        result_event.id = "new_ev1"
        result_event.summary = "Review Meeting"
        result_event.html_link = "https://cal.google.com/ev1"

        client = MagicMock()
        client.authenticate.return_value = True
        client.create_event.return_value = result_event
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={
                "action": "create_event",
                "summary": "Review ${project}",
                "start": "2025-06-01T10:00:00+00:00",
                "end": "2025-06-01T11:00:00+00:00",
                "location": "Zoom",
                "description": "Review ${project} progress",
                "all_day": False,
            },
        )
        out = exe._execute_calendar(step, {"project": "Gorgon"})
        assert out["event_id"] == "new_ev1"
        assert out["result"]["url"] == "https://cal.google.com/ev1"
        # Verify CalendarEvent was constructed with substituted values
        call_kwargs = MockCalEvent.call_args[1]
        assert call_kwargs["summary"] == "Review Gorgon"
        assert call_kwargs["description"] == "Review Gorgon progress"

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_get_event(self, MockCal):
        from datetime import datetime

        result_event = MagicMock()
        result_event.id = "ev99"
        result_event.summary = "Sprint Planning"
        result_event.start = datetime(2025, 3, 1, 14, 0, tzinfo=UTC)
        result_event.end = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
        result_event.location = "Main Office"

        client = MagicMock()
        client.authenticate.return_value = True
        client.get_event.return_value = result_event
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "get_event", "event_id": "ev99"},
        )
        out = exe._execute_calendar(step, {})
        assert out["event_id"] == "ev99"
        assert out["result"]["summary"] == "Sprint Planning"
        client.get_event.assert_called_once_with("ev99", "primary")

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_get_event_none_result(self, MockCal):
        """get_event returns None."""
        client = MagicMock()
        client.authenticate.return_value = True
        client.get_event.return_value = None
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "get_event", "event_id": "missing"},
        )
        out = exe._execute_calendar(step, {})
        assert out["result"] is None

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_delete_event(self, MockCal):
        client = MagicMock()
        client.authenticate.return_value = True
        client.delete_event.return_value = True
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "delete_event", "event_id": "ev42"},
        )
        out = exe._execute_calendar(step, {})
        assert out["success"] is True
        client.delete_event.assert_called_once_with("ev42", "primary")

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_check_availability(self, MockCal):
        client = MagicMock()
        client.authenticate.return_value = True
        client.check_availability.return_value = [
            {"start": "09:00", "end": "10:00"},
        ]
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "check_availability", "days": 2},
        )
        out = exe._execute_calendar(step, {})
        assert out["count"] == 1
        client.check_availability.assert_called_once()

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_quick_add(self, MockCal):
        result_event = MagicMock()
        result_event.id = "qa1"
        result_event.summary = "Lunch with Bob tomorrow"

        client = MagicMock()
        client.authenticate.return_value = True
        client.quick_add.return_value = result_event
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "quick_add", "text": "Meet ${person} tomorrow"},
        )
        out = exe._execute_calendar(step, {"person": "Alice"})
        assert out["text"] == "Meet Alice tomorrow"
        client.quick_add.assert_called_once_with("Meet Alice tomorrow", "primary")

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_quick_add_none_result(self, MockCal):
        """quick_add returns None."""
        client = MagicMock()
        client.authenticate.return_value = True
        client.quick_add.return_value = None
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="calendar",
            params={"action": "quick_add", "text": "Something"},
        )
        out = exe._execute_calendar(step, {})
        assert out["result"] is None

    @patch("animus_forge.api_clients.calendar_client.CalendarClient")
    def test_unknown_action_raises(self, MockCal):
        client = MagicMock()
        client.authenticate.return_value = True
        MockCal.return_value = client

        exe = _bare_executor(dry_run=False)
        step = _make_step(step_type="calendar", params={"action": "reschedule"})
        with pytest.raises(ValueError, match="Unknown Calendar action"):
            exe._execute_calendar(step, {})


# -------------------------------------------------------------------
# _execute_browser — navigate, click, fill, screenshot, extract,
#                    scroll, wait, dry run, unknown action
# -------------------------------------------------------------------


class TestExecuteBrowser:
    """_execute_browser: all 7 actions + dry run."""

    def test_dry_run(self):
        exe = _bare_executor(dry_run=True)
        step = _make_step(
            step_type="browser",
            params={
                "action": "navigate",
                "url": "https://${domain}",
            },
        )
        out = exe._execute_browser(step, {"domain": "example.com"})
        assert out["dry_run"] is True
        assert out["url"] == "https://example.com"

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_navigate(self, MockConfig, MockBrowser):
        """Navigate action returns URL, title, success."""
        nav_result = MagicMock()
        nav_result.url = "https://example.com"
        nav_result.title = "Example"
        nav_result.success = True
        nav_result.error = None

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = nav_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "navigate",
                "url": "https://example.com",
                "wait_until": "networkidle",
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        assert out["title"] == "Example"

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_click(self, MockConfig, MockBrowser):
        """Click action navigates first if URL provided, then clicks."""
        click_result = MagicMock(success=True, error=None)
        nav_result = MagicMock()

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = nav_result
        browser_instance.click.return_value = click_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "click",
                "url": "https://example.com",
                "selector": "#submit-btn",
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        browser_instance.navigate.assert_called_once()
        browser_instance.click.assert_called_once_with("#submit-btn")

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_click_no_url(self, MockConfig, MockBrowser):
        """Click without URL does not navigate first."""
        click_result = MagicMock(success=True, error=None)

        browser_instance = AsyncMock()
        browser_instance.click.return_value = click_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={"action": "click", "selector": ".btn"},
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        browser_instance.navigate.assert_not_called()

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_fill(self, MockConfig, MockBrowser):
        """Fill action with context variable substitution."""
        fill_result = MagicMock(success=True, error=None)
        nav_result = MagicMock()

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = nav_result
        browser_instance.fill.return_value = fill_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "fill",
                "url": "https://example.com/login",
                "selector": "#username",
                "value": "${user_name}",
            },
        )
        out = exe._execute_browser(step, {"user_name": "admin"})
        assert out["success"] is True
        browser_instance.fill.assert_called_once_with("#username", "admin")

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_screenshot(self, MockConfig, MockBrowser):
        """Screenshot action returns path."""
        ss_result = MagicMock(screenshot_path="/tmp/screenshot.png", success=True, error=None)

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = MagicMock()
        browser_instance.screenshot.return_value = ss_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "screenshot",
                "url": "https://example.com",
                "full_page": True,
                "path": "/tmp/screenshot.png",
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        assert out["screenshot_path"] == "/tmp/screenshot.png"

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_extract(self, MockConfig, MockBrowser):
        """Extract action returns content data."""
        extract_result = MagicMock(
            title="Page Title",
            url="https://example.com",
            data={"text": "extracted content"},
            success=True,
            error=None,
        )

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = MagicMock()
        browser_instance.extract_content.return_value = extract_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "extract",
                "url": "https://example.com",
                "selector": ".content",
                "extract_links": True,
                "extract_tables": False,
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        assert out["title"] == "Page Title"
        browser_instance.extract_content.assert_called_once_with(".content", True, False)

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_scroll(self, MockConfig, MockBrowser):
        """Scroll action with direction and amount."""
        scroll_result = MagicMock(success=True)

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = MagicMock()
        browser_instance.scroll.return_value = scroll_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "scroll",
                "url": "https://example.com",
                "direction": "down",
                "amount": 1000,
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        assert out["direction"] == "down"
        assert out["amount"] == 1000

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_wait(self, MockConfig, MockBrowser):
        """Wait action waits for selector."""
        wait_result = MagicMock(success=True, error=None)

        browser_instance = AsyncMock()
        browser_instance.navigate.return_value = MagicMock()
        browser_instance.wait_for_selector.return_value = wait_result
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={
                "action": "wait",
                "url": "https://example.com",
                "selector": "#loaded",
                "state": "visible",
                "timeout": 5000,
            },
        )
        out = exe._execute_browser(step, {})
        assert out["success"] is True
        assert out["selector"] == "#loaded"
        assert out["state"] == "visible"
        browser_instance.wait_for_selector.assert_called_once_with("#loaded", "visible", 5000)

    @patch("animus_forge.browser.BrowserAutomation")
    @patch("animus_forge.browser.BrowserConfig")
    def test_unknown_action_raises(self, MockConfig, MockBrowser):
        """Unknown browser action raises ValueError."""
        browser_instance = AsyncMock()
        browser_instance.__aenter__ = AsyncMock(return_value=browser_instance)
        browser_instance.__aexit__ = AsyncMock(return_value=False)
        MockBrowser.return_value = browser_instance

        exe = _bare_executor(dry_run=False)
        step = _make_step(
            step_type="browser",
            params={"action": "drag_and_drop", "url": ""},
        )
        with pytest.raises(ValueError, match="Unknown Browser action"):
            exe._execute_browser(step, {})


# ===================================================================
# PARALLEL GROUP EXECUTION — executor_parallel_exec.py
# ===================================================================


# -------------------------------------------------------------------
# _execute_parallel_group (sync) — unit-level tests with mocked deps
# -------------------------------------------------------------------


class TestExecuteParallelGroup:
    """_execute_parallel_group: sync parallel execution with tracking."""

    def _make_workflow_settings(self, auto_parallel=True, max_workers=4):
        return WorkflowSettings(
            auto_parallel=auto_parallel,
            auto_parallel_max_workers=max_workers,
        )

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_non_ai_steps_use_threading_executor(self, MockPE, mock_tracker):
        """Non-AI steps use ParallelExecutor with THREADING strategy."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        mock_executor = MagicMock()
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(
            return_value=StepResult(step_id="s1", status=StepStatus.SUCCESS)
        )
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [
            _make_step(step_id="s1", step_type="shell", timeout_seconds=60),
            _make_step(step_id="s2", step_type="shell", timeout_seconds=60),
        ]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        # Should use ParallelExecutor (not RateLimitedParallelExecutor)
        MockPE.assert_called_once()

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.RateLimitedParallelExecutor")
    def test_ai_steps_use_rate_limited_executor(self, MockRLE, mock_tracker):
        """AI steps (claude_code, openai) use RateLimitedParallelExecutor."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        mock_executor = MagicMock()
        mock_executor.get_provider_stats.return_value = {}
        MockRLE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(
            return_value=StepResult(step_id="s1", status=StepStatus.SUCCESS)
        )
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [
            _make_step(step_id="ai1", step_type="claude_code", timeout_seconds=120),
            _make_step(step_id="ai2", step_type="openai", timeout_seconds=120),
        ]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        MockRLE.assert_called_once()
        call_kwargs = MockRLE.call_args[1]
        assert call_kwargs["adaptive"] is True

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_failed_step_triggers_abort(self, MockPE, mock_tracker):
        """When a step fails and _handle_step_failure returns 'abort',
        result.status is set to 'failed'."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="boom")

        def fake_execute_parallel(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                on_complete(task.id, failed_result)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = fake_execute_parallel
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="abort")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        assert result.status == "failed"
        tracker.fail_execution.assert_called_once()

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_failed_step_skip_still_stores_outputs(self, MockPE, mock_tracker):
        """When _handle_step_failure returns 'skip', outputs are NOT stored
        for that step (action == 'skip' falls through without storing)."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="oops")

        def fake_execute_parallel(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                on_complete(task.id, failed_result)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = fake_execute_parallel
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="skip")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        # With "skip", _store_step_outputs should not be called
        exe._store_step_outputs.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_on_error_callback_creates_failed_result(self, MockPE, mock_tracker):
        """on_error callback creates a FAILED StepResult."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        def fake_execute_parallel(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                on_error(task.id, RuntimeError("handler crashed"))

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = fake_execute_parallel
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock()
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        # _record_step_completion should receive a FAILED result
        call_args = exe._record_step_completion.call_args[0]
        step_result = call_args[1]
        assert step_result.status == StepStatus.FAILED
        assert "handler crashed" in step_result.error

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_successful_execution_completes_tracking(self, MockPE, mock_tracker):
        """Successful execution calls tracker.complete_execution."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS, output={"data": "ok"})

        def fake_execute_parallel(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                on_complete(task.id, success_result)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = fake_execute_parallel
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.complete_execution.assert_called_once()
        tracker.fail_execution.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.RateLimitedParallelExecutor")
    def test_rate_limit_stats_captured(self, MockRLE, mock_tracker):
        """Rate limit stats from AI executor are captured by tracker."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        success_result = StepResult(step_id="ai1", status=StepStatus.SUCCESS)

        def fake_execute_parallel(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                on_complete(task.id, success_result)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = fake_execute_parallel
        mock_executor.get_provider_stats.return_value = {
            "anthropic": {
                "total_429s": 3,
                "is_throttled": True,
                "current_limit": 50,
                "base_limit": 100,
            }
        }
        MockRLE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        steps = [
            _make_step(step_id="ai1", step_type="claude_code", timeout_seconds=120),
        ]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.update_rate_limit_state.assert_called_once_with(
            provider="anthropic",
            current_limit=50,
            base_limit=100,
            total_429s=3,
            is_throttled=True,
        )


# -------------------------------------------------------------------
# _execute_parallel_group_async — async variant
# -------------------------------------------------------------------


class TestExecuteParallelGroupAsync:
    """_execute_parallel_group_async: async parallel with semaphore."""

    def test_async_parallel_success(self):
        """All steps succeed in async parallel."""
        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS, output={"data": "ok"})

        exe = _bare_executor()
        exe._execute_step_async = AsyncMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [
            _make_step(step_id="s1", step_type="shell"),
            _make_step(step_id="s2", step_type="shell"),
        ]
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        assert exe._record_step_completion.call_count == 2
        assert exe._store_step_outputs.call_count == 2

    def test_async_parallel_failure_abort(self):
        """Failed step with abort action sets result to failed."""
        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="boom")

        exe = _bare_executor()
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="abort")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell")]
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        assert result.status == "failed"

    def test_async_parallel_failure_skip(self):
        """Failed step with skip action does not store outputs."""
        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="oops")

        exe = _bare_executor()
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="skip")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell")]
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        exe._store_step_outputs.assert_not_called()

    def test_async_parallel_exception_in_step(self):
        """Exception from _execute_step_async is handled via return_exceptions."""

        async def raise_error(step, wf_id):
            raise RuntimeError("step exploded")

        exe = _bare_executor()
        exe._execute_step_async = raise_error
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell")]
        result = ExecutionResult(workflow_name="test")

        # Exception items are skipped (isinstance check in loop)
        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        # No step_results collected for exceptions, so no recording
        exe._record_step_completion.assert_not_called()

    def test_async_parallel_failure_continue_stores_outputs(self):
        """Failed step with 'continue' action (not 'skip') stores outputs."""
        failed_result = StepResult(
            step_id="s1",
            status=StepStatus.FAILED,
            error="non-fatal",
            output={"partial": "data"},
        )

        exe = _bare_executor()
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell")]
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        # "continue" is not "skip" and not "abort", so outputs are stored
        exe._store_step_outputs.assert_called_once()


# -------------------------------------------------------------------
# _execute_with_auto_parallel — orchestrates groups
# -------------------------------------------------------------------


class TestExecuteWithAutoParallel:
    """_execute_with_auto_parallel: group orchestration logic."""

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_empty_steps_sets_success(self, mock_build, mock_find):
        """Empty step list immediately sets result to success."""
        exe = _bare_executor()
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        assert result.status == "success"
        mock_build.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_group_executes_directly(self, mock_build, mock_find):
        """Single-step groups execute via _execute_step directly."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS, output={"data": "ok"})

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        assert result.status == "success"
        exe._execute_step.assert_called_once_with(step, "wf-1")
        exe._store_step_outputs.assert_called_once()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_failure_aborts(self, mock_build, mock_find):
        """Failed single step with abort action aborts execution."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="boom")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="abort")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        # Aborted — result.status not set to "success"
        assert result.status != "success"

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_budget_exceeded_returns_early(self, mock_build, mock_find):
        """Budget exceeded in group returns early without executing."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=True)
        exe._execute_step = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        exe._execute_step.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_multi_step_group_calls_parallel_group(self, mock_build, mock_find):
        """Multi-step group dispatches to _execute_parallel_group."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1", "s2"]
        mock_find.return_value = [group]

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_parallel_group = MagicMock()

        s1 = _make_step(step_id="s1", step_type="shell")
        s2 = _make_step(step_id="s2", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[s1, s2],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        exe._execute_parallel_group.assert_called_once()
        call_args = exe._execute_parallel_group.call_args[0]
        assert len(call_args[0]) == 2  # 2 steps
        assert call_args[1] == "wf-1"  # workflow_id

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_multi_step_group_failure_aborts(self, mock_build, mock_find):
        """Multi-step group that sets result.status='failed' aborts."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1", "s2"]
        mock_find.return_value = [group]

        def set_failed(steps, wf_id, result, workers):
            result.status = "failed"

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_parallel_group = MagicMock(side_effect=set_failed)

        s1 = _make_step(step_id="s1", step_type="shell")
        s2 = _make_step(step_id="s2", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[s1, s2],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        assert result.status == "failed"

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_failure_skip_no_store(self, mock_build, mock_find):
        """Single step failure with 'skip' does NOT call _store_step_outputs."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="oops")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="skip")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        # "skip" means no output storage
        exe._store_step_outputs.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_failure_continue_stores(self, mock_build, mock_find):
        """Single step failure with non-skip/non-abort stores outputs."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="non-fatal")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 0, "wf-1", result)

        # "continue" stores outputs
        exe._store_step_outputs.assert_called_once()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_start_index_slices_steps(self, mock_build, mock_find):
        """start_index > 0 skips earlier steps."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s3"]
        mock_find.return_value = [group]

        success_result = StepResult(step_id="s3", status=StepStatus.SUCCESS)

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        steps = [
            _make_step(step_id="s1", step_type="shell"),
            _make_step(step_id="s2", step_type="shell"),
            _make_step(step_id="s3", step_type="shell"),
        ]
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=steps,
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        exe._execute_with_auto_parallel(wf, 2, "wf-1", result)

        # build_dependency_graph called with only the sliced steps
        call_args = mock_build.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].id == "s3"


# -------------------------------------------------------------------
# _execute_with_auto_parallel_async
# -------------------------------------------------------------------


class TestExecuteWithAutoParallelAsync:
    """_execute_with_auto_parallel_async: async orchestration."""

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_empty_steps_sets_success(self, mock_build, mock_find):
        exe = _bare_executor()
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        assert result.status == "success"

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_async_success(self, mock_build, mock_find):
        """Single-step group uses _execute_step_async."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS)

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step_async = AsyncMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock()
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        assert result.status == "success"

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_async_failure_abort(self, mock_build, mock_find):
        """Failed async single step with abort returns early."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="boom")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="abort")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        assert result.status != "success"

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_multi_step_async_dispatches(self, mock_build, mock_find):
        """Multi-step async group dispatches to _execute_parallel_group_async."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1", "s2"]
        mock_find.return_value = [group]

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_parallel_group_async = AsyncMock()

        s1 = _make_step(step_id="s1", step_type="shell")
        s2 = _make_step(step_id="s2", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[s1, s2],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        exe._execute_parallel_group_async.assert_called_once()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_budget_exceeded_async_returns_early(self, mock_build, mock_find):
        """Budget exceeded returns early without executing async."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=True)
        exe._execute_step_async = AsyncMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        exe._execute_step_async.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_multi_step_async_failure_aborts(self, mock_build, mock_find):
        """Multi-step async group failure aborts remaining groups."""
        mock_build.return_value = MagicMock()
        group1 = MagicMock()
        group1.step_ids = ["s1", "s2"]
        group2 = MagicMock()
        group2.step_ids = ["s3"]
        mock_find.return_value = [group1, group2]

        async def fail_group(steps, wf_id, result, workers):
            result.status = "failed"

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_parallel_group_async = AsyncMock(side_effect=fail_group)

        s1 = _make_step(step_id="s1", step_type="shell")
        s2 = _make_step(step_id="s2", step_type="shell")
        s3 = _make_step(step_id="s3", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[s1, s2, s3],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        assert result.status == "failed"
        # Only first group executed
        assert exe._execute_parallel_group_async.call_count == 1

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_async_failure_skip(self, mock_build, mock_find):
        """Single step async failure with 'skip' does not store outputs."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="oops")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="skip")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        exe._store_step_outputs.assert_not_called()

    @patch("animus_kernel.executor.executor_parallel_exec.find_parallel_groups")
    @patch("animus_kernel.executor.executor_parallel_exec.build_dependency_graph")
    def test_single_step_async_failure_continue_stores(self, mock_build, mock_find):
        """Single step async failure with 'continue' stores outputs (line 301)."""
        mock_build.return_value = MagicMock()
        group = MagicMock()
        group.step_ids = ["s1"]
        mock_find.return_value = [group]

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="non-fatal")

        exe = _bare_executor()
        exe._check_budget_exceeded = MagicMock(return_value=False)
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        step = _make_step(step_id="s1", step_type="shell")
        wf = WorkflowConfig(
            name="test",
            version="1",
            description="",
            steps=[step],
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
        )
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_with_auto_parallel_async(wf, 0, "wf-1", result))

        # "continue" should store outputs (covers line 301)
        exe._store_step_outputs.assert_called_once()


# -------------------------------------------------------------------
# _execute_parallel_group handler closure — lines 171-184
# -------------------------------------------------------------------


class TestParallelGroupHandlerClosure:
    """Exercise the inner handler() closure inside _execute_parallel_group
    to cover tracker.start_branch, complete_branch, fail_branch paths."""

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_handler_success_calls_complete_branch(self, MockPE, mock_tracker):
        """Successful handler calls tracker.complete_branch."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS, tokens_used=42)

        def capture_and_run(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                try:
                    result = task.handler(**task.kwargs)
                    on_complete(task.id, result)
                except Exception as e:
                    on_error(task.id, e)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = capture_and_run
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.start_branch.assert_called_once()
        tracker.complete_branch.assert_called_once()
        call_args = tracker.complete_branch.call_args[0]
        assert call_args[2] == 42  # tokens

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_handler_failed_step_calls_fail_branch(self, MockPE, mock_tracker):
        """Failed step result calls tracker.fail_branch."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        failed_result = StepResult(step_id="s1", status=StepStatus.FAILED, error="step failed")

        def capture_and_run(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                try:
                    result = task.handler(**task.kwargs)
                    on_complete(task.id, result)
                except Exception as e:
                    on_error(task.id, e)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = capture_and_run
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.fail_branch.assert_called_once()
        fail_args = tracker.fail_branch.call_args[0]
        assert fail_args[1] == "s1"
        assert "step failed" in fail_args[2]

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_handler_exception_calls_fail_branch_and_raises(self, MockPE, mock_tracker):
        """Exception in handler calls tracker.fail_branch then re-raises."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        def capture_and_run(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                try:
                    task.handler(**task.kwargs)
                    on_complete(
                        task.id,
                        StepResult(step_id=task.id, status=StepStatus.SUCCESS),
                    )
                except Exception as e:
                    on_error(task.id, e)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = capture_and_run
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(side_effect=RuntimeError("exploded"))
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.fail_branch.assert_called_once()
        fail_args = tracker.fail_branch.call_args[0]
        assert "exploded" in fail_args[2]

    @patch("animus_kernel.executor.executor_parallel_exec.get_parallel_tracker")
    @patch("animus_kernel.executor.executor_parallel_exec.ParallelExecutor")
    def test_handler_none_result_zero_tokens(self, MockPE, mock_tracker):
        """Handler returning result with tokens_used=0 still works."""
        tracker = MagicMock()
        mock_tracker.return_value = tracker

        success_result = StepResult(step_id="s1", status=StepStatus.SUCCESS, tokens_used=0)

        def capture_and_run(tasks, on_complete, on_error, fail_fast):
            for task in tasks:
                result = task.handler(**task.kwargs)
                on_complete(task.id, result)

        mock_executor = MagicMock()
        mock_executor.execute_parallel.side_effect = capture_and_run
        MockPE.return_value = mock_executor

        exe = _bare_executor()
        exe._execute_step = MagicMock(return_value=success_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure = MagicMock()
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell", timeout_seconds=30)]
        result = ExecutionResult(workflow_name="test")

        exe._execute_parallel_group(steps, "wf-1", result, max_workers=2)

        tracker.complete_branch.assert_called_once()
        call_args = tracker.complete_branch.call_args[0]
        assert call_args[2] == 0  # zero tokens


# -------------------------------------------------------------------
# _execute_parallel_group_async — failure continue stores outputs (line 301)
# -------------------------------------------------------------------


class TestAsyncParallelGroupContinueStores:
    """Covers line 301: failed step with non-skip/non-abort stores outputs
    in the async parallel group."""

    def test_async_parallel_failed_step_continue_stores(self):
        """Failed step with 'continue' action stores outputs in async group."""
        failed_result = StepResult(
            step_id="s1",
            status=StepStatus.FAILED,
            error="non-fatal",
            output={"partial": "data"},
        )

        exe = _bare_executor()
        exe._execute_step_async = AsyncMock(return_value=failed_result)
        exe._record_step_completion = MagicMock()
        exe._handle_step_failure_async = AsyncMock(return_value="continue")
        exe._store_step_outputs = MagicMock()

        steps = [_make_step(step_id="s1", step_type="shell")]
        result = ExecutionResult(workflow_name="test")

        asyncio.run(exe._execute_parallel_group_async(steps, "wf-1", result, max_workers=2))

        # "continue" should store outputs (line 301)
        exe._store_step_outputs.assert_called_once()
        # Should NOT set abort
        assert result.status != "failed"
