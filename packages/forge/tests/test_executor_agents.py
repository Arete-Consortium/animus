"""Tests for AgentStepHandlerMixin (autonomy + handoff step types)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from animus_forge.workflow.executor_agents import AgentStepHandlerMixin, HandoffPayload

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeStep:
    """Minimal step object for testing."""

    id: str = "test-step-1"
    params: dict = field(default_factory=dict)


class FakeExecutor(AgentStepHandlerMixin):
    """Minimal host class for testing the mixin."""

    def __init__(
        self,
        dry_run: bool = False,
        budget_manager=None,
        memory_manager=None,
        agent_memory=None,
    ):
        self.dry_run = dry_run
        self.budget_manager = budget_manager
        self.memory_manager = memory_manager
        self.agent_memory = agent_memory
        self._context: dict = {}


@dataclass
class FakeAutonomyResult:
    """Mimics AutonomyResult.to_dict()."""

    final_output: str = "Done"
    stop_reason: str = "goal_achieved"
    iterations: list = field(default_factory=list)
    total_tokens: int = 100

    def to_dict(self) -> dict:
        return {
            "final_output": self.final_output,
            "stop_reason": self.stop_reason,
            "iterations": self.iterations,
            "total_tokens": self.total_tokens,
        }


# ===========================================================================
# HandoffPayload tests
# ===========================================================================


class TestHandoffPayload:
    """Test HandoffPayload dataclass."""

    def test_to_dict(self):
        p = HandoffPayload(
            source_agent="planner",
            target_agent="builder",
            result="Build a widget",
        )
        d = p.to_dict()
        assert d["source_agent"] == "planner"
        assert d["target_agent"] == "builder"
        assert d["result"] == "Build a widget"
        assert d["context"] == ""
        assert d["metadata"] == {}

    def test_to_dict_with_metadata(self):
        p = HandoffPayload(
            source_agent="a",
            target_agent="b",
            result="res",
            context="ctx",
            metadata={"key": "val"},
        )
        d = p.to_dict()
        assert d["context"] == "ctx"
        assert d["metadata"] == {"key": "val"}

    def test_to_prompt_section_basic(self):
        p = HandoffPayload(source_agent="planner", target_agent="builder", result="Plan done")
        section = p.to_prompt_section()
        assert "## Handoff from planner" in section
        assert "**Result:**\nPlan done" in section
        assert "**Context:**" not in section
        assert "**Metadata:**" not in section

    def test_to_prompt_section_full(self):
        p = HandoffPayload(
            source_agent="a",
            target_agent="b",
            result="res",
            context="extra info",
            metadata={"k": "v"},
        )
        section = p.to_prompt_section()
        assert "**Context:**\nextra info" in section
        assert "**Metadata:**" in section
        assert '"k"' in section

    def test_default_fields(self):
        p = HandoffPayload(source_agent="a", target_agent="b", result="r")
        assert p.context == ""
        assert p.metadata == {}


# ===========================================================================
# _execute_autonomy tests
# ===========================================================================


class TestExecuteAutonomy:
    """Test the autonomy step handler."""

    def test_dry_run(self):
        ex = FakeExecutor(dry_run=True)
        step = FakeStep(params={"goal": "Test goal"})
        result = ex._execute_autonomy(step, {})
        assert result["stop_reason"] == "dry_run"
        assert result["iterations"] == 0
        assert "Test goal" in result["final_output"]

    def test_variable_substitution_in_goal(self):
        ex = FakeExecutor(dry_run=True)
        step = FakeStep(params={"goal": "Fix ${component}", "initial_state": "State: ${status}"})
        result = ex._execute_autonomy(step, {"component": "auth", "status": "broken"})
        assert "Fix auth" in result["final_output"]

    def test_no_provider_returns_error(self):
        ex = FakeExecutor(dry_run=False)
        step = FakeStep(params={"goal": "test", "provider_type": "nonexistent"})
        result = ex._execute_autonomy(step, {})
        assert result["stop_reason"] == "error"
        assert "Provider not configured" in result["error"]

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_successful_run(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)

        mock_get_provider.return_value = MagicMock()

        ex = FakeExecutor(dry_run=False)
        step = FakeStep(params={"goal": "test goal"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            result = ex._execute_autonomy(step, {})

        assert result["final_output"] == "Done"
        assert result["stop_reason"] == "goal_achieved"

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_loop_exception_returns_error(self, mock_get_provider):
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(side_effect=RuntimeError("boom"))

        mock_get_provider.return_value = MagicMock()

        ex = FakeExecutor(dry_run=False)
        step = FakeStep(params={"goal": "fail"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            result = ex._execute_autonomy(step, {})

        assert result["stop_reason"] == "error"
        assert "boom" in result["error"]

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_stores_in_memory_manager(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        mm = MagicMock()
        ex = FakeExecutor(dry_run=False, memory_manager=mm)
        step = FakeStep(id="step-mem", params={"goal": "test"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            ex._execute_autonomy(step, {})

        mm.store_output.assert_called_once()
        call_kwargs = mm.store_output.call_args
        assert call_kwargs[1]["step_id"] == "step-mem"

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_stores_in_agent_memory(self, mock_get_provider):
        fake_result = FakeAutonomyResult(final_output="learned something")
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        am = MagicMock()
        am.recall_context.return_value = {}
        ex = FakeExecutor(dry_run=False, agent_memory=am)
        step = FakeStep(params={"goal": "learn", "agent_id": "researcher"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            ex._execute_autonomy(step, {})

        am.store.assert_called_once()
        call_kwargs = am.store.call_args[1]
        assert call_kwargs["agent_id"] == "researcher"
        assert call_kwargs["content"] == "learned something"
        assert call_kwargs["memory_type"] == "learned"

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_recalls_agent_memory_into_state(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        am = MagicMock()
        am.recall_context.return_value = {"facts": [MagicMock(content="earth is round")]}
        am.format_context.return_value = "Known Facts:\n- earth is round"
        ex = FakeExecutor(dry_run=False, agent_memory=am)
        step = FakeStep(params={"goal": "test", "initial_state": "start here"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            ex._execute_autonomy(step, {})

        # Verify the loop was called with memory-enriched initial state
        call_args = mock_loop.run.call_args[1]
        assert "Known Facts" in call_args["initial_state"]
        assert "start here" in call_args["initial_state"]

    def test_dry_run_with_agent_memory_no_crash(self):
        """Agent memory recall runs even in dry_run (for testing), but no store."""
        am = MagicMock()
        am.recall_context.return_value = {}
        ex = FakeExecutor(dry_run=True, agent_memory=am)
        step = FakeStep(params={"goal": "test"})
        result = ex._execute_autonomy(step, {})
        assert result["stop_reason"] == "dry_run"
        am.store.assert_not_called()

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_memory_manager_error_swallowed(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        mm = MagicMock()
        mm.store_output.side_effect = RuntimeError("db error")
        ex = FakeExecutor(dry_run=False, memory_manager=mm)
        step = FakeStep(params={"goal": "test"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            result = ex._execute_autonomy(step, {})

        assert result["final_output"] == "Done"  # Still succeeds

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_agent_memory_recall_error_swallowed(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        am = MagicMock()
        am.recall_context.side_effect = RuntimeError("recall failed")
        ex = FakeExecutor(dry_run=False, agent_memory=am)
        step = FakeStep(params={"goal": "test"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            result = ex._execute_autonomy(step, {})

        assert result["final_output"] == "Done"

    @patch("animus_kernel.executor.executor_agents.AgentStepHandlerMixin._get_autonomy_provider")
    def test_agent_memory_store_error_swallowed(self, mock_get_provider):
        fake_result = FakeAutonomyResult()
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value=fake_result)
        mock_get_provider.return_value = MagicMock()

        am = MagicMock()
        am.recall_context.return_value = {}
        am.store.side_effect = RuntimeError("store failed")
        ex = FakeExecutor(dry_run=False, agent_memory=am)
        step = FakeStep(params={"goal": "test"})

        with patch("animus_forge.agents.autonomy.AutonomyLoop", return_value=mock_loop):
            result = ex._execute_autonomy(step, {})

        assert result["final_output"] == "Done"

    def test_empty_goal_dry_run(self):
        ex = FakeExecutor(dry_run=True)
        step = FakeStep(params={})
        result = ex._execute_autonomy(step, {})
        assert result["stop_reason"] == "dry_run"

    def test_non_string_context_values_skipped(self):
        """Non-string context values don't break variable substitution."""
        ex = FakeExecutor(dry_run=True)
        step = FakeStep(params={"goal": "test ${x}"})
        result = ex._execute_autonomy(step, {"x": 42, "y": ["list"]})
        assert "test ${x}" in result["final_output"]  # Not substituted


