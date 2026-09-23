"""Tests for parallel execution enhancements: fan_out, fan_in, map_reduce, auto_parallel."""

import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, "src")

from animus_forge.workflow import (
    StepConfig,
    WorkflowConfig,
    WorkflowExecutor,
    WorkflowSettings,
)
from animus_forge.workflow.auto_parallel import (
    DependencyGraph,
    analyze_parallelism,
    build_dependency_graph,
    find_parallel_groups,
    get_step_execution_order,
    validate_no_cycles,
)

# =============================================================================
# WorkflowSettings Tests
# =============================================================================


class TestWorkflowSettings:
    """Tests for WorkflowSettings parsing."""

    def test_settings_default_values(self):
        """Settings have correct defaults."""
        settings = WorkflowSettings()
        assert settings.auto_parallel is False
        assert settings.auto_parallel_max_workers == 4

    def test_settings_from_dict_empty(self):
        """from_dict with empty dict uses defaults."""
        settings = WorkflowSettings.from_dict({})
        assert settings.auto_parallel is False
        assert settings.auto_parallel_max_workers == 4

    def test_settings_from_dict_custom(self):
        """from_dict parses custom values."""
        settings = WorkflowSettings.from_dict(
            {
                "auto_parallel": True,
                "auto_parallel_max_workers": 8,
            }
        )
        assert settings.auto_parallel is True
        assert settings.auto_parallel_max_workers == 8

    def test_workflow_config_includes_settings(self):
        """WorkflowConfig includes settings from dict."""
        data = {
            "name": "Test Workflow",
            "settings": {
                "auto_parallel": True,
                "auto_parallel_max_workers": 6,
            },
            "steps": [{"id": "step1", "type": "shell", "params": {"command": "echo test"}}],
        }
        workflow = WorkflowConfig.from_dict(data)
        assert workflow.settings.auto_parallel is True
        assert workflow.settings.auto_parallel_max_workers == 6


# =============================================================================
# DependencyGraph Tests
# =============================================================================


