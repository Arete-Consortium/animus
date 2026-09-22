"""Forge connector and credential adapters for Kernel's MCP step handler."""

from typing import Any

from animus_kernel.executor.executor_mcp import MCPHandlersMixin as KernelMCPHandlersMixin


class MCPHandlersMixin(KernelMCPHandlersMixin):
    def _mcp_connector_manager(self) -> Any:
        from animus_forge.mcp.manager import MCPConnectorManager
        from animus_forge.state.database import get_database

        return MCPConnectorManager(get_database())

    def _call_mcp_tool(self, **kwargs: Any) -> dict:
        from animus_forge.mcp.client import call_mcp_tool

        return call_mcp_tool(**kwargs)