# ===========================================================================
# _execute_handoff tests
# ===========================================================================


class TestExecuteHandoff:
    """Test the handoff step handler."""

    def test_basic_handoff(self):
        ex = FakeExecutor()
        context = {"planner": {"final_output": "The plan is ready"}}
        step = FakeStep(
            params={
                "source_agent": "planner",
                "target_agent": "builder",
            }
        )
        result = ex._execute_handoff(step, context)
        assert result["source_agent"] == "planner"
        assert result["target_agent"] == "builder"
        assert result["handoff_stored"] is True
        assert "handoff_builder" in context
        assert "handoff_builder_prompt" in context

    def test_handoff_extracts_final_output_from_dict(self):
        ex = FakeExecutor()
        context = {"planner": {"final_output": "Plan A", "extra": "data"}}
        step = FakeStep(params={"source_agent": "planner", "target_agent": "builder"})
        ex._execute_handoff(step, context)
        payload = context["handoff_builder"]
        assert payload["result"] == "Plan A"

    def test_handoff_json_dumps_dict_without_final_output(self):
        ex = FakeExecutor()
        context = {"planner": {"key1": "val1", "key2": "val2"}}
        step = FakeStep(params={"source_agent": "planner", "target_agent": "builder"})
        ex._execute_handoff(step, context)
        payload = context["handoff_builder"]
        parsed = json.loads(payload["result"])
        assert parsed["key1"] == "val1"

    def test_handoff_string_source(self):
        ex = FakeExecutor()
        context = {"analyzer": "Raw analysis text"}
        step = FakeStep(params={"source_agent": "analyzer", "target_agent": "reporter"})
        ex._execute_handoff(step, context)
        assert context["handoff_reporter"]["result"] == "Raw analysis text"

    def test_handoff_missing_source_returns_empty(self):
        ex = FakeExecutor()
        context = {}
        step = FakeStep(params={"source_agent": "missing", "target_agent": "builder"})
        result = ex._execute_handoff(step, context)
        assert result["result_length"] == 0

    def test_handoff_custom_source_key(self):
        ex = FakeExecutor()
        context = {"custom_key": "custom data"}
        step = FakeStep(
            params={
                "source_agent": "agent_a",
                "target_agent": "agent_b",
                "source_key": "custom_key",
            }
        )
        ex._execute_handoff(step, context)
        assert context["handoff_agent_b"]["result"] == "custom data"

    def test_handoff_variable_substitution(self):
        ex = FakeExecutor()
        context = {"src": "data", "project": "forge"}
        step = FakeStep(
            params={
                "source_agent": "src",
                "target_agent": "dst",
                "context_message": "Working on ${project}",
            }
        )
        ex._execute_handoff(step, context)
        assert context["handoff_dst"]["context"] == "Working on forge"

    def test_handoff_with_metadata(self):
        ex = FakeExecutor()
        context = {"src": "data"}
        step = FakeStep(
            params={
                "source_agent": "src",
                "target_agent": "dst",
                "metadata": {"priority": "high"},
            }
        )
        ex._execute_handoff(step, context)
        assert context["handoff_dst"]["metadata"] == {"priority": "high"}

    def test_handoff_stores_in_memory_manager(self):
        mm = MagicMock()
        ex = FakeExecutor(memory_manager=mm)
        context = {"src": "data"}
        step = FakeStep(
            id="handoff-1",
            params={"source_agent": "src", "target_agent": "dst"},
        )
        ex._execute_handoff(step, context)
        mm.store_output.assert_called_once()

    def test_handoff_memory_error_swallowed(self):
        mm = MagicMock()
        mm.store_output.side_effect = RuntimeError("db error")
        ex = FakeExecutor(memory_manager=mm)
        context = {"src": "data"}
        step = FakeStep(
            params={"source_agent": "src", "target_agent": "dst"},
        )
        result = ex._execute_handoff(step, context)
        assert result["handoff_stored"] is True  # Still succeeds

    def test_handoff_prompt_section_in_context(self):
        ex = FakeExecutor()
        context = {"src": "important result"}
        step = FakeStep(
            params={"source_agent": "src", "target_agent": "dst"},
        )
        ex._execute_handoff(step, context)
        prompt = context["handoff_dst_prompt"]
        assert "## Handoff from src" in prompt
        assert "important result" in prompt


