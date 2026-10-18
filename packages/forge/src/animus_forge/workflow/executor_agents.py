"""Forge autonomy implementation for Kernel workflow execution."""

from animus_kernel.executor.executor_agents import *  # noqa: F401,F403
from animus_kernel.executor.executor_agents import (
    AgentStepHandlerMixin as KernelAgentStepHandlerMixin,
)


class AgentStepHandlerMixin(KernelAgentStepHandlerMixin):
    def _create_autonomy_loop(self, **kwargs):
        from animus_forge.agents.autonomy import AutonomyLoop

        return AutonomyLoop(**kwargs)
