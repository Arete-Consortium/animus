"""Compose Kernel execution with Forge-owned clients, storage, and agents."""

from animus_kernel.executor.executor_core import *  # noqa: F401,F403
from animus_kernel.executor.executor_core import WorkflowExecutor as KernelWorkflowExecutor

from .executor_agents import AgentStepHandlerMixin
from .executor_integrations import IntegrationHandlersMixin
from .executor_mcp import MCPHandlersMixin


class WorkflowExecutor(
    MCPHandlersMixin, AgentStepHandlerMixin, IntegrationHandlersMixin, KernelWorkflowExecutor
):
    """Kernel workflow engine with Forge's connector and credential boundary."""

    def _budget_store(self):
        from animus_forge.db import get_task_store

        return get_task_store()

    def _approval_store(self):
        from animus_forge.workflow.approval_store import get_approval_store

        return get_approval_store()

    def _claude_api_client(self):
        from .executor_clients import _get_claude_client

        return _get_claude_client()

    def _openai_api_client(self):
        from .executor_clients import _get_openai_client

        return _get_openai_client()
