"""Tests for the Gorgon intelligence layer modules."""

import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from animus_forge.intelligence.cross_workflow_memory import (
    CrossWorkflowMemory,
)
from animus_forge.intelligence.feedback_engine import (
    AgentTrajectory,
    FeedbackEngine,
    FeedbackResult,
    WorkflowFeedback,
)
from animus_forge.intelligence.outcome_tracker import OutcomeRecord, OutcomeTracker
from animus_forge.intelligence.provider_router import (
    ProviderRouter,
    ProviderSelection,
)
from animus_forge.state.backends import SQLiteBackend
from animus_forge.state.memory import AgentMemory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend(tmp_path):
    """Create a SQLiteBackend backed by a temp file."""
    db_path = str(tmp_path / "test_outcomes.db")
    return SQLiteBackend(db_path)


@pytest.fixture
def tracker(backend):
    """Create an OutcomeTracker."""
    return OutcomeTracker(backend)


@pytest.fixture
def memory(tmp_path):
    """Create an AgentMemory instance."""
    db_path = str(tmp_path / "test_memory.db")
    return AgentMemory(db_path=db_path)


@pytest.fixture
def cross_memory(memory):
    """Create a CrossWorkflowMemory instance."""
    return CrossWorkflowMemory(memory)


def _make_outcome(**overrides) -> OutcomeRecord:
    """Helper to build an OutcomeRecord with sensible defaults."""
    defaults = dict(
        step_id="s1",
        workflow_id="w1",
        agent_role="builder",
        provider="openai",
        model="gpt-4o",
        success=True,
        quality_score=0.9,
        cost_usd=0.02,
        tokens_used=1000,
        latency_ms=800,
        metadata={},
    )
    defaults.update(overrides)
    return OutcomeRecord(**defaults)


# ===========================================================================
# OutcomeTracker tests
# ===========================================================================


