"""Tests for the Animus MCP server."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from animus.mcp_server import MCPDeploymentMode
from animus.memory import Memory, MemoryType
from animus.tools import (
    ApprovalGate,
    DenyAllToolPolicy,
    Tool,
    ToolRegistry,
    ToolResult,
    WorkspaceToolPolicy,
    create_default_registry,
)

# Skip all tests if mcp not installed
mcp = pytest.importorskip("mcp")


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _sync_run_coro(coro):
    """Helper to run a coroutine in a new event loop (for nested asyncio.run patches)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _patch_nested_asyncio_run():
    """Patch asyncio.run to handle nested calls from within MCP tool handlers.

    When the test calls _run() (asyncio.run) → MCP tool calls asyncio.run() internally,
    this patches the inner asyncio.run to just await the coroutine in the running loop.
    """
    _original_run = asyncio.run

    def _smart_run(coro, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # We're inside an event loop already — create a task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=30)
        return _original_run(coro, **kwargs)

    return patch("asyncio.run", side_effect=_smart_run)


def _make_memory(content: str, tags: list[str] | None = None) -> Memory:
    from datetime import datetime

    return Memory(
        id="mem-test-001",
        content=content,
        memory_type=MemoryType.SEMANTIC,
        created_at=datetime(2026, 3, 5),
        updated_at=datetime(2026, 3, 5),
        metadata={},
        tags=tags or [],
    )


@pytest.fixture
def mock_config():
    with patch("animus.mcp_server.AnimusConfig") as mock_cls:
        cfg = MagicMock()
        cfg.data_dir = "/tmp/animus-test"
        cfg.memory.backend = "json"
        mock_cls.load.return_value = cfg
        yield cfg


@pytest.fixture
def mock_memory():
    with patch("animus.mcp_server.MemoryLayer") as mock_cls:
        mem = MagicMock()
        mock_cls.return_value = mem
        yield mem


@pytest.fixture
def mock_tasks():
    with patch("animus.mcp_server.TaskTracker") as mock_cls:
        tracker = MagicMock()
        mock_cls.return_value = tracker
        yield tracker


@pytest.fixture
def server(mock_config, mock_memory, mock_tasks):
    from animus.mcp_server import create_mcp_server

    return create_mcp_server()


class TestMcpServerCreation:
    def test_server_created(self, server):
        assert server is not None
        assert server.name == "animus"

    def test_server_has_tools(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_remember" in tool_names
        assert "animus_recall" in tool_names
        assert "animus_search_tags" in tool_names
        assert "animus_memory_stats" in tool_names
        assert "animus_list_tasks" in tool_names
        assert "animus_create_task" in tool_names
        assert "animus_complete_task" in tool_names
        assert "animus_brief" in tool_names
        assert "animus_run_workflow" in tool_names
        assert "animus_self_improve" in tool_names
        assert "animus_harvest" in tool_names

    def test_tool_count(self, server):
        tools = server._tool_manager.list_tools()
        # 4 memory + 2 versioning + 3 task + 1 brief + 1 workflow + 1 harvest
        # + 4 watchlist + 3 transcripts + 1 self-improve
        # + 2 architect + 2 conversation_designer + 2 knowledge_curator
        # + 2 test_oracle + 4 proposal_queue + 2 citizen_council
        # + 2 session_steward + 1 list_citizens
        # + 4 intelligence + 3 harvester + 2 abstraction + 2 pattern + 2 first_principles + 2 architecture_citizen
        # + 2 research_guild + 1 intent_gating + 1 media_pipeline = 59
        assert len(tools) == 59

    def test_intelligence_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_intelligence_extract" in tool_names
        assert "animus_intelligence_secrets" in tool_names
        assert "animus_intelligence_osint" in tool_names
        assert "animus_intelligence_analyze" in tool_names

    def test_harvester_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_harvester_scan" in tool_names
        assert "animus_harvester_watchlist_scan" in tool_names
        assert "animus_harvester_list_sources" in tool_names

    def test_research_guild_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_research_guild_pipeline" in tool_names
        assert "animus_research_guild_report" in tool_names


class TestMemoryTools:
    def test_remember(self, server, mock_memory):
        mock_memory.remember.return_value = _make_memory("test content")
        result = _run(server.call_tool("animus_remember", {"content": "test fact", "tags": "a,b"}))
        assert "Stored memory" in result[0][0].text
        mock_memory.remember.assert_called_once()
        call_kwargs = mock_memory.remember.call_args.kwargs
        assert call_kwargs["content"] == "test fact"
        assert call_kwargs["tags"] == ["a", "b"]

    def test_remember_no_tags(self, server, mock_memory):
        mock_memory.remember.return_value = _make_memory("test")
        result = _run(server.call_tool("animus_remember", {"content": "test"}))
        assert "Stored memory" in result[0][0].text
        call_kwargs = mock_memory.remember.call_args.kwargs
        assert call_kwargs["tags"] == []

    def test_remember_invalid_type(self, server, mock_memory):
        mock_memory.remember.return_value = _make_memory("test")
        result = _run(
            server.call_tool("animus_remember", {"content": "test", "memory_type": "invalid"})
        )
        assert "Stored memory" in result[0][0].text
        call_kwargs = mock_memory.remember.call_args.kwargs
        assert call_kwargs["memory_type"] == MemoryType.SEMANTIC

    def test_recall_with_results(self, server, mock_memory):
        mock_memory.recall.return_value = [
            _make_memory("Python is great", ["python"]),
            _make_memory("Rust is fast"),
        ]
        result = _run(server.call_tool("animus_recall", {"query": "languages"}))
        text = result[0][0].text
        assert "Python is great" in text
        assert "Rust is fast" in text
        assert "[python]" in text

    def test_recall_empty(self, server, mock_memory):
        mock_memory.recall.return_value = []
        result = _run(server.call_tool("animus_recall", {"query": "nothing"}))
        assert "No matching" in result[0][0].text

    def test_search_tags(self, server, mock_memory):
        mock_memory.recall_by_tags.return_value = [_make_memory("tagged item")]
        result = _run(server.call_tool("animus_search_tags", {"tags": "python,code"}))
        assert "tagged item" in result[0][0].text
        # Stage 2.C — MCP scope is pinned to PUBLIC for egress protection.
        from animus.memory.types import Sensitivity

        mock_memory.recall_by_tags.assert_called_once_with(
            tags=["python", "code"], limit=10, allowed_tiers={Sensitivity.PUBLIC}
        )

    def test_search_tags_empty(self, server, mock_memory):
        result = _run(server.call_tool("animus_search_tags", {"tags": ""}))
        assert "No tags provided" in result[0][0].text

    def test_memory_stats(self, server, mock_memory):
        mock_memory.get_statistics.return_value = {"total": 42, "unique_tags": 10}
        result = _run(server.call_tool("animus_memory_stats", {}))
        data = json.loads(result[0][0].text)
        assert data["total"] == 42


class TestTaskTools:
    def test_list_tasks(self, server, mock_tasks):
        task = MagicMock()
        task.id = "task-001"
        task.status = MagicMock(value="pending")
        task.description = "Fix the bug"
        mock_tasks.list.return_value = [task]
        result = _run(server.call_tool("animus_list_tasks", {"status": "pending"}))
        assert "Fix the bug" in result[0][0].text

    def test_list_tasks_empty(self, server, mock_tasks):
        mock_tasks.list.return_value = []
        result = _run(server.call_tool("animus_list_tasks", {"status": "pending"}))
        assert "No pending" in result[0][0].text

    def test_create_task(self, server, mock_tasks):
        task = MagicMock()
        task.id = "task-002"
        mock_tasks.add_task.return_value = task
        result = _run(server.call_tool("animus_create_task", {"description": "Write tests"}))
        assert "Created task" in result[0][0].text

    def test_complete_task(self, server, mock_tasks):
        mock_tasks.complete.return_value = True
        result = _run(server.call_tool("animus_complete_task", {"task_id": "task-001"}))
        assert "complete" in result[0][0].text

    def test_complete_task_not_found(self, server, mock_tasks):
        mock_tasks.complete.return_value = False
        result = _run(server.call_tool("animus_complete_task", {"task_id": "bad-id"}))
        assert "not found" in result[0][0].text


class TestBriefTool:
    def test_brief_with_results(self, server, mock_memory):
        mock_memory.recall.return_value = [
            _make_memory("Sprint 3 is in progress"),
            _make_memory("Deploy deadline is Friday"),
        ]
        result = _run(server.call_tool("animus_brief", {"topic": "sprint"}))
        text = result[0][0].text
        assert "Animus Briefing" in text
        assert "Sprint 3" in text
        assert "Friday" in text

    def test_brief_empty(self, server, mock_memory):
        mock_memory.recall.return_value = []
        result = _run(server.call_tool("animus_brief", {}))
        assert "No relevant context" in result[0][0].text


class TestRunWorkflow:
    """Test animus_run_workflow MCP tool."""

    @pytest.fixture
    def server(self, tmp_path):
        with patch("animus.mcp_server.AnimusConfig") as mock_config_cls:
            mock_config = MagicMock()
            mock_config.data_dir = tmp_path
            mock_config.memory.backend = "dict"
            mock_config_cls.load.return_value = mock_config
            from animus.mcp_server import create_mcp_server

            return create_mcp_server()

    def test_workflow_not_found(self, server):
        result = _run(
            server.call_tool("animus_run_workflow", {"workflow_path": "/nonexistent/wf.yaml"})
        )
        assert "not found" in result[0][0].text.lower()

    def test_workflow_load_error(self, server, tmp_path):
        """Test ForgeError when loading invalid workflow YAML."""
        bad_yaml = tmp_path / "bad_wf.yaml"
        bad_yaml.write_text("not: valid: workflow")
        from animus.forge.models import ForgeError

        with patch("animus.forge.loader.load_workflow", side_effect=ForgeError("bad schema")):
            result = _run(server.call_tool("animus_run_workflow", {"workflow_path": str(bad_yaml)}))
            assert "Failed to load workflow" in result[0][0].text

    def test_workflow_success_with_results(self, server, tmp_path):
        """Test successful workflow execution with result formatting."""
        wf_yaml = tmp_path / "ok_wf.yaml"
        wf_yaml.write_text("placeholder")

        mock_wf_config = MagicMock()
        mock_wf_config.name = "test_pipeline"
        mock_wf_config.agents = []

        mock_agent_result = MagicMock()
        mock_agent_result.success = True
        mock_agent_result.agent_name = "analyzer"
        mock_agent_result.tokens_used = 500
        mock_agent_result.error = None

        mock_fail_result = MagicMock()
        mock_fail_result.success = False
        mock_fail_result.agent_name = "broken_step"
        mock_fail_result.tokens_used = 100
        mock_fail_result.error = "timeout"

        mock_state = MagicMock()
        mock_state.status = "completed"
        mock_state.results = [mock_agent_result, mock_fail_result]
        mock_state.total_tokens = 600
        mock_state.total_cost = 0.0042

        with (
            patch("animus.forge.loader.load_workflow", return_value=mock_wf_config),
            patch("animus.cognitive.CognitiveLayer"),
            patch("animus.cognitive.ModelConfig") as mock_mc,
            patch("animus.tools.create_default_registry"),
            patch("animus.forge.ForgeEngine") as mock_engine_cls,
        ):
            mock_mc.ollama.return_value = MagicMock()
            mock_engine_cls.return_value.run.return_value = mock_state
            result = _run(server.call_tool("animus_run_workflow", {"workflow_path": str(wf_yaml)}))
            text = result[0][0].text
            assert "test_pipeline" in text
            assert "completed" in text
            assert "[OK] analyzer" in text
            assert "[FAIL] broken_step" in text
            assert "timeout" in text
            assert "$0.0042" in text

    def test_workflow_runs(self, server, tmp_path):
        # Create a minimal workflow YAML
        wf_yaml = tmp_path / "test_wf.yaml"
        wf_yaml.write_text(
            "name: test_wf\n"
            "description: Test\n"
            "provider: mock\n"
            "model: mock\n"
            "max_cost_usd: 1.0\n"
            "agents:\n"
            "  - name: step1\n"
            "    archetype: writer\n"
            "    budget_tokens: 100\n"
            "    outputs: [result]\n"
            "gates: []\n"
        )
        result = _run(
            server.call_tool(
                "animus_run_workflow",
                {"workflow_path": str(wf_yaml), "task_description": "test task"},
            )
        )
        text = result[0][0].text
        # Should complete or fail gracefully
        assert "test_wf" in text or "failed" in text.lower()


class TestMCPAuth:
    """Test MCP server API key authentication."""

    def test_no_auth_configured(self):
        """Without ANIMUS_MCP_API_KEY, all calls pass."""
        from animus.mcp_server import _check_auth

        with patch.dict("os.environ", {}, clear=False):
            with patch("animus.mcp_server._MCP_API_KEY", None):
                assert _check_auth() is None
                assert _check_auth("anything") is None

    def test_auth_required_no_key(self):
        """With ANIMUS_MCP_API_KEY set, missing key is rejected."""
        from animus.mcp_server import _check_auth

        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _check_auth("")
            assert result is not None
            assert "Authentication required" in result

    def test_auth_required_wrong_key(self):
        """Wrong key is rejected."""
        from animus.mcp_server import _check_auth

        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _check_auth("wrong")
            assert result is not None

    def test_auth_required_correct_key(self):
        """Correct key passes."""
        from animus.mcp_server import _check_auth

        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            assert _check_auth("secret123") is None

    def test_remember_with_auth(self, tmp_path):
        """animus_remember blocks without valid key when auth is configured."""
        with (
            patch("animus.mcp_server._MCP_API_KEY", "testkey"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            with patch("animus.mcp_server.AnimusConfig") as mock_config_cls:
                mock_config = MagicMock()
                mock_config.data_dir = tmp_path
                mock_config.memory.backend = "sqlite"
                mock_config_cls.load.return_value = mock_config

                from animus.mcp_server import create_mcp_server

                server = create_mcp_server()

                # No key → blocked
                result = _run(server.call_tool("animus_remember", {"content": "test"}))
                assert "Authentication required" in result[0][0].text

                # Correct key → passes
                result = _run(
                    server.call_tool(
                        "animus_remember",
                        {"content": "test", "api_key": "testkey"},
                    )
                )
                assert "Authentication required" not in result[0][0].text


class TestHarvestTool:
    """Test animus_harvest MCP tool."""

    def test_harvest_success(self, server, mock_memory):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"repo": "test/repo", "patterns": 5}
        with patch("animus.lugh.repos.harvest_repo", return_value=mock_result):
            result = _run(server.call_tool("animus_harvest", {"target": "test/repo"}))
            data = json.loads(result[0][0].text)
            assert data["repo"] == "test/repo"

    def test_harvest_value_error(self, server, mock_memory):
        with patch("animus.lugh.repos.harvest_repo", side_effect=ValueError("bad target")):
            result = _run(server.call_tool("animus_harvest", {"target": "bad"}))
            assert "Harvest failed" in result[0][0].text

    def test_harvest_runtime_error(self, server, mock_memory):
        with patch("animus.lugh.repos.harvest_repo", side_effect=RuntimeError("clone failed")):
            result = _run(server.call_tool("animus_harvest", {"target": "bad/repo"}))
            assert "Harvest failed" in result[0][0].text

    def test_harvest_unexpected_error(self, server, mock_memory):
        with patch("animus.lugh.repos.harvest_repo", side_effect=OSError("disk full")):
            result = _run(server.call_tool("animus_harvest", {"target": "test/repo"}))
            assert "Harvest error" in result[0][0].text

    def test_harvest_auth_blocked(self, server, mock_memory):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_harvest", {"target": "test/repo"}))
            assert "Authentication required" in result[0][0].text

    def test_harvest_auth_passes(self, server, mock_memory):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"repo": "ok"}
        with (
            patch("animus.mcp_server._MCP_API_KEY", "key123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            with patch("animus.lugh.repos.harvest_repo", return_value=mock_result):
                result = _run(
                    server.call_tool("animus_harvest", {"target": "test/repo", "api_key": "key123"})
                )
                assert "Authentication required" not in result[0][0].text


class TestWatchlistTools:
    """Test watchlist MCP tools."""

    def test_watchlist_add(self, server):
        entry = {"target": "test/repo", "tags": ["ai"], "added": "2026-03-25"}
        with patch("animus.lugh.watchlist.add_to_watchlist", return_value=entry):
            result = _run(
                server.call_tool(
                    "animus_watchlist_add",
                    {"target": "test/repo", "tags": "ai,ml", "notes": "competitor"},
                )
            )
            data = json.loads(result[0][0].text)
            assert data["target"] == "test/repo"

    def test_watchlist_add_no_tags(self, server):
        entry = {"target": "test/repo", "tags": [], "added": "2026-03-25"}
        with patch("animus.lugh.watchlist.add_to_watchlist", return_value=entry):
            result = _run(server.call_tool("animus_watchlist_add", {"target": "test/repo"}))
            data = json.loads(result[0][0].text)
            assert data["target"] == "test/repo"

    def test_watchlist_add_value_error(self, server):
        with patch(
            "animus.lugh.watchlist.add_to_watchlist",
            side_effect=ValueError("duplicate"),
        ):
            result = _run(server.call_tool("animus_watchlist_add", {"target": "test/repo"}))
            assert "Watchlist add failed" in result[0][0].text

    def test_watchlist_add_unexpected_error(self, server):
        with patch(
            "animus.lugh.watchlist.add_to_watchlist",
            side_effect=OSError("disk"),
        ):
            result = _run(server.call_tool("animus_watchlist_add", {"target": "test/repo"}))
            assert "Watchlist error" in result[0][0].text

    def test_watchlist_add_auth_blocked(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_watchlist_add", {"target": "test/repo"}))
            assert "Authentication required" in result[0][0].text

    def test_watchlist_remove_success(self, server):
        with patch("animus.lugh.watchlist.remove_from_watchlist", return_value=True):
            result = _run(server.call_tool("animus_watchlist_remove", {"target": "test/repo"}))
            assert "Removed" in result[0][0].text

    def test_watchlist_remove_not_found(self, server):
        with patch("animus.lugh.watchlist.remove_from_watchlist", return_value=False):
            result = _run(server.call_tool("animus_watchlist_remove", {"target": "test/repo"}))
            assert "not found" in result[0][0].text

    def test_watchlist_remove_auth_blocked(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_watchlist_remove", {"target": "test/repo"}))
            assert "Authentication required" in result[0][0].text

    def test_watchlist_list_with_repos(self, server):
        repos = [{"target": "a/b", "last_scan": "2026-03-20"}]
        with patch("animus.lugh.watchlist.get_watchlist", return_value=repos):
            result = _run(server.call_tool("animus_watchlist_list", {}))
            data = json.loads(result[0][0].text)
            assert len(data) == 1

    def test_watchlist_list_empty(self, server):
        with patch("animus.lugh.watchlist.get_watchlist", return_value=[]):
            result = _run(server.call_tool("animus_watchlist_list", {}))
            assert "empty" in result[0][0].text.lower()

    def test_watchlist_scan_success(self, server):
        report = {"scanned": 2, "changes": 1}

        async def fake_scan(**kwargs):
            return report

        with (
            patch("animus.lugh.watchlist.run_watchlist_scan", side_effect=fake_scan),
            _patch_nested_asyncio_run(),
        ):
            result = _run(server.call_tool("animus_watchlist_scan", {}))
            data = json.loads(result[0][0].text)
            assert data["scanned"] == 2

    def test_watchlist_scan_with_interval(self, server):
        report = {"scanned": 1}
        call_log = {}

        async def fake_scan(**kwargs):
            call_log.update(kwargs)
            return report

        with (
            patch("animus.lugh.watchlist.run_watchlist_scan", side_effect=fake_scan),
            _patch_nested_asyncio_run(),
        ):
            result = _run(server.call_tool("animus_watchlist_scan", {"interval_hours": 24}))
            data = json.loads(result[0][0].text)
            assert data["scanned"] == 1
            assert call_log["interval_hours"] == 24

    def test_watchlist_scan_failure(self, server):
        with patch(
            "animus.lugh.watchlist.run_watchlist_scan",
            side_effect=RuntimeError("network error"),
        ):
            result = _run(server.call_tool("animus_watchlist_scan", {}))
            assert "Watchlist scan failed" in result[0][0].text

    def test_watchlist_scan_auth_blocked(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_watchlist_scan", {}))
            assert "Authentication required" in result[0][0].text


@pytest.fixture
def fake_forge_modules(monkeypatch):
    """Mock the optional Forge boundary without installing its runtime stack."""
    names = [
        "animus_forge",
        "animus_forge.agents",
        "animus_forge.agents.provider_wrapper",
        "animus_forge.self_improve",
        "animus_forge.self_improve.orchestrator",
    ]
    modules = {name: ModuleType(name) for name in names}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        if "." in name:
            parent, attr = name.rsplit(".", 1)
            setattr(modules[parent], attr, module)
    modules["animus_forge.agents.provider_wrapper"].create_agent_provider = MagicMock()
    modules["animus_forge.self_improve.orchestrator"].SelfImproveOrchestrator = MagicMock()


class TestSelfImproveTool:
    """Test animus_self_improve MCP tool."""

    def test_self_improve_path_not_found(self, server):
        result = _run(
            server.call_tool("animus_self_improve", {"codebase_path": "/nonexistent/path"})
        )
        assert "Path not found" in result[0][0].text

    def test_self_improve_forge_not_installed(self, server, tmp_path):
        # Patch the specific imports that animus_self_improve tries
        with patch.dict("sys.modules", {"animus_forge.agents.provider_wrapper": None}):
            result = _run(server.call_tool("animus_self_improve", {"codebase_path": str(tmp_path)}))
            assert "Forge not installed" in result[0][0].text

    def test_self_improve_provider_error(self, server, tmp_path, fake_forge_modules):
        with patch(
            "animus_forge.agents.provider_wrapper.create_agent_provider",
            side_effect=ValueError("bad provider"),
        ):
            result = _run(
                server.call_tool(
                    "animus_self_improve",
                    {"codebase_path": str(tmp_path), "provider": "bad"},
                )
            )
            assert "Failed to create" in result[0][0].text

    def test_self_improve_success(self, server, tmp_path, fake_forge_modules):
        mock_result = MagicMock()
        mock_result.stage_reached.value = "completed"
        mock_result.success = True
        mock_result.plan = MagicMock()
        mock_result.plan.title = "Fix bare excepts"
        mock_result.plan.suggestions = [MagicMock(description="Replace bare except in foo.py")]
        mock_result.error = None
        mock_result.sandbox_result = MagicMock()
        mock_result.sandbox_result.tests_passed = True
        mock_result.pull_request = MagicMock()
        mock_result.pull_request.url = "https://github.com/test/pr/1"
        mock_result.pull_request.branch = "self-improve-1"

        mock_orch = MagicMock()

        async def mock_run(**kwargs):
            return mock_result

        mock_orch.run = mock_run

        with (
            patch(
                "animus_forge.agents.provider_wrapper.create_agent_provider",
                return_value=MagicMock(),
            ),
            patch(
                "animus_forge.self_improve.orchestrator.SelfImproveOrchestrator",
                return_value=mock_orch,
            ),
            _patch_nested_asyncio_run(),
        ):
            result = _run(
                server.call_tool(
                    "animus_self_improve",
                    {"codebase_path": str(tmp_path)},
                )
            )
            text = result[0][0].text
            assert "completed" in text
            assert "Fix bare excepts" in text
            assert "passed" in text

    def test_self_improve_failure(self, server, tmp_path, fake_forge_modules):
        mock_result = MagicMock()
        mock_result.stage_reached.value = "analysis"
        mock_result.success = False
        mock_result.plan = None
        mock_result.error = "No issues found"
        mock_result.sandbox_result = None
        mock_result.pull_request = None

        mock_orch = MagicMock()

        async def mock_run(**kwargs):
            return mock_result

        mock_orch.run = mock_run

        with (
            patch(
                "animus_forge.agents.provider_wrapper.create_agent_provider",
                return_value=MagicMock(),
            ),
            patch(
                "animus_forge.self_improve.orchestrator.SelfImproveOrchestrator",
                return_value=mock_orch,
            ),
            _patch_nested_asyncio_run(),
        ):
            result = _run(
                server.call_tool(
                    "animus_self_improve",
                    {"codebase_path": str(tmp_path)},
                )
            )
            text = result[0][0].text
            assert "analysis" in text
            assert "No issues found" in text

    def test_self_improve_exception(self, server, tmp_path, fake_forge_modules):
        mock_orch = MagicMock()

        async def mock_run(**kwargs):
            raise RuntimeError("sandbox crashed")

        mock_orch.run = mock_run

        with (
            patch(
                "animus_forge.agents.provider_wrapper.create_agent_provider",
                return_value=MagicMock(),
            ),
            patch(
                "animus_forge.self_improve.orchestrator.SelfImproveOrchestrator",
                return_value=mock_orch,
            ),
            _patch_nested_asyncio_run(),
        ):
            result = _run(
                server.call_tool(
                    "animus_self_improve",
                    {"codebase_path": str(tmp_path)},
                )
            )
            assert "Self-improve failed" in result[0][0].text

    def test_self_improve_auth_blocked(self, server, tmp_path):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(
                server.call_tool(
                    "animus_self_improve",
                    {"codebase_path": str(tmp_path)},
                )
            )
            assert "Authentication required" in result[0][0].text


class TestWriteToolsAuth:
    """Test auth blocks on all write tools."""

    def test_create_task_auth(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "authkey"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_create_task", {"description": "test"}))
            assert "Authentication required" in result[0][0].text

    def test_complete_task_auth(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "authkey"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_complete_task", {"task_id": "t1"}))
            assert "Authentication required" in result[0][0].text

    def test_run_workflow_auth(self, server):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "authkey"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_run_workflow", {"workflow_path": "/test.yaml"}))
            assert "Authentication required" in result[0][0].text


class TestListTasksFilter:
    """Test task list filtering edge cases."""

    def test_list_all_tasks(self, server, mock_tasks):
        task = MagicMock()
        task.id = "task-001"
        task.status = MagicMock(value="completed")
        task.description = "Done task"
        mock_tasks.list.return_value = [task]
        result = _run(server.call_tool("animus_list_tasks", {"status": "all"}))
        assert "Done task" in result[0][0].text

    def test_list_tasks_filters_by_status(self, server, mock_tasks):
        pending = MagicMock()
        pending.id = "t1"
        pending.status = MagicMock(value="pending")
        pending.description = "Pending one"
        done = MagicMock()
        done.id = "t2"
        done.status = MagicMock(value="completed")
        done.description = "Done one"
        mock_tasks.list.return_value = [pending, done]
        result = _run(server.call_tool("animus_list_tasks", {"status": "pending"}))
        text = result[0][0].text
        assert "Pending one" in text
        assert "Done one" not in text


class TestSearchTagsNoResults:
    """Test search_tags with no matching results."""

    def test_search_tags_no_results(self, server, mock_memory):
        mock_memory.recall_by_tags.return_value = []
        result = _run(server.call_tool("animus_search_tags", {"tags": "nonexistent"}))
        assert "No memories found" in result[0][0].text


class TestBriefMemoryType:
    """Test brief tool memory_type attribute handling."""

    def test_brief_with_memory_type(self, server, mock_memory):
        mem = _make_memory("Important context")
        mock_memory.recall.return_value = [mem]
        result = _run(server.call_tool("animus_brief", {"topic": "test"}))
        text = result[0][0].text
        assert "semantic" in text
        assert "Important context" in text

    def test_brief_default_topic(self, server, mock_memory):
        mock_memory.recall.return_value = [_make_memory("data")]
        _run(server.call_tool("animus_brief", {}))
        # Stage 2.C — brief query is MCP egress; pinned to PUBLIC tier.
        from animus.memory.types import Sensitivity

        mock_memory.recall.assert_called_with(
            query="recent important context", limit=10, allowed_tiers={Sensitivity.PUBLIC}
        )


class TestArchitectTools:
    """Test Architect Citizen MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_architect_scan" in tool_names
        assert "animus_architect_list_proposals" in tool_names

    def test_architect_scan_disabled(self, server, mock_config):
        mock_config.citizens.enabled = False
        result = _run(server.call_tool("animus_architect_scan", {}))
        assert "Citizens are disabled" in result[0][0].text

    def test_architect_scan_codebase(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)
        mock_config.citizens.auto_store_proposals = False

        with patch("animus.citizens.ArchitectCitizen") as mock_cls:
            mock_architect = MagicMock()
            mock_cls.return_value = mock_architect

            from animus.citizens.architect import Observation

            mock_architect.observe_codebase.return_value = [
                Observation(source="codebase", description="High complexity", severity="high"),
            ]
            mock_architect.observe_conversations.return_value = []
            mock_architect.observe_evaluations.return_value = []

            report = MagicMock()
            report.technical_debt_items = ["High complexity"]
            report.friction_points = []
            report.findings = []
            report.observations = mock_architect.observe_codebase.return_value
            mock_architect.analyze.return_value = report

            proposal = MagicMock()
            proposal.id = "ADL-20260705-001"
            proposal.title = "Refactor complex module"
            proposal.problem = "High complexity in parser.py"
            proposal.confidence_score = 0.75
            proposal.confidence.value = "high"
            proposal.estimated_effort_hours = 4.0
            proposal.affected_components = ["Factory"]
            proposal.recommendation = "Split into smaller functions"
            proposal.potential_risks = [
                MagicMock(description="Regressions", severity="medium", mitigation="Tests"),
            ]
            mock_architect.generate_proposal.return_value = proposal
            mock_architect.store_proposal.return_value = True

            result = _run(server.call_tool("animus_architect_scan", {"focus": "codebase"}))
            text = result[0][0].text
            assert "Architect Citizen Scan Report" in text
            assert "Refactor complex module" in text
            assert "High complexity" in text
            mock_architect.observe_codebase.assert_called_once()

    def test_architect_scan_no_findings(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)

        with patch("animus.citizens.ArchitectCitizen") as mock_cls:
            mock_architect = MagicMock()
            mock_cls.return_value = mock_architect
            mock_architect.observe_codebase.return_value = []
            mock_architect.observe_conversations.return_value = []
            mock_architect.observe_evaluations.return_value = []

            report = MagicMock()
            report.technical_debt_items = []
            report.friction_points = []
            report.findings = []
            report.observations = []
            mock_architect.analyze.return_value = report
            mock_architect.generate_proposal.return_value = None

            result = _run(server.call_tool("animus_architect_scan", {"focus": "all"}))
            text = result[0][0].text
            assert "No Proposal Generated" in text
            assert "No actionable findings" in text

    def test_architect_scan_auth_blocked(self, server, tmp_path):
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            result = _run(server.call_tool("animus_architect_scan", {}))
            assert "Authentication required" in result[0][0].text

    def test_architect_list_proposals_empty(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = "/tmp/test"

        with patch("animus.citizens.ArchitectCitizen") as mock_cls:
            mock_architect = MagicMock()
            mock_cls.return_value = mock_architect
            mock_architect.list_pending_proposals.return_value = []

            result = _run(
                server.call_tool("animus_architect_list_proposals", {"status": "pending"})
            )
            assert "No pending proposals found" in result[0][0].text

    def test_architect_list_proposals_with_results(self, server, mock_config):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = "/tmp/test"

        with patch("animus.citizens.ArchitectCitizen") as mock_cls:
            mock_architect = MagicMock()
            mock_cls.return_value = mock_architect

            proposal = MagicMock()
            proposal.id = "ADL-001"
            proposal.title = "Fix parser"
            proposal.status.value = "draft"
            proposal.confidence.value = "medium"
            proposal.confidence_score = 0.6
            proposal.problem = "Parser is too complex"
            proposal.recommendation = "Split it up"
            mock_architect.list_pending_proposals.return_value = [proposal]

            result = _run(
                server.call_tool("animus_architect_list_proposals", {"status": "pending"})
            )
            text = result[0][0].text
            assert "ADL-001" in text
            assert "Fix parser" in text
            assert "medium" in text


class TestConversationDesignerTools:
    """Test Conversation Designer Citizen MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_conversation_designer_scan" in tool_names
        assert "animus_conversation_designer_list_proposals" in tool_names

    def test_conversation_designer_scan(self, server, mock_config):
        mock_config.citizens.enabled = True

        with patch("animus.citizens.ConversationDesignerCitizen") as mock_cls:
            mock_designer = MagicMock()
            mock_cls.return_value = mock_designer

            mock_obs = MagicMock()
            mock_obs.severity = "high"
            mock_obs.description = "Repeated 'explain this' prompts"

            mock_designer.observe_repeated_prompts.return_value = [mock_obs]
            mock_designer.observe_vague_requests.return_value = []
            mock_designer.observe_correction_loops.return_value = []

            proposal = MagicMock()
            proposal.id = "CD-001"
            proposal.title = "Add reusable prompt templates"
            proposal.confidence.value = "high"
            proposal.confidence_score = 0.85
            mock_designer.generate_proposal.return_value = proposal
            mock_designer.store_proposal.return_value = True

            result = _run(server.call_tool("animus_conversation_designer_scan", {}))
            text = result[0][0].text
            assert "Conversation Designer Scan Report" in text
            assert "Add reusable prompt templates" in text
            assert "Repeated 'explain this' prompts" in text
            assert "Proposal stored in memory for review" in text

    def test_conversation_designer_scan_no_findings(self, server, mock_config):
        mock_config.citizens.enabled = True

        with patch("animus.citizens.ConversationDesignerCitizen") as mock_cls:
            mock_designer = MagicMock()
            mock_cls.return_value = mock_designer

            mock_designer.observe_repeated_prompts.return_value = []
            mock_designer.observe_vague_requests.return_value = []
            mock_designer.observe_correction_loops.return_value = []
            mock_designer.generate_proposal.return_value = None

            result = _run(server.call_tool("animus_conversation_designer_scan", {}))
            text = result[0][0].text
            assert "No actionable conversation patterns found" in text

    def test_conversation_designer_list_proposals_empty(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True
        mock_config.citizens.conversation_log_dir = "/tmp/logs"

        with patch("animus.citizens.ConversationDesignerCitizen") as mock_cls:
            mock_designer = MagicMock()
            mock_cls.return_value = mock_designer

            result = _run(
                server.call_tool(
                    "animus_conversation_designer_list_proposals", {"status": "pending"}
                )
            )
            assert "No pending proposals found" in result[0][0].text


class TestKnowledgeCuratorTools:
    """Test Knowledge Curator Citizen MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_knowledge_curator_scan" in tool_names
        assert "animus_knowledge_curator_list_proposals" in tool_names

    def test_knowledge_curator_scan(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)

        with patch("animus.citizens.KnowledgeCuratorCitizen") as mock_cls:
            mock_curator = MagicMock()
            mock_cls.return_value = mock_curator

            mock_obs = MagicMock()
            mock_obs.severity = "medium"
            mock_obs.description = "Stale reference to old API"

            mock_curator.observe_stale_references.return_value = [mock_obs]
            mock_curator.observe_contradictions.return_value = []
            mock_curator.observe_outdated_claims.return_value = []
            mock_curator.observe_orphan_topics.return_value = []

            proposal = MagicMock()
            proposal.id = "KC-001"
            proposal.title = "Update API references"
            proposal.confidence.value = "medium"
            proposal.confidence_score = 0.7
            mock_curator.generate_proposal.return_value = proposal
            mock_curator.store_proposal.return_value = True

            result = _run(server.call_tool("animus_knowledge_curator_scan", {}))
            text = result[0][0].text
            assert "Knowledge Curator Scan Report" in text
            assert "Update API references" in text
            assert "Stale reference to old API" in text
            assert "Proposal stored in memory for review" in text

    def test_knowledge_curator_scan_no_findings(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)

        with patch("animus.citizens.KnowledgeCuratorCitizen") as mock_cls:
            mock_curator = MagicMock()
            mock_cls.return_value = mock_curator

            mock_curator.observe_stale_references.return_value = []
            mock_curator.observe_contradictions.return_value = []
            mock_curator.observe_outdated_claims.return_value = []
            mock_curator.observe_orphan_topics.return_value = []
            mock_curator.generate_proposal.return_value = None

            result = _run(server.call_tool("animus_knowledge_curator_scan", {}))
            text = result[0][0].text
            assert "No actionable knowledge drift found" in text

    def test_knowledge_curator_list_proposals_empty(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = "/tmp/test"

        with patch("animus.citizens.KnowledgeCuratorCitizen") as mock_cls:
            mock_curator = MagicMock()
            mock_cls.return_value = mock_curator

            result = _run(
                server.call_tool("animus_knowledge_curator_list_proposals", {"status": "pending"})
            )
            assert "No pending proposals found" in result[0][0].text


class TestTestOracleTools:
    """Test Test Oracle Citizen MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_test_oracle_scan" in tool_names
        assert "animus_test_oracle_list_proposals" in tool_names

    def test_test_oracle_scan(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)

        with patch("animus.citizens.TestOracleCitizen") as mock_cls:
            mock_oracle = MagicMock()
            mock_cls.return_value = mock_oracle

            mock_failure = MagicMock()
            mock_failure.severity = "high"
            mock_failure.description = "test_foo_bar fails intermittently"

            mock_gap = MagicMock()
            mock_gap.severity = "medium"
            mock_gap.description = "core/app.py has 30% coverage"

            mock_drift = MagicMock()
            mock_drift.severity = "low"
            mock_drift.description = "Eval score dropped 5%"

            mock_oracle.observe_test_failures.return_value = [mock_failure]
            mock_oracle.observe_coverage_gaps.return_value = [mock_gap]
            mock_oracle.observe_eval_drift.return_value = [mock_drift]

            proposal = MagicMock()
            proposal.id = "TO-001"
            proposal.title = "Improve test reliability"
            proposal.confidence.value = "high"
            proposal.confidence_score = 0.9
            mock_oracle.generate_proposal.return_value = proposal
            mock_oracle.store_proposal.return_value = True

            result = _run(server.call_tool("animus_test_oracle_scan", {}))
            text = result[0][0].text
            assert "Test Oracle Scan Report" in text
            assert "Improve test reliability" in text
            assert "test_foo_bar fails intermittently" in text
            assert "core/app.py has 30% coverage" in text
            assert "Proposal stored in memory for review" in text

    def test_test_oracle_scan_no_findings(self, server, mock_config, tmp_path):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = str(tmp_path)

        with patch("animus.citizens.TestOracleCitizen") as mock_cls:
            mock_oracle = MagicMock()
            mock_cls.return_value = mock_oracle

            mock_oracle.observe_test_failures.return_value = []
            mock_oracle.observe_coverage_gaps.return_value = []
            mock_oracle.observe_eval_drift.return_value = []
            mock_oracle.generate_proposal.return_value = None

            result = _run(server.call_tool("animus_test_oracle_scan", {}))
            text = result[0][0].text
            assert "No actionable quality regressions found" in text

    def test_test_oracle_list_proposals_empty(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True
        mock_config.citizens.codebase_path = "/tmp/test"

        with patch("animus.citizens.TestOracleCitizen") as mock_cls:
            mock_oracle = MagicMock()
            mock_cls.return_value = mock_oracle

            result = _run(
                server.call_tool("animus_test_oracle_list_proposals", {"status": "pending"})
            )
            assert "No pending proposals found" in result[0][0].text


class TestProposalQueueTools:
    """Test Proposal Queue MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_proposal_queue_list" in tool_names
        assert "animus_proposal_queue_approve" in tool_names
        assert "animus_proposal_queue_reject" in tool_names
        assert "animus_proposal_queue_stats" in tool_names

    def test_proposal_queue_list_pending(self, server, mock_memory):
        mock_qp = MagicMock()
        mock_qp.proposal.id = "PROP-001"
        mock_qp.proposal.title = "Fix flaky tests"
        mock_qp.current_status.value = "pending"
        mock_qp.priority = 3
        mock_qp.tags = ["testing", "urgent"]
        mock_qp.proposal.confidence.value = "high"
        mock_qp.proposal.confidence_score = 0.85
        mock_qp.proposal.estimated_effort_hours = 4.0
        mock_qp.proposal.problem = "Tests fail randomly"
        mock_qp.proposal.recommendation = "Add retries and isolation"
        mock_qp.transitions = [
            MagicMock(
                from_status=MagicMock(value="submitted"),
                to_status=MagicMock(value="pending"),
                actor="citizen",
            )
        ]

        with patch("animus.citizens.ProposalQueue") as mock_cls:
            mock_queue = MagicMock()
            mock_cls.return_value = mock_queue
            mock_queue.list_pending.return_value = [mock_qp]

            result = _run(server.call_tool("animus_proposal_queue_list", {"status": "pending"}))
            text = result[0][0].text
            assert "Proposal Queue (pending)" in text
            assert "PROP-001" in text
            assert "Fix flaky tests" in text
            assert "submitted → pending by citizen" in text

    def test_proposal_queue_list_empty(self, server, mock_memory):
        with patch("animus.citizens.ProposalQueue") as mock_cls:
            mock_queue = MagicMock()
            mock_cls.return_value = mock_queue
            mock_queue.list_pending.return_value = []

            result = _run(server.call_tool("animus_proposal_queue_list", {"status": "pending"}))
            assert "No proposals with status 'pending' found" in result[0][0].text

    def test_proposal_queue_approve(self, server, mock_memory):
        mock_qp = MagicMock()
        mock_qp.current_status.value = "approved"

        with patch("animus.citizens.ProposalQueue") as mock_cls:
            mock_queue = MagicMock()
            mock_cls.return_value = mock_queue
            mock_queue.approve.return_value = mock_qp

            result = _run(
                server.call_tool(
                    "animus_proposal_queue_approve", {"proposal_id": "PROP-001", "reason": "LGTM"}
                )
            )
            text = result[0][0].text
            assert "PROP-001 approved" in text
            assert "approved" in text

    def test_proposal_queue_reject(self, server, mock_memory):
        mock_qp = MagicMock()
        mock_qp.current_status.value = "rejected"

        with patch("animus.citizens.ProposalQueue") as mock_cls:
            mock_queue = MagicMock()
            mock_cls.return_value = mock_queue
            mock_queue.reject.return_value = mock_qp

            result = _run(
                server.call_tool(
                    "animus_proposal_queue_reject",
                    {"proposal_id": "PROP-001", "reason": "Not feasible"},
                )
            )
            text = result[0][0].text
            assert "PROP-001 rejected" in text
            assert "rejected" in text

    def test_proposal_queue_stats(self, server, mock_memory):
        stats = {
            "total": 5,
            "pending": 2,
            "approved": 1,
            "commissioned": 1,
            "complete": 1,
            "rejected": 0,
        }

        with patch("animus.citizens.ProposalQueue") as mock_cls:
            mock_queue = MagicMock()
            mock_cls.return_value = mock_queue
            mock_queue.stats.return_value = stats

            result = _run(server.call_tool("animus_proposal_queue_stats", {}))
            data = json.loads(result[0][0].text)
            assert data["total"] == 5
            assert data["pending"] == 2


class TestCitizenCouncilTools:
    """Test Citizen Council MCP tools."""

    def test_tools_exist(self, server):
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        assert "animus_citizen_council_backlog" in tool_names
        assert "animus_citizen_council_summary" in tool_names

    def test_citizen_council_backlog(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True

        mock_rp = MagicMock()
        mock_rp.proposal.id = "CC-001"
        mock_rp.proposal.title = "Unified backlog item"
        mock_rp.proposal.confidence.value = "high"
        mock_rp.proposal.confidence_score = 0.9
        mock_rp.proposal.estimated_effort_hours = 3.0
        mock_rp.proposal.affected_components = ["core/app.py"]
        mock_rp.proposal.problem = "Multiple citizens flagged this"
        mock_rp.proposal.recommendation = "Fix it once"
        mock_rp.rank = 1
        mock_rp.priority_score = 2.5
        mock_rp.severity_score = 3
        mock_rp.source_citizens = ["architect", "test_oracle"]
        mock_rp.duplicates = []

        with patch("animus.citizens.CitizenCouncil") as mock_cls:
            mock_council = MagicMock()
            mock_cls.return_value = mock_council
            mock_council.collect_from_memory.return_value = 1
            mock_council.rank_backlog.return_value = [mock_rp]
            mock_council.summary.return_value = {"unique_components": 1}

            result = _run(server.call_tool("animus_citizen_council_backlog", {}))
            text = result[0][0].text
            assert "Citizen Council — Unified Ranked Backlog" in text
            assert "Unified backlog item" in text
            assert "architect" in text

    def test_citizen_council_summary(self, server, mock_config, mock_memory):
        mock_config.citizens.enabled = True

        summary = {
            "total_proposals": 3,
            "unique_components": 2,
            "total_estimated_effort_hours": 12.5,
            "sources": {"architect": 2, "test_oracle": 1},
        }

        with patch("animus.citizens.CitizenCouncil") as mock_cls:
            mock_council = MagicMock()
            mock_cls.return_value = mock_council
            mock_council.collect_from_memory.return_value = 3
            mock_council.summary.return_value = summary

            result = _run(server.call_tool("animus_citizen_council_summary", {}))
            data = json.loads(result[0][0].text)
            assert data["total_proposals"] == 3
            assert data["unique_components"] == 2
            assert data["sources"]["architect"] == 2


class TestIntelligenceTools:
    """Test animus_intelligence_* MCP tools."""

    def test_intelligence_extract(self, server):
        result = _run(
            server.call_tool(
                "animus_intelligence_extract",
                {"text": "Email: alice@example.com, IP: 192.168.1.1"},
            )
        )
        text = result[0][0].text
        assert "alice@example.com" in text
        assert "192.168.1.1" in text
        assert "Emails" in text
        assert "Ipv4 Addresses" in text

    def test_intelligence_extract_empty(self, server):
        result = _run(server.call_tool("animus_intelligence_extract", {"text": ""}))
        text = result[0][0].text
        assert "Total entities found" in text
        assert "0" in text

    def test_intelligence_secrets_text(self, server):
        result = _run(
            server.call_tool(
                "animus_intelligence_secrets",
                {"text": "API key: AKIAIOSFODNN7EXAMPLE"},
            )
        )
        text = result[0][0].text
        assert "AWS Access Key ID" in text
        assert "CRITICAL" in text

    def test_intelligence_secrets_empty(self, server):
        result = _run(server.call_tool("animus_intelligence_secrets", {"text": "safe text"}))
        text = result[0][0].text
        assert "No secrets detected" in text

    def test_intelligence_secrets_file_not_found(self, server):
        result = _run(
            server.call_tool(
                "animus_intelligence_secrets",
                {"file_path": "/nonexistent/path"},
            )
        )
        text = result[0][0].text
        assert "File not found" in text

    def test_intelligence_osint(self, server):
        result = _run(
            server.call_tool(
                "animus_intelligence_osint",
                {"usernames": "octocat,testuser"},
            )
        )
        text = result[0][0].text
        assert "GitHub" in text
        assert "octocat" in text
        assert "testuser" in text

    def test_intelligence_analyze_text(self, server, mock_memory):
        result = _run(
            server.call_tool(
                "animus_intelligence_analyze",
                {"text": "Contact alice@example.com or visit https://github.com/test"},
            )
        )
        text = result[0][0].text
        assert "Intelligence Analysis Report" in text
        assert "alice@example.com" in text
        assert "Entities" in text

    def test_intelligence_analyze_file_not_found(self, server, mock_memory):
        result = _run(
            server.call_tool(
                "animus_intelligence_analyze",
                {"file_path": "/nonexistent/path"},
            )
        )
        text = result[0][0].text
        assert "File not found" in text


class TestMcpImportError:
    """Test create_mcp_server when mcp is not installed."""

    def test_import_error_raised(self, server):
        from animus.mcp_server import create_mcp_server

        with patch("animus.mcp_server.FastMCP", None):
            with pytest.raises(ImportError, match="MCP server requires"):
                create_mcp_server()


class TestMainEntrypoint:
    """Test the main() entrypoint."""

    def test_main_calls_run(self, mock_config, mock_memory, mock_tasks):
        from animus.mcp_server import main

        with patch("animus.mcp_server.create_mcp_server") as mock_create:
            with patch("animus.mcp_server.LockedPidFile"):
                mock_server = MagicMock()
                mock_create.return_value = mock_server
                main()
                mock_server.run.assert_called_once()


class TestToolGating:
    """Test MCP tool gating (Proposal 1: ADL-20260714-001)."""

    def test_server_is_gated_fastmcp(self, server):
        from animus.mcp_server import GatedFastMCP

        assert isinstance(server, GatedFastMCP)

    def test_list_tools_without_intent_returns_all_full(self, server):
        """Backward compatibility: no intent = all tools, full schemas."""
        import asyncio

        from animus.mcp_gating import set_mcp_intent

        set_mcp_intent("")
        tools = asyncio.run(server.list_tools())
        # Should return all tools (56 total)
        assert len(tools) >= 50
        # All schemas should have properties (full schema)
        full_count = sum(1 for t in tools if t.inputSchema.get("properties"))
        assert full_count >= 50

    def test_list_tools_with_intent_returns_gated(self, server):
        """With intent set, some tools get compact schemas."""
        import asyncio

        from animus.mcp_gating import set_mcp_intent

        set_mcp_intent("search memory")
        tools = asyncio.run(server.list_tools())
        # Should still return all tools
        assert len(tools) >= 50
        # But some should have compact schemas
        compact_count = sum(
            1 for t in tools if t.inputSchema.get("description", "").startswith("Compact")
        )
        assert compact_count > 0
        # Core tools should still be full
        recall = next((t for t in tools if t.name == "animus_recall"), None)
        assert recall is not None
        assert recall.inputSchema.get("properties") is not None

    def test_set_intent_tool(self, server):
        result = _run(server.call_tool("animus_set_intent", {"intent": "fix tests"}))
        text = result[0][0].text
        assert "Intent set" in text
        assert "fix tests" in text

    def test_set_intent_updates_max_full(self, server):
        result = _run(
            server.call_tool(
                "animus_set_intent",
                {"intent": "fix tests", "max_full_schemas": 10},
            )
        )
        text = result[0][0].text
        assert "top-10" in text


class TestMCPAuthHardening:
    """SEC-04 — harden MCP authentication, authorization, and execution."""

    @pytest.fixture
    def auth_server(self, tmp_path):
        """Create an MCP server in authenticated mode with a configured key."""
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer") as mock_mem_cls,
            patch("animus.mcp_server.TaskTracker") as mock_tasks_cls,
            patch("animus.mcp_server._MCP_API_KEY", "supersecret"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            cfg.memory.backend = "json"
            mock_config_cls.load.return_value = cfg
            mock_mem_cls.return_value = MagicMock()
            mock_tasks_cls.return_value = MagicMock()

            from animus.mcp_server import create_mcp_server

            yield create_mcp_server()

    @pytest.fixture
    def local_server(self, tmp_path):
        """Create an MCP server in explicit local_stdio mode."""
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer") as mock_mem_cls,
            patch("animus.mcp_server.TaskTracker") as mock_tasks_cls,
            patch("animus.mcp_server._MCP_API_KEY", "supersecret"),
            patch("animus.mcp_server._MCP_DEPLOYMENT_MODE", MCPDeploymentMode.local_stdio),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            cfg.memory.backend = "json"
            mock_config_cls.load.return_value = cfg
            mock_mem_cls.return_value = MagicMock()
            mock_tasks_cls.return_value = MagicMock()

            from animus.mcp_server import create_mcp_server

            yield create_mcp_server()

    def test_check_auth_uses_constant_time_comparison(self, monkeypatch):
        """_check_auth must compare keys with secrets.compare_digest."""
        from animus.mcp_server import _check_auth

        calls = []

        def _capture_compare(a, b):
            calls.append((a, b))
            return False

        monkeypatch.setattr("secrets.compare_digest", _capture_compare)
        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            with patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ):
                _check_auth("wrong")

        assert len(calls) == 1
        assert calls[0] == ("wrong", "secret123")

    def test_check_auth_wrong_key_rejected(self):
        from animus.mcp_server import _check_auth

        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            with patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ):
                assert _check_auth("wrong") is not None
                assert "Invalid API key" in _check_auth("wrong")

    def test_check_auth_correct_key_allowed(self):
        from animus.mcp_server import _check_auth

        with (
            patch("animus.mcp_server._MCP_API_KEY", "secret123"),
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
        ):
            with patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ):
                assert _check_auth("secret123") is None

    def test_no_auth_local_mode_only_when_explicitly_configured(self, local_server):
        """Explicit local_stdio mode must ignore a configured key."""
        result = _run(local_server.call_tool("animus_remember", {"content": "test"}))
        assert "Authentication required" not in result[0][0].text
        assert "Stored memory" in result[0][0].text

    def test_authenticated_mode_blocks_without_key(self, auth_server):
        result = _run(auth_server.call_tool("animus_remember", {"content": "test"}))
        assert "Authentication required" in result[0][0].text

    def test_authenticated_mode_allows_with_correct_key(self, auth_server):
        result = _run(
            auth_server.call_tool(
                "animus_remember",
                {"content": "test", "api_key": "supersecret"},
            )
        )
        assert "Authentication required" not in result[0][0].text
        assert "Stored memory" in result[0][0].text

    def test_authenticated_mode_denies_incorrect_key(self, auth_server):
        result = _run(
            auth_server.call_tool(
                "animus_remember",
                {"content": "test", "api_key": "wrong"},
            )
        )
        assert "Authentication required" in result[0][0].text
        assert "Invalid API key" in result[0][0].text

    def test_remote_without_auth_fails_startup(self, tmp_path):
        with (
            patch("animus.mcp_server._MCP_DEPLOYMENT_MODE", MCPDeploymentMode.remote),
            patch("animus.mcp_server._MCP_API_KEY", None),
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config_cls.load.return_value = cfg

            from animus.mcp_server import create_mcp_server

            with pytest.raises(RuntimeError, match="remote deployment requires"):
                create_mcp_server()

    def test_authenticated_mode_with_empty_key_fails_startup(self, tmp_path):
        with (
            patch(
                "animus.mcp_server._MCP_DEPLOYMENT_MODE",
                MCPDeploymentMode.authenticated_local_network,
            ),
            patch("animus.mcp_server._MCP_API_KEY", ""),
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config_cls.load.return_value = cfg

            from animus.mcp_server import create_mcp_server

            with pytest.raises(RuntimeError, match="authenticated_local_network mode requires"):
                create_mcp_server()

    def test_create_mcp_server_defaults_to_deny_all_policy(self, tmp_path):
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config_cls.load.return_value = cfg

            from animus.mcp_server import create_mcp_server

            server = create_mcp_server()
            assert isinstance(server.policy, DenyAllToolPolicy)

    def test_create_mcp_server_accepts_explicit_policy(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        policy = WorkspaceToolPolicy(
            allowed_paths=[str(workspace)],
            write_roots=[str(workspace)],
            command_enabled=True,
        )
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config_cls.load.return_value = cfg

            from animus.mcp_server import create_mcp_server

            server = create_mcp_server(policy=policy)
            assert server.policy is policy

    def test_mcp_tool_allowlist_denies_unlisted_tool(self, auth_server):
        """An authenticated caller cannot invoke a tool outside the allowlist."""
        with patch("animus.mcp_server._MCP_ALLOWED_TOOLS", frozenset({"animus_recall"})):
            result = _run(
                auth_server.call_tool(
                    "animus_remember",
                    {"content": "test", "api_key": "supersecret"},
                )
            )
        assert "not in the MCP allowlist" in result[0][0].text

    def test_mcp_tool_allowlist_allows_listed_tool(self, auth_server):
        with patch("animus.mcp_server._MCP_ALLOWED_TOOLS", frozenset({"animus_recall"})):
            result = _run(
                auth_server.call_tool("animus_recall", {"query": "x", "api_key": "supersecret"})
            )
        assert "not in the MCP allowlist" not in result[0][0].text

    def test_request_size_limit_enforced(self, auth_server):
        """Oversized tool payloads are denied before reaching the handler."""
        auth_server.max_request_size = 50
        result = _run(
            auth_server.call_tool(
                "animus_remember",
                {
                    "content": "this payload is definitely larger than fifty bytes",
                    "api_key": "supersecret",
                },
            )
        )
        assert "payload size" in result[0][0].text
        assert "exceeds" in result[0][0].text

    def test_concurrency_limit_configured(self, tmp_path):
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_config_cls,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
            patch.dict("os.environ", {"ANIMUS_MCP_MAX_CONCURRENT_CALLS": "3"}, clear=False),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config_cls.load.return_value = cfg

            from animus.mcp_server import create_mcp_server

            server = create_mcp_server()
            assert server._concurrency_semaphore is not None
            assert server._concurrency_semaphore._value == 3

    def test_mcp_audit_logs_without_secrets(self, auth_server, caplog):
        import logging

        mcp_logger = logging.getLogger("animus.mcp_server")
        old_propagate = mcp_logger.propagate
        mcp_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="animus.mcp_server"):
                _run(
                    auth_server.call_tool(
                        "animus_remember",
                        {"content": "audit me", "api_key": "supersecret"},
                    )
                )
            audit_lines = [r for r in caplog.records if "MCP_AUDIT" in r.getMessage()]
            assert audit_lines, "expected MCP_AUDIT log record"
            assert "supersecret" not in audit_lines[0].getMessage()
            assert "caller=" in audit_lines[0].getMessage()
        finally:
            mcp_logger.propagate = old_propagate

    def test_workflow_registry_cannot_escape_workspace(self, tmp_path):
        """A registry built for an MCP workflow is sandboxed to its workspace."""
        workspace = tmp_path / "mcp_workflows" / "test_wf"
        workspace.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()

        workflow_policy = WorkspaceToolPolicy(
            allowed_paths=[str(tmp_path)],
            write_roots=[str(workspace)],
            command_enabled=True,
        )
        registry = create_default_registry(policy=workflow_policy)

        # Attempt to write outside the workspace should be denied.
        params = {"path": str(outside / "escaped.txt"), "content": "escape"}
        approval_id = registry.request_approval("write_file", params)
        params["_approval_id"] = approval_id
        result = registry.execute("write_file", params)
        assert result.success is False
        assert "not in write_roots" in result.error or "denied" in result.error.lower()

    def test_execute_registry_with_approval_requires_external_gate(self):
        from animus.mcp_server import _execute_registry_with_approval

        registry = ToolRegistry(policy=WorkspaceToolPolicy())

        def handler(params: dict) -> ToolResult:
            return ToolResult(tool_name="dangerous", success=True, output="ran")

        registry.register(
            Tool(
                name="dangerous",
                description="requires approval",
                parameters={},
                handler=handler,
                requires_approval=True,
            )
        )

        # Without an approval gate the helper must deny, not auto-approve.
        result = _run(_execute_registry_with_approval(registry, "dangerous", {}))
        assert result.success is False
        assert "ApprovalGate" in result.error

    def test_execute_registry_with_approval_allows_via_gate(self):
        from animus.mcp_server import _execute_registry_with_approval

        registry = ToolRegistry(policy=WorkspaceToolPolicy())

        def handler(params: dict) -> ToolResult:
            return ToolResult(tool_name="dangerous", success=True, output="ran")

        registry.register(
            Tool(
                name="dangerous",
                description="requires approval",
                parameters={},
                handler=handler,
                requires_approval=True,
            )
        )

        class AllowGate(ApprovalGate):
            async def request_decision(
                self,
                approval_store,
                tool_name,
                params,
                params_hash,
                request_id,
            ):
                return approval_store.request_approval(
                    tool_name=tool_name,
                    params_hash=params_hash,
                    requesting_actor="test",
                    scope="test",
                    expiry=datetime.now(timezone.utc) + timedelta(seconds=60),
                    decision="allow",
                    approver="external-gate",
                    reason="Mock external approval",
                )

        gate = AllowGate()
        result = _run(
            _execute_registry_with_approval(registry, "dangerous", {}, approval_gate=gate)
        )
        assert result.success is True
        assert result.output == "ran"
