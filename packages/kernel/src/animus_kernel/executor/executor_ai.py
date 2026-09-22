"""AI provider step handlers for workflow execution.

Mixin class providing handlers for Claude and OpenAI API steps.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from animus_kernel.state.agent_context import WorkflowMemoryManager

from .executor_clients import _get_claude_client, _get_ollama_provider, _get_openai_client
from .loader import StepConfig

logger = logging.getLogger(__name__)


def _resolve_sensitivity(value: object):
    """C1-2 — coerce a step's ``sensitivity`` param to a Sensitivity enum.

    Accepts a Sensitivity, a tier name ("confidential", "secret", "personal",
    "public", case-insensitive), or None → PUBLIC default. An unrecognized
    string fails CLOSED to SECRET so a typo can never silently widen egress.
    """
    from animus_types import Sensitivity

    if isinstance(value, Sensitivity):
        return value
    if value is None:
        return Sensitivity.PUBLIC
    try:
        return Sensitivity[str(value).strip().upper()]
    except KeyError:
        logger.warning("Unknown sensitivity %r — failing closed to SECRET", value)
        return Sensitivity.SECRET


class AIHandlersMixin:
    """Mixin providing AI provider step handlers.

    Expects the following attributes from the host class:
    - dry_run: bool
    - memory_manager: WorkflowMemoryManager | None
    """

    dry_run: bool
    memory_manager: WorkflowMemoryManager | None

    def _execute_claude_code(self, step: StepConfig, context: dict) -> dict:
        """Execute a Claude Code step using the Anthropic API.

        Params:
            prompt: The task/prompt to send
            role: Agent role (planner, builder, tester, reviewer)
            model: Claude model to use (default: claude-sonnet-4-20250514)
            max_tokens: Maximum tokens in response (default: 4096)
            system_prompt: Optional custom system prompt (overrides role)
            use_memory: Enable memory context injection (default: True)
        """
        prompt = step.params.get("prompt", "")
        role = step.params.get("role", "builder")
        model = step.params.get("model", "claude-sonnet-4-20250514")
        max_tokens = step.params.get("max_tokens", 4096)
        system_prompt = step.params.get("system_prompt")
        use_memory = step.params.get("use_memory", True)

        # Substitute context variables in prompt
        for key, value in context.items():
            if isinstance(value, str):
                prompt = prompt.replace(f"${{{key}}}", value)

        # Inject memory context if available
        if use_memory and self.memory_manager:
            prompt = self.memory_manager.inject_context(role, prompt)

        # Inject budget context if available
        budget_mgr = getattr(self, "budget_manager", None)
        if budget_mgr:
            budget_ctx = budget_mgr.get_budget_context()
            if budget_ctx:
                prompt = prompt + "\n\n" + budget_ctx

        # Dry run mode - return mock response
        if self.dry_run:
            output = {
                "role": role,
                "prompt": prompt,
                "response": f"[DRY RUN] Claude {role} would process: {prompt[:100]}...",
                "tokens_used": step.params.get("estimated_tokens", 1000),
                "model": model,
                "dry_run": True,
            }
            # Store output in memory even for dry run
            if self.memory_manager:
                self.memory_manager.store_output(role, step.id, output)
            return output

        # Get Claude client
        client = _get_claude_client()
        if not client:
            raise RuntimeError("Claude Code client not available. Check API key configuration.")

        if not client.is_configured():
            raise RuntimeError("Claude Code client not configured. Set ANTHROPIC_API_KEY.")

        # Execute via API
        if system_prompt:
            # Custom system prompt - use generate_completion
            result = client.generate_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                max_tokens=max_tokens,
            )
        else:
            # Role-based execution
            result = client.execute_agent(
                role=role,
                task=prompt,
                context=context.get("_previous_output"),
                model=model,
                max_tokens=max_tokens,
            )

        if not result.get("success"):
            error_msg = result.get("error", "Unknown error")
            # Store error in memory
            if self.memory_manager:
                self.memory_manager.store_error(role, step.id, error_msg)
            raise RuntimeError(f"Claude API error: {error_msg}")

        # Estimate tokens (actual count would require API response metadata)
        response_text = result.get("output", "")
        estimated_tokens = len(response_text) // 4 + len(prompt) // 4

        output = {
            "role": role,
            "prompt": prompt,
            "response": response_text,
            "tokens_used": estimated_tokens,
            "model": model,
        }

        # Propagate consensus metadata into step output
        if result.get("consensus"):
            output["consensus"] = result["consensus"]
        if result.get("pending_user_confirmation"):
            output["pending_user_confirmation"] = True

        # Store output in memory
        if self.memory_manager:
            self.memory_manager.store_output(role, step.id, output)

        return output

    def _execute_openai(self, step: StepConfig, context: dict) -> dict:
        """Execute an OpenAI step using the OpenAI API.

        Params:
            prompt: The prompt to send
            model: OpenAI model to use (default: gpt-4o-mini)
            system_prompt: Optional system prompt
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens in response (optional)
            use_memory: Enable memory context injection (default: True)
        """
        prompt = step.params.get("prompt", "")
        model = step.params.get("model", "gpt-4o-mini")
        system_prompt = step.params.get("system_prompt")
        temperature = step.params.get("temperature", 0.7)
        max_tokens = step.params.get("max_tokens")
        use_memory = step.params.get("use_memory", True)

        # Substitute context variables in prompt
        for key, value in context.items():
            if isinstance(value, str):
                prompt = prompt.replace(f"${{{key}}}", value)

        # Inject memory context if available
        agent_id = f"openai-{model}"
        if use_memory and self.memory_manager:
            prompt = self.memory_manager.inject_context(agent_id, prompt)

        # Dry run mode - return mock response
        if self.dry_run:
            output = {
                "model": model,
                "prompt": prompt,
                "response": f"[DRY RUN] OpenAI {model} would process: {prompt[:100]}...",
                "tokens_used": step.params.get("estimated_tokens", 1000),
                "dry_run": True,
            }
            if self.memory_manager:
                self.memory_manager.store_output(agent_id, step.id, output)
            return output

        # Get OpenAI client
        client = _get_openai_client()
        if not client:
            raise RuntimeError("OpenAI client not available. Check API key configuration.")

        try:
            response_text = client.generate_completion(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )
        except Exception as e:
            error_msg = str(e)
            if self.memory_manager:
                self.memory_manager.store_error(agent_id, step.id, error_msg)
            raise RuntimeError(f"OpenAI API error: {e}")

        # Estimate tokens (actual count would require API response metadata)
        estimated_tokens = len(response_text) // 4 + len(prompt) // 4

        output = {
            "model": model,
            "prompt": prompt,
            "response": response_text,
            "tokens_used": estimated_tokens,
        }

        # Store output in memory
        if self.memory_manager:
            self.memory_manager.store_output(agent_id, step.id, output)

        return output

    def _execute_ollama(self, step: StepConfig, context: dict) -> dict:
        """Execute an Ollama step using a local Ollama model.

        Params:
            prompt: The prompt to send
            model: Ollama model to use (default: OLLAMA_MODEL env or deepseek-coder-v2)
            system_prompt: Optional system prompt
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens in response (default: 4096)
            use_memory: Enable memory context injection (default: True)
        """
        prompt = step.params.get("prompt", "")
        model = step.params.get("model")
        system_prompt = step.params.get("system_prompt")
        temperature = step.params.get("temperature", 0.7)
        max_tokens = step.params.get("max_tokens", 4096)
        use_memory = step.params.get("use_memory", True)

        # Substitute context variables in prompt
        for key, value in context.items():
            if isinstance(value, str):
                prompt = prompt.replace(f"${{{key}}}", value)

        # Inject memory context if available
        agent_id = f"ollama-{model or 'default'}"
        if use_memory and self.memory_manager:
            prompt = self.memory_manager.inject_context(agent_id, prompt)

        # Inject budget context if available
        budget_mgr = getattr(self, "budget_manager", None)
        if budget_mgr:
            budget_ctx = budget_mgr.get_budget_context()
            if budget_ctx:
                prompt = prompt + "\n\n" + budget_ctx

        # Dry run mode
        if self.dry_run:
            output = {
                "model": model or "ollama-default",
                "prompt": prompt,
                "response": f"[DRY RUN] Ollama would process: {prompt[:100]}...",
                "tokens_used": step.params.get("estimated_tokens", 1000),
                "dry_run": True,
            }
            if self.memory_manager:
                self.memory_manager.store_output(agent_id, step.id, output)
            return output

        # Get Ollama provider
        provider = _get_ollama_provider()
        if not provider:
            raise RuntimeError(
                "Ollama provider not available. Make sure Ollama is running (ollama serve)."
            )

        from animus_kernel.providers.base import CompletionRequest

        # C1-2 — carry the step's declared sensitivity so the egress tier gate
        # actually sees it. Without this every executor-issued request defaulted
        # to PUBLIC, making the CONFIDENTIAL/SECRET tier gate inert on the
        # workflow path. Accepts a Sensitivity enum or a tier-name string.
        sensitivity = _resolve_sensitivity(step.params.get("sensitivity"))

        request = CompletionRequest(
            prompt=prompt,
            system_prompt=system_prompt or "You are a helpful assistant.",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            sensitivity=sensitivity,
        )

        try:
            response = provider.complete(request)
        except Exception as e:
            error_msg = str(e)
            if self.memory_manager:
                self.memory_manager.store_error(agent_id, step.id, error_msg)
            raise RuntimeError(f"Ollama error: {e}")

        response_text = response.content
        estimated_tokens = response.tokens_used or (len(response_text) // 4 + len(prompt) // 4)

        # C1-1 — surface the real model + input/output split so record_usage()
        # computes cost-weighted Effective-Tokens instead of collapsing to raw.
        output = {
            "model": response.model or model or "ollama",
            "prompt": prompt,
            "response": response_text,
            "tokens_used": estimated_tokens,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }

        # Store output in memory
        if self.memory_manager:
            self.memory_manager.store_output(agent_id, step.id, output)

        return output