class TestOutcomeTracker:
    """Tests for the OutcomeTracker module."""

    def test_record_and_retrieve(self, tracker):
        """Record an outcome and retrieve it by workflow_id."""
        outcome = _make_outcome(step_id="s1", workflow_id="w1")
        tracker.record(outcome)

        results = tracker.get_workflow_outcomes("w1")
        assert len(results) == 1
        assert results[0].step_id == "s1"
        assert results[0].success is True
        assert results[0].quality_score == 0.9

    def test_get_agent_success_rate_mixed(self, tracker):
        """Success rate with a mix of success and failure."""
        tracker.record(_make_outcome(step_id="s1", success=True))
        tracker.record(_make_outcome(step_id="s2", success=True))
        tracker.record(_make_outcome(step_id="s3", success=False))

        rate = tracker.get_agent_success_rate("builder")
        assert abs(rate - 2.0 / 3.0) < 0.01

    def test_get_provider_stats(self, tracker):
        """Provider stats returns correct aggregates."""
        tracker.record(_make_outcome(step_id="s1", cost_usd=0.01, latency_ms=100, success=True))
        tracker.record(_make_outcome(step_id="s2", cost_usd=0.03, latency_ms=300, success=False))

        stats = tracker.get_provider_stats("openai")
        assert stats.total_calls == 2
        assert abs(stats.avg_cost_usd - 0.02) < 0.001
        assert abs(stats.avg_latency_ms - 200.0) < 0.1
        assert abs(stats.success_rate - 0.5) < 0.01

    def test_get_provider_stats_with_model_filter(self, tracker):
        """Provider stats filtered by model."""
        tracker.record(_make_outcome(step_id="s1", model="gpt-4o", cost_usd=0.05))
        tracker.record(_make_outcome(step_id="s2", model="gpt-4o-mini", cost_usd=0.01))

        stats = tracker.get_provider_stats("openai", model="gpt-4o-mini")
        assert stats.total_calls == 1
        assert abs(stats.avg_cost_usd - 0.01) < 0.001

    def test_get_best_provider_for_role(self, tracker):
        """Best provider picks highest quality*success combo."""
        # Provider A: high quality, always succeeds
        for i in range(3):
            tracker.record(
                _make_outcome(
                    step_id=f"a{i}",
                    provider="openai",
                    model="gpt-4o",
                    quality_score=0.95,
                    success=True,
                )
            )
        # Provider B: lower quality, sometimes fails
        for i in range(3):
            tracker.record(
                _make_outcome(
                    step_id=f"b{i}",
                    provider="anthropic",
                    model="claude-3-haiku",
                    quality_score=0.60,
                    success=(i != 2),
                )
            )

        provider, model = tracker.get_best_provider_for_role("builder")
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_get_best_provider_empty(self, tracker):
        """Returns empty strings when no records exist."""
        provider, model = tracker.get_best_provider_for_role("nonexistent")
        assert provider == ""
        assert model == ""

    def test_thread_safety(self, tracker):
        """Record from multiple threads without errors."""
        errors = []

        def _record(idx):
            try:
                tracker.record(_make_outcome(step_id=f"thread-{idx}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        results = tracker.get_workflow_outcomes("w1")
        assert len(results) == 20


# ===========================================================================
# CrossWorkflowMemory tests
# ===========================================================================


class TestCrossWorkflowMemory:
    """Tests for the CrossWorkflowMemory module."""

    def test_record_learning(self, cross_memory):
        """record_learning stores a learned memory and returns an id."""
        mid = cross_memory.record_learning("reviewer", "Always check edge cases")
        assert isinstance(mid, int)
        assert mid > 0

    def test_get_agent_profile(self, cross_memory):
        """get_agent_profile returns accumulated stats."""
        cross_memory.record_learning(
            "builder",
            "Use type hints",
            importance=0.8,
            tags=["success"],
        )
        cross_memory.record_learning(
            "builder",
            "Avoid broad exceptions",
            importance=0.6,
            tags=["failure"],
        )

        profile = cross_memory.get_agent_profile("builder")
        assert profile.agent_role == "builder"
        assert profile.total_executions == 2
        assert profile.success_rate == 0.5  # 1 of 2 tagged success
        assert len(profile.top_learnings) == 2

    def test_get_agent_profile_empty(self, cross_memory):
        """get_agent_profile with no data returns empty profile."""
        profile = cross_memory.get_agent_profile("nonexistent")
        assert profile.total_executions == 0
        assert profile.success_rate == 0.0

    def test_build_context_for_agent(self, cross_memory, memory):
        """build_context_for_agent returns a formatted context string."""
        cross_memory.record_learning("builder", "FastAPI uses async endpoints", tags=["tip"])
        cross_memory.record_learning("builder", "Always validate input data", tags=["tip"])

        # Ensure created_at is timezone-aware (SQLite stores naive timestamps)
        now_iso = datetime.now(UTC).isoformat()
        with memory.backend.transaction():
            memory.backend.execute(
                "UPDATE agent_memories SET created_at = ?, accessed_at = ?",
                (now_iso, now_iso),
            )

        context = cross_memory.build_context_for_agent("builder", "Write a new FastAPI endpoint")
        assert "Cross-Workflow Learnings" in context
        assert "FastAPI" in context or "validate" in context

    def test_build_context_empty(self, cross_memory):
        """build_context_for_agent returns empty string with no memories."""
        context = cross_memory.build_context_for_agent("nobody", "some task")
        assert context == ""

    def test_detect_patterns(self, cross_memory):
        """detect_patterns finds recurring phrases."""
        for i in range(4):
            cross_memory.record_learning("tester", f"Always check error handling in test {i}")

        patterns = cross_memory.detect_patterns("tester", min_occurrences=3)
        assert len(patterns) > 0
        # "error" or "handling" or "check" should appear as a pattern
        phrase_texts = [p.phrase for p in patterns]
        assert any("error" in p or "handling" in p or "check" in p for p in phrase_texts)

    def test_detect_patterns_empty(self, cross_memory):
        """detect_patterns returns empty list with no memories."""
        patterns = cross_memory.detect_patterns("nobody")
        assert patterns == []

    def test_promote_memory(self, cross_memory, memory):
        """promote_memory increases importance."""
        mid = cross_memory.record_learning("builder", "Important insight", importance=0.3)
        result = cross_memory.promote_memory(mid, 0.9)
        assert result is True

        # Verify the importance changed by checking the raw DB value
        row = memory.backend.fetchone("SELECT importance FROM agent_memories WHERE id = ?", (mid,))
        assert row is not None
        assert abs(row["importance"] - 0.9) < 0.01

    def test_promote_memory_not_found(self, cross_memory):
        """promote_memory returns False for nonexistent id."""
        result = cross_memory.promote_memory(99999, 0.9)
        assert result is False

    def test_decay_memories(self, cross_memory, memory):
        """decay_memories reduces old memory importance."""
        # Store a memory and manually backdate it via direct SQL
        mid = cross_memory.record_learning("builder", "Old insight", importance=0.5)
        old_date = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        with memory.backend.transaction():
            memory.backend.execute(
                "UPDATE agent_memories SET created_at = ?, accessed_at = ? WHERE id = ?",
                (old_date, old_date, mid),
            )

        affected = cross_memory.decay_memories(
            half_life_days=90, min_importance=0.05, agent_roles=["builder"]
        )
        assert affected >= 1


# ===========================================================================
# ProviderRouter tests
# ===========================================================================


class TestProviderRouter:
    """Tests for the ProviderRouter module."""

    def _make_router(self, **kwargs):
        """Create a router with a mock outcome tracker."""
        mock_tracker = MagicMock()
        mock_tracker.get_provider_stats.side_effect = Exception("no data")
        return ProviderRouter(outcome_tracker=mock_tracker, **kwargs)

    def test_select_provider_returns_valid_selection(self):
        """select_provider returns a ProviderSelection."""
        router = self._make_router()
        sel = router.select_provider("builder")
        assert isinstance(sel, ProviderSelection)
        assert sel.provider != ""
        assert sel.model != ""
        assert 0.0 <= sel.confidence <= 1.0

    def test_cheapest_strategy(self):
        """CHEAPEST strategy picks lowest cost model."""
        router = self._make_router()
        sel = router.select_provider("builder", strategy="cheapest")
        # gpt-4o-mini (0.000375) or claude-3-haiku (0.00075) are cheapest
        assert sel.model in ("gpt-4o-mini", "claude-3-haiku")

    def test_quality_strategy(self):
        """QUALITY strategy picks highest quality model."""
        router = self._make_router()
        sel = router.select_provider("builder", strategy="quality")
        # claude-sonnet-4 (0.92) is highest quality by default
        assert sel.model == "claude-sonnet-4-20250514"

    def test_balanced_strategy_produces_weighted_score(self):
        """BALANCED strategy returns a selection with a fallback."""
        router = self._make_router()
        sel = router.select_provider("builder", strategy="balanced")
        assert isinstance(sel, ProviderSelection)
        # Balanced should attach a fallback (runner-up) when multiple candidates exist
        assert sel.fallback is not None

    def test_budget_constraint_forces_cheaper(self):
        """Budget constraint excludes expensive models."""
        router = self._make_router()
        # Very tight budget should exclude costly models
        sel = router.select_provider("builder", budget_remaining=0.0005)
        assert sel.model in ("gpt-4o-mini", "claude-3-haiku")

    def test_fallback_set_for_critical_complexity(self):
        """Critical complexity with FALLBACK strategy sets a fallback."""
        router = self._make_router()
        sel = router.select_provider("builder", task_complexity="critical", strategy="fallback")
        assert sel.fallback is not None

    def test_update_after_execution_changes_scores(self):
        """update_after_execution changes internal routing scores."""
        router = self._make_router()

        # Record a very high quality execution for a specific combo
        router.update_after_execution(
            "builder",
            "openai",
            "gpt-4o-mini",
            {"quality_score": 0.99, "latency_seconds": 0.2, "cost_usd": 0.0001},
        )

        # Now quality strategy should still pick the highest-quality model
        # but the EMA stats for gpt-4o-mini should have been updated
        key = ("builder", "openai", "gpt-4o-mini")
        assert key in router._stats
        assert router._stats[key].sample_count == 1
        # Quality should be EMA-blended: 0.3*0.99 + 0.7*0.5 = 0.647
        assert router._stats[key].quality > 0.6

    def test_no_candidates_returns_default(self):
        """When no candidates match, a default selection is returned."""
        router = self._make_router()
        # Impossibly small budget
        sel = router.select_provider("builder", budget_remaining=0.0)
        assert sel.confidence == 0.2  # default fallback confidence


# ===========================================================================
# FeedbackEngine tests
# ===========================================================================


class TestFeedbackEngine:
    """Tests for the FeedbackEngine module."""

    @pytest.fixture
    def engine(self, tracker, cross_memory):
        """Create a FeedbackEngine with real tracker and mocked router/memory."""
        mock_router = MagicMock()
        return FeedbackEngine(
            outcome_tracker=tracker,
            cross_memory=cross_memory,
            provider_router=mock_router,
        )

    def test_process_step_result_records_outcome(self, engine, tracker):
        """process_step_result records the outcome in the tracker."""
        result = engine.process_step_result(
            step_id="s1",
            workflow_id="w1",
            agent_role="builder",
            provider="openai",
            model="gpt-4o",
            step_result={"success": True, "quality_score": 0.9, "latency_ms": 500},
            cost_usd=0.02,
            tokens_used=1000,
        )
        assert isinstance(result, FeedbackResult)
        assert result.outcome_recorded is True
        assert result.step_id == "s1"

    def test_process_step_result_generates_learning_on_failure(self, engine):
        """Failure generates a learning."""
        result = engine.process_step_result(
            step_id="s1",
            workflow_id="w1",
            agent_role="builder",
            provider="openai",
            model="gpt-4o",
            step_result={"success": False, "quality_score": 0.1, "latency_ms": 500},
            cost_usd=0.02,
            tokens_used=1000,
        )
        assert result.notable is True
        assert result.learning_generated is not None
        assert (
            "failed" in result.learning_generated.lower()
            or "first execution" in result.learning_generated.lower()
        )

    def test_process_workflow_result_produces_insights(self, engine, tracker):
        """process_workflow_result produces insights."""
        # Record some step outcomes first
        tracker.record(_make_outcome(step_id="s1", workflow_id="wf1", success=True, cost_usd=0.05))
        tracker.record(_make_outcome(step_id="s2", workflow_id="wf1", success=False, cost_usd=0.01))

        feedback = engine.process_workflow_result(
            workflow_id="wf1",
            workflow_name="test-workflow",
            execution_result={"steps": []},
        )
        assert isinstance(feedback, WorkflowFeedback)
        assert feedback.total_steps == 2
        assert feedback.successful_steps == 1
        assert len(feedback.insights) >= 1
        assert "test-workflow" in feedback.insights[0]

    def test_process_workflow_result_empty(self, engine):
        """process_workflow_result with no outcomes."""
        feedback = engine.process_workflow_result(
            workflow_id="empty-wf",
            workflow_name="empty",
            execution_result={"steps": []},
        )
        assert feedback.total_steps == 0

    def test_analyze_agent_trajectory_improving(self, engine, tracker):
        """Detects improving trend when recent half is better."""
        now = datetime.now(UTC)
        # Earlier half: mostly failures
        for i in range(5):
            ts = (now - timedelta(days=25 - i)).isoformat()
            tracker.record(
                _make_outcome(
                    step_id=f"old-{i}",
                    success=False,
                    quality_score=0.3,
                    cost_usd=0.01,
                    timestamp=ts,
                )
            )
        # Recent half: mostly successes
        for i in range(5):
            ts = (now - timedelta(days=10 - i)).isoformat()
            tracker.record(
                _make_outcome(
                    step_id=f"new-{i}",
                    success=True,
                    quality_score=0.9,
                    cost_usd=0.01,
                    timestamp=ts,
                )
            )

        trajectory = engine.analyze_agent_trajectory("builder", days=30)
        assert isinstance(trajectory, AgentTrajectory)
        assert trajectory.trend == "improving"
        assert trajectory.current_success_rate > trajectory.previous_success_rate

    def test_analyze_agent_trajectory_declining(self, engine, tracker):
        """Detects declining trend when recent half is worse."""
        now = datetime.now(UTC)
        # Earlier half: successes
        for i in range(5):
            ts = (now - timedelta(days=25 - i)).isoformat()
            tracker.record(
                _make_outcome(
                    step_id=f"old-d-{i}",
                    success=True,
                    quality_score=0.9,
                    cost_usd=0.01,
                    timestamp=ts,
                )
            )
        # Recent half: failures
        for i in range(5):
            ts = (now - timedelta(days=10 - i)).isoformat()
            tracker.record(
                _make_outcome(
                    step_id=f"new-d-{i}",
                    success=False,
                    quality_score=0.2,
                    cost_usd=0.01,
                    timestamp=ts,
                )
            )

        trajectory = engine.analyze_agent_trajectory("builder", days=30)
        assert trajectory.trend == "declining"

    def test_suggest_workflow_improvements_provider_upgrade(self, engine, tracker):
        """Suggests provider upgrade for low success rate."""
        # Record enough failures for the same role/workflow
        for i in range(5):
            tracker.record(
                _make_outcome(
                    step_id=f"fail-{i}",
                    workflow_id="wf-bad",
                    agent_role="reviewer",
                    success=(i == 0),  # 1/5 = 20%
                    quality_score=0.3,
                    cost_usd=0.02,
                )
            )

        suggestions = engine.suggest_workflow_improvements("wf-bad")
        assert len(suggestions) >= 1
        categories = [s.category for s in suggestions]
        assert "provider_upgrade" in categories

    def test_suggest_workflow_improvements_empty(self, engine):
        """No suggestions when no outcomes exist."""
        suggestions = engine.suggest_workflow_improvements("nonexistent")
        assert suggestions == []
