"""Tests for MCP tool workflow executor (animus_forge.workflow.executor_mcp)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.executor_core import WorkflowExecutor
from animus_forge.workflow.loader import VALID_STEP_TYPES, StepConfig, WorkflowConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def executor():
    """Create a WorkflowExecutor in dry-run mode."""
    return WorkflowExecutor(dry_run=True)


@pytest.fixture
def live_executor():
    """Create a WorkflowExecutor with dry_run=False."""
    return WorkflowExecutor(dry_run=False)


def _make_step(params: dict, step_id: str = "mcp_step") -> StepConfig:
    """Helper to build an mcp_tool StepConfig."""
    return StepConfig(id=step_id, type="mcp_tool", params=params)


def _make_server(**overrides) -> MagicMock:
    """Helper to build a mock MCPServer."""
    server = MagicMock()
    server.name = overrides.get("name", "test-server")
    server.url = overrides.get("url", "https://example.com/mcp")
    server.type = overrides.get("type", "sse")
    server.authType = overrides.get("authType", "none")
    server.credentialId = overrides.get("credentialId", None)
    return server


# ---------------------------------------------------------------------------
# Loader validation
# ---------------------------------------------------------------------------


class TestMCPToolValidation:
    """Ensure mcp_tool is accepted by the loader."""

    def test_mcp_tool_in_valid_step_types(self):
        assert "mcp_tool" in VALID_STEP_TYPES

    def test_step_config_accepts_mcp_tool(self):
        step = StepConfig(
            id="t1",
            type="mcp_tool",
            params={"server": "fs", "tool": "read_file", "arguments": {"path": "/x"}},
        )
        assert step.type == "mcp_tool"

    def test_workflow_config_with_mcp_tool(self):
        wf = WorkflowConfig.from_dict(
            {
                "name": "MCP Test",
                "steps": [
                    {
                        "id": "s1",
                        "type": "mcp_tool",
                        "params": {
                            "server": "fs",
                            "tool": "read_file",
                            "arguments": {"path": "/tmp"},
                        },
                    }
                ],
            }
        )
        assert wf.steps[0].type == "mcp_tool"


# ---------------------------------------------------------------------------
# Dry-run behaviour
# ---------------------------------------------------------------------------


class TestMCPToolDryRun:
    """Dry-run should return simulated output without network calls."""

    def test_basic_dry_run(self, executor):
        step = _make_step(
            {"server": "filesystem", "tool": "read_file", "arguments": {"path": "/tmp"}}
        )
        result = executor._execute_mcp_tool(step, {})
        assert result["dry_run"] is True
        assert result["tokens_used"] == 0
        assert "filesystem" in result["response"]
        assert "read_file" in result["response"]
        assert result["server"] == "filesystem"
        assert result["tool"] == "read_file"

    def test_dry_run_with_variable_substitution(self, executor):
        step = _make_step(
            {
                "server": "fs",
                "tool": "read_file",
                "arguments": {"path": "${project_path}/README.md"},
            }
        )
        ctx = {"project_path": "/home/user/project"}
        result = executor._execute_mcp_tool(step, ctx)
        assert "/home/user/project/README.md" in result["response"]


# ---------------------------------------------------------------------------
# Variable substitution
# ---------------------------------------------------------------------------


class TestMCPToolVariableSubstitution:
    """Test recursive ${var} substitution in arguments."""

    def test_string_substitution(self, executor):
        result = executor._substitute_mcp_arguments(
            {"path": "${dir}/file.txt"},
            {"dir": "/opt"},
        )
        assert result == {"path": "/opt/file.txt"}

    def test_nested_dict_substitution(self, executor):
        result = executor._substitute_mcp_arguments(
            {"outer": {"inner": "${val}"}},
            {"val": "replaced"},
        )
        assert result == {"outer": {"inner": "replaced"}}

    def test_list_substitution(self, executor):
        result = executor._substitute_mcp_arguments(
            ["${a}", "${b}", "literal"],
            {"a": "x", "b": "y"},
        )
        assert result == ["x", "y", "literal"]

    def test_non_string_passthrough(self, executor):
        """Non-string scalars should pass through unchanged."""
        result = executor._substitute_mcp_arguments(
            {"count": 42, "flag": True, "nothing": None},
            {"count": "ignored"},
        )
        assert result == {"count": 42, "flag": True, "nothing": None}

    def test_server_and_tool_substitution(self, executor):
        step = _make_step({"server": "${srv}", "tool": "${tl}", "arguments": {}})
        ctx = {"srv": "github", "tl": "list_repos"}
        result = executor._execute_mcp_tool(step, ctx)
        assert result["server"] == "github"
        assert result["tool"] == "list_repos"


# ---------------------------------------------------------------------------
# Missing params
# ---------------------------------------------------------------------------


class TestMCPToolMissingParams:
    """Missing required params should raise RuntimeError."""

    def test_missing_server(self, executor):
        step = _make_step({"tool": "read_file"})
        with pytest.raises(RuntimeError, match="missing required param 'server'"):
            executor._execute_mcp_tool(step, {})

    def test_missing_tool(self, executor):
        step = _make_step({"server": "fs"})
        with pytest.raises(RuntimeError, match="missing required param 'tool'"):
            executor._execute_mcp_tool(step, {})


# ---------------------------------------------------------------------------
# Server resolution
# ---------------------------------------------------------------------------


class TestMCPToolServerResolution:
    """Test _resolve_mcp_server by ID and by name."""

    def test_resolve_by_uuid(self, live_executor):
        server = _make_server(name="resolved")
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = server

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                result = live_executor._resolve_mcp_server("12345678-1234-1234-1234-123456789abc")
                assert result.name == "resolved"
                mock_manager.get_server.assert_called_once_with(
                    "12345678-1234-1234-1234-123456789abc"
                )

    def test_resolve_by_name(self, live_executor):
        server = _make_server(name="filesystem")
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None
        mock_manager.get_server_by_name.return_value = server

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                result = live_executor._resolve_mcp_server("filesystem")
                assert result.name == "filesystem"
                mock_manager.get_server_by_name.assert_called_once_with("filesystem")

    def test_resolve_not_found(self, live_executor):
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None
        mock_manager.get_server_by_name.return_value = None

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                with pytest.raises(RuntimeError, match="MCP server not found"):
                    live_executor._resolve_mcp_server("nonexistent")

    def test_resolve_name_fallback_after_uuid_miss(self, live_executor):
        """UUID-format ref that doesn't match by ID should still try by name."""
        server = _make_server(name="my-uuid-named-server")
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None
        mock_manager.get_server_by_name.return_value = server

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                result = live_executor._resolve_mcp_server("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
                assert result.name == "my-uuid-named-server"


# ---------------------------------------------------------------------------
# Credential / auth header injection
# ---------------------------------------------------------------------------


class TestMCPToolCredentialInjection:
    """Test _get_mcp_auth_headers for different auth types."""

    def test_no_auth(self, live_executor):
        server = _make_server(authType="none", credentialId=None)
        headers = live_executor._get_mcp_auth_headers(server)
        assert headers is None

    def test_bearer_auth(self, live_executor):
        server = _make_server(authType="bearer", credentialId="cred-1")
        mock_manager = MagicMock()
        mock_manager.get_credential_value.return_value = "my-token"

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                headers = live_executor._get_mcp_auth_headers(server)
                assert headers == {"Authorization": "Bearer my-token"}

    def test_api_key_auth(self, live_executor):
        server = _make_server(authType="api_key", credentialId="cred-2")
        mock_manager = MagicMock()
        mock_manager.get_credential_value.return_value = "secret-key"

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                headers = live_executor._get_mcp_auth_headers(server)
                assert headers == {"X-API-Key": "secret-key"}

    def test_missing_credential_value(self, live_executor):
        server = _make_server(authType="bearer", credentialId="cred-gone")
        mock_manager = MagicMock()
        mock_manager.get_credential_value.return_value = None

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                headers = live_executor._get_mcp_auth_headers(server)
                assert headers is None

    def test_unsupported_auth_type(self, live_executor):
        server = _make_server(authType="oauth", credentialId="cred-3")
        mock_manager = MagicMock()
        mock_manager.get_credential_value.return_value = "token"

        with patch("animus_forge.state.database.get_database"):
            with patch(
                "animus_forge.mcp.manager.MCPConnectorManager",
                return_value=mock_manager,
            ):
                headers = live_executor._get_mcp_auth_headers(server)
                assert headers is None


# ---------------------------------------------------------------------------
# Live execution (mocked call_mcp_tool)
# ---------------------------------------------------------------------------


class TestMCPToolExecution:
    """Test live execution path with mocked MCP client."""

    def _run_step(self, executor, server, tool_result, arguments=None):
        """Helper: execute an mcp_tool step with mocked resolution + client."""
        step = _make_step(
            {
                "server": "test-server",
                "tool": "my_tool",
                "arguments": arguments or {"key": "val"},
            }
        )
        with patch.object(executor, "_resolve_mcp_server", return_value=server):
            with patch.object(executor, "_get_mcp_auth_headers", return_value=None):
                with patch(
                    "animus_forge.mcp.client.call_mcp_tool",
                    return_value=tool_result,
                ):
                    return executor._execute_mcp_tool(step, {})

    def test_success(self, live_executor):
        server = _make_server()
        result = self._run_step(
            live_executor, server, {"content": "file contents", "is_error": False}
        )
        assert result["response"] == "file contents"
        assert result["server"] == "test-server"
        assert result["tool"] == "my_tool"
        assert result["tokens_used"] == 0

    def test_tool_error(self, live_executor):
        server = _make_server()
        with pytest.raises(RuntimeError, match="returned error"):
            self._run_step(live_executor, server, {"content": "not found", "is_error": True})

    def test_sdk_missing_raises(self, live_executor):
        """When SDK is not installed, should raise MCPClientError."""
        from animus_forge.mcp.client import MCPClientError

        step = _make_step({"server": "srv", "tool": "tool", "arguments": {}})
        server = _make_server()
        with patch.object(live_executor, "_resolve_mcp_server", return_value=server):
            with patch.object(live_executor, "_get_mcp_auth_headers", return_value=None):
                with patch(
                    "animus_forge.mcp.client.call_mcp_tool",
                    side_effect=MCPClientError("MCP SDK not installed"),
                ):
                    with pytest.raises(MCPClientError, match="MCP SDK not installed"):
                        live_executor._execute_mcp_tool(step, {})

    def test_passes_headers_to_client(self, live_executor):
        """Auth headers should be forwarded to call_mcp_tool."""
        step = _make_step({"server": "srv", "tool": "tool", "arguments": {}})
        server = _make_server()
        auth_headers = {"Authorization": "Bearer tok123"}

        with patch.object(live_executor, "_resolve_mcp_server", return_value=server):
            with patch.object(live_executor, "_get_mcp_auth_headers", return_value=auth_headers):
                with patch(
                    "animus_forge.mcp.client.call_mcp_tool",
                    return_value={"content": "ok", "is_error": False},
                ) as mock_call:
                    live_executor._execute_mcp_tool(step, {})
                    mock_call.assert_called_once()
                    call_kwargs = mock_call.call_args
                    assert call_kwargs.kwargs.get("headers") == auth_headers


# ---------------------------------------------------------------------------
# Full workflow integration (with mocked MCP)
# ---------------------------------------------------------------------------


class TestMCPToolInWorkflow:
    """Test mcp_tool step within full WorkflowExecutor.execute()."""

    def test_workflow_with_mcp_tool(self):
        """A workflow with an mcp_tool step should execute end-to-end."""
        workflow = WorkflowConfig(
            name="MCP Workflow",
            version="1.0",
            description="Tests MCP tool step in workflow",
            steps=[
                StepConfig(
                    id="read_files",
                    type="mcp_tool",
                    params={
                        "server": "filesystem",
                        "tool": "read_file",
                        "arguments": {"path": "/tmp/test.txt"},
                    },
                    outputs=["file_content"],
                ),
            ],
            outputs=["file_content"],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)
        assert result.status == "success"
        assert len(result.steps) == 1
        assert result.steps[0].output.get("dry_run") is True
        # Output mapping: 'response' maps to first custom output
        assert "file_content" in result.outputs

    def test_workflow_mcp_tool_chained(self):
        """MCP tool output should be available to subsequent steps."""
        workflow = WorkflowConfig(
            name="Chained MCP",
            version="1.0",
            description="Chain MCP output to shell",
            steps=[
                StepConfig(
                    id="fetch",
                    type="mcp_tool",
                    params={
                        "server": "fs",
                        "tool": "read_file",
                        "arguments": {"path": "/tmp/x"},
                    },
                    outputs=["file_data"],
                ),
                StepConfig(
                    id="echo",
                    type="shell",
                    params={"command": "echo done"},
                    outputs=["echo_out"],
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)
        assert result.status == "success"
        assert len(result.steps) == 2

    def test_handler_registered(self):
        """mcp_tool handler should be in the executor's _handlers dict."""
        executor = WorkflowExecutor()
        assert "mcp_tool" in executor._handlers


def test_public_executor_imports_use_forge_mcp_adapter():
    from animus_forge.workflow import WorkflowExecutor as PackageExecutor
    from animus_forge.workflow.executor import WorkflowExecutor as CompatibilityExecutor

    assert PackageExecutor is WorkflowExecutor
    assert CompatibilityExecutor is WorkflowExecutor


def test_standalone_kernel_requires_explicit_mcp_adapter():
    from animus_kernel.executor.executor_core import WorkflowExecutor as KernelExecutor

    executor = KernelExecutor(dry_run=False)
    with pytest.raises(RuntimeError, match="registry is not configured"):
        executor._resolve_mcp_server("test")
    with pytest.raises(RuntimeError, match="transport is not configured"):
        executor._call_mcp_tool()
