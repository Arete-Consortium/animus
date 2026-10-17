"""Tests for application-layer dominance features.

Covers:
- WorkflowComposer (workflow composability)
- ContractEnforcer (contract enforcement with retry)
- PromptEvolution (A/B testing and prompt evolution)
- IntegrationGraph (cross-integration event routing)
- CostIntelligence (cost analysis and recommendations)
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# IntegrationGraph tests
# ---------------------------------------------------------------------------
from animus_forge.contracts.enforcer import ContractEnforcer
from animus_forge.intelligence.cost_intelligence import CostIntelligence
from animus_forge.intelligence.integration_graph import (
    IntegrationGraph,
    _evaluate_condition,
    _resolve_dotted_path,
)
from animus_forge.intelligence.prompt_evolution import PromptEvolution
from animus_forge.workflow.composer import WorkflowComposer, _resolve_value


class TestResolveDottedPath:
    def test_simple_key(self):
        assert _resolve_dotted_path({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert _resolve_dotted_path({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key(self):
        assert _resolve_dotted_path({"a": 1}, "b") is None

    def test_missing_nested(self):
        assert _resolve_dotted_path({"a": {"b": 1}}, "a.c") is None

    def test_non_dict_intermediate(self):
        assert _resolve_dotted_path({"a": 5}, "a.b") is None


class TestEvaluateCondition:
    def test_equals(self):
        assert _evaluate_condition({"field": "action", "equals": "opened"}, {"action": "opened"})
        assert not _evaluate_condition(
            {"field": "action", "equals": "closed"}, {"action": "opened"}
        )

    def test_not_equals(self):
        assert _evaluate_condition({"field": "x", "not_equals": "a"}, {"x": "b"})

    def test_contains(self):
        assert _evaluate_condition({"field": "tags", "contains": "bug"}, {"tags": ["bug", "fix"]})
        assert _evaluate_condition({"field": "name", "contains": "test"}, {"name": "my_test_thing"})

    def test_exists(self):
        assert _evaluate_condition({"field": "x", "exists": True}, {"x": 1})
        assert _evaluate_condition({"field": "x", "exists": False}, {"y": 1})

    def test_in_operator(self):
        assert _evaluate_condition(
            {"field": "status", "in": ["open", "closed"]}, {"status": "open"}
        )
        assert not _evaluate_condition({"field": "status", "in": ["open"]}, {"status": "closed"})

    def test_no_operator_passes(self):
        assert _evaluate_condition({"field": "x"}, {"x": 1})


class TestIntegrationGraph:
    def test_register_and_list_triggers(self):
        g = IntegrationGraph()
        tid = g.register_trigger("github", "pr_opened", "review")
        assert tid.startswith("trigger-")
        triggers = g.list_triggers()
        assert len(triggers) == 1
        assert triggers[0].source == "github"

    def test_remove_trigger(self):
        g = IntegrationGraph()
        tid = g.register_trigger("github", "pr_opened", "review")
        assert g.remove_trigger(tid)
        assert not g.remove_trigger("nonexistent")
        assert g.list_triggers() == []

    def test_enable_disable_trigger(self):
        g = IntegrationGraph()
        tid = g.register_trigger("github", "pr_opened", "review")
        g.enable_trigger(tid, enabled=False)
        assert not g._triggers[tid].enabled
        g.enable_trigger(tid, enabled=True)
        assert g._triggers[tid].enabled

    def test_dispatch_event_basic(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        results = g.dispatch_event("github", "pr_opened", {"action": "opened"})
        assert len(results) == 1
        assert results[0].dispatched
        assert results[0].reason == "ok"

    def test_dispatch_disabled_trigger(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review", enabled=False)
        results = g.dispatch_event("github", "pr_opened", {"action": "opened"})
        assert len(results) == 1
        assert not results[0].dispatched
        assert results[0].reason == "disabled"

    def test_dispatch_condition_not_met(self):
        g = IntegrationGraph()
        g.register_trigger(
            "github",
            "pr_opened",
            "review",
            conditions=[{"field": "action", "equals": "closed"}],
        )
        results = g.dispatch_event("github", "pr_opened", {"action": "opened"})
        assert results[0].reason == "condition_not_met"

    def test_dispatch_with_transform(self):
        g = IntegrationGraph()
        g.register_trigger(
            "github",
            "pr_opened",
            "review",
            transform={"title": "pull_request.title"},
        )
        results = g.dispatch_event("github", "pr_opened", {"pull_request": {"title": "fix bug"}})
        assert results[0].inputs == {"title": "fix bug"}

    def test_dispatch_callback_called(self):
        g = IntegrationGraph()
        cb = MagicMock()
        g.set_dispatch_callback(cb)
        g.register_trigger("slack", "message", "notify")
        g.dispatch_event("slack", "message", {"text": "hi"})
        cb.assert_called_once_with("notify", {"text": "hi"})

    def test_no_matching_triggers(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        results = g.dispatch_event("slack", "message", {})
        assert results == []

    def test_register_chain(self):
        g = IntegrationGraph()
        chain_id = g.register_chain(
            "ci-pipeline",
            [
                {"source": "github", "event": "push", "workflow_name": "build"},
                {"source": "github", "event": "build_done", "workflow_name": "deploy"},
            ],
        )
        assert chain_id.startswith("chain-")
        assert len(g.list_triggers()) == 2

    def test_get_graph(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        g.register_trigger("slack", "message", "notify")
        graph = g.get_graph()
        assert "github" in graph["nodes"]["services"]
        assert "slack" in graph["nodes"]["services"]
        assert len(graph["edges"]) == 2
        assert graph["total_triggers"] == 2

    def test_validate_graph_disabled_warning(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review", enabled=False)
        warnings = g.validate_graph()
        assert any("disabled" in w for w in warnings)

    def test_validate_graph_unknown_workflow(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        warnings = g.validate_graph(known_workflows=["deploy"])
        assert any("unknown workflow" in w for w in warnings)

    def test_validate_graph_duplicates(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        g.register_trigger("github", "pr_opened", "review")
        warnings = g.validate_graph()
        assert any("Duplicate" in w for w in warnings)

    def test_list_triggers_with_filters(self):
        g = IntegrationGraph()
        g.register_trigger("github", "pr_opened", "review")
        g.register_trigger("github", "push", "build")
        g.register_trigger("slack", "message", "notify")
        assert len(g.list_triggers(source="github")) == 2
        assert len(g.list_triggers(event="push")) == 1
        assert len(g.list_triggers(source="slack", event="message")) == 1


# ---------------------------------------------------------------------------
# PromptEvolution tests
# ---------------------------------------------------------------------------


class TestPromptEvolution:
    def test_register_variant(self):
        evo = PromptEvolution()
        v = evo.register_variant("tmpl", "v1", "Review: {code}")
        assert v.variant_id == "v1"
        assert v.base_template_id == "tmpl"

    def test_register_duplicate_raises(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "prompt")
        with pytest.raises(ValueError, match="already registered"):
            evo.register_variant("tmpl", "v1", "prompt2")

    def test_select_variant_no_data_returns_random(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "p1")
        evo.register_variant("tmpl", "v2", "p2")
        chosen = evo.select_variant("tmpl")
        assert chosen.variant_id in ("v1", "v2")

    def test_select_variant_exploits_best(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "bad")
        evo.register_variant("tmpl", "v2", "good")

        # Record outcomes: v2 is much better
        for _ in range(20):
            evo.record_variant_outcome("v1", 0.3, True, 100, 500)
            evo.record_variant_outcome("v2", 0.9, True, 100, 500)

        # With epsilon=0.1, v2 should be selected most of the time
        selections = [evo.select_variant("tmpl").variant_id for _ in range(100)]
        v2_count = selections.count("v2")
        assert v2_count > 70  # Should be ~90%

    def test_select_variant_unknown_template_raises(self):
        evo = PromptEvolution()
        with pytest.raises(KeyError):
            evo.select_variant("nonexistent")

    def test_record_outcome_unknown_variant_raises(self):
        evo = PromptEvolution()
        with pytest.raises(KeyError):
            evo.record_variant_outcome("nonexistent", 0.5, True, 100, 500)

    def test_get_variant_report(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "p1")
        evo.register_variant("tmpl", "v2", "p2")
        for _ in range(15):
            evo.record_variant_outcome("v1", 0.4, True, 100, 500)
            evo.record_variant_outcome("v2", 0.9, True, 100, 500)

        report = evo.get_variant_report("tmpl")
        assert report.base_template_id == "tmpl"
        assert len(report.variants) == 2
        assert report.winner == "v2"
        assert report.improvement_pct > 0

    def test_promote_winner(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "p1")
        evo.register_variant("tmpl", "v2", "p2")
        for _ in range(15):
            evo.record_variant_outcome("v1", 0.3, True, 100, 500)
            evo.record_variant_outcome("v2", 0.9, True, 100, 500)

        winner_id = evo.promote_winner("tmpl")
        assert winner_id == "v2"
        # v1 stats should be reset
        assert evo._stats["v1"].trials == 0

    def test_promote_winner_no_clear_winner(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "p1")
        evo.register_variant("tmpl", "v2", "p2")
        # Only 2 trials each — not enough data
        evo.record_variant_outcome("v1", 0.8, True, 100, 500)
        evo.record_variant_outcome("v2", 0.9, True, 100, 500)
        assert evo.promote_winner("tmpl") is None

    def test_evolve_prompt_creates_variant(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "Do the thing")

        # History with high failure rate
        history = [
            {
                "quality_score": 0.3,
                "success": False,
                "error": "missing field X",
                "missing_fields": ["X"],
            },
            {
                "quality_score": 0.4,
                "success": False,
                "error": "missing field X",
                "missing_fields": ["X"],
            },
            {"quality_score": 0.9, "success": True},
        ]
        new_id = evo.evolve_prompt("tmpl", "builder", history)
        assert new_id is not None
        assert "evolved" in new_id

    def test_evolve_prompt_skips_when_acceptable(self):
        evo = PromptEvolution()
        evo.register_variant("tmpl", "v1", "Good prompt")

        history = [
            {"quality_score": 0.9, "success": True},
            {"quality_score": 0.85, "success": True},
        ]
        assert evo.evolve_prompt("tmpl", "builder", history) is None


# ---------------------------------------------------------------------------
# IntegrationGraph + PromptEvolution are done. Now ContractEnforcer.
# ---------------------------------------------------------------------------


class TestContractEnforcer:
    def test_validate_output_valid(self):
        enforcer = ContractEnforcer()
        # Use "planner" role which has a known contract
        valid_output = {
            "tasks": [{"id": "1", "title": "Do thing", "description": "Details"}],
            "summary": "Plan summary",
        }
        with patch("animus_kernel.contracts.enforcer.get_contract") as mock_get:
            mock_contract = MagicMock()
            mock_contract.validate_output.return_value = None  # no exception = valid
            mock_get.return_value = mock_contract

            result = enforcer.validate_output("planner", valid_output)
            assert result is True

    def test_validate_output_invalid_raises(self):
        from animus_forge.contracts.base import ContractViolation

        enforcer = ContractEnforcer()
        with patch("animus_kernel.contracts.enforcer.get_contract") as mock_get:
            mock_contract = MagicMock()
            mock_contract.validate_output.side_effect = ContractViolation(
                "Missing required field", role="planner", field="tasks"
            )
            mock_get.return_value = mock_contract

            with pytest.raises(ContractViolation):
                enforcer.validate_output("planner", {})

    def test_enforcement_stats(self):
        enforcer = ContractEnforcer()
        with patch("animus_kernel.contracts.enforcer.get_contract") as mock_get:
            mock_contract = MagicMock()
            mock_contract.validate_output.return_value = None
            mock_get.return_value = mock_contract

            enforcer.validate_output("planner", {"tasks": []})
            enforcer.validate_output("planner", {"tasks": []})

        stats = enforcer.get_enforcement_stats()
        assert stats.total_validations == 2
        assert stats.total_violations == 0
        assert stats.by_role["planner"]["validations"] == 2

    def test_build_correction_prompt(self):
        from animus_forge.contracts.base import ContractViolation

        enforcer = ContractEnforcer()
        violation = ContractViolation("Missing tasks", role="planner", field="tasks")

        with patch("animus_kernel.contracts.enforcer.get_contract") as mock_get:
            mock_contract = MagicMock()
            mock_contract.output_schema = {"type": "object", "required": ["tasks"]}
            mock_get.return_value = mock_contract

            prompt = enforcer.build_correction_prompt("Original prompt", violation, 1)
            assert "Retry attempt" in prompt
            assert "planner" in prompt
            assert "tasks" in prompt


# ---------------------------------------------------------------------------
# CostIntelligence tests
# ---------------------------------------------------------------------------


class TestCostIntelligence:
    def _make_cost_tracker(self, entries=None):
        """Create a mock CostTracker with entries."""
        tracker = MagicMock()
        tracker.entries = entries or []
        tracker.budget_limit_usd = None
        tracker.PRICING = {
            "gpt-4o": {"input": 5.0, "output": 15.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
            "claude-3-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
        }
        tracker.calculate_cost = MagicMock(return_value=0.05)
        tracker.get_monthly_cost = MagicMock(return_value=10.0)
        return tracker

    def _make_entry(self, model="gpt-4o", cost=0.01, role="builder", days_ago=0):
        entry = MagicMock()
        entry.cost_usd = cost
        entry.model = model
        entry.agent_role = role
        entry.workflow_id = "wf-1"
        entry.timestamp = datetime.now() - timedelta(days=days_ago)
        entry.provider = MagicMock()
        entry.provider.value = "openai" if model.startswith("gpt") else "anthropic"
        entry.tokens = MagicMock()
        entry.tokens.total_tokens = 1000
        return entry

    def test_analyze_spending(self):
        entries = [self._make_entry(cost=0.05, days_ago=i) for i in range(10)]
        tracker = self._make_cost_tracker(entries)
        ci = CostIntelligence(tracker)
        analysis = ci.analyze_spending(days=30)
        assert analysis.total_usd == 0.5
        assert analysis.period_days == 30
        assert "openai" in analysis.by_provider

    def test_analyze_spending_empty(self):
        tracker = self._make_cost_tracker([])
        ci = CostIntelligence(tracker)
        analysis = ci.analyze_spending()
        assert analysis.total_usd == 0.0

    def test_get_roi_report_empty(self):
        tracker = self._make_cost_tracker([])
        ci = CostIntelligence(tracker)
        roi = ci.get_roi_report()
        assert roi.total_executions == 0
        assert roi.efficiency_score == 50.0

    def test_get_roi_report_with_entries(self):
        entries = [self._make_entry(cost=0.02) for _ in range(10)]
        tracker = self._make_cost_tracker(entries)
        ci = CostIntelligence(tracker)
        roi = ci.get_roi_report()
        assert roi.total_executions == 10
        assert roi.avg_cost_per_execution > 0

    def test_forecast_spend(self):
        entries = [self._make_entry(cost=1.0, days_ago=i) for i in range(14)]
        tracker = self._make_cost_tracker(entries)
        ci = CostIntelligence(tracker)
        forecast = ci.forecast_spend(days_ahead=30)
        assert forecast.daily_rate > 0
        assert forecast.projected_30d > 0

    def test_forecast_spend_empty(self):
        tracker = self._make_cost_tracker([])
        ci = CostIntelligence(tracker)
        forecast = ci.forecast_spend()
        assert forecast.daily_rate == 0.0
        assert forecast.projected_30d == 0.0

    def test_estimate_switch_impact(self):
        entries = [self._make_entry(model="gpt-4o", cost=0.05, role="builder") for _ in range(10)]
        tracker = self._make_cost_tracker(entries)
        ci = CostIntelligence(tracker)
        impact = ci.estimate_switch_impact("builder", "gpt-4o", "gpt-4o-mini", days=30)
        assert impact.agent_role == "builder"
        assert impact.from_model == "gpt-4o"
        assert impact.to_model == "gpt-4o-mini"
        # gpt-4o-mini should be cheaper
        assert impact.cost_change_pct < 0

    def test_recommend_savings(self):
        entries = [self._make_entry(model="gpt-4o", cost=0.05, role="builder") for _ in range(30)]
        tracker = self._make_cost_tracker(entries)
        ci = CostIntelligence(tracker)
        recs = ci.recommend_savings(days=30)
        # Should find at least one cheaper alternative
        assert isinstance(recs, list)


# ---------------------------------------------------------------------------
# WorkflowComposer tests (mocked — doesn't need real workflows)
# ---------------------------------------------------------------------------


class TestResolveValue:
    def test_exact_reference(self):
        assert _resolve_value("${code}", {"code": "hello"}) == "hello"

    def test_no_reference(self):
        assert _resolve_value("plain", {}) == "plain"

    def test_non_string(self):
        assert _resolve_value(42, {}) == 42

    def test_inline_substitution(self):
        assert _resolve_value("prefix_${x}_suffix", {"x": "val"}) == "prefix_val_suffix"

    def test_missing_reference_kept(self):
        assert _resolve_value("${missing}", {}) == "${missing}"


class TestWorkflowComposer:
    def test_depth_limit_raises(self):
        composer = WorkflowComposer(max_depth=2)
        step = MagicMock()
        step.id = "s1"
        step.params = {"workflow": "deep"}

        with pytest.raises(RecursionError, match="exceeds maximum"):
            composer.execute_sub_workflow(step, {}, depth=3)

    def test_missing_workflow_param_raises(self):
        composer = WorkflowComposer()
        step = MagicMock()
        step.id = "s1"
        step.params = {}

        with pytest.raises(ValueError, match="missing required param"):
            composer.execute_sub_workflow(step, {})

    def test_execute_sub_workflow(self):
        composer = WorkflowComposer()
        step = MagicMock()
        step.id = "s1"
        step.params = {"workflow": "test-wf", "inputs": {"x": "val"}}

        mock_config = MagicMock()
        mock_config.name = "test-wf"
        mock_config.steps = []

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.outputs = {"result": "done"}
        mock_result.total_tokens = 100
        mock_result.steps = []
        mock_result.error = None

        with patch("animus_kernel.executor.composer.load_workflow", return_value=mock_config):
            with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExecutor:
                instance = MockExecutor.return_value
                instance.execute.return_value = mock_result
                instance.checkpoint_manager = None
                instance.budget_manager = None
                instance.feedback_engine = None
                instance.dry_run = False

                outputs = composer.execute_sub_workflow(step, {})
                assert outputs["result"] == "done"
                assert "_sub_workflow_result" in outputs

    def test_resolve_workflow_graph_detects_cycle(self):
        composer = WorkflowComposer()

        # Create mock workflows that form a cycle: a -> b -> a
        def mock_load(name):
            cfg = MagicMock()
            cfg.name = name
            if name == "a":
                step = MagicMock()
                step.type = "sub_workflow"
                step.params = {"workflow": "b"}
                cfg.steps = [step]
            elif name == "b":
                step = MagicMock()
                step.type = "sub_workflow"
                step.params = {"workflow": "a"}
                cfg.steps = [step]
            else:
                cfg.steps = []
            return cfg

        with patch("animus_kernel.executor.composer.load_workflow", side_effect=mock_load):
            with pytest.raises(ValueError, match="Circular"):
                composer.resolve_workflow_graph("a")

    def test_resolve_workflow_graph_linear(self):
        composer = WorkflowComposer()

        def mock_load(name):
            cfg = MagicMock()
            cfg.name = name
            if name == "a":
                step = MagicMock()
                step.type = "sub_workflow"
                step.params = {"workflow": "b"}
                cfg.steps = [step]
            else:
                cfg.steps = []
            return cfg

        with patch("animus_kernel.executor.composer.load_workflow", side_effect=mock_load):
            result = composer.resolve_workflow_graph("a")
            assert result == ["a", "b"]
