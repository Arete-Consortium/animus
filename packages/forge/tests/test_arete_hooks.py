"""Tests for AreteHooks runtime wiring."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from animus_forge.workflow.arete_hooks import (
    AreteHooks,
    _classify_failure,
    _extract_domain,
    get_arete_hooks,
)

# ─── AreteHooks.on_step_failure ────────────────────────────────────────


class TestOnStepFailure:
    """Tests for the error callback hook."""

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", False)
    def test_noop_without_quorum(self):
        hooks = AreteHooks(phi_scorer=MagicMock(), stigmergy_field=MagicMock())
        # Should not raise
        hooks.on_step_failure("step1", "wf1", Exception("err"))

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_records_phi_score(self, mock_marker, mock_record):
        mock_record.return_value = 0.4
        scorer = MagicMock()
        field = MagicMock()
        hooks = AreteHooks(phi_scorer=scorer, stigmergy_field=field)
        hooks.on_step_failure("retry_step", "wf-1", Exception("max retries exceeded"))
        mock_record.assert_called_once()
        assert mock_record.call_args.kwargs["failure_type"] == "tool_loop"

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_leaves_stigmergy_marker(self, mock_marker, mock_record):
        mock_record.return_value = 0.5
        scorer = MagicMock()
        field = MagicMock()
        hooks = AreteHooks(phi_scorer=scorer, stigmergy_field=field)
        hooks.on_step_failure("build", "wf-2", Exception("not found"))
        mock_marker.assert_called_once()
        assert mock_marker.call_args.kwargs["target"] == "wf-2/build"

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_no_scorer_skips_phi(self, mock_marker, mock_record):
        hooks = AreteHooks(phi_scorer=None, stigmergy_field=MagicMock())
        hooks.on_step_failure("s1", "wf1", Exception("err"))
        mock_record.assert_not_called()
        mock_marker.assert_called_once()

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_no_field_skips_marker(self, mock_marker, mock_record):
        mock_record.return_value = 0.5
        hooks = AreteHooks(phi_scorer=MagicMock(), stigmergy_field=None)
        hooks.on_step_failure("s1", "wf1", Exception("err"))
        mock_record.assert_called_once()
        mock_marker.assert_not_called()

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_phi_exception_swallowed(self, mock_marker, mock_record):
        mock_record.side_effect = RuntimeError("scorer broken")
        hooks = AreteHooks(phi_scorer=MagicMock(), stigmergy_field=MagicMock())
        # Should not raise
        hooks.on_step_failure("s1", "wf1", Exception("err"))
        mock_marker.assert_called_once()  # marker still called

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_uses_default_agent_id(self, mock_marker, mock_record):
        mock_record.return_value = 0.5
        hooks = AreteHooks(
            phi_scorer=MagicMock(),
            stigmergy_field=MagicMock(),
            default_agent_id="my-agent",
        )
        hooks.on_step_failure("s1", "wf1", Exception("err"))
        assert mock_record.call_args.kwargs["agent_id"] == "my-agent"

    @patch("animus_kernel.executor.arete_hooks.HAS_QUORUM_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.record_failure_outcome", create=True)
    @patch("animus_kernel.executor.arete_hooks.leave_autopsy_marker", create=True)
    def test_error_text_truncated_to_500(self, mock_marker, mock_record):
        mock_record.return_value = 0.5
        hooks = AreteHooks(phi_scorer=MagicMock(), stigmergy_field=MagicMock())
        long_error = "x" * 1000
        hooks.on_step_failure("s1", "wf1", Exception(long_error))
        details = mock_marker.call_args.kwargs["details"]
        assert len(details) == 500


# ─── AreteHooks.on_workflow_complete ───────────────────────────────────


class TestOnWorkflowComplete:
    """Tests for the post-workflow hook."""

    @patch("animus_kernel.executor.arete_hooks.HAS_CORE_BRIDGE", False)
    def test_noop_without_core(self):
        hooks = AreteHooks(memory_layer=MagicMock())
        hooks.on_workflow_complete("wf1", "success")

    def test_noop_on_failure(self):
        hooks = AreteHooks(memory_layer=MagicMock())
        hooks.on_workflow_complete("wf1", "failed")

    def test_noop_without_memory_layer(self):
        hooks = AreteHooks()
        hooks.on_workflow_complete("wf1", "success")

    @patch("animus_kernel.executor.arete_hooks.HAS_CORE_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.auto_sync_verdicts", create=True)
    def test_syncs_on_success(self, mock_sync):
        mock_sync.return_value = 3
        memory = MagicMock()
        hooks = AreteHooks(memory_layer=memory)
        hooks.on_workflow_complete("wf-1", "success")
        mock_sync.assert_called_once_with(memory)

    @patch("animus_kernel.executor.arete_hooks.HAS_CORE_BRIDGE", True)
    @patch("animus_kernel.executor.arete_hooks.auto_sync_verdicts", create=True)
    def test_sync_exception_swallowed(self, mock_sync):
        mock_sync.side_effect = RuntimeError("DB locked")
        hooks = AreteHooks(memory_layer=MagicMock())
        # Should not raise
        hooks.on_workflow_complete("wf-1", "success")


# ─── _classify_failure ─────────────────────────────────────────────────


class TestClassifyFailure:
    """Tests for heuristic failure classification."""

    def test_loop_keywords(self):
        assert _classify_failure("max retries exceeded") == "tool_loop"
        assert _classify_failure("infinite loop detected") == "tool_loop"

    def test_hallucination_keywords(self):
        assert _classify_failure("file not found") == "tool_hallucination"
        assert _classify_failure("does not exist") == "tool_hallucination"

    def test_overconfidence_keywords(self):
        assert _classify_failure("confidence threshold not met") == "overconfidence"

    def test_autoimmunity_keywords(self):
        assert _classify_failure("conflicting goals") == "goal_autoimmunity"

    def test_cancer_keywords(self):
        assert _classify_failure("scope bloat detected") == "goal_cancer"

    def test_necrosis_keywords(self):
        assert _classify_failure("stale task abandoned") == "goal_necrosis"

    def test_unknown_default(self):
        assert _classify_failure("segfault at 0x0") == "unknown"

    def test_case_insensitive(self):
        assert _classify_failure("MAX RETRIES") == "tool_loop"


# ─── _extract_domain ──────────────────────────────────────────────────


class TestExtractDomain:
    """Tests for domain extraction from step IDs."""

    def test_compound_step_id(self):
        assert _extract_domain("security_review") == "security"

    def test_single_word(self):
        assert _extract_domain("build") == "general"

    def test_multiple_underscores(self):
        assert _extract_domain("code_quality_check") == "code"


# ─── get_arete_hooks factory ─────────────────────────────────────────


class TestGetAreteHooks:
    """Tests for the AreteHooks factory function."""

    def test_returns_none_when_nothing_available(self):
        with patch.dict(
            "sys.modules",
            {
                "animus_quorum.scoring": None,
                "animus_quorum.stigmergy": None,
                "animus_kernel.memory": None,
            },
        ):
            result = get_arete_hooks()
        assert result is None

    def test_returns_hooks_with_phi_scorer(self):
        fake_scoring = types.ModuleType("animus_quorum.scoring")
        fake_scoring.PhiScorer = MagicMock
        fake_scoring.ScoreStore = MagicMock
        with patch.dict(
            "sys.modules",
            {
                "animus_quorum.scoring": fake_scoring,
                "animus_quorum.stigmergy": None,
                "animus_kernel.memory": None,
            },
        ):
            result = get_arete_hooks()
        assert result is not None
        assert result._phi_scorer is not None
        assert result._stigmergy_field is None
        assert result._memory_layer is None

    def test_returns_hooks_with_all_deps(self):
        fake_scoring = types.ModuleType("animus_quorum.scoring")
        fake_scoring.PhiScorer = MagicMock
        fake_scoring.ScoreStore = MagicMock
        fake_stigmergy = types.ModuleType("animus_quorum.stigmergy")
        fake_stigmergy.StigmergyField = MagicMock
        fake_memory = types.ModuleType("animus_kernel.memory")
        fake_memory.MemoryLayer = MagicMock
        with patch.dict(
            "sys.modules",
            {
                "animus_quorum.scoring": fake_scoring,
                "animus_quorum.stigmergy": fake_stigmergy,
                "animus_kernel.memory": fake_memory,
            },
        ):
            result = get_arete_hooks()
        assert result is not None
        assert result._phi_scorer is not None
        assert result._stigmergy_field is not None
        assert result._memory_layer is not None