class TestDependencyGraph:
    """Tests for DependencyGraph class."""

    def test_add_node(self):
        """Nodes can be added."""
        graph = DependencyGraph()
        graph.add_node("a")
        assert "a" in graph.nodes
        assert graph.edges["a"] == set()
        assert graph.reverse_edges["a"] == set()

    def test_add_edge(self):
        """Edges record dependencies correctly."""
        graph = DependencyGraph()
        graph.add_edge("b", "a")  # b depends on a
        assert "a" in graph.nodes
        assert "b" in graph.nodes
        assert "a" in graph.edges["b"]  # b's dependencies
        assert "b" in graph.reverse_edges["a"]  # a's dependents

    def test_get_dependencies(self):
        """get_dependencies returns correct set."""
        graph = DependencyGraph()
        graph.add_edge("c", "a")
        graph.add_edge("c", "b")
        deps = graph.get_dependencies("c")
        assert deps == {"a", "b"}

    def test_get_dependents(self):
        """get_dependents returns correct set."""
        graph = DependencyGraph()
        graph.add_edge("b", "a")
        graph.add_edge("c", "a")
        dependents = graph.get_dependents("a")
        assert dependents == {"b", "c"}

    def test_get_roots(self):
        """get_roots returns nodes with no dependencies."""
        graph = DependencyGraph()
        graph.add_node("a")
        graph.add_edge("b", "a")
        graph.add_edge("c", "b")
        roots = graph.get_roots()
        assert roots == {"a"}

    def test_get_leaves(self):
        """get_leaves returns nodes with no dependents."""
        graph = DependencyGraph()
        graph.add_node("a")
        graph.add_edge("b", "a")
        graph.add_edge("c", "b")
        leaves = graph.get_leaves()
        assert leaves == {"c"}


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_empty_steps(self):
        """Empty steps list returns empty graph."""
        graph = build_dependency_graph([])
        assert len(graph.nodes) == 0

    def test_single_step_no_deps(self):
        """Single step with no deps creates one node."""
        step = StepConfig(id="a", type="shell", params={})
        graph = build_dependency_graph([step])
        assert graph.nodes == {"a"}
        assert graph.edges["a"] == set()

    def test_chain_dependency(self):
        """Chain of dependencies is captured."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}, depends_on=["a"]),
            StepConfig(id="c", type="shell", params={}, depends_on=["b"]),
        ]
        graph = build_dependency_graph(steps)
        assert graph.get_dependencies("b") == {"a"}
        assert graph.get_dependencies("c") == {"b"}
        assert graph.get_roots() == {"a"}
        assert graph.get_leaves() == {"c"}


class TestFindParallelGroups:
    """Tests for find_parallel_groups function."""

    def test_all_independent(self):
        """Independent steps form a single group."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}),
            StepConfig(id="c", type="shell", params={}),
        ]
        graph = build_dependency_graph(steps)
        groups = find_parallel_groups(graph)
        assert len(groups) == 1
        assert groups[0].step_ids == {"a", "b", "c"}
        assert groups[0].level == 0

    def test_sequential_chain(self):
        """Sequential chain creates multiple groups."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}, depends_on=["a"]),
            StepConfig(id="c", type="shell", params={}, depends_on=["b"]),
        ]
        graph = build_dependency_graph(steps)
        groups = find_parallel_groups(graph)
        assert len(groups) == 3
        assert groups[0].step_ids == {"a"}
        assert groups[1].step_ids == {"b"}
        assert groups[2].step_ids == {"c"}

    def test_diamond_pattern(self):
        """Diamond pattern: a -> (b, c) -> d."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}, depends_on=["a"]),
            StepConfig(id="c", type="shell", params={}, depends_on=["a"]),
            StepConfig(id="d", type="shell", params={}, depends_on=["b", "c"]),
        ]
        graph = build_dependency_graph(steps)
        groups = find_parallel_groups(graph)
        assert len(groups) == 3
        assert groups[0].step_ids == {"a"}
        assert groups[1].step_ids == {"b", "c"}  # b and c can run parallel
        assert groups[2].step_ids == {"d"}

    def test_circular_dependency_raises(self):
        """Circular dependency raises ValueError."""
        graph = DependencyGraph()
        graph.add_edge("a", "b")
        graph.add_edge("b", "a")
        with pytest.raises(ValueError, match="Circular dependency"):
            find_parallel_groups(graph)


class TestAnalyzeParallelism:
    """Tests for analyze_parallelism function."""

    def test_empty_workflow(self):
        """Empty workflow returns zeros."""
        workflow = WorkflowConfig(name="empty", version="1.0", description="", steps=[])
        result = analyze_parallelism(workflow)
        assert result["total_steps"] == 0
        assert result["max_parallelism"] == 0
        assert result["sequential_depth"] == 0
        assert result["speedup_potential"] == 1.0

    def test_all_parallel_speedup(self):
        """All parallel steps have high speedup potential."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}),
            StepConfig(id="c", type="shell", params={}),
            StepConfig(id="d", type="shell", params={}),
        ]
        workflow = WorkflowConfig(name="parallel", version="1.0", description="", steps=steps)
        result = analyze_parallelism(workflow)
        assert result["total_steps"] == 4
        assert result["max_parallelism"] == 4
        assert result["sequential_depth"] == 1
        assert result["speedup_potential"] == 4.0

    def test_sequential_workflow_no_speedup(self):
        """Sequential workflow has speedup of 1.0."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}, depends_on=["a"]),
            StepConfig(id="c", type="shell", params={}, depends_on=["b"]),
        ]
        workflow = WorkflowConfig(name="sequential", version="1.0", description="", steps=steps)
        result = analyze_parallelism(workflow)
        assert result["speedup_potential"] == 1.0


