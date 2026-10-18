"""SEC-06 non-memory audit: verify raw secrets do not reach INFO/DEBUG logs.

Covers normal-operation log paths in the execution plane that were identified
as emitting full argument dictionaries or command lines containing secrets.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from animus_kernel.head.tool_orchestrator import HeadToolOrchestrator
from animus_kernel.tools.registry import ToolDefinition
from animus_kernel.tools_core import Tool, ToolRegistry, ToolResult


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def head_orchestrator(tmp_path: Path) -> HeadToolOrchestrator:
    """Minimal HeadToolOrchestrator with MCP disabled."""
    return HeadToolOrchestrator(
        project_root=tmp_path,
        memory_dir=tmp_path,
        enable_mcp=False,
    )


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Empty ToolRegistry ready for fake-tool registration."""
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Adversarial secret shapes (same corpus as SEC-08)
# ---------------------------------------------------------------------------

SECRET_SHAPES = [
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123",
    "ghp_abcdefghij1234567890ABCDEFGH",
    "Bearer abcdefghijklmnopqrstuvwxyz1234",
    "credential_value=test1234567890ABCDEF",
    "ssn_value=123-45-6789 on file",
    "ProprietaryProjectX-SECRET-SAUCE-2026",
]


# ---------------------------------------------------------------------------
# 1. HeadToolOrchestrator.execute() logs full arguments JSON at INFO
# ---------------------------------------------------------------------------


class TestHeadToolOrchestratorLogging:
    """HeadToolOrchestrator.execute() must never emit raw argument values."""

    @pytest.mark.parametrize("secret", SECRET_SHAPES)
    def test_execute_info_excludes_raw_arguments(
        self,
        head_orchestrator: HeadToolOrchestrator,
        caplog: pytest.LogCaptureFixture,
        secret: str,
    ) -> None:
        """INFO-level tool-call log must not contain the secret string."""
        head_orchestrator._head_tools["test_echo"] = ToolDefinition(
            name="test_echo",
            description="Inert test tool.",
            parameters={"type": "object", "properties": {}},
            handler=lambda _args: "ok",
        )
        with caplog.at_level(logging.INFO, logger="animus_kernel.head.tool_orchestrator"):
            head_orchestrator.execute("test_echo", {"api_key": secret, "query": "hello"})
        assert secret not in caplog.text

    def test_execute_info_preserves_tool_name_and_keys(
        self,
        head_orchestrator: HeadToolOrchestrator,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Operational metadata (tool name, argument keys) must remain visible."""
        head_orchestrator._head_tools["test_echo"] = ToolDefinition(
            name="test_echo",
            description="Inert test tool.",
            parameters={"type": "object", "properties": {}},
            handler=lambda _args: "ok",
        )
        with caplog.at_level(logging.INFO, logger="animus_kernel.head.tool_orchestrator"):
            head_orchestrator.execute("test_echo", {"path": "/tmp/test", "mode": "w"})
        assert "test_echo" in caplog.text
        assert "path" in caplog.text or "keys=" in caplog.text


# ---------------------------------------------------------------------------
# 2. ToolRegistry.execute() logs full params dict at DEBUG
# ---------------------------------------------------------------------------


class TestToolRegistryLogging:
    """ToolRegistry.execute() must never emit raw parameter values at DEBUG."""

    @pytest.mark.parametrize("secret", SECRET_SHAPES)
    def test_execute_debug_excludes_raw_params(
        self,
        tool_registry: ToolRegistry,
        caplog: pytest.LogCaptureFixture,
        secret: str,
    ) -> None:
        """DEBUG-level execution log must not contain the secret string."""
        tool_registry.register(
            Tool(
                name="test_tool",
                description="Inert test tool.",
                parameters={"type": "object", "properties": {}},
                handler=lambda _params: ToolResult(
                    tool_name="test_tool",
                    success=True,
                    output="ok",
                    error=None,
                ),
            )
        )
        with caplog.at_level(logging.DEBUG, logger="animus.tools"):
            tool_registry.execute("test_tool", {"api_key": secret, "query": "hello"})
        assert secret not in caplog.text

    def test_execute_debug_preserves_tool_name_and_keys(
        self,
        tool_registry: ToolRegistry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Operational metadata (tool name, param keys) must remain visible."""
        tool_registry.register(
            Tool(
                name="test_tool",
                description="Inert test tool.",
                parameters={"type": "object", "properties": {}},
                handler=lambda _params: ToolResult(
                    tool_name="test_tool",
                    success=True,
                    output="ok",
                    error=None,
                ),
            )
        )
        with caplog.at_level(logging.DEBUG, logger="animus.tools"):
            tool_registry.execute("test_tool", {"path": "/tmp/test", "mode": "w"})
        assert "test_tool" in caplog.text
        assert "path" in caplog.text or "keys=" in caplog.text
