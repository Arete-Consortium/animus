"""Compose Kernel execution with Forge-owned MCP connectors."""

from animus_kernel.executor.executor_core import *  # noqa: F401,F403
from animus_kernel.executor.executor_core import WorkflowExecutor as KernelWorkflowExecutor

from .executor_mcp import MCPHandlersMixin


class WorkflowExecutor(MCPHandlersMixin, KernelWorkflowExecutor):
    """Kernel workflow engine with Forge's connector and credential boundary."""
