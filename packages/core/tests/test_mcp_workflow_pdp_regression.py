"""Regression: an MCP workflow requires an explicit policy grant.

This is intentionally a red test until the MCP workflow entry point has an
enforced PDP gate. Engine and model work are mocked: no workflow executes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")


def test_mcp_workflow_without_capability_grant_does_not_execute(tmp_path):
    """Local-stdio transport trust must not imply workflow authorization."""
    from animus.mcp_server import MCPDeploymentMode, create_mcp_server

    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text("placeholder")

    workflow_config = MagicMock()
    workflow_config.name = "unauthorized_workflow"
    workflow_config.agents = []

    with (
        patch("animus.mcp_server._MCP_DEPLOYMENT_MODE", MCPDeploymentMode.local_stdio),
        patch("animus.mcp_server._MCP_API_KEY", None),
        patch("animus.mcp_server.AnimusConfig") as config_cls,
        patch("animus.mcp_server.MemoryLayer"),
        patch("animus.mcp_server.TaskTracker"),
        patch("animus.mcp_server.EgressAuditLog"),
        patch("animus.forge.loader.load_workflow", return_value=workflow_config),
        patch("animus.cognitive.CognitiveLayer"),
        patch("animus.cognitive.ModelConfig"),
        patch("animus.tools.create_default_registry"),
        patch("animus.forge.ForgeEngine") as engine_cls,
    ):
        config = MagicMock()
        config.data_dir = tmp_path
        config.memory.backend = "local"
        config_cls.load.return_value = config

        server = create_mcp_server()
        response = asyncio.run(
            server.call_tool(
                "animus_run_workflow",
                {"workflow_path": str(workflow_file)},
            )
        )

        # There is no capability grant or explicit ALLOW decision in this test.
        # Authorization must fail before the engine (or model) is constructed.
        engine_cls.assert_not_called()
        assert "denied" in response[0][0].text.lower() or "authorization" in response[0][0].text.lower()
