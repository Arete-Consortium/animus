"""Mixin providing agent workflow step handlers.

Adds 'autonomy' and 'handoff' step types to the workflow executor.
The autonomy step runs an observe→plan→act→reflect loop, and the
handoff step passes structured results between agents.

Expects the following attributes from the host class:
- dry_run: bool
- budget_manager: BudgetManager | None
- memory_manager: WorkflowMemoryManager | None
- agent_memory: AgentMemory | None  (persistent cross-workflow memory)
- _context: dict
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HandoffPayload:
    """Structured data passed between agents during handoff.

    Attributes:
        source_agent: Agent role that produced the data.
        target_agent: Agent role receiving the data.
        result: The primary output from the source agent.
        context: Additional context for the target.
        metadata: Arbitrary key-value metadata.
    """

    source_agent: str
    target_agent: str
    result: str
    context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    def to_prompt_section(self) -> str:
        """Format as a prompt section for injection into agent context."""
        parts = [
            f"## Handoff from {self.source_agent}",
            f"**Result:**\n{self.result}",
        ]
        if self.context:
            parts.append(f"**Context:**\n{self.context}")
        if self.metadata:
            parts.append(f"**Metadata:** {json.dumps(self.metadata)}")
        return "\n\n".join(parts)


class AgentStepHandlerMixin:
    """Mixin providing autonomy and handoff workflow step handlers."""

    dry_run: bool
    budget_manager: Any

    def _create_autonomy_loop(self, **kwargs):
        raise RuntimeError("Autonomy execution requires an application adapter")

    def _execute_autonomy(self, step: Any, context: dict) -> dict:
        """Execute an autonomy loop step.

        Params:
            goal: str — The goal for the autonomy loop.
            max_iterations: int — Maximum loop cycles (default 5).
            initial_state: str — Starting context (supports ${var} substitution).
            provider_type: str — Provider to use: 'ollama' (default).

        Returns:
            Dict with goal, stop_reason, iterations, final_output, total_tokens.
        """
        params = step.params or {}
        goal = params.get("goal", "")
        max_iterations = params.get("max_iterations", 5)
        initial_state = params.get("initial_state", "")

        # Variable substitution in goal and state
        for key, value in context.items():
            if isinstance(value, str):
                goal = goal.replace(f"${{{key}}}", value)
                initial_state = initial_state.replace(f"${{{key}}}", value)

        # Inject persistent memory context if available
        agent_id = params.get("agent_id", "autonomy")
        agent_mem = getattr(self, "agent_memory", None)
        if agent_mem is not None:
            try:
                memories = agent_mem.recall_context(agent_id, max_entries=10)
                if memories:
                    mem_text = agent_mem.format_context(memories)
                    initial_state = f"{mem_text}\n\n{initial_state}" if initial_state else mem_text
            except Exception as e:
                logger.debug("Failed to recall agent memory: %s", e)

        if self.dry_run:
            return {
                "goal": goal,
                "stop_reason": "dry_run",
                "iterations": 0,
                "final_output": f"[DRY RUN] Would run autonomy loop for: {goal}",
                "total_tokens": 0,
            }

        # Build provider
        provider = self._get_autonomy_provider(params)
        if provider is None:
            return {
                "goal": goal,
                "stop_reason": "error",
                "iterations": 0,
                "final_output": "No provider available for autonomy loop",
                "total_tokens": 0,
                "error": "Provider not configured",
            }

        loop = self._create_autonomy_loop(
            provider=provider,
            max_iterations=max_iterations,
            budget_manager=self.budget_manager,
        )

        # Run the async loop synchronously
        try:
            loop_coro = loop.run(goal=goal, initial_state=initial_state)
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is not None:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, loop_coro).result()
            else:
                result = asyncio.run(loop_coro)
        except Exception as e:
            logger.error("Autonomy loop failed: %s", e)
            return {
                "goal": goal,
                "stop_reason": "error",
                "iterations": 0,
                "final_output": "",
                "total_tokens": 0,
                "error": str(e),
            }

        # Store result in workflow memory if available
        if hasattr(self, "memory_manager") and self.memory_manager is not None:
            with contextlib.suppress(Exception):
                self.memory_manager.store_output(
                    agent_id=agent_id,
                    step_id=step.id,
                    output=result.to_dict(),
                )

        # Store result in persistent agent memory
        if agent_mem is not None:
            try:
                agent_mem.store(
                    agent_id=agent_id,
                    content=result.final_output or "",
                    memory_type="learned",
                    metadata={
                        "goal": goal,
                        "stop_reason": str(result.stop_reason),
                        "iterations": len(result.iterations),
                        "step_id": step.id,
                    },
                    importance=0.7,
                )
            except Exception as e:
                logger.debug("Failed to store agent memory: %s", e)

        return result.to_dict()

    def _execute_handoff(self, step: Any, context: dict) -> dict:
        """Execute an agent handoff step.

        Passes structured data from one agent's output to another agent's input.
        The source result is read from context, formatted as a HandoffPayload,
        and stored in context for the target agent.

        Params:
            source_agent: str — Agent role providing the result.
            target_agent: str — Agent role receiving the result.
            source_key: str — Context key containing source output (default: source_agent).
            context_message: str — Additional context for the target.
            metadata: dict — Extra metadata to pass along.

        Returns:
            Dict with handoff details.
        """
        params = step.params or {}
        source_agent = params.get("source_agent", "")
        target_agent = params.get("target_agent", "")
        source_key = params.get("source_key", source_agent)
        context_message = params.get("context_message", "")
        metadata = params.get("metadata", {})

        # Variable substitution
        for key, value in context.items():
            if isinstance(value, str):
                context_message = context_message.replace(f"${{{key}}}", value)

        # Get source result from context
        source_result = context.get(source_key, "")
        if isinstance(source_result, dict):
            # Extract final_output if it's an autonomy result
            source_result = source_result.get("final_output", json.dumps(source_result))

        payload = HandoffPayload(
            source_agent=source_agent,
            target_agent=target_agent,
            result=str(source_result),
            context=context_message,
            metadata=metadata,
        )

        # Store handoff in context for target agent
        context[f"handoff_{target_agent}"] = payload.to_dict()
        context[f"handoff_{target_agent}_prompt"] = payload.to_prompt_section()

        # Store in memory if available
        if hasattr(self, "memory_manager") and self.memory_manager is not None:
            with contextlib.suppress(Exception):
                self.memory_manager.store_output(
                    agent_id=target_agent,
                    step_id=step.id,
                    output={"handoff_from": source_agent, "result_length": len(str(source_result))},
                )

        return {
            "source_agent": source_agent,
            "target_agent": target_agent,
            "result_length": len(str(source_result)),
            "handoff_stored": True,
            "context_key": f"handoff_{target_agent}",
        }

    def _get_autonomy_provider(self, params: dict) -> Any:
        """Create a provider for the autonomy loop.

        Returns a simple wrapper with async complete(prompt) -> str.
        """
        provider_type = params.get("provider_type", "ollama")

        try:
            if provider_type == "ollama":
                return self._build_ollama_autonomy_provider(params)
        except Exception as e:
            logger.warning("Failed to create autonomy provider: %s", e)

        return None

    @staticmethod
    def _build_ollama_autonomy_provider(params: dict) -> Any:
        """Build an Ollama-backed provider for the autonomy loop."""
        import os

        from animus_kernel.providers.base import CompletionRequest
        from animus_kernel.providers.ollama_provider import OllamaProvider

        host = params.get("ollama_host", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        model = params.get("ollama_model", os.environ.get("OLLAMA_MODEL", "llama3.1:8b"))

        raw = OllamaProvider(model=model, host=host)
        raw.initialize()

        class _OllamaAutonomyProvider:
            async def complete(self, prompt: str) -> str:
                request = CompletionRequest(
                    prompt=prompt,
                    system_prompt="You are a helpful autonomous agent.",
                    max_tokens=1024,
                    temperature=0.3,
                )
                response = await raw.complete_async(request)
                return response.content

        return _OllamaAutonomyProvider()
