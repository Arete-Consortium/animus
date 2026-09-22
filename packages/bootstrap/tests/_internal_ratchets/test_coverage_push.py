"""Targeted tests to push coverage from 92% to 95%+.

Covers uncovered lines in: cli.py, mcp_bridge.py, api_keys.py,
dashboard/routers/tools.py, forge_ctl.py, identity.py, forge_page.py,
logs.py, animus_backend.py, timers_page.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from animus_bootstrap.cli import app
from animus_bootstrap.config.schema import (
    AnimusConfig,
    AnimusSection,
    ApiSection,
    ForgeSection,
    IdentitySection,
    MemorySection,
    ServicesSection,
)
from animus_bootstrap.intelligence.tools.executor import ToolDefinition

runner = CliRunner()


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _make_config(**overrides: object) -> AnimusConfig:
    """Build an AnimusConfig with sensible test defaults."""
    kwargs: dict[str, object] = {
        "animus": AnimusSection(version="0.1.0", first_run=False, data_dir="/tmp/animus-test"),
        "api": ApiSection(anthropic_key="sk-ant-xxxx1234abcd5678", openai_key="sk-oai-yyyy"),
        "forge": ForgeSection(enabled=False, host="localhost", port=8000),
        "memory": MemorySection(backend="sqlite", path="/tmp/animus-test/memory.db"),
        "identity": IdentitySection(name="Tester", timezone="US/Eastern", locale="en_US"),
        "services": ServicesSection(autostart=True, port=7700, log_level="info"),
    }
    kwargs.update(overrides)
    return AnimusConfig(**kwargs)


def _mock_config_manager(config: AnimusConfig | None = None) -> MagicMock:
    """Create a mock ConfigManager instance."""
    if config is None:
        config = _make_config()
    mock = MagicMock()
    mock.load.return_value = config
    mock.exists.return_value = True
    mock.get_config_path.return_value = Path("/tmp/animus-test/config.toml")
    return mock


def _mock_installer(*, running: bool = True, os_name: str = "linux") -> MagicMock:
    """Create a mock AnimusInstaller."""
    mock = MagicMock()
    mock.is_service_running.return_value = running
    mock.detect_os.return_value = os_name
    mock.start_service.return_value = True
    mock.stop_service.return_value = True
    mock.check_dependencies.return_value = {"python3": True, "pip": True, "ollama": False}
    mock.install_missing_deps.return_value = []
    mock.register_service.return_value = True
    return mock


def _template_dir() -> Path:
    """Resolve the dashboard templates directory."""
    return (
        Path(__file__).resolve().parents[2] / "src" / "animus_bootstrap" / "dashboard" / "templates"
    )


def _mock_httpx_async_client(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a mock for httpx.AsyncClient as an async context manager."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = json.dumps(json_data or {})
    mock_resp.json.return_value = json_data or {}

    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_resp)

    mock_cls = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    ctx.__aexit__ = AsyncMock(return_value=False)
    mock_cls.return_value = ctx

    return mock_cls


# ===========================================================================
# 1. CLI Tests — install, status (forge paths), dashboard
# ===========================================================================


class TestInstallCommand:
    """Cover cli.py:73-126 — install command paths."""

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.setup.wizard.AnimusWizard")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_first_run(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_wizard_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        config = _make_config(animus=AnimusSection(version="0.1.0", first_run=True))
        mock_mgr = _mock_config_manager(config)
        mock_config_cls.return_value = mock_mgr
        mock_installer_cls.return_value = _mock_installer()

        mock_wizard_inst = MagicMock()
        mock_wizard_cls.return_value = mock_wizard_inst

        result = runner.invoke(app, ["install"])
        assert result.exit_code == 0
        assert "Checking dependencies" in result.output
        assert "Service registered" in result.output
        mock_wizard_inst.run.assert_called_once()

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_skip_wizard(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        config = _make_config()
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()

        result = runner.invoke(app, ["install", "--skip-wizard"])
        assert result.exit_code == 0
        assert "Dashboard available" in result.output

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_config_exists_no_first_run(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        config = _make_config()
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()

        result = runner.invoke(app, ["install"])
        assert result.exit_code == 0
        assert "Config already exists" in result.output

    @patch("animus_bootstrap.cli.webbrowser.open", side_effect=Exception("no browser"))
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_webbrowser_fails(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        config = _make_config()
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()

        result = runner.invoke(app, ["install", "--skip-wizard"])
        assert result.exit_code == 0
        assert "Could not open browser" in result.output

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_service_registration_fails(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        inst = _mock_installer()
        inst.register_service.return_value = False
        mock_installer_cls.return_value = inst
        mock_config_cls.return_value = _mock_config_manager()

        result = runner.invoke(app, ["install", "--skip-wizard"])
        assert result.exit_code == 0
        assert "may need manual setup" in result.output

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_service_start_fails(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        inst = _mock_installer()
        inst.start_service.return_value = False
        mock_installer_cls.return_value = inst
        mock_config_cls.return_value = _mock_config_manager()

        result = runner.invoke(app, ["install", "--skip-wizard"])
        assert result.exit_code == 0
        assert "Could not start service" in result.output

    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    def test_install_missing_deps(
        self,
        mock_installer_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
    ) -> None:
        inst = _mock_installer()
        inst.check_dependencies.return_value = {"python3": True, "pip": False}
        inst.install_missing_deps.return_value = ["pip"]
        mock_installer_cls.return_value = inst
        mock_config_cls.return_value = _mock_config_manager()

        result = runner.invoke(app, ["install", "--skip-wizard"])
        assert result.exit_code == 0
        assert "pip" in result.output


class TestStatusForgeEnabled:
    """Cover cli.py:213-225 — status with forge enabled and various health states."""

    @patch("httpx.get")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_status_forge_connected(
        self,
        mock_config_cls: MagicMock,
        mock_installer_cls: MagicMock,
        mock_httpx_get: MagicMock,
    ) -> None:
        config = _make_config(forge=ForgeSection(enabled=True, host="localhost", port=8000))
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx_get.return_value = mock_resp

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Connected" in result.output

    @patch("httpx.get")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_status_forge_unhealthy(
        self,
        mock_config_cls: MagicMock,
        mock_installer_cls: MagicMock,
        mock_httpx_get: MagicMock,
    ) -> None:
        config = _make_config(forge=ForgeSection(enabled=True, host="localhost", port=8000))
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_httpx_get.return_value = mock_resp

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Unhealthy" in result.output

    @patch("httpx.get")
    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_status_forge_unreachable(
        self,
        mock_config_cls: MagicMock,
        mock_installer_cls: MagicMock,
        mock_httpx_get: MagicMock,
    ) -> None:
        import httpx

        config = _make_config(forge=ForgeSection(enabled=True, host="localhost", port=8000))
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()
        mock_httpx_get.side_effect = httpx.RequestError("connection refused")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Unreachable" in result.output

    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_status_memory_no_data(
        self,
        mock_config_cls: MagicMock,
        mock_installer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = _make_config(
            memory=MemorySection(backend="sqlite", path=str(tmp_path / "nope.db"))
        )
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No data yet" in result.output

    @patch("animus_bootstrap.daemon.installer.AnimusInstaller")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_status_no_identity(
        self,
        mock_config_cls: MagicMock,
        mock_installer_cls: MagicMock,
    ) -> None:
        config = _make_config(identity=IdentitySection(name="", timezone="UTC", locale="en_US"))
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_installer_cls.return_value = _mock_installer()

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Not set" in result.output


class TestDashboardCommand:
    """Cover cli.py:293-308 — dashboard command."""

    @patch("animus_bootstrap.dashboard.app.serve")
    @patch("animus_bootstrap.cli.webbrowser.open")
    @patch("animus_bootstrap.config.ConfigManager")
    def test_dashboard_launches(
        self,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
        mock_serve: MagicMock,
    ) -> None:
        config = _make_config()
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_serve.return_value = None

        result = runner.invoke(app, ["dashboard"])
        assert result.exit_code == 0
        mock_serve.assert_called_once()

    @patch("animus_bootstrap.dashboard.app.serve")
    @patch("animus_bootstrap.cli.webbrowser.open", side_effect=Exception("no browser"))
    @patch("animus_bootstrap.config.ConfigManager")
    def test_dashboard_webbrowser_fails(
        self,
        mock_config_cls: MagicMock,
        mock_webbrowser: MagicMock,
        mock_serve: MagicMock,
    ) -> None:
        config = _make_config()
        mock_config_cls.return_value = _mock_config_manager(config)
        mock_serve.return_value = None

        result = runner.invoke(app, ["dashboard"])
        assert result.exit_code == 0


class TestChannelsCommands:
    """Cover cli.py:425 and channels enable/disable paths."""

    @patch("animus_bootstrap.config.ConfigManager")
    def test_channels_enable_unknown(self, mock_config_cls: MagicMock) -> None:
        mock_config_cls.return_value = _mock_config_manager()
        result = runner.invoke(app, ["channels", "enable", "fakechannel"])
        assert result.exit_code == 1
        assert "Unknown channel" in result.output

    @patch("animus_bootstrap.config.ConfigManager")
    def test_channels_disable_unknown(self, mock_config_cls: MagicMock) -> None:
        mock_config_cls.return_value = _mock_config_manager()
        result = runner.invoke(app, ["channels", "disable", "fakechannel"])
        assert result.exit_code == 1
        assert "Unknown channel" in result.output

    @patch("animus_bootstrap.config.ConfigManager")
    def test_channels_list(self, mock_config_cls: MagicMock) -> None:
        mock_config_cls.return_value = _mock_config_manager()
        result = runner.invoke(app, ["channels", "list"])
        assert result.exit_code == 0
        assert "Messaging Channels" in result.output

    @patch("animus_bootstrap.config.ConfigManager")
    def test_channels_enable_valid(self, mock_config_cls: MagicMock) -> None:
        mock_mgr = _mock_config_manager()
        mock_config_cls.return_value = mock_mgr
        result = runner.invoke(app, ["channels", "enable", "webchat"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    @patch("animus_bootstrap.config.ConfigManager")
    def test_channels_disable_valid(self, mock_config_cls: MagicMock) -> None:
        mock_mgr = _mock_config_manager()
        mock_config_cls.return_value = mock_mgr
        result = runner.invoke(app, ["channels", "disable", "webchat"])
        assert result.exit_code == 0
        assert "disabled" in result.output


class TestPersonasListWithProfiles:
    """Cover cli.py:577 — personas list with profiles."""

    @patch("animus_bootstrap.config.ConfigManager")
    def test_personas_list_with_profile(self, mock_config_cls: MagicMock) -> None:
        config = _make_config()
        # Add a profile to personas
        from animus_bootstrap.config.schema import PersonaProfileConfig

        config.personas.profiles["tech"] = PersonaProfileConfig(
            name="TechBot", tone="technical", knowledge_domains=["python", "rust"]
        )
        mock_config_cls.return_value = _mock_config_manager(config)

        result = runner.invoke(app, ["personas", "list"])
        assert result.exit_code == 0
        assert "TechBot" in result.output
        assert "python" in result.output


# ===========================================================================
# 2. MCP Bridge Tests
# ===========================================================================


class TestMCPServerConnection:
    """Cover mcp_bridge.py — MCPServerConnection send_request paths."""

    def test_send_request_no_pipes(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = None
        proc.stdout = None
        conn = MCPServerConnection("test", proc)

        with pytest.raises(RuntimeError, match="no stdio pipes"):
            _run(conn.send_request("test"))

    def test_send_request_timeout(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)
        conn = MCPServerConnection("test", proc)

        with pytest.raises(TimeoutError, match="timed out"):
            _run(conn.send_request("test"))

    def test_send_request_empty_response(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(return_value=b"")
        conn = MCPServerConnection("test", proc)

        with pytest.raises(RuntimeError, match="closed stdout"):
            _run(conn.send_request("test"))

    def test_send_request_invalid_json(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(return_value=b"not json\n")
        conn = MCPServerConnection("test", proc)

        with pytest.raises(RuntimeError, match="invalid JSON"):
            _run(conn.send_request("test"))

    def test_send_request_error_response(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "bad request"}})
        proc.stdout.readline = AsyncMock(return_value=resp.encode() + b"\n")
        conn = MCPServerConnection("test", proc)

        with pytest.raises(RuntimeError, match="bad request"):
            _run(conn.send_request("test"))

    def test_send_request_success(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
        proc.stdout.readline = AsyncMock(return_value=resp.encode() + b"\n")
        conn = MCPServerConnection("test", proc)

        result = _run(conn.send_request("tools/list"))
        assert result == {"tools": []}

    def test_close_running_process(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.returncode = None
        proc.terminate = MagicMock()
        proc.wait = AsyncMock()
        conn = MCPServerConnection("test", proc)

        _run(conn.close())
        proc.terminate.assert_called_once()

    def test_close_kills_on_timeout(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPServerConnection

        proc = MagicMock()
        proc.returncode = None
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock(side_effect=asyncio.TimeoutError)
        conn = MCPServerConnection("test", proc)

        _run(conn.close())
        proc.kill.assert_called_once()


class TestMCPToolBridge:
    """Cover mcp_bridge.py — MCPToolBridge discovery, import, and call paths."""

    def test_discover_servers_no_config(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge(config_path=None)
        result = _run(bridge.discover_servers())
        assert result == []

    def test_discover_servers_missing_file(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge(config_path=tmp_path / "missing.json")
        result = _run(bridge.discover_servers())
        assert result == []

    def test_discover_servers_invalid_json(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        cfg_file = tmp_path / "mcp.json"
        cfg_file.write_text("not json")
        bridge = MCPToolBridge(config_path=cfg_file)
        result = _run(bridge.discover_servers())
        assert result == []

    def test_discover_servers_not_dict(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        cfg_file = tmp_path / "mcp.json"
        cfg_file.write_text(json.dumps({"mcpServers": "not a dict"}))
        bridge = MCPToolBridge(config_path=cfg_file)
        result = _run(bridge.discover_servers())
        assert result == []

    def test_discover_servers_success(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        cfg_file = tmp_path / "mcp.json"
        cfg_file.write_text(
            json.dumps({"mcpServers": {"test-server": {"command": "node", "args": ["server.js"]}}})
        )
        bridge = MCPToolBridge(config_path=cfg_file)
        result = _run(bridge.discover_servers())
        assert result == ["test-server"]

    def test_import_tools_unknown_server(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge()
        result = _run(bridge.import_tools("nonexistent"))
        assert result == []

    def test_start_server_no_command(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge()
        bridge._servers = {"empty": {"command": ""}}

        with pytest.raises(ValueError, match="no command"):
            _run(bridge._start_server("empty"))

    def test_start_server_command_not_found(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge()
        bridge._servers = {"bad": {"command": "/nonexistent_binary_xyz"}}

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
            with pytest.raises(FileNotFoundError, match="not found"):
                _run(bridge._start_server("bad"))

    def test_import_tools_server_start_fails(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge()
        bridge._servers = {"fail": {"command": "/bad"}}

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("fail")):
            result = _run(bridge.import_tools("fail"))
            assert result == []

    def test_call_tool_not_connected(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import MCPToolBridge

        bridge = MCPToolBridge()
        result = _run(bridge.call_tool("missing", "tool", {}))
        assert "not connected" in result

    def test_call_tool_request_fails(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import (
            MCPServerConnection,
            MCPToolBridge,
        )

        bridge = MCPToolBridge()
        conn = MagicMock(spec=MCPServerConnection)
        conn.send_request = AsyncMock(side_effect=TimeoutError("timeout"))
        bridge._connections["srv"] = conn

        result = _run(bridge.call_tool("srv", "tool", {}))
        assert "failed" in result

    def test_call_tool_text_content(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import (
            MCPServerConnection,
            MCPToolBridge,
        )

        bridge = MCPToolBridge()
        conn = MagicMock(spec=MCPServerConnection)
        conn.send_request = AsyncMock(return_value={"content": [{"type": "text", "text": "hello"}]})
        bridge._connections["srv"] = conn

        result = _run(bridge.call_tool("srv", "tool", {}))
        assert result == "hello"

    def test_call_tool_non_text_content(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import (
            MCPServerConnection,
            MCPToolBridge,
        )

        bridge = MCPToolBridge()
        conn = MagicMock(spec=MCPServerConnection)
        conn.send_request = AsyncMock(return_value={"content": [{"type": "image", "data": "abc"}]})
        bridge._connections["srv"] = conn

        result = _run(bridge.call_tool("srv", "tool", {}))
        # No text items → falls back to json.dumps
        assert "content" in result

    def test_call_tool_non_list_content(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import (
            MCPServerConnection,
            MCPToolBridge,
        )

        bridge = MCPToolBridge()
        conn = MagicMock(spec=MCPServerConnection)
        conn.send_request = AsyncMock(return_value={"content": "raw string"})
        bridge._connections["srv"] = conn

        result = _run(bridge.call_tool("srv", "tool", {}))
        assert "raw string" in result

    def test_close_all(self) -> None:
        from animus_bootstrap.intelligence.tools.mcp_bridge import (
            MCPServerConnection,
            MCPToolBridge,
        )

        bridge = MCPToolBridge()
        conn1 = MagicMock(spec=MCPServerConnection)
        conn1.close = AsyncMock()
        conn2 = MagicMock(spec=MCPServerConnection)
        conn2.close = AsyncMock()
        bridge._connections = {"a": conn1, "b": conn2}

        _run(bridge.close())
        conn1.close.assert_awaited_once()
        conn2.close.assert_awaited_once()
        assert len(bridge._connections) == 0


# ===========================================================================
# 3. API Keys Step Tests
# ===========================================================================


class TestConfigureOllama:
    """Cover api_keys.py:95-140 — _configure_ollama paths."""

    def test_ollama_detected_with_models(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _configure_ollama

        console = Console(file=io.StringIO(), force_terminal=True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3.2"}, {"name": "codellama"}]}

        with patch("httpx.get", return_value=mock_resp):
            with patch("animus_bootstrap.setup.steps.api_keys.Prompt.ask", return_value="llama3.2"):
                result = _configure_ollama(console)

        assert result["ollama_enabled"] is True
        assert result["ollama_model"] == "llama3.2"

    def test_ollama_detected_no_models(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _configure_ollama

        console = Console(file=io.StringIO(), force_terminal=True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}

        with patch("httpx.get", return_value=mock_resp):
            with patch("animus_bootstrap.setup.steps.api_keys.Prompt.ask", return_value="llama3.2"):
                result = _configure_ollama(console)

        assert result["ollama_enabled"] is True
        assert result["ollama_model"] == "llama3.2"

    def test_ollama_not_available_connection_error(self) -> None:
        import httpx
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _configure_ollama

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = _configure_ollama(console)

        assert result["ollama_enabled"] is False

    def test_ollama_not_available_timeout(self) -> None:
        import httpx
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _configure_ollama

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "httpx.get",
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = _configure_ollama(console)

        assert result["ollama_enabled"] is False


class TestCollectAnthropicKey:
    """Cover api_keys.py:148-172 — _collect_anthropic_key retry paths."""

    def test_valid_key_first_attempt(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _collect_anthropic_key

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("animus_bootstrap.setup.steps.api_keys.Prompt.ask", return_value="sk-ant-valid"):
            with patch(
                "animus_bootstrap.setup.steps.api_keys.test_anthropic_key", return_value=True
            ):
                result = _collect_anthropic_key(console)

        assert result == "sk-ant-valid"

    def test_retry_then_success(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _collect_anthropic_key

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "animus_bootstrap.setup.steps.api_keys.Prompt.ask",
            side_effect=["bad-key", "sk-ant-valid"],
        ):
            with patch(
                "animus_bootstrap.setup.steps.api_keys.test_anthropic_key",
                side_effect=[False, True],
            ):
                result = _collect_anthropic_key(console)

        assert result == "sk-ant-valid"

    def test_retry_exhaustion(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import _collect_anthropic_key

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "animus_bootstrap.setup.steps.api_keys.Prompt.ask",
            side_effect=["bad1", "bad2", "bad3"],
        ):
            with patch(
                "animus_bootstrap.setup.steps.api_keys.test_anthropic_key",
                return_value=False,
            ):
                result = _collect_anthropic_key(console)

        assert result == ""


class TestRunApiKeys:
    """Cover api_keys.py:50-51, 73 — run_api_keys flow."""

    def test_ollama_only(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import run_api_keys

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "animus_bootstrap.setup.steps.api_keys.Confirm.ask",
            side_effect=[True, False, False],  # ollama=yes, anthropic=no, openai=no
        ):
            with patch(
                "animus_bootstrap.setup.steps.api_keys._configure_ollama",
                return_value={"ollama_enabled": True, "ollama_model": "llama3.2"},
            ):
                result = run_api_keys(console)

        assert result["ollama_enabled"] is True
        assert result["default_backend"] == "ollama"

    def test_no_provider_exits(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.api_keys import run_api_keys

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch(
            "animus_bootstrap.setup.steps.api_keys.Confirm.ask",
            side_effect=[False, False, False],  # all no
        ):
            with pytest.raises(SystemExit):
                run_api_keys(console)


# ===========================================================================
# 4. Tools Router Tests
# ===========================================================================


class TestToolsRouter:
    """Cover dashboard/routers/tools.py — approval flow, SSE, execute."""

    @pytest.fixture()
    def tools_app(self) -> FastAPI:
        from animus_bootstrap.dashboard.routers.tools import router

        test_app = FastAPI()
        test_app.include_router(router)

        from fastapi.templating import Jinja2Templates

        test_app.state.templates = Jinja2Templates(directory=str(_template_dir()))
        return test_app

    def test_tools_page_no_runtime(self, tools_app: FastAPI) -> None:
        # No runtime on app state
        client = TestClient(tools_app)
        resp = client.get("/tools")
        assert resp.status_code == 200

    def test_tools_page_with_runtime(self, tools_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.tool_executor.list_tools.return_value = [
            ToolDefinition(
                name="test_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {}},
                handler=AsyncMock(),
                category="test",
            )
        ]
        runtime.tool_executor.get_history.return_value = []
        tools_app.state.runtime = runtime

        client = TestClient(tools_app)
        resp = client.get("/tools")
        assert resp.status_code == 200

    def test_approve_tool_not_found(self, tools_app: FastAPI) -> None:
        client = TestClient(tools_app)
        resp = client.post("/tools/approve/nonexistent", data={"decision": "approve"})
        assert resp.status_code == 200
        assert "not found" in resp.text

    def test_approve_tool_approve(self, tools_app: FastAPI) -> None:
        from animus_bootstrap.dashboard.routers.tools import _pending_approvals

        event = asyncio.Event()
        _pending_approvals["test-id"] = {
            "tool_name": "shell_exec",
            "arguments": {"cmd": "ls"},
            "event": event,
            "approved": None,
        }

        client = TestClient(tools_app)
        resp = client.post("/tools/approve/test-id", data={"decision": "approve"})
        assert resp.status_code == 200
        assert "approved" in resp.text
        _pending_approvals.clear()

    def test_approve_tool_deny(self, tools_app: FastAPI) -> None:
        from animus_bootstrap.dashboard.routers.tools import _pending_approvals

        event = asyncio.Event()
        _pending_approvals["deny-id"] = {
            "tool_name": "shell_exec",
            "arguments": {},
            "event": event,
            "approved": None,
        }

        client = TestClient(tools_app)
        resp = client.post("/tools/approve/deny-id", data={"decision": "deny"})
        assert resp.status_code == 200
        assert "denied" in resp.text
        _pending_approvals.clear()

    def test_pending_approvals_none(self, tools_app: FastAPI) -> None:
        client = TestClient(tools_app)
        resp = client.get("/tools/pending")
        assert resp.status_code == 200
        assert "No pending approvals" in resp.text

    def test_pending_approvals_with_items(self, tools_app: FastAPI) -> None:
        from animus_bootstrap.dashboard.routers.tools import _pending_approvals

        _pending_approvals["p1"] = {
            "tool_name": "web_search",
            "arguments": {"query": "test"},
            "event": asyncio.Event(),
            "approved": None,
        }

        client = TestClient(tools_app)
        resp = client.get("/tools/pending")
        assert resp.status_code == 200
        assert "web_search" in resp.text
        _pending_approvals.clear()

    def test_execute_tool_no_runtime(self, tools_app: FastAPI) -> None:
        client = TestClient(tools_app)
        resp = client.post("/tools/execute", data={"tool_name": "test", "arguments_json": "{}"})
        assert resp.status_code == 200
        assert "No tool executor" in resp.text

    def test_execute_tool_invalid_json(self, tools_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.tool_executor = MagicMock()
        tools_app.state.runtime = runtime

        client = TestClient(tools_app)
        resp = client.post(
            "/tools/execute", data={"tool_name": "test", "arguments_json": "not json"}
        )
        assert resp.status_code == 200
        assert "Invalid JSON" in resp.text

    def test_execute_tool_unknown(self, tools_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.tool_executor.get_tool.return_value = None
        tools_app.state.runtime = runtime

        client = TestClient(tools_app)
        resp = client.post("/tools/execute", data={"tool_name": "nope", "arguments_json": "{}"})
        assert resp.status_code == 200
        assert "Unknown tool" in resp.text

    def test_execute_tool_success(self, tools_app: FastAPI) -> None:
        runtime = MagicMock()
        tool = MagicMock()
        runtime.tool_executor.get_tool.return_value = tool
        result_mock = MagicMock()
        result_mock.success = True
        result_mock.output = "executed"
        result_mock.duration_ms = 42.0
        runtime.tool_executor.execute = AsyncMock(return_value=result_mock)
        tools_app.state.runtime = runtime

        client = TestClient(tools_app)
        resp = client.post("/tools/execute", data={"tool_name": "echo", "arguments_json": "{}"})
        assert resp.status_code == 200
        assert "OK" in resp.text

    def test_execute_tool_failure_result(self, tools_app: FastAPI) -> None:
        runtime = MagicMock()
        tool = MagicMock()
        runtime.tool_executor.get_tool.return_value = tool
        result_mock = MagicMock()
        result_mock.success = False
        result_mock.output = "permission denied"
        result_mock.duration_ms = 5.0
        runtime.tool_executor.execute = AsyncMock(return_value=result_mock)
        tools_app.state.runtime = runtime

        client = TestClient(tools_app)
        resp = client.post(
            "/tools/execute", data={"tool_name": "shell_exec", "arguments_json": "{}"}
        )
        assert resp.status_code == 200
        assert "FAIL" in resp.text


class TestApprovalCallback:
    """Cover tools.py:89-93 — dashboard_approval_callback timeout."""

    def test_approval_timeout(self) -> None:
        from animus_bootstrap.dashboard.routers.tools import (
            _pending_approvals,
            dashboard_approval_callback,
        )

        async def run():
            # Patch wait_for to always timeout
            with patch(
                "animus_bootstrap.dashboard.routers.tools.asyncio.wait_for",
                side_effect=TimeoutError,
            ):
                return await dashboard_approval_callback("test_tool", {"arg": "val"})

        result = _run(run())
        assert result is False
        assert len(_pending_approvals) == 0


class TestNotifySSE:
    """Cover tools.py QueueFull path."""

    def test_notify_sse_queue_full(self) -> None:
        from animus_bootstrap.dashboard.routers.tools import _notify_sse, _sse_subscribers

        # Add a full queue
        full_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=1)
        full_queue.put_nowait({"event": "dummy", "data": "{}"})
        _sse_subscribers.append(full_queue)

        # Should remove the full queue
        _notify_sse("test", {"key": "value"})
        assert full_queue not in _sse_subscribers


# ===========================================================================
# 5. Forge Control Tests
# ===========================================================================


class TestForgeStatus:
    """Cover forge_ctl.py — _forge_status paths."""

    def test_forge_status_running(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_status

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_status())
        assert "Forge is running" in result

    def test_forge_status_bad_http(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_status

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_status())
        assert "HTTP 500" in result

    def test_forge_status_connect_error(self) -> None:
        import httpx

        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_status

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_status())
        assert "not reachable" in result

    def test_forge_status_http_error(self) -> None:
        import httpx

        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_status

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_status())
        assert "Error checking Forge" in result

    def test_forge_status_no_httpx(self) -> None:

        with patch.dict(sys.modules, {"httpx": None}):
            # Need to force reimport
            import importlib

            from animus_bootstrap.intelligence.tools.builtin import forge_ctl

            importlib.reload(forge_ctl)
            result = _run(forge_ctl._forge_status())
            assert "httpx not installed" in result
            importlib.reload(forge_ctl)


class TestForgeStart:
    """Cover forge_ctl.py — _forge_start paths."""

    def test_forge_start_already_running(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_start

        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"active\n", b""))
        proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = _run(_forge_start())
        assert "already running" in result

    def test_forge_start_systemd_success(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_start

        check_proc = MagicMock()
        check_proc.communicate = AsyncMock(return_value=(b"inactive\n", b""))
        check_proc.returncode = 3

        start_proc = MagicMock()
        start_proc.communicate = AsyncMock(return_value=(b"", b""))
        start_proc.returncode = 0

        call_count = 0

        async def mock_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return check_proc
            return start_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = _run(_forge_start())
        assert "started via systemd" in result

    def test_forge_start_no_systemctl_no_uvicorn(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_start

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = _run(_forge_start())
        assert "Neither systemctl nor uvicorn" in result


class TestForgeStop:
    """Cover forge_ctl.py — _forge_stop paths."""

    def test_forge_stop_systemd_success(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_stop

        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = _run(_forge_stop())
        assert "stopped via systemd" in result

    def test_forge_stop_pkill_fallback(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_stop

        exec_proc = MagicMock()
        exec_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        exec_proc.returncode = 1

        shell_proc = MagicMock()
        shell_proc.communicate = AsyncMock(return_value=(b"", b""))
        shell_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=exec_proc):
            with patch("asyncio.create_subprocess_shell", return_value=shell_proc):
                result = _run(_forge_stop())
        assert "killed" in result

    def test_forge_stop_nothing_to_stop(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_stop

        exec_proc = MagicMock()
        exec_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        exec_proc.returncode = 1

        shell_proc = MagicMock()
        shell_proc.communicate = AsyncMock(return_value=(b"", b""))
        shell_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=exec_proc):
            with patch("asyncio.create_subprocess_shell", return_value=shell_proc):
                result = _run(_forge_stop())
        assert "No Forge process" in result

    def test_forge_stop_oserror(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_stop

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with patch("asyncio.create_subprocess_shell", side_effect=OSError("no pkill")):
                result = _run(_forge_stop())
        assert "Error stopping Forge" in result


class TestForgeInvoke:
    """Cover forge_ctl.py — _forge_invoke paths."""

    def test_invoke_post(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"result": "ok"}'
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api/v1/workflows", method="POST", body='{"key": "val"}'))
        assert "HTTP 200" in result

    def test_invoke_put(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api/v1/thing", method="PUT"))
        assert "HTTP 200" in result

    def test_invoke_delete(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.text = ""
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api/v1/thing/1", method="DELETE"))
        assert "HTTP 204" in result

    def test_invoke_unsupported_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api", method="PATCH"))
        assert "Unsupported HTTP method" in result

    def test_invoke_invalid_json_body(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api", method="POST", body="not json"))
        assert "Invalid JSON body" in result

    def test_invoke_connect_error(self) -> None:
        import httpx

        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api"))
        assert "not reachable" in result

    def test_invoke_http_error(self) -> None:
        import httpx

        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import _forge_invoke

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(_forge_invoke("/api"))
        assert "invoke error" in result

    def test_get_forge_tools(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.forge_ctl import get_forge_tools

        tools = get_forge_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "forge_status" in names
        assert "forge_start" in names
        assert "forge_stop" in names
        assert "forge_invoke" in names


# ===========================================================================
# 6. Identity Step Tests
# ===========================================================================


class TestIdentityStep:
    """Cover identity.py:52-61 — _detect_timezone paths."""

    def test_detect_timezone_success(self) -> None:
        from animus_bootstrap.setup.steps.identity import _detect_timezone

        tz = _detect_timezone()
        # Should return a non-empty string
        assert isinstance(tz, str)
        assert len(tz) > 0

    def test_detect_timezone_value_error(self) -> None:
        from animus_bootstrap.setup.steps.identity import _detect_timezone

        with patch("animus_bootstrap.setup.steps.identity.datetime") as mock_dt:
            mock_dt.datetime.now.return_value.astimezone.side_effect = ValueError("bad")
            tz = _detect_timezone()
        assert tz == "UTC"

    def test_detect_timezone_os_error(self) -> None:
        from animus_bootstrap.setup.steps.identity import _detect_timezone

        with patch("animus_bootstrap.setup.steps.identity.datetime") as mock_dt:
            mock_dt.datetime.now.return_value.astimezone.side_effect = OSError("no tz")
            tz = _detect_timezone()
        assert tz == "UTC"

    def test_detect_timezone_none_tzinfo(self) -> None:
        from animus_bootstrap.setup.steps.identity import _detect_timezone

        with patch("animus_bootstrap.setup.steps.identity.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.astimezone.return_value.tzinfo = None
            mock_dt.datetime.now.return_value = mock_now
            tz = _detect_timezone()
        assert tz == "UTC"

    def test_detect_timezone_empty_name(self) -> None:
        from animus_bootstrap.setup.steps.identity import _detect_timezone

        with patch("animus_bootstrap.setup.steps.identity.datetime") as mock_dt:
            mock_tz = MagicMock()
            mock_tz.__str__ = MagicMock(return_value="")
            mock_now = MagicMock()
            mock_now.astimezone.return_value.tzinfo = mock_tz
            mock_dt.datetime.now.return_value = mock_now
            tz = _detect_timezone()
        assert tz == "UTC"

    def test_run_identity_override_timezone(self) -> None:
        from rich.console import Console

        from animus_bootstrap.setup.steps.identity import run_identity

        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("animus_bootstrap.setup.steps.identity._detect_timezone", return_value="EST"):
            with patch(
                "animus_bootstrap.setup.steps.identity.Prompt.ask",
                side_effect=["TestUser", "America/New_York", "en_US"],
            ):
                with patch("animus_bootstrap.setup.steps.identity.Confirm.ask", return_value=False):
                    result = run_identity(console)

        assert result["name"] == "TestUser"
        assert result["timezone"] == "America/New_York"


# ===========================================================================
# 7. Forge Page Tests
# ===========================================================================


class TestForgePageRouter:
    """Cover forge_page.py:47-53 — error paths."""

    @pytest.fixture()
    def forge_app(self) -> FastAPI:
        from animus_bootstrap.dashboard.routers.forge_page import router

        test_app = FastAPI()
        test_app.include_router(router)

        from fastapi.templating import Jinja2Templates

        test_app.state.templates = Jinja2Templates(directory=str(_template_dir()))
        return test_app

    def test_forge_page_no_runtime(self, forge_app: FastAPI) -> None:
        client = TestClient(forge_app)
        resp = client.get("/forge")
        assert resp.status_code == 200

    def test_forge_page_forge_disabled(self, forge_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.config.forge.enabled = False
        forge_app.state.runtime = runtime

        client = TestClient(forge_app)
        resp = client.get("/forge")
        assert resp.status_code == 200

    @patch("httpx.AsyncClient")
    def test_forge_page_connection_error(
        self, mock_client_cls: MagicMock, forge_app: FastAPI
    ) -> None:
        runtime = MagicMock()
        runtime.config.forge.enabled = True
        runtime.config.forge.host = "localhost"
        runtime.config.forge.port = 8000
        forge_app.state.runtime = runtime

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("connection failed"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = ctx

        client = TestClient(forge_app)
        resp = client.get("/forge")
        assert resp.status_code == 200

    @patch("httpx.AsyncClient")
    def test_forge_page_http_error_status(
        self, mock_client_cls: MagicMock, forge_app: FastAPI
    ) -> None:
        runtime = MagicMock()
        runtime.config.forge.enabled = True
        runtime.config.forge.host = "localhost"
        runtime.config.forge.port = 8000
        forge_app.state.runtime = runtime

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = ctx

        client = TestClient(forge_app)
        resp = client.get("/forge")
        assert resp.status_code == 200

    @patch("httpx.AsyncClient")
    def test_forge_page_running(self, mock_client_cls: MagicMock, forge_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.config.forge.enabled = True
        runtime.config.forge.host = "localhost"
        runtime.config.forge.port = 8000
        forge_app.state.runtime = runtime

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = ctx

        client = TestClient(forge_app)
        resp = client.get("/forge")
        assert resp.status_code == 200


# ===========================================================================
# 8. Logs Router Tests
# ===========================================================================


class TestLogsRouter:
    """Cover logs.py:27-36 — _tail_log with existing file."""

    def test_tail_log_reads_new_lines(self, tmp_path: Path) -> None:
        """Test that _tail_log reads newly appended lines from a file.

        The generator seeks to end first, so we need to append AFTER it opens.
        We use a sleep side-effect to write a line then raise to break the loop.
        """
        from animus_bootstrap.dashboard.routers import logs

        log_file = tmp_path / "animus.log"
        log_file.write_text("")  # Start empty

        call_count = 0

        async def mock_sleep(_):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Append a line to simulate new log output
                with open(log_file, "a") as f:
                    f.write("new_line\n")
            else:
                raise asyncio.CancelledError

        with patch.object(logs, "_LOG_FILE", log_file):
            with patch(
                "animus_bootstrap.dashboard.routers.logs.asyncio.sleep", side_effect=mock_sleep
            ):

                async def collect():
                    events = []
                    try:
                        async for event in logs._tail_log():
                            events.append(event)
                    except asyncio.CancelledError:
                        return events  # Expected: tail cancelled after yielding
                    return events

                events = _run(collect())
                assert len(events) == 1
                assert events[0]["data"] == "new_line"

    def test_tail_log_no_file(self) -> None:
        from animus_bootstrap.dashboard.routers import logs

        with patch.object(logs, "_LOG_FILE") as mock_path:
            mock_path.is_file.return_value = False

            async def collect():
                events = []
                async for event in logs._tail_log():
                    events.append(event)
                return events

            events = _run(collect())
            assert len(events) == 1
            assert events[0]["data"] == "No logs yet"

    def test_tail_log_empty_file(self, tmp_path: Path) -> None:
        """Verify _tail_log opens an empty file and enters the sleep loop."""
        from animus_bootstrap.dashboard.routers import logs

        log_file = tmp_path / "animus.log"
        log_file.write_text("")  # empty file

        with patch.object(logs, "_LOG_FILE", log_file):
            with patch(
                "animus_bootstrap.dashboard.routers.logs.asyncio.sleep",
                side_effect=asyncio.CancelledError,
            ):

                async def collect():
                    events = []
                    try:
                        async for event in logs._tail_log():
                            events.append(event)
                    except asyncio.CancelledError:
                        return events  # Expected: sleep cancelled, no events
                    return events

                events = _run(collect())
                # Empty file — no lines yielded, sleep triggered then broke
                assert events == []


# ===========================================================================
# 9. Animus Backend Tests
# ===========================================================================


class TestAnimusBackend:
    """Cover animus_backend.py — ImportError fallback and creation."""

    def test_import_error_fallback(self, tmp_path) -> None:
        from animus_bootstrap.intelligence.memory_backends.animus_backend import (
            AnimusMemoryBackend,
        )

        with patch.dict(sys.modules, {"animus": None, "animus.memory": None}):
            with pytest.raises(RuntimeError, match="animus-core is not installed"):
                AnimusMemoryBackend(data_dir=tmp_path / "mem")

    def test_creates_backend_when_core_available(self, tmp_path) -> None:
        from animus_bootstrap.intelligence.memory_backends.animus_backend import (
            AnimusMemoryBackend,
        )

        try:
            b = AnimusMemoryBackend(data_dir=tmp_path / "mem")
            assert (tmp_path / "mem").exists()
            b.close()
        except RuntimeError:
            pytest.skip("animus-core not installed")


# ===========================================================================
# 10. Timers Page Tests
# ===========================================================================


class TestTimersPage:
    """Cover timers_page.py:30-33 — runtime with proactive_engine."""

    @pytest.fixture()
    def timers_app(self) -> FastAPI:
        from animus_bootstrap.dashboard.routers.timers_page import router

        test_app = FastAPI()
        test_app.include_router(router)

        from fastapi.templating import Jinja2Templates

        test_app.state.templates = Jinja2Templates(directory=str(_template_dir()))
        return test_app

    def test_timers_no_runtime(self, timers_app: FastAPI) -> None:
        client = TestClient(timers_app)
        resp = client.get("/timers")
        assert resp.status_code == 200

    def test_timers_no_engine(self, timers_app: FastAPI) -> None:
        runtime = MagicMock()
        runtime.proactive_engine = None
        timers_app.state.runtime = runtime

        client = TestClient(timers_app)
        resp = client.get("/timers")
        assert resp.status_code == 200

    def test_timers_with_engine(self, timers_app: FastAPI) -> None:
        runtime = MagicMock()
        check = MagicMock()
        check.name = "timer:my_timer"
        check.schedule = "0 * * * *"
        check.enabled = True
        check.next_fire = None
        runtime.proactive_engine.list_checks.return_value = [check]
        timers_app.state.runtime = runtime

        client = TestClient(timers_app)
        resp = client.get("/timers")
        assert resp.status_code == 200

    def test_timers_with_non_timer_check(self, timers_app: FastAPI) -> None:
        runtime = MagicMock()
        check = MagicMock()
        check.name = "morning_brief"
        check.schedule = "0 7 * * *"
        check.enabled = True
        runtime.proactive_engine.list_checks.return_value = [check]
        timers_app.state.runtime = runtime

        client = TestClient(timers_app)
        resp = client.get("/timers")
        assert resp.status_code == 200