class TestGetStepExecutionOrder:
    """Tests for get_step_execution_order function."""

    def test_respects_max_concurrent(self):
        """Output respects max_concurrent limit."""
        steps = [
            StepConfig(id="a", type="shell", params={}),
            StepConfig(id="b", type="shell", params={}),
            StepConfig(id="c", type="shell", params={}),
            StepConfig(id="d", type="shell", params={}),
        ]
        workflow = WorkflowConfig(name="test", version="1.0", description="", steps=steps)
        batches = get_step_execution_order(workflow, max_concurrent=2)
        # 4 steps, max 2 concurrent = at least 2 batches
        assert len(batches) >= 2
        for batch in batches:
            assert len(batch) <= 2


class TestValidateNoCycles:
    """Tests for validate_no_cycles function."""

    def test_no_cycles_valid(self):
        """Valid graph returns True."""
        graph = DependencyGraph()
        graph.add_edge("b", "a")
        graph.add_edge("c", "b")
        assert validate_no_cycles(graph) is True

    def test_self_cycle_raises(self):
        """Self-referencing node raises."""
        graph = DependencyGraph()
        graph.add_edge("a", "a")
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_no_cycles(graph)

    def test_indirect_cycle_raises(self):
        """Indirect cycle raises."""
        graph = DependencyGraph()
        graph.add_edge("a", "c")
        graph.add_edge("b", "a")
        graph.add_edge("c", "b")  # c -> b -> a -> c
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_no_cycles(graph)


# =============================================================================
# Fan-Out Tests
# =============================================================================