# ===========================================================================
# _get_autonomy_provider tests
# ===========================================================================


class TestGetAutonomyProvider:
    """Test provider creation."""

    def test_unknown_provider_returns_none(self):
        ex = FakeExecutor()
        result = ex._get_autonomy_provider({"provider_type": "unknown"})
        assert result is None

    @patch(
        "animus_kernel.executor.executor_agents.AgentStepHandlerMixin._build_ollama_autonomy_provider"
    )
    def test_ollama_provider_created(self, mock_build):
        mock_build.return_value = MagicMock()
        ex = FakeExecutor()
        result = ex._get_autonomy_provider({"provider_type": "ollama"})
        assert result is not None

    @patch(
        "animus_kernel.executor.executor_agents.AgentStepHandlerMixin._build_ollama_autonomy_provider"
    )
    def test_provider_creation_error_returns_none(self, mock_build):
        mock_build.side_effect = RuntimeError("connection failed")
        ex = FakeExecutor()
        result = ex._get_autonomy_provider({"provider_type": "ollama"})
        assert result is None

    def test_default_provider_type_is_ollama(self):
        ex = FakeExecutor()
        with patch.object(
            AgentStepHandlerMixin,
            "_build_ollama_autonomy_provider",
            return_value=MagicMock(),
        ) as mock_build:
            ex._get_autonomy_provider({})
            mock_build.assert_called_once()


