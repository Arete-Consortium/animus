"""Integration step handlers for workflow execution.

Mixin class providing handlers for external service integrations:
shell, github, notion, gmail, slack, calendar, browser.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import tempfile
from datetime import UTC
from pathlib import Path

from .loader import StepConfig

logger = logging.getLogger(__name__)


class IntegrationHandlersMixin:
    """Mixin providing external service integration handlers.

    Expects the following attributes from the host class:
    - dry_run: bool
    - _context: dict
    - fallback_callbacks: dict
    """

    dry_run: bool

    def _integration_dependency(self, module: str, name: str):
        """Resolve an application-owned integration dependency."""
        raise RuntimeError(f"Integration {module}.{name} requires an application adapter")

    def _integration_settings(self):
        from animus_kernel.config import get_settings

        return get_settings()

    def _get_var_dir(self, step: StepConfig) -> Path:
        """Per-execution temp directory for ${name.file} payloads.

        Lazily created on first shell-step substitution. Reused
        across all shell steps in the same executor instance so
        downstream steps can find the files written upstream.
        Survives the workflow run for debugging; cleanup is the
        caller's responsibility (typically not needed since temp
        files are short-lived OS-managed paths).
        """
        existing = getattr(self, "_shell_var_dir", None)
        if existing is not None:
            return existing
        prefix = f"forge-vars-{step.id or 'workflow'}-"
        var_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self._shell_var_dir = var_dir  # type: ignore[attr-defined]
        return var_dir

    def _execute_shell(self, step: StepConfig, context: dict) -> dict:
        """Execute a shell command step with resource limits.

        Security: Variables are escaped using shlex.quote to prevent injection.
        Set allow_dangerous=True in params to skip dangerous pattern checks.
        Set escape_variables=False to disable escaping (use with extreme caution).

        Resource limits (configurable via settings):
        - Timeout: SHELL_TIMEOUT_SECONDS (default: 300s / 5 minutes)
        - Output size: SHELL_MAX_OUTPUT_BYTES (default: 10MB)
        - Command whitelist: SHELL_ALLOWED_COMMANDS (optional)
        """
        from animus_kernel.utils.validation import (
            substitute_shell_variables,
            validate_shell_command,
        )

        settings = self._integration_settings()
        command = step.params.get("command", "")
        if not command:
            raise ValueError("Shell step requires 'command' parameter")

        # Check command whitelist if configured
        if settings.shell_allowed_commands:
            allowed = [c.strip() for c in settings.shell_allowed_commands.split(",")]
            # Extract the base command (first word before space or pipe)
            base_cmd = command.split()[0].split("/")[-1] if command.split() else ""
            if base_cmd not in allowed:
                raise ValueError(
                    f"Command '{base_cmd}' not in allowed list. "
                    f"Allowed commands: {', '.join(allowed)}"
                )

        # Validate command template (before substitution)
        allow_dangerous = step.params.get("allow_dangerous", False)
        validate_shell_command(command, allow_dangerous=allow_dangerous)

        # Safely substitute context variables with shell escaping.
        # ``var_dir`` enables ${name.file} substitution (issue #38)
        # by writing values to disk and substituting paths instead
        # of inline strings — required for multi-KB LLM outputs that
        # would otherwise break shell parsing on heredocs/quotes.
        escape_variables = step.params.get("escape_variables", True)
        var_dir = self._get_var_dir(step)
        command = substitute_shell_variables(
            command, context, escape=escape_variables, var_dir=var_dir
        )

        # Determine timeout: use step timeout if set, otherwise use global setting
        timeout = step.timeout_seconds or settings.shell_timeout_seconds

        # SEC-03: workflow shell steps must run with shell=False.  Template
        # substitution can still produce a shell-like string, so we tokenize it
        # with shlex.split and pass an argv list.  Shell operators (pipes,
        # redirects, command chaining) in templates are rejected below because
        # they cannot be expressed safely with shell=False; this is a known
        # security-vs-flexibility trade-off.
        _SHELL_INJECTION_CHARS: frozenset[str] = frozenset(";&|`$<>\\\n\r")
        _INTERPRETER_COMMANDS: frozenset[str] = frozenset(
            {"python", "python3", "node", "nodejs", "ruby", "perl", "php"}
        )
        _INTERPRETER_CODE_FLAGS: frozenset[str] = frozenset({"-c", "--command", "-e", "--eval"})

        if any(ch in command for ch in _SHELL_INJECTION_CHARS):
            raise ValueError(
                "Substituted shell command contains forbidden shell metacharacters; "
                "workflow shell steps do not support pipes, redirects, or command chaining"
            )

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ValueError(f"Invalid shell command syntax after substitution: {exc}") from exc

        if not argv:
            raise ValueError("Shell command parsed to empty argument list")

        raw_base = argv[0]
        if "/" in raw_base or "\\" in raw_base or raw_base.startswith(".."):
            raise ValueError(f"Shell command must use a bare command name, not a path: {raw_base}")

        base_cmd = Path(raw_base).name
        if settings.shell_allowed_commands:
            allowed = [c.strip() for c in settings.shell_allowed_commands.split(",")]
            if base_cmd not in allowed:
                raise ValueError(
                    f"Command '{base_cmd}' not in allowed list. "
                    f"Allowed commands: {', '.join(allowed)}"
                )

        if base_cmd in _INTERPRETER_COMMANDS:
            if any(flag in argv for flag in _INTERPRETER_CODE_FLAGS):
                raise ValueError(
                    f"Command '{base_cmd}' code-execution flag is not allowed in shell steps"
                )

        logger.debug(
            "Executing shell command (timeout=%ds): %s",
            timeout,
            command[:200],
        )

        working_directory = step.params.get("working_directory")
        if working_directory is not None:
            if not isinstance(working_directory, str):
                raise ValueError("working_directory must be a string")
            for key, value in context.items():
                if isinstance(value, (str, Path)):
                    working_directory = working_directory.replace(f"${{{key}}}", str(value))
            working_directory = Path(working_directory).expanduser().resolve(strict=True)
            if not working_directory.is_dir():
                raise ValueError("working_directory must name a directory")

        try:
            result = subprocess.run(
                argv,
                shell=False,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Command timed out after {timeout} seconds. "
                f"Partial stdout: {e.stdout[:500] if e.stdout else 'None'}... "
                f"Partial stderr: {e.stderr[:500] if e.stderr else 'None'}..."
            )

        # Check output size limits
        max_output = settings.shell_max_output_bytes
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if len(stdout.encode()) > max_output:
            logger.warning(
                "Shell stdout truncated from %d to %d bytes",
                len(stdout.encode()),
                max_output,
            )
            stdout = stdout[:max_output] + "\n... [OUTPUT TRUNCATED]"

        if len(stderr.encode()) > max_output:
            logger.warning(
                "Shell stderr truncated from %d to %d bytes",
                len(stderr.encode()),
                max_output,
            )
            stderr = stderr[:max_output] + "\n... [OUTPUT TRUNCATED]"

        if result.returncode != 0 and not step.params.get("allow_failure", False):
            raise RuntimeError(f"Command failed with code {result.returncode}: {stderr[:1000]}")

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
        }

    def _execute_checkpoint(self, step: StepConfig, context: dict) -> dict:
        """Create a checkpoint (no-op if no checkpoint manager)."""
        return {"checkpoint": step.id}

    def _execute_github(self, step: StepConfig, context: dict) -> dict:
        """Execute a GitHub step.

        Params:
            action: GitHub action (create_issue, commit_file, list_repos, get_repo_info)
            repo: Repository name (owner/repo format)
            title: Issue title (for create_issue)
            body: Issue body or file content
            labels: Issue labels (optional list)
            file_path: File path for commit_file
            message: Commit message for commit_file
            branch: Branch name (default: main)
        """
        if not self.dry_run:
            GitHubClient = self._integration_dependency("api_clients", "GitHubClient")

        action = step.params.get("action", "get_repo_info")
        repo = step.params.get("repo", "")

        # Substitute context variables
        for key, value in context.items():
            if isinstance(value, str):
                repo = repo.replace(f"${{{key}}}", value)

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "repo": repo,
                "result": f"[DRY RUN] GitHub {action} on {repo}",
                "dry_run": True,
            }

        client = GitHubClient()
        if not client.is_configured():
            raise RuntimeError("GitHub client not configured. Check GITHUB_TOKEN.")

        if action == "create_issue":
            if os.environ.get("ANIMUS_ALLOW_AUTONOMOUS_ISSUES") != "1":
                raise RuntimeError(
                    "Autonomous gh issue create is blocked. "
                    "Set ANIMUS_ALLOW_AUTONOMOUS_ISSUES=1 to enable, or route "
                    "issue filing through send_approval for human-in-the-loop."
                )
            title = step.params.get("title", "")
            body = step.params.get("body", "")
            labels = step.params.get("labels", [])

            for key, value in context.items():
                if isinstance(value, str):
                    title = title.replace(f"${{{key}}}", value)
                    body = body.replace(f"${{{key}}}", value)

            result = client.create_issue(repo, title, body, labels)
            return {
                "action": action,
                "repo": repo,
                "result": result,
                "issue_number": result.get("number") if result else None,
                "issue_url": result.get("url") if result else None,
            }

        elif action == "commit_file":
            file_path = step.params.get("file_path", "")
            content = step.params.get("body", "")
            message = step.params.get("message", "Update file via Animus Kernel")
            branch = step.params.get("branch", "main")

            for key, value in context.items():
                if isinstance(value, str):
                    file_path = file_path.replace(f"${{{key}}}", value)
                    content = content.replace(f"${{{key}}}", value)
                    message = message.replace(f"${{{key}}}", value)

            result = client.commit_file(repo, file_path, content, message, branch)
            return {
                "action": action,
                "repo": repo,
                "file_path": file_path,
                "result": result,
                "commit_sha": result.get("commit_sha") if result else None,
            }

        elif action == "list_repos":
            result = client.list_repositories()
            return {
                "action": action,
                "result": result,
                "count": len(result),
            }

        elif action == "get_repo_info":
            result = client.get_repo_info(repo)
            return {
                "action": action,
                "repo": repo,
                "result": result,
            }

        else:
            raise ValueError(f"Unknown GitHub action: {action}")

    def _execute_notion(self, step: StepConfig, context: dict) -> dict:
        """Execute a Notion step.

        Params:
            action: Notion action (query_database, create_page, get_page,
                    update_page, search, read_content, append)
            database_id: Database ID (for query/create)
            page_id: Page ID (for get/update/read/append)
            parent_id: Parent database ID (for create_page)
            title: Page title
            content: Page content
            properties: Page properties dict
            filter: Query filter dict
            sorts: Query sorts list
            query: Search query string
        """
        if not self.dry_run:
            NotionClientWrapper = self._integration_dependency("api_clients", "NotionClientWrapper")

        action = step.params.get("action", "search")

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "result": f"[DRY RUN] Notion {action}",
                "dry_run": True,
            }

        client = NotionClientWrapper()
        if not client.is_configured():
            raise RuntimeError("Notion client not configured. Check NOTION_TOKEN.")

        if action == "query_database":
            database_id = step.params.get("database_id", "")
            filter_param = step.params.get("filter")
            sorts = step.params.get("sorts")
            page_size = step.params.get("page_size", 100)

            result = client.query_database(database_id, filter_param, sorts, page_size)
            return {
                "action": action,
                "database_id": database_id,
                "result": result,
                "count": len(result),
            }

        elif action == "create_page":
            parent_id = step.params.get("parent_id", "")
            title = step.params.get("title", "")
            content = step.params.get("content", "")

            for key, value in context.items():
                if isinstance(value, str):
                    title = title.replace(f"${{{key}}}", value)
                    content = content.replace(f"${{{key}}}", value)

            result = client.create_page(parent_id, title, content)
            return {
                "action": action,
                "result": result,
                "page_id": result.get("id") if result else None,
                "page_url": result.get("url") if result else None,
            }

        elif action == "get_page":
            page_id = step.params.get("page_id", "")
            result = client.get_page(page_id)
            return {
                "action": action,
                "page_id": page_id,
                "result": result,
            }

        elif action == "update_page":
            page_id = step.params.get("page_id", "")
            properties = step.params.get("properties", {})
            result = client.update_page(page_id, properties)
            return {
                "action": action,
                "page_id": page_id,
                "result": result,
            }

        elif action == "read_content":
            page_id = step.params.get("page_id", "")
            result = client.read_page_content(page_id)
            return {
                "action": action,
                "page_id": page_id,
                "result": result,
                "blocks": len(result),
            }

        elif action == "append":
            page_id = step.params.get("page_id", "")
            content = step.params.get("content", "")

            for key, value in context.items():
                if isinstance(value, str):
                    content = content.replace(f"${{{key}}}", value)

            result = client.append_to_page(page_id, content)
            return {
                "action": action,
                "page_id": page_id,
                "result": result,
            }

        elif action == "search":
            query = step.params.get("query", "")

            for key, value in context.items():
                if isinstance(value, str):
                    query = query.replace(f"${{{key}}}", value)

            result = client.search_pages(query)
            return {
                "action": action,
                "query": query,
                "result": result,
                "count": len(result),
            }

        else:
            raise ValueError(f"Unknown Notion action: {action}")

    def _execute_gmail(self, step: StepConfig, context: dict) -> dict:
        """Execute a Gmail step.

        Params:
            action: Gmail action (list_messages, get_message)
            max_results: Maximum messages to return (default: 10)
            query: Gmail search query
            message_id: Message ID for get_message
        """
        if not self.dry_run:
            GmailClient = self._integration_dependency("api_clients", "GmailClient")

        action = step.params.get("action", "list_messages")

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "result": f"[DRY RUN] Gmail {action}",
                "dry_run": True,
            }

        client = GmailClient()
        if not client.is_configured():
            raise RuntimeError("Gmail client not configured. Check credentials.")

        if not client.authenticate():
            raise RuntimeError("Gmail authentication failed.")

        if action == "list_messages":
            max_results = step.params.get("max_results", 10)
            query = step.params.get("query")

            for key, value in context.items():
                if isinstance(value, str) and query:
                    query = query.replace(f"${{{key}}}", value)

            result = client.list_messages(max_results, query)
            return {
                "action": action,
                "result": result,
                "count": len(result),
            }

        elif action == "get_message":
            message_id = step.params.get("message_id", "")
            result = client.get_message(message_id)

            # Extract body if available
            body = ""
            if result:
                body = client.extract_email_body(result)

            return {
                "action": action,
                "message_id": message_id,
                "result": result,
                "body": body,
            }

        else:
            raise ValueError(f"Unknown Gmail action: {action}")

    def _execute_slack(self, step: StepConfig, context: dict) -> dict:
        """Execute a Slack step.

        Params:
            action: Slack action (send_message, send_notification,
                    send_approval, update_message, add_reaction)
            channel: Slack channel ID or name
            text: Message text
            message_type: Message type (info, success, warning, error)
            workflow_name: Workflow name for notifications
            status: Workflow status for notifications
            title: Approval request title
            description: Approval request description
            ts: Message timestamp for updates/reactions
            emoji: Emoji name for reactions
        """
        if not self.dry_run:
            MessageType = self._integration_dependency("api_clients.slack_client", "MessageType")
            SlackClient = self._integration_dependency("api_clients.slack_client", "SlackClient")

        action = step.params.get("action", "send_message")
        channel = step.params.get("channel", "")

        # Substitute context variables
        for key, value in context.items():
            if isinstance(value, str):
                channel = channel.replace(f"${{{key}}}", value)

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "channel": channel,
                "result": f"[DRY RUN] Slack {action} to {channel}",
                "dry_run": True,
            }

        # Get Slack token from settings
        settings = self._integration_settings()
        token = settings.slack_token if hasattr(settings, "slack_token") else None

        if not token:
            raise RuntimeError("Slack client not configured. Check SLACK_TOKEN.")

        client = SlackClient(token)
        if not client.is_configured():
            raise RuntimeError("Slack client initialization failed.")

        if action == "send_message":
            text = step.params.get("text", "")
            msg_type = step.params.get("message_type", "info")
            thread_ts = step.params.get("thread_ts")

            for key, value in context.items():
                if isinstance(value, str):
                    text = text.replace(f"${{{key}}}", value)

            message_type = MessageType(msg_type)
            result = client.send_message(channel, text, message_type, thread_ts=thread_ts)
            return {
                "action": action,
                "channel": channel,
                "result": result,
                "success": result.get("success", False),
                "ts": result.get("ts"),
            }

        elif action == "send_notification":
            workflow_name = step.params.get("workflow_name", "")
            status = step.params.get("status", "started")
            details = step.params.get("details")
            thread_ts = step.params.get("thread_ts")

            result = client.send_workflow_notification(
                channel, workflow_name, status, details, thread_ts
            )
            return {
                "action": action,
                "channel": channel,
                "result": result,
                "success": result.get("success", False),
            }

        elif action == "send_approval":
            title = step.params.get("title", "")
            description = step.params.get("description", "")
            requester = step.params.get("requester")
            callback_id = step.params.get("callback_id")
            details = step.params.get("details")

            for key, value in context.items():
                if isinstance(value, str):
                    title = title.replace(f"${{{key}}}", value)
                    description = description.replace(f"${{{key}}}", value)

            result = client.send_approval_request(
                channel, title, description, requester, callback_id, details
            )
            return {
                "action": action,
                "channel": channel,
                "result": result,
                "success": result.get("success", False),
                "ts": result.get("ts"),
            }

        elif action == "update_message":
            ts = step.params.get("ts", "")
            text = step.params.get("text", "")

            for key, value in context.items():
                if isinstance(value, str):
                    text = text.replace(f"${{{key}}}", value)

            result = client.update_message(channel, ts, text)
            return {
                "action": action,
                "channel": channel,
                "ts": ts,
                "result": result,
                "success": result.get("success", False),
            }

        elif action == "add_reaction":
            ts = step.params.get("ts", "")
            emoji = step.params.get("emoji", "thumbsup")

            result = client.add_reaction(channel, ts, emoji)
            return {
                "action": action,
                "channel": channel,
                "ts": ts,
                "emoji": emoji,
                "result": result,
                "success": result.get("success", False),
            }

        else:
            raise ValueError(f"Unknown Slack action: {action}")

    def _execute_calendar(self, step: StepConfig, context: dict) -> dict:
        """Execute a Google Calendar step.

        Params:
            action: Calendar action (list_events, create_event, get_event,
                    delete_event, check_availability, quick_add)
            calendar_id: Calendar ID (default: primary)
            days: Number of days to list (default: 7)
            max_results: Maximum events to return
            summary: Event title
            start: Event start time (ISO format)
            end: Event end time (ISO format)
            location: Event location
            description: Event description
            event_id: Event ID for get/delete
            text: Natural language text for quick_add
        """
        from datetime import datetime, timedelta

        if not self.dry_run:
            CalendarClient = self._integration_dependency(
                "api_clients.calendar_client", "CalendarClient"
            )
            CalendarEvent = self._integration_dependency(
                "api_clients.calendar_client", "CalendarEvent"
            )

        action = step.params.get("action", "list_events")
        calendar_id = step.params.get("calendar_id", "primary")

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "calendar_id": calendar_id,
                "result": f"[DRY RUN] Calendar {action}",
                "dry_run": True,
            }

        client = CalendarClient()
        if not client.authenticate():
            raise RuntimeError("Calendar client authentication failed. Check credentials.")

        if action == "list_events":
            days = step.params.get("days", 7)
            max_results = step.params.get("max_results", 20)

            now = datetime.now(UTC)
            end = now + timedelta(days=days)

            events = client.list_events(
                calendar_id=calendar_id,
                max_results=max_results,
                time_min=now,
                time_max=end,
            )

            # Convert events to dicts
            events_list = [
                {
                    "id": e.id,
                    "summary": e.summary,
                    "start": e.start.isoformat() if e.start else None,
                    "end": e.end.isoformat() if e.end else None,
                    "location": e.location,
                    "all_day": e.all_day,
                }
                for e in events
            ]

            return {
                "action": action,
                "calendar_id": calendar_id,
                "result": events_list,
                "count": len(events_list),
            }

        elif action == "create_event":
            summary = step.params.get("summary", "")
            start_str = step.params.get("start", "")
            end_str = step.params.get("end", "")
            location = step.params.get("location", "")
            description = step.params.get("description", "")
            all_day = step.params.get("all_day", False)

            for key, value in context.items():
                if isinstance(value, str):
                    summary = summary.replace(f"${{{key}}}", value)
                    description = description.replace(f"${{{key}}}", value)

            # Parse dates
            start = datetime.fromisoformat(start_str) if start_str else None
            end = datetime.fromisoformat(end_str) if end_str else None

            event = CalendarEvent(
                summary=summary,
                start=start,
                end=end,
                location=location,
                description=description,
                all_day=all_day,
            )

            result = client.create_event(event, calendar_id)
            return {
                "action": action,
                "calendar_id": calendar_id,
                "result": {
                    "id": result.id if result else None,
                    "summary": result.summary if result else None,
                    "url": result.html_link if result else None,
                },
                "event_id": result.id if result else None,
            }

        elif action == "get_event":
            event_id = step.params.get("event_id", "")
            result = client.get_event(event_id, calendar_id)
            return {
                "action": action,
                "event_id": event_id,
                "result": {
                    "id": result.id,
                    "summary": result.summary,
                    "start": result.start.isoformat() if result and result.start else None,
                    "end": result.end.isoformat() if result and result.end else None,
                    "location": result.location if result else None,
                }
                if result
                else None,
            }

        elif action == "delete_event":
            event_id = step.params.get("event_id", "")
            success = client.delete_event(event_id, calendar_id)
            return {
                "action": action,
                "event_id": event_id,
                "success": success,
            }

        elif action == "check_availability":
            days = step.params.get("days", 1)
            now = datetime.now(UTC)
            end = now + timedelta(days=days)

            busy_periods = client.check_availability(now, end, [calendar_id])
            return {
                "action": action,
                "calendar_id": calendar_id,
                "busy_periods": busy_periods,
                "count": len(busy_periods),
            }

        elif action == "quick_add":
            text = step.params.get("text", "")

            for key, value in context.items():
                if isinstance(value, str):
                    text = text.replace(f"${{{key}}}", value)

            result = client.quick_add(text, calendar_id)
            return {
                "action": action,
                "text": text,
                "result": {
                    "id": result.id if result else None,
                    "summary": result.summary if result else None,
                }
                if result
                else None,
            }

        else:
            raise ValueError(f"Unknown Calendar action: {action}")

    def _execute_browser(self, step: StepConfig, context: dict) -> dict:
        """Execute a browser automation step.

        Params:
            action: Browser action (navigate, click, fill, type, screenshot,
                    extract, scroll, wait)
            url: URL to navigate to
            selector: CSS selector for element actions
            value: Value for fill/type actions
            headless: Run headless (default: True)
            full_page: Full page screenshot (default: False)
        """
        if not self.dry_run:
            BrowserAutomation = self._integration_dependency("browser", "BrowserAutomation")
            BrowserConfig = self._integration_dependency("browser", "BrowserConfig")

        action = step.params.get("action", "navigate")
        url = step.params.get("url", "")
        headless = step.params.get("headless", True)

        # Substitute context variables
        for key, value in context.items():
            if isinstance(value, str):
                url = url.replace(f"${{{key}}}", value)

        # Dry run mode
        if self.dry_run:
            return {
                "action": action,
                "url": url,
                "result": f"[DRY RUN] Browser {action} on {url}",
                "dry_run": True,
            }

        async def run_browser():
            config = BrowserConfig(headless=headless)
            async with BrowserAutomation(config) as browser:
                if action == "navigate":
                    wait_until = step.params.get("wait_until", "load")
                    result = await browser.navigate(url, wait_until)
                    return {
                        "action": action,
                        "url": result.url,
                        "title": result.title,
                        "success": result.success,
                        "error": result.error,
                    }

                elif action == "click":
                    # First navigate if URL provided
                    if url:
                        await browser.navigate(url)
                    selector = step.params.get("selector", "")
                    result = await browser.click(selector)
                    return {
                        "action": action,
                        "selector": selector,
                        "success": result.success,
                        "error": result.error,
                    }

                elif action == "fill":
                    if url:
                        await browser.navigate(url)
                    selector = step.params.get("selector", "")
                    value = step.params.get("value", "")
                    for key, val in context.items():
                        if isinstance(val, str):
                            value = value.replace(f"${{{key}}}", val)
                    result = await browser.fill(selector, value)
                    return {
                        "action": action,
                        "selector": selector,
                        "success": result.success,
                        "error": result.error,
                    }

                elif action == "screenshot":
                    if url:
                        await browser.navigate(url)
                    full_page = step.params.get("full_page", False)
                    path = step.params.get("path")
                    result = await browser.screenshot(path=path, full_page=full_page)
                    return {
                        "action": action,
                        "screenshot_path": result.screenshot_path,
                        "success": result.success,
                        "error": result.error,
                    }

                elif action == "extract":
                    if url:
                        await browser.navigate(url)
                    selector = step.params.get("selector")
                    extract_links = step.params.get("extract_links", True)
                    extract_tables = step.params.get("extract_tables", True)
                    result = await browser.extract_content(selector, extract_links, extract_tables)
                    return {
                        "action": action,
                        "title": result.title,
                        "url": result.url,
                        "data": result.data,
                        "success": result.success,
                        "error": result.error,
                    }

                elif action == "scroll":
                    if url:
                        await browser.navigate(url)
                    direction = step.params.get("direction", "down")
                    amount = step.params.get("amount", 500)
                    result = await browser.scroll(direction, amount)
                    return {
                        "action": action,
                        "direction": direction,
                        "amount": amount,
                        "success": result.success,
                    }

                elif action == "wait":
                    if url:
                        await browser.navigate(url)
                    selector = step.params.get("selector", "")
                    state = step.params.get("state", "visible")
                    timeout = step.params.get("timeout")
                    result = await browser.wait_for_selector(selector, state, timeout)
                    return {
                        "action": action,
                        "selector": selector,
                        "state": state,
                        "success": result.success,
                        "error": result.error,
                    }

                else:
                    raise ValueError(f"Unknown Browser action: {action}")

        return asyncio.run(run_browser())