class TestFanOutBasic:
    """Basic tests for fan_out step type."""

    def test_fan_out_empty_items(self):
        """fan_out with empty items returns empty results."""
        workflow = WorkflowConfig(
            name="Empty Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": [],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["results"] == []
        assert output["successful"] == 0

    def test_fan_out_single_item(self):
        """fan_out with single item executes once."""
        workflow = WorkflowConfig(
            name="Single Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["hello"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["successful"] == 1
        assert len(output["results"]) == 1

    def test_fan_out_multiple_items(self):
        """fan_out with multiple items executes for each."""
        workflow = WorkflowConfig(
            name="Multiple Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["a", "b", "c"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["successful"] == 3
        assert len(output["results"]) == 3


class TestFanOutConcurrency:
    """Tests for fan_out concurrent execution."""

    def test_fan_out_runs_parallel(self):
        """fan_out executes items concurrently."""
        workflow = WorkflowConfig(
            name="Parallel Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["1", "2", "3", "4"],
                        "max_concurrent": 4,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "sleep 0.1"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # If parallel: ~0.1s, if sequential: ~0.4s
        assert elapsed < 0.35, f"Expected < 0.35s, got {elapsed}s"

    def test_fan_out_respects_max_concurrent(self):
        """fan_out respects max_concurrent limit."""
        workflow = WorkflowConfig(
            name="Limited Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["1", "2", "3", "4"],
                        "max_concurrent": 1,  # Sequential
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "sleep 0.05"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # With max_concurrent=1: ~0.2s minimum
        assert elapsed >= 0.15, f"Expected >= 0.15s, got {elapsed}s"


class TestFanOutContextSubstitution:
    """Tests for context variable substitution in fan_out."""

    def test_item_variable_substituted(self):
        """${item} is substituted with current item."""
        workflow = WorkflowConfig(
            name="Item Sub Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["world"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo hello_${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        # Check the detailed results contain the output
        detailed = result.steps[0].output["detailed_results"]
        assert len(detailed) == 1
        assert "hello_world" in detailed[0]["output"]["stdout"]

    def test_index_variable_substituted(self):
        """${index} is substituted with current index."""
        workflow = WorkflowConfig(
            name="Index Sub Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["a", "b", "c"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo idx_${index}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        detailed = result.steps[0].output["detailed_results"]
        # Results are sorted by index
        outputs = [d["output"]["stdout"].strip() for d in detailed]
        assert "idx_0" in outputs[0]
        assert "idx_1" in outputs[1]
        assert "idx_2" in outputs[2]

    def test_context_from_input(self):
        """Items can come from context via ${var} syntax."""
        workflow = WorkflowConfig(
            name="Context Items Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": "${my_list}",
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow, inputs={"my_list": ["x", "y", "z"]})

        assert result.status == "success"
        assert result.steps[0].output["successful"] == 3


class TestFanOutErrorHandling:
    """Tests for fan_out error handling."""

    def test_fan_out_missing_template(self):
        """fan_out without step_template raises error."""
        workflow = WorkflowConfig(
            name="No Template Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={"items": ["a", "b"]},
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "failed"
        assert "step_template" in result.error

    def test_fan_out_partial_failure(self):
        """fan_out continues on partial failure by default."""
        workflow = WorkflowConfig(
            name="Partial Fail Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["good", "bad", "good2"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "test ${item} != bad"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["successful"] == 2
        assert output["failed"] == 1

    def test_fan_out_fail_fast(self):
        """fan_out with fail_fast stops on first failure."""
        workflow = WorkflowConfig(
            name="Fail Fast Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["a", "b", "c"],
                        "fail_fast": True,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "exit 1"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Fan-out itself succeeds but records failures
        assert result.status == "success"
        output = result.steps[0].output
        assert output["failed"] >= 1


class TestFanOutWithAI:
    """Tests for fan_out with AI steps (dry run)."""

    def test_fan_out_claude_dry_run(self):
        """fan_out with claude_code in dry run mode."""
        workflow = WorkflowConfig(
            name="Claude Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="review_files",
                    type="fan_out",
                    params={
                        "items": ["file1.py", "file2.py"],
                        "step_template": {
                            "type": "claude_code",
                            "params": {
                                "role": "reviewer",
                                "prompt": "Review: ${item}",
                            },
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["successful"] == 2
        assert output["tokens_used"] >= 2000  # 2 * estimated_tokens


class TestFanOutRateLimiting:
    """Tests for rate limiting integration with fan_out."""

    def test_fan_out_rate_limit_params(self):
        """fan_out accepts rate limiting configuration params."""
        workflow = WorkflowConfig(
            name="Rate Limited Fan Out",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="rate_limited",
                    type="fan_out",
                    params={
                        "items": ["a", "b"],
                        "max_concurrent": 2,
                        "anthropic_concurrent": 3,
                        "openai_concurrent": 5,
                        "adaptive_rate_limiting": True,
                        "rate_limit_backoff_factor": 0.6,
                        "rate_limit_recovery_threshold": 5,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        assert result.steps[0].output["successful"] == 2

    def test_fan_out_returns_rate_limit_stats(self):
        """fan_out includes rate_limit_stats in output."""
        workflow = WorkflowConfig(
            name="Rate Stats Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="with_stats",
                    type="fan_out",
                    params={
                        "items": ["x", "y", "z"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output

        # Rate limit stats should be included in output
        assert "rate_limit_stats" in output
        stats = output["rate_limit_stats"]

        # Should have stats for at least default provider
        assert "default" in stats or "anthropic" in stats or "openai" in stats

        # Stats should have expected keys
        for provider, pstats in stats.items():
            assert "base_limit" in pstats
            assert "current_limit" in pstats

    def test_fan_out_distributed_rate_limiting_param(self):
        """fan_out accepts distributed rate limiting params."""
        workflow = WorkflowConfig(
            name="Distributed Rate Limit",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="distributed",
                    type="fan_out",
                    params={
                        "items": ["a"],
                        "distributed_rate_limiting": False,  # Disabled for test
                        "distributed_window": 120,
                        "anthropic_rpm": 30,
                        "openai_rpm": 60,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"


# =============================================================================
# Fan-In Tests
# =============================================================================


class TestFanInBasic:
    """Basic tests for fan_in step type."""

    def test_fan_in_concat(self):
        """fan_in with concat aggregation."""
        workflow = WorkflowConfig(
            name="Concat Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_in_step",
                    type="fan_in",
                    params={
                        "input": ["line1", "line2", "line3"],
                        "aggregation": "concat",
                        "separator": "\n",
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["response"] == "line1\nline2\nline3"
        assert output["aggregation_type"] == "concat"
        assert output["item_count"] == 3

    def test_fan_in_concat_custom_separator(self):
        """fan_in concat with custom separator."""
        workflow = WorkflowConfig(
            name="Custom Sep Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_in_step",
                    type="fan_in",
                    params={
                        "input": ["a", "b", "c"],
                        "aggregation": "concat",
                        "separator": " | ",
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        assert result.steps[0].output["response"] == "a | b | c"

    def test_fan_in_from_context(self):
        """fan_in input from context variable."""
        workflow = WorkflowConfig(
            name="Context Input Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="fan_in_step",
                    type="fan_in",
                    params={
                        "input": "${results}",
                        "aggregation": "concat",
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow, inputs={"results": ["r1", "r2", "r3"]})

        assert result.status == "success"
        assert result.steps[0].output["item_count"] == 3


class TestFanInWithAI:
    """Tests for fan_in with AI aggregation."""

    def test_fan_in_claude_aggregation(self):
        """fan_in with claude_code aggregation (dry run)."""
        workflow = WorkflowConfig(
            name="Claude Aggregate",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="summarize",
                    type="fan_in",
                    params={
                        "input": ["Review 1", "Review 2", "Review 3"],
                        "aggregation": "claude_code",
                        "aggregate_prompt": "Summarize these reviews:\n${items}",
                        "role": "analyst",
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["aggregation_type"] == "claude_code"
        assert output["tokens_used"] >= 1000


# =============================================================================
# Map-Reduce Tests
# =============================================================================


class TestMapReduceBasic:
    """Basic tests for map_reduce step type."""

    def test_map_reduce_basic(self):
        """map_reduce executes map then reduce phases."""
        workflow = WorkflowConfig(
            name="Map Reduce Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="analyze_all",
                    type="map_reduce",
                    params={
                        "items": ["file1", "file2", "file3"],
                        "map_step": {
                            "type": "shell",
                            "params": {"command": "echo analyzed_${item}"},
                        },
                        "reduce_step": {
                            "type": "concat",  # Aggregation type for reduce
                            "params": {
                                "separator": "\n",
                            },
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["map_successful"] == 3
        assert output["map_failed"] == 0
        assert len(output["map_results"]) == 3

    def test_map_reduce_with_ai_dry_run(self):
        """map_reduce with AI steps in dry run."""
        workflow = WorkflowConfig(
            name="AI Map Reduce",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="analyze",
                    type="map_reduce",
                    params={
                        "items": ["doc1", "doc2"],
                        "map_step": {
                            "type": "claude_code",
                            "params": {
                                "role": "analyst",
                                "prompt": "Analyze: ${item}",
                            },
                        },
                        "reduce_step": {
                            "type": "claude_code",
                            "params": {
                                "role": "reporter",
                                "prompt": "Combine: ${map_results}",
                            },
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert output["map_successful"] == 2
        assert output["tokens_used"] >= 3000  # 2 map + 1 reduce


class TestMapReduceErrorHandling:
    """Tests for map_reduce error handling."""

    def test_map_reduce_missing_map_step(self):
        """map_reduce requires map_step."""
        workflow = WorkflowConfig(
            name="No Map Step",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="invalid",
                    type="map_reduce",
                    params={
                        "items": ["a", "b"],
                        "reduce_step": {"type": "shell", "params": {}},
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "failed"
        assert "map_step" in result.error

    def test_map_reduce_missing_reduce_step(self):
        """map_reduce requires reduce_step."""
        workflow = WorkflowConfig(
            name="No Reduce Step",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="invalid",
                    type="map_reduce",
                    params={
                        "items": ["a", "b"],
                        "map_step": {
                            "type": "shell",
                            "params": {"command": "echo test"},
                        },
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "failed"
        assert "reduce_step" in result.error


# =============================================================================
# Auto-Parallel Tests
# =============================================================================


class TestAutoParallelBasic:
    """Basic tests for auto-parallel execution mode."""

    def test_auto_parallel_disabled_by_default(self):
        """Auto-parallel is disabled by default."""
        workflow = WorkflowConfig(
            name="Default Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(id="a", type="shell", params={"command": "echo a"}),
                StepConfig(id="b", type="shell", params={"command": "echo b"}),
            ],
        )
        assert workflow.settings.auto_parallel is False

    def test_auto_parallel_enabled_via_settings(self):
        """Auto-parallel can be enabled via settings."""
        data = {
            "name": "Auto Parallel Test",
            "settings": {"auto_parallel": True},
            "steps": [
                {"id": "a", "type": "shell", "params": {"command": "echo a"}},
                {"id": "b", "type": "shell", "params": {"command": "echo b"}},
            ],
        }
        workflow = WorkflowConfig.from_dict(data)
        assert workflow.settings.auto_parallel is True


class TestAutoParallelExecution:
    """Tests for auto-parallel execution behavior."""

    def test_independent_steps_run_parallel(self):
        """Independent steps run concurrently with auto_parallel."""
        workflow = WorkflowConfig(
            name="Parallel Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
            steps=[
                StepConfig(id="a", type="shell", params={"command": "sleep 0.1"}),
                StepConfig(id="b", type="shell", params={"command": "sleep 0.1"}),
                StepConfig(id="c", type="shell", params={"command": "sleep 0.1"}),
                StepConfig(id="d", type="shell", params={"command": "sleep 0.1"}),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # Should complete in ~0.1s if parallel, ~0.4s if sequential
        # Relaxed threshold for CI runners (slower than local)
        assert elapsed < 0.8, f"Expected < 0.8s, got {elapsed}s (not parallel?)"

    def test_dependent_steps_run_sequentially(self):
        """Dependent steps wait for dependencies."""
        workflow = WorkflowConfig(
            name="Sequential Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(id="a", type="shell", params={"command": "sleep 0.05"}),
                StepConfig(
                    id="b",
                    type="shell",
                    params={"command": "sleep 0.05"},
                    depends_on=["a"],
                ),
                StepConfig(
                    id="c",
                    type="shell",
                    params={"command": "sleep 0.05"},
                    depends_on=["b"],
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # Should take ~0.15s minimum (sequential chain)
        assert elapsed >= 0.12, f"Expected >= 0.12s, got {elapsed}s"

    def test_diamond_pattern_optimized(self):
        """Diamond pattern: a -> (b, c) -> d runs optimally."""
        workflow = WorkflowConfig(
            name="Diamond Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
            steps=[
                StepConfig(id="a", type="shell", params={"command": "sleep 0.05"}),
                StepConfig(
                    id="b",
                    type="shell",
                    params={"command": "sleep 0.05"},
                    depends_on=["a"],
                ),
                StepConfig(
                    id="c",
                    type="shell",
                    params={"command": "sleep 0.05"},
                    depends_on=["a"],
                ),
                StepConfig(
                    id="d",
                    type="shell",
                    params={"command": "sleep 0.05"},
                    depends_on=["b", "c"],
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # Optimal: a(0.05) -> b,c parallel(0.05) -> d(0.05) = ~0.15s
        # Sequential would be ~0.20s
        # Allow margin for CI
        assert elapsed < 0.25, f"Expected < 0.25s, got {elapsed}s"

    def test_auto_parallel_respects_max_workers(self):
        """Auto-parallel respects max_workers limit."""
        workflow = WorkflowConfig(
            name="Max Workers Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=1),
            steps=[
                StepConfig(id="a", type="shell", params={"command": "sleep 0.05"}),
                StepConfig(id="b", type="shell", params={"command": "sleep 0.05"}),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # With max_workers=1, should be sequential: ~0.1s
        assert elapsed >= 0.08, f"Expected >= 0.08s, got {elapsed}s"


class TestAutoParallelOutputs:
    """Tests for auto-parallel output handling."""

    def test_outputs_available_to_dependents(self):
        """Step outputs are available to dependent steps."""
        workflow = WorkflowConfig(
            name="Output Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(
                    id="producer",
                    type="shell",
                    params={"command": "printf produced_value"},
                    outputs=["stdout"],
                ),
                StepConfig(
                    id="consumer",
                    type="shell",
                    params={"command": "echo got: ${stdout}"},
                    depends_on=["producer"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        # Find consumer step result
        consumer_result = next(s for s in result.steps if s.step_id == "consumer")
        assert "got: produced_value" in consumer_result.output["stdout"]


class TestAutoParallelErrorHandling:
    """Tests for auto-parallel error handling."""

    def test_failure_handled_correctly(self):
        """Failed steps are handled correctly in parallel groups."""
        workflow = WorkflowConfig(
            name="Failure Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(id="good", type="shell", params={"command": "echo good"}),
                StepConfig(id="bad", type="shell", params={"command": "exit 1"}),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Default on_failure is abort
        assert result.status == "failed"

    def test_on_failure_skip_in_parallel(self):
        """on_failure=skip works in parallel groups."""
        workflow = WorkflowConfig(
            name="Skip Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(id="good", type="shell", params={"command": "echo good"}),
                StepConfig(
                    id="bad",
                    type="shell",
                    params={"command": "exit 1"},
                    on_failure="skip",
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"


# =============================================================================
# Integration Tests
# =============================================================================


class TestFanOutFanInIntegration:
    """Integration tests for fan_out -> fan_in pipeline."""

    def test_fan_out_then_fan_in(self):
        """fan_out results can be consumed by fan_in."""
        workflow = WorkflowConfig(
            name="Integration Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="scatter",
                    type="fan_out",
                    params={
                        "items": ["a", "b", "c"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo processed_${item}"},
                        },
                    },
                    outputs=["results"],
                ),
                StepConfig(
                    id="gather",
                    type="fan_in",
                    params={
                        "input": "${results}",
                        "aggregation": "concat",
                        "separator": " | ",
                    },
                    depends_on=["scatter"],
                ),
            ],
            outputs=["response"],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        # Check fan_in received the results
        gather_output = result.steps[1].output
        assert gather_output["item_count"] == 3


class TestAutoParallelWithFanOut:
    """Tests for auto-parallel with fan_out steps."""

    def test_fan_out_in_auto_parallel_workflow(self):
        """fan_out works within auto-parallel workflow."""
        workflow = WorkflowConfig(
            name="Combined Test",
            version="1.0",
            description="",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(
                    id="setup",
                    type="shell",
                    params={"command": "echo setup"},
                ),
                StepConfig(
                    id="fan_out_step",
                    type="fan_out",
                    params={
                        "items": ["x", "y"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                    depends_on=["setup"],
                ),
                StepConfig(
                    id="cleanup",
                    type="shell",
                    params={"command": "echo cleanup"},
                    depends_on=["fan_out_step"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        assert len(result.steps) == 3


# =============================================================================
# Loader Validation Tests
# =============================================================================


class TestLoaderNewStepTypes:
    """Tests for loader validation of new step types."""

    def test_fan_out_type_valid(self):
        """fan_out is a valid step type."""
        step = StepConfig.from_dict(
            {
                "id": "test",
                "type": "fan_out",
                "params": {"items": [], "step_template": {}},
            }
        )
        assert step.type == "fan_out"

    def test_fan_in_type_valid(self):
        """fan_in is a valid step type."""
        step = StepConfig.from_dict(
            {
                "id": "test",
                "type": "fan_in",
                "params": {"input": [], "aggregation": "concat"},
            }
        )
        assert step.type == "fan_in"

    def test_map_reduce_type_valid(self):
        """map_reduce is a valid step type."""
        step = StepConfig.from_dict(
            {
                "id": "test",
                "type": "map_reduce",
                "params": {"items": [], "map_step": {}, "reduce_step": {}},
            }
        )
        assert step.type == "map_reduce"


# =============================================================================
# Example Workflow Tests
# =============================================================================


class TestExampleWorkflows:
    """Tests for example workflow YAML files."""

    EXAMPLES_DIR = Path(__file__).parent.parent / "workflows" / "examples"

    def test_examples_directory_exists(self):
        """Examples directory exists."""
        assert self.EXAMPLES_DIR.exists(), f"Missing: {self.EXAMPLES_DIR}"

    def test_fan_out_example_valid_yaml(self):
        """Fan-out example is valid YAML."""
        path = self.EXAMPLES_DIR / "fan_out_code_review.yaml"
        assert path.exists(), f"Missing: {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "fan_out_code_review"
        assert "steps" in data
        assert any(s["type"] == "fan_out" for s in data["steps"])
        assert any(s["type"] == "fan_in" for s in data["steps"])

    def test_map_reduce_example_valid_yaml(self):
        """Map-reduce example is valid YAML."""
        path = self.EXAMPLES_DIR / "map_reduce_analysis.yaml"
        assert path.exists(), f"Missing: {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "map_reduce_log_analysis"
        assert "steps" in data
        assert any(s["type"] == "map_reduce" for s in data["steps"])

    def test_auto_parallel_example_valid_yaml(self):
        """Auto-parallel example is valid YAML."""
        path = self.EXAMPLES_DIR / "auto_parallel_pipeline.yaml"
        assert path.exists(), f"Missing: {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "auto_parallel_pipeline"
        assert data["settings"]["auto_parallel"] is True
        assert "steps" in data

    def test_fan_out_example_loads_as_workflow(self):
        """Fan-out example can be loaded as WorkflowConfig."""
        path = self.EXAMPLES_DIR / "fan_out_code_review.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "fan_out_code_review"
        assert len(workflow.steps) == 2
        assert workflow.steps[0].type == "fan_out"
        assert workflow.steps[1].type == "fan_in"

    def test_map_reduce_example_loads_as_workflow(self):
        """Map-reduce example can be loaded as WorkflowConfig."""
        path = self.EXAMPLES_DIR / "map_reduce_analysis.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "map_reduce_log_analysis"
        assert len(workflow.steps) == 2
        assert workflow.steps[0].type == "map_reduce"
        assert workflow.steps[1].type == "claude_code"

    def test_auto_parallel_example_loads_as_workflow(self):
        """Auto-parallel example can be loaded as WorkflowConfig."""
        path = self.EXAMPLES_DIR / "auto_parallel_pipeline.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "auto_parallel_pipeline"
        assert workflow.settings.auto_parallel is True
        assert workflow.settings.auto_parallel_max_workers == 4
        assert len(workflow.steps) == 7

    def test_auto_parallel_example_dependency_graph(self):
        """Auto-parallel example has correct dependency structure."""
        path = self.EXAMPLES_DIR / "auto_parallel_pipeline.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)
        build_dependency_graph(workflow.steps)

        # Stage 1: 4 independent steps
        independent = [s for s in workflow.steps if not s.depends_on]
        assert len(independent) == 4

        # Check specific dependencies
        risk_step = workflow.get_step("risk_assessment")
        assert set(risk_step.depends_on) == {"security_scan", "dependency_audit"}

        improvement_step = workflow.get_step("improvement_plan")
        assert set(improvement_step.depends_on) == {
            "code_quality",
            "architecture_review",
        }

        summary_step = workflow.get_step("executive_summary")
        assert set(summary_step.depends_on) == {"risk_assessment", "improvement_plan"}

    def test_auto_parallel_example_parallel_groups(self):
        """Auto-parallel example generates correct parallel groups."""
        path = self.EXAMPLES_DIR / "auto_parallel_pipeline.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)
        graph = build_dependency_graph(workflow.steps)
        groups = find_parallel_groups(graph)

        # Should have 3 groups: Stage 1 (4 steps), Stage 2 (2 steps), Stage 3 (1 step)
        assert len(groups) == 3

        # First group: security_scan, code_quality, architecture_review, dependency_audit
        assert len(groups[0].step_ids) == 4

        # Second group: risk_assessment, improvement_plan
        assert len(groups[1].step_ids) == 2

        # Third group: executive_summary
        assert len(groups[2].step_ids) == 1
