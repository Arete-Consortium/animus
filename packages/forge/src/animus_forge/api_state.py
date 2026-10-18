"""Shared mutable state for API modules.

All module-level globals live here so that both the lifespan (in api.py)
and route modules can reference the same objects.  Route modules should
import this *module* (not individual names) so they see lifespan updates:

    from animus_forge import api_state as state
    state.schedule_manager.list_schedules()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from slowapi import Limiter
from slowapi.util import get_remote_address

if TYPE_CHECKING:
    from animus_kernel.executor import WorkflowVersionManager

    from animus_forge.agents.process_registry import ProcessRegistry
    from animus_forge.agents.subagent_manager import SubAgentManager
    from animus_forge.agents.task_runner import AgentTaskRunner
    from animus_forge.budget import PersistentBudgetManager
    from animus_forge.db import TaskStore
    from animus_forge.executions import ExecutionManager
    from animus_forge.jobs import JobManager
    from animus_forge.mcp import MCPConnectorManager
    from animus_forge.scheduler import MissionScheduler, ScheduleManager
    from animus_forge.settings import SettingsManager
    from animus_forge.state.agent_memory import AgentMemory
    from animus_forge.webhooks import WebhookManager
    from animus_forge.webhooks.webhook_delivery import WebhookDeliveryManager
    from animus_forge.websocket import Broadcaster, ConnectionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Eagerly-initialized components (created at import time)
# ---------------------------------------------------------------------------
from animus_kernel.executor.arete_hooks import get_arete_hooks  # noqa: E402

from animus_forge.api_clients import OpenAIClient  # noqa: E402
from animus_forge.config import get_settings  # noqa: E402
from animus_forge.orchestrator.workflow_engine_adapter import WorkflowEngineAdapter  # noqa: E402
from animus_forge.prompts import PromptTemplateManager  # noqa: E402
from animus_forge.workflow.executor import WorkflowExecutor  # noqa: E402

workflow_engine = WorkflowEngineAdapter()
yaml_workflow_executor = WorkflowExecutor()
prompt_manager = PromptTemplateManager()
openai_client = OpenAIClient()
yaml_workflow_executor = WorkflowExecutor(arete_hooks=get_arete_hooks())
YAML_WORKFLOWS_DIR = get_settings().base_dir / "workflows"

# ---------------------------------------------------------------------------
# Managers (initialized in lifespan)
# ---------------------------------------------------------------------------
schedule_manager: ScheduleManager | None = None
webhook_manager: WebhookManager | None = None
delivery_manager: WebhookDeliveryManager | None = None
job_manager: JobManager | None = None
version_manager: WorkflowVersionManager | None = None
execution_manager: ExecutionManager | None = None
mcp_manager: MCPConnectorManager | None = None
settings_manager: SettingsManager | None = None
budget_manager: PersistentBudgetManager | None = None
task_store: TaskStore | None = None
citizen_commissioner: Any | None = None
arete_guard: Any | None = None
mission_scheduler: MissionScheduler | None = None

# ---------------------------------------------------------------------------
# Coordination (initialized in lifespan, optional)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Agent infrastructure (initialized in lifespan, optional)
# ---------------------------------------------------------------------------
agent_memory: AgentMemory | None = None
process_registry: ProcessRegistry | None = None
subagent_manager: SubAgentManager | None = None
task_runner: AgentTaskRunner | None = None
agent_configs: dict | None = None  # dict[str, AgentConfig] from config_loader

coordination_event_log = None  # animus_quorum.EventLog or None
coordination_bridge = None  # animus_quorum.GorgonBridge or None
consciousness_bridge = None  # ConsciousnessBridge or None

# ---------------------------------------------------------------------------
# WebSocket components (initialized in lifespan)
# ---------------------------------------------------------------------------
ws_manager: ConnectionManager | None = None
ws_broadcaster: Broadcaster | None = None

# ---------------------------------------------------------------------------
# Application health state
# ---------------------------------------------------------------------------
_app_state: dict = {
    "ready": False,
    "shutting_down": False,
    "start_time": None,
    "active_requests": 0,
}
_state_lock = asyncio.Lock()


async def increment_active_requests() -> None:
    """Increment active request counter."""
    async with _state_lock:
        _app_state["active_requests"] += 1


async def decrement_active_requests() -> None:
    """Decrement active request counter."""
    async with _state_lock:
        _app_state["active_requests"] -= 1
