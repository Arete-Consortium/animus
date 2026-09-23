"""Tests for Ollama workflow step handler and client factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.executor_ai import AIHandlersMixin
from animus_forge.workflow.loader import StepConfig


def _make_ai_host(dry_run=False):
    """Create a minimal host for AIHandlersMixin."""

    class _AIHost(AIHandlersMixin):
        def __init__(self):
            self.dry_run = dry_run
            self.memory_manager = None
            self.budget_manager = None

    return _AIHost()


def _make_step(prompt="Hello", model=None, **extra):
    """Create a StepConfig for Ollama."""
    params = {"prompt": prompt}
    if model:
        params["model"] = model
    params.update(extra)
    return StepConfig(id="test-ollama", type="ollama", params=params)


class TestOllamaClientFactory:
    """Tests for _get_ollama_provider factory."""

    def test_caches_provider(self):
        import animus_kernel.executor.executor_clients as mod

        mock_provider = MagicMock()
        mod._ollama_provider = mock_provider

        result = mod._get_ollama_provider()
        assert result is mock_provider

        mod._ollama_provider = None

    def test_returns_none_when_marked_unavailable(self):
        import animus_kernel.executor.executor_clients as mod

        mod._ollama_provider = False  # marked unavailable

        result = mod._get_ollama_provider()
        assert result is None

        mod._ollama_provider = None


class TestExecuteOllamaDryRun:
    """Tests for Ollama dry run mode."""

    def test_dry_run_returns_mock_response(self):
        host = _make_ai_host(dry_run=True)
        step = _make_step(prompt="Analyze this code")
        result = host._execute_ollama(step, {})

        assert result["dry_run"] is True
        assert "DRY RUN" in result["response"]
        assert "Analyze this code" in result["response"]

    def test_dry_run_stores_memory(self):
        host = _make_ai_host(dry_run=True)
        host.memory_manager = MagicMock()
        step = _make_step(prompt="test")
        host._execute_ollama(step, {})
        host.memory_manager.store_output.assert_called_once()

    def test_dry_run_uses_estimated_tokens(self):
        host = _make_ai_host(dry_run=True)
        step = _make_step(prompt="test", estimated_tokens=500)
        result = host._execute_ollama(step, {})
        assert result["tokens_used"] == 500


class TestExecuteOllamaLive:
    """Tests for Ollama live execution paths."""

    def test_provider_not_available_raises(self):
        host = _make_ai_host()
        step = _make_step()
        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="not available"):
                host._execute_ollama(step, {})

    def test_success_path(self):
        host = _make_ai_host()
        step = _make_step(prompt="Hello", model="llama3.2")

        mock_response = MagicMock()
        mock_response.content = "Ollama response"
        mock_response.tokens_used = 42
        mock_response.model = "llama3.2"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = mock_response

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            result = host._execute_ollama(step, {})

        assert result["response"] == "Ollama response"
        assert result["tokens_used"] == 42
        assert result["model"] == "llama3.2"

    def test_success_with_memory(self):
        host = _make_ai_host()
        host.memory_manager = MagicMock()
        host.memory_manager.inject_context.return_value = "enriched prompt"
        step = _make_step(prompt="Hello")

        mock_response = MagicMock()
        mock_response.content = "response"
        mock_response.tokens_used = 10
        mock_response.model = "test"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = mock_response

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            host._execute_ollama(step, {})

        host.memory_manager.inject_context.assert_called_once()
        host.memory_manager.store_output.assert_called_once()

    def test_context_variable_substitution(self):
        host = _make_ai_host()
        step = _make_step(prompt="Analyze ${code}")

        mock_response = MagicMock()
        mock_response.content = "done"
        mock_response.tokens_used = 5
        mock_response.model = "test"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = mock_response

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            host._execute_ollama(step, {"code": "print('hi')"})

        # Verify prompt had substitution
        call_args = mock_provider.complete.call_args[0][0]
        assert "print('hi')" in call_args.prompt

    def test_provider_error_stores_memory_error(self):
        host = _make_ai_host()
        host.memory_manager = MagicMock()
        step = _make_step()

        mock_provider = MagicMock()
        mock_provider.complete.side_effect = Exception("connection refused")

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            with pytest.raises(RuntimeError, match="Ollama error"):
                host._execute_ollama(step, {})

        host.memory_manager.store_error.assert_called_once()

    def test_budget_context_injection(self):
        host = _make_ai_host()
        host.budget_manager = MagicMock()
        host.budget_manager.get_budget_context.return_value = "Budget: 1000 tokens remaining"
        step = _make_step(prompt="Hello")

        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.tokens_used = 5
        mock_response.model = "test"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = mock_response

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            host._execute_ollama(step, {})

        call_args = mock_provider.complete.call_args[0][0]
        assert "Budget: 1000 tokens remaining" in call_args.prompt

    def test_fallback_token_estimation(self):
        """When total_tokens is None, estimate from text length."""
        host = _make_ai_host()
        step = _make_step(prompt="Hello")

        mock_response = MagicMock()
        mock_response.content = "A" * 400  # ~100 tokens
        mock_response.tokens_used = None
        mock_response.model = "test"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = mock_response

        with patch(
            "animus_kernel.executor.executor_ai._get_ollama_provider",
            return_value=mock_provider,
        ):
            result = host._execute_ollama(step, {})

        # Should be len(response)//4 + len(prompt)//4
        assert result["tokens_used"] > 0


class TestOllamaInExecutor:
    """Test that WorkflowExecutor has ollama registered."""

    def test_ollama_handler_registered(self):
        from animus_forge.workflow.executor_core import WorkflowExecutor

        ex = WorkflowExecutor.__new__(WorkflowExecutor)
        ex.dry_run = False
        ex.memory_manager = None
        ex.budget_manager = None
        ex.checkpoint_manager = None
        ex.contract_validator = None
        ex.error_callback = None
        ex.fallback_callbacks = {}
        ex.memory_config = None
        ex.feedback_engine = None
        ex.execution_manager = None
        ex.arete_hooks = None
        ex._execution_id = None
        ex._context = {}
        ex._current_workflow_id = None
        ex._handlers = {
            "ollama": ex._execute_ollama,
        }

        assert "ollama" in ex._handlers

    def test_ollama_in_valid_step_types(self):
        from animus_forge.workflow.loader import VALID_STEP_TYPES

        assert "ollama" in VALID_STEP_TYPES