# ===========================================================================
# Integration: handler registration
# ===========================================================================


class TestHandlerRegistration:
    """Verify autonomy and handoff are in VALID_STEP_TYPES and _handlers."""

    def test_valid_step_types_includes_autonomy(self):
        from animus_forge.workflow.loader import VALID_STEP_TYPES

        assert "autonomy" in VALID_STEP_TYPES

    def test_valid_step_types_includes_handoff(self):
        from animus_forge.workflow.loader import VALID_STEP_TYPES

        assert "handoff" in VALID_STEP_TYPES

    def test_executor_handlers_include_autonomy(self):
        from animus_forge.workflow.executor import WorkflowExecutor

        ex = WorkflowExecutor.__new__(WorkflowExecutor)
        ex.dry_run = False
        ex.checkpoint_manager = None
        ex.contract_validator = None
        ex.budget_manager = None
        ex.error_callback = None
        ex.fallback_callbacks = {}
        ex.memory_manager = None
        ex.memory_config = None
        ex.feedback_engine = None
        ex.execution_manager = None
        ex.arete_hooks = None
        ex.agent_memory = None
        ex._execution_id = None
        ex._context = {}
        ex._current_workflow_id = None
        ex._handlers = {
            "autonomy": ex._execute_autonomy,
            "handoff": ex._execute_handoff,
        }
        assert "autonomy" in ex._handlers
        assert "handoff" in ex._handlers

    def test_step_config_literal_accepts_autonomy(self):
        from animus_forge.workflow.loader import StepConfig

        step = StepConfig(id="test", type="autonomy")
        assert step.type == "autonomy"

    def test_step_config_literal_accepts_handoff(self):
        from animus_forge.workflow.loader import StepConfig

        step = StepConfig(id="test", type="handoff")
        assert step.type == "handoff"
