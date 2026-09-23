"""MCP tool step handler for workflow execution.

Mixin class providing the ``mcp_tool`` step type so workflows can
invoke tools on registered MCP servers.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from animus_kernel.monitoring.mcp_tool_usage import record_mcp_tool_usage

from .loader import StepConfig

logger = logging.getLogger(__name__)


class MCPHandlersMixin:
    """Mixin providing the MCP tool step handler.

    Expects the following attributes from the host class:
    - dry_run: bool
    """

    def _execute_mcp_tool(self, step: StepConfig, context: dict) -> dict:
        """Execute an MCP tool step.

        Params (from ``step.params``):
            server: Server name or ID
            tool: Tool name on the server
            arguments: Tool-specific arguments (supports ``${var}`` substitution)
        """
        server_ref = step.params.get("server")
        tool_name = step.params.get("tool")

        if not server_ref:
            raise RuntimeError("mcp_tool step missing required param 'server'")
        if not tool_name:
            raise RuntimeError("mcp_tool step missing required param 'tool'")

        # Substitute variables in server/tool strings
        server_ref = self._substitute_mcp_string(server_ref, context)
        tool_name = self._substitute_mcp_string(tool_name, context)

        # Substitute variables in arguments (recursive for nested dicts)
        raw_arguments = step.params.get("arguments", {})
        arguments = self._substitute_mcp_arguments(raw_arguments, context)

        # Dry run mode
        if self.dry_run:
            return {
                "response": (
                    f"[DRY RUN] MCP tool '{tool_name}' on server "
                    f"'{server_ref}' with args: {arguments}"
                ),
                "server": server_ref,
                "tool": tool_name,
                "tokens_used": 0,
                "dry_run": True,
            }

        # Resolve server
        server = self._resolve_mcp_server(server_ref)

        # Build auth headers
        headers = self._get_mcp_auth_headers(server)

        # Parse stdio command vs SSE URL

        server_url = server.url
        server_type = server.type

        start_ms = time.monotonic()
        try:
            result = self._call_mcp_tool(
                server_type=server_type,
                server_url=server_url,
                tool_name=tool_name,
                arguments=arguments,
                headers=headers,
            )
        except Exception:
            # Record the failed attempt so the pruner can see which tools
            # are flaky as well as which go unused.
            record_mcp_tool_usage(
                workflow_id=getattr(self, "_current_workflow_id", "") or "",
                step_id=step.id,
                server=server.name,
                tool=tool_name,
                duration_ms=int((time.monotonic() - start_ms) * 1000),
                is_error=True,
            )
            raise

        duration_ms = int((time.monotonic() - start_ms) * 1000)
        content = result.get("content", "")
        is_error = result.get("is_error", False)

        record_mcp_tool_usage(
            workflow_id=getattr(self, "_current_workflow_id", "") or "",
            step_id=step.id,
            server=server.name,
            tool=tool_name,
            duration_ms=duration_ms,
            is_error=is_error,
        )

        if is_error:
            raise RuntimeError(
                f"MCP tool '{tool_name}' on '{server.name}' returned error: {content}"
            )

        return {
            "response": content,
            "server": server.name,
            "tool": tool_name,
            "tokens_used": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _substitute_mcp_string(self, value: str, context: dict) -> str:
        """Replace ``${var}`` placeholders in a string."""
        for key, val in context.items():
            if isinstance(val, str):
                value = value.replace(f"${{{key}}}", val)
        return value

    def _substitute_mcp_arguments(self, arguments: Any, context: dict) -> Any:
        """Recursively substitute ``${var}`` in argument values."""
        if isinstance(arguments, str):
            return self._substitute_mcp_string(arguments, context)
        if isinstance(arguments, dict):
            return {k: self._substitute_mcp_arguments(v, context) for k, v in arguments.items()}
        if isinstance(arguments, list):
            return [self._substitute_mcp_arguments(v, context) for v in arguments]
        # Non-string scalars (int, float, bool, None) pass through
        return arguments

    def _mcp_connector_manager(self) -> Any:
        """Applications supply their own connector/credential registry."""
        raise RuntimeError("MCP connector registry is not configured for this executor")

    def _call_mcp_tool(self, **kwargs: Any) -> dict:
        """Applications supply an MCP transport; Kernel owns no credentials."""
        raise RuntimeError("MCP transport is not configured for this executor")

    def _resolve_mcp_server(self, server_ref: str) -> Any:
        """Look up an MCP server by ID or name.

        Raises RuntimeError if not found.
        """
        manager = self._mcp_connector_manager()

        # Try by ID first (UUID pattern)
        _uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        if _uuid_re.match(server_ref):
            server = manager.get_server(server_ref)
            if server:
                return server

        # Try by name
        server = manager.get_server_by_name(server_ref)
        if server:
            return server

        raise RuntimeError(f"MCP server not found: '{server_ref}'")

    def _get_mcp_auth_headers(self, server: Any) -> dict[str, str] | None:
        """Build auth headers from server credential if configured."""
        if server.authType == "none" or not server.credentialId:
            return None

        manager = self._mcp_connector_manager()
        value = manager.get_credential_value(server.credentialId)
        if not value:
            logger.warning(
                "Credential %s for server %s not found",
                server.credentialId,
                server.name,
            )
            return None

        if server.authType == "bearer":
            return {"Authorization": f"Bearer {value}"}
        elif server.authType == "api_key":
            return {"X-API-Key": value}

        return None
