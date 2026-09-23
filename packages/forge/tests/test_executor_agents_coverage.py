"""Targeted coverage for executor_agents.py gaps on origin/main.

Closes two uncovered blocks flagged by CI on commit 2c8cde2:

- Lines 137-140: the ThreadPoolExecutor branch inside `_execute_autonomy`
  that handles being called while a running event loop already exists.
- Lines 269-291: `_build_ollama_autonomy_provider` and its inner
  `_OllamaAutonomyProvider` wrapper.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animus_forge.workflow.executor_agents import AgentStepHandlerMixin


@dataclass
class _Step:
    id: str = "step-1"
    params: dict = field(default_factory=dict)


class _Executor(AgentStepHandlerMixin):
    def __init__(self):
        self.dry_run = False
        self.budget_manager = None
        self.memory_manager = None
        self.agent_memory = None
        self._context: dict = {}


class _FakeAutonomyResult:
    final_output = "done"
    stop_reason = "goal_achieved"
    iterations = []
    total_tokens = 0

    def to_dict(self) -> dict:
        return {
            "final_output": self.final_output,
            "stop_reason": self.stop_reason,
            "iterations": self.iterations,
            "total_tokens": self.total_tokens,
        }


class TestBuildOllamaAutonomyProvider:
    """Covers lines 269-291 — the previously-mocked provider builder."""

    @patch("animus_kernel.providers.ollama_provider.OllamaProvider")
    def test_builds_provider_with_explicit_params(self, mock_ollama_cls):
        """Explicit host/model params flow into the constructor."""
        raw = MagicMock()
        raw.initialize = MagicMock()
        mock_ollama_cls.return_value = raw

        provider = AgentStepHandlerMixin._build_ollama_autonomy_provider(
            {"ollama_host": "http://fake:11434", "ollama_model": "qwen2.5:7b"}
        )

        mock_ollama_cls.assert_called_once_with(model="qwen2.5:7b", host="http://fake:11434")
        raw.initialize.assert_called_once()
        # Inner wrapper exposes async complete(prompt) -> str.
        assert hasattr(provider, "complete")
        assert asyncio.iscoroutinefunction(provider.complete)

    @patch.dict(
        "os.environ",
        {"OLLAMA_HOST": "http://env-host:11434", "OLLAMA_MODEL": "env-model:3b"},
        clear=False,
    )
    @patch("animus_kernel.providers.ollama_provider.OllamaProvider")
    def test_falls_back_to_environment(self, mock_ollama_cls):
        """When params omit host/model, env vars drive the config."""
        raw = MagicMock()
        raw.initialize = MagicMock()
        mock_ollama_cls.return_value = raw

        AgentStepHandlerMixin._build_ollama_autonomy_provider({})

        mock_ollama_cls.assert_called_once_with(model="env-model:3b", host="http://env-host:11434")

    @patch("animus_kernel.providers.ollama_provider.OllamaProvider")
    def test_wrapper_complete_returns_response_content(self, mock_ollama_cls):
        """The inner _OllamaAutonomyProvider.complete passes prompt through
        and returns response.content from complete_async."""
        response = MagicMock()
        response.content = "model output"

        raw = MagicMock()
        raw.initialize = MagicMock()
        raw.complete_async = AsyncMock(return_value=response)
        mock_ollama_cls.return_value = raw

        provider = AgentStepHandlerMixin._build_ollama_autonomy_provider({})
        result = asyncio.run(provider.complete("hello"))

        assert result == "model output"
        raw.complete_async.assert_awaited_once()
        # The CompletionRequest carries our prompt + defaults.
        req = raw.complete_async.await_args.args[0]
        assert req.prompt == "hello"
        assert req.max_tokens == 1024
        assert req.temperature == 0.3
        assert req.system_prompt.startswith("You are")


class TestExecuteAutonomyNestedLoop:
    """Covers lines 136-140 — the ThreadPoolExecutor branch that runs
    the autonomy coro when there's already a running event loop."""

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    @patch("animus_forge.agents.autonomy.AutonomyLoop")
    @pytest.mark.asyncio
    async def test_runs_inside_thread_pool_when_loop_is_live(
        self, mock_loop_cls, mock_get_provider
    ):
        """Call _execute_autonomy from inside an async test (running loop
        already exists) so the ThreadPoolExecutor path runs."""
        mock_get_provider.return_value = MagicMock()

        fake_loop = MagicMock()

        async def _fake_run(goal, initial_state):
            return _FakeAutonomyResult()

        fake_loop.run = _fake_run
        mock_loop_cls.return_value = fake_loop

        ex = _Executor()
        step = _Step(
            params={
                "goal": "make a sandwich",
                "agent_id": "sous-chef",
                "provider_type": "ollama",
            }
        )

        # Directly call the sync handler from inside the async test.
        result = ex._execute_autonomy(step, {})

        assert result["stop_reason"] == "goal_achieved"
        assert result["final_output"] == "done"
