"""End-to-end tests for parallel execution features.

These tests verify the complete flow from YAML workflow definition
through execution to metrics tracking.
"""

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, "src")

from animus_forge.monitoring.parallel_tracker import (
    get_parallel_tracker,
)
from animus_forge.workflow import (
    StepConfig,
    WorkflowConfig,
    WorkflowExecutor,
    WorkflowSettings,
)
from animus_forge.workflow.auto_parallel import build_dependency_graph, find_parallel_groups

EXAMPLES_DIR = Path(__file__).parent.parent / "workflows" / "examples"


class TestFanOutE2E:
    """End-to-end tests for fan-out pattern."""

    def test_fan_out_shell_commands(self):
        """Fan-out executes shell commands for each item."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Fan Out Shell",
            version="1.0",
            description="Test fan-out with shell commands",
            steps=[
                StepConfig(
                    id="process_files",
                    type="fan_out",
                    params={
                        "items": ["file1.txt", "file2.txt", "file3.txt"],
                        "max_concurrent": 3,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo Processing ${item}"},
                        },
                    },
                    outputs=["processed_files"],
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Verify execution succeeded
        assert result.status == "success"
        assert len(result.steps) == 1

        output = result.steps[0].output
        assert output["successful"] == 3
        assert output["failed"] == 0
        assert len(output["results"]) == 3

        # Verify tracker recorded the execution
        summary = tracker.get_summary()
        assert summary["counters"]["executions_completed"] >= 1
        assert summary["counters"]["branches_completed"] >= 3

    def test_fan_out_with_context_variable(self):
        """Fan-out resolves items from workflow inputs."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Fan Out Context",
            version="1.0",
            description="Test fan-out with context variable",
            steps=[
                StepConfig(
                    id="echo_items",
                    type="fan_out",
                    params={
                        "items": "${input_list}",
                        "max_concurrent": 2,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},
                        },
                    },
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(
            workflow, inputs={"input_list": ["alpha", "beta", "gamma", "delta"]}
        )

        assert result.status == "success"
        output = result.steps[0].output
        assert output["successful"] == 4

    def test_fan_out_fail_fast(self):
        """Fan-out with fail_fast stops on first failure."""
        workflow = WorkflowConfig(
            name="E2E Fan Out Fail Fast",
            version="1.0",
            description="Test fail_fast behavior",
            steps=[
                StepConfig(
                    id="mixed_results",
                    type="fan_out",
                    params={
                        "items": ["ok", "fail", "ok2"],
                        "max_concurrent": 1,  # Sequential to ensure order
                        "fail_fast": True,
                        "step_template": {
                            "type": "shell",
                            "params": {
                                "command": 'if [ "${item}" = "fail" ]; then exit 1; else echo ${item}; fi'
                            },
                        },
                    },
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        output = result.steps[0].output
        # With fail_fast, some items should be cancelled
        assert output["failed"] >= 1 or output["cancelled"] >= 1


class TestMapReduceE2E:
    """End-to-end tests for map-reduce pattern."""

    def test_map_reduce_shell_commands(self):
        """Map-reduce processes items and aggregates results."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Map Reduce",
            version="1.0",
            description="Test map-reduce pattern",
            steps=[
                StepConfig(
                    id="analyze",
                    type="map_reduce",
                    params={
                        "items": ["data1", "data2", "data3"],
                        "max_concurrent": 3,
                        "map_step": {
                            "type": "shell",
                            "params": {"command": "echo Analyzed: ${item}"},
                        },
                        "reduce_step": {
                            "type": "concat",
                            "params": {"separator": " | "},
                        },
                    },
                    outputs=["analysis_result"],
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert "map_results" in output
        assert len(output["map_results"]) == 3

    def test_map_reduce_from_example_yaml(self):
        """Load and validate map-reduce example workflow structure."""
        yaml_path = EXAMPLES_DIR / "map_reduce_analysis.yaml"
        assert yaml_path.exists(), f"Missing example: {yaml_path}"

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "map_reduce_log_analysis"
        assert len(workflow.steps) == 2

        # First step is map_reduce
        mr_step = workflow.steps[0]
        assert mr_step.type == "map_reduce"
        assert "map_step" in mr_step.params
        assert "reduce_step" in mr_step.params


class TestAutoParallelE2E:
    """End-to-end tests for auto-parallel mode."""

    def test_auto_parallel_independent_steps(self):
        """Auto-parallel runs independent steps concurrently."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Auto Parallel",
            version="1.0",
            description="Test auto-parallel mode",
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=4),
            steps=[
                StepConfig(
                    id="step_a",
                    type="shell",
                    params={"command": "sleep 0.1"},
                    outputs=["result_a"],
                ),
                StepConfig(
                    id="step_b",
                    type="shell",
                    params={"command": "sleep 0.1"},
                    outputs=["result_b"],
                ),
                StepConfig(
                    id="step_c",
                    type="shell",
                    params={"command": "sleep 0.1"},
                    outputs=["result_c"],
                ),
                StepConfig(
                    id="step_d",
                    type="shell",
                    params={"command": "echo D"},
                    depends_on=["step_a", "step_b", "step_c"],
                    outputs=["result_d"],
                ),
            ],
        )

        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        assert len(result.steps) == 4

        # Steps a, b, c should run in parallel (~0.1s)
        # Step d runs after (~0.0s)
        # Total should be ~0.1-0.2s, not 0.3s+
        assert elapsed < 0.3, f"Expected parallel execution, got {elapsed}s"

    def test_auto_parallel_from_example_yaml(self):
        """Load and analyze auto-parallel example workflow."""
        yaml_path = EXAMPLES_DIR / "auto_parallel_pipeline.yaml"
        assert yaml_path.exists(), f"Missing example: {yaml_path}"

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "auto_parallel_pipeline"
        assert workflow.settings.auto_parallel is True
        assert workflow.settings.auto_parallel_max_workers == 4

        # Verify dependency analysis
        graph = build_dependency_graph(workflow.steps)
        groups = find_parallel_groups(graph)

        # Should have 3 groups based on the example structure
        assert len(groups) == 3

        # First group should have 4 independent steps
        assert len(groups[0].step_ids) == 4

    def test_auto_parallel_respects_dependencies(self):
        """Auto-parallel correctly handles step dependencies."""
        workflow = WorkflowConfig(
            name="E2E Dependency Test",
            version="1.0",
            description="Test dependency handling",
            settings=WorkflowSettings(auto_parallel=True),
            steps=[
                StepConfig(
                    id="first",
                    type="shell",
                    params={"command": "echo first"},
                    outputs=["first_out"],
                ),
                StepConfig(
                    id="second",
                    type="shell",
                    params={"command": "echo second after ${first_out}"},
                    depends_on=["first"],
                    outputs=["second_out"],
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        # Verify order: first before second
        first_idx = next(i for i, s in enumerate(result.steps) if s.step_id == "first")
        second_idx = next(i for i, s in enumerate(result.steps) if s.step_id == "second")
        assert first_idx < second_idx


class TestFanOutFanInE2E:
    """End-to-end tests for fan-out followed by fan-in."""

    def test_fan_out_fan_in_pipeline(self):
        """Fan-out results flow into fan-in aggregation."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Fan Out Fan In",
            version="1.0",
            description="Test fan-out to fan-in pipeline",
            steps=[
                StepConfig(
                    id="scatter",
                    type="fan_out",
                    params={
                        "items": ["a", "b", "c"],
                        "max_concurrent": 3,
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo Result:${item}"},
                        },
                    },
                    outputs=["scattered_results"],
                ),
                StepConfig(
                    id="gather",
                    type="fan_in",
                    depends_on=["scatter"],
                    params={
                        "input": "${scattered_results}",
                        "aggregation": "concat",
                        "separator": "\n",
                    },
                    outputs=["final_result"],
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        assert len(result.steps) == 2

        # Check fan-out results
        scatter_output = result.steps[0].output
        assert scatter_output["successful"] == 3

        # Check fan-in aggregation
        gather_output = result.steps[1].output
        assert "response" in gather_output or "aggregated" in gather_output

    def test_fan_out_example_yaml_structure(self):
        """Validate fan-out example YAML has proper structure."""
        yaml_path = EXAMPLES_DIR / "fan_out_code_review.yaml"
        assert yaml_path.exists(), f"Missing example: {yaml_path}"

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        workflow = WorkflowConfig.from_dict(data)

        assert workflow.name == "fan_out_code_review"
        assert len(workflow.steps) == 2

        # First step: fan_out
        fan_out_step = workflow.steps[0]
        assert fan_out_step.type == "fan_out"
        assert fan_out_step.id == "review_files"
        assert "items" in fan_out_step.params
        assert "step_template" in fan_out_step.params

        # Second step: fan_in
        fan_in_step = workflow.steps[1]
        assert fan_in_step.type == "fan_in"
        assert fan_in_step.id == "summarize_reviews"
        assert "review_files" in fan_in_step.depends_on


class TestMetricsTracking:
    """End-to-end tests for metrics tracking during execution."""

    def test_fan_out_metrics_recorded(self):
        """Fan-out execution records proper metrics."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Metrics Test",
            version="1.0",
            description="Test metrics recording",
            steps=[
                StepConfig(
                    id="metered_fan_out",
                    type="fan_out",
                    params={
                        "items": ["x", "y"],
                        "max_concurrent": 2,
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

        # Check tracker recorded metrics
        summary = tracker.get_summary()

        assert summary["counters"]["executions_started"] >= 1
        assert summary["counters"]["executions_completed"] >= 1
        assert summary["counters"]["branches_started"] >= 2
        assert summary["counters"]["branches_completed"] >= 2

        # Check timing histograms have data
        assert summary["execution_duration"]["count"] >= 1
        assert summary["branch_duration"]["count"] >= 2

    def test_parallel_group_metrics_recorded(self):
        """Auto-parallel execution records parallel group metrics."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Parallel Group Metrics",
            version="1.0",
            description="Test parallel group metrics",
            settings=WorkflowSettings(auto_parallel=True, auto_parallel_max_workers=2),
            steps=[
                StepConfig(id="a", type="shell", params={"command": "echo a"}),
                StepConfig(id="b", type="shell", params={"command": "echo b"}),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"

        summary = tracker.get_summary()

        # Should have recorded parallel_group execution
        assert summary["counters"].get("executions_started_parallel_group", 0) >= 1

    def test_dashboard_data_after_execution(self):
        """Dashboard data reflects execution state."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Dashboard Data",
            version="1.0",
            description="Test dashboard data",
            steps=[
                StepConfig(
                    id="quick_fan_out",
                    type="fan_out",
                    params={
                        "items": ["1", "2"],
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

        # Get dashboard data
        data = tracker.get_dashboard_data()

        assert "summary" in data
        assert "active_executions" in data
        assert "recent_executions" in data
        assert "rate_limits" in data

        # Should have recent execution in history
        assert len(data["recent_executions"]) >= 1

        recent = data["recent_executions"][0]
        assert recent["pattern_type"] == "fan_out"
        assert recent["status"] == "completed"


class TestRateLimitIntegration:
    """End-to-end tests for rate limit tracking."""

    def test_rate_limit_stats_in_output(self):
        """Fan-out includes rate_limit_stats in output."""
        workflow = WorkflowConfig(
            name="E2E Rate Limit Stats",
            version="1.0",
            description="Test rate limit stats",
            steps=[
                StepConfig(
                    id="with_rate_stats",
                    type="fan_out",
                    params={
                        "items": ["a", "b"],
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

        # Rate limit stats should be present
        assert "rate_limit_stats" in output
        assert isinstance(output["rate_limit_stats"], dict)

    def test_rate_limit_config_accepted(self):
        """Fan-out accepts all rate limit configuration params."""
        workflow = WorkflowConfig(
            name="E2E Rate Limit Config",
            version="1.0",
            description="Test rate limit config",
            steps=[
                StepConfig(
                    id="configured_rate_limit",
                    type="fan_out",
                    params={
                        "items": ["x"],
                        "adaptive_rate_limiting": True,
                        "rate_limit_backoff_factor": 0.6,
                        "rate_limit_recovery_threshold": 8,
                        "anthropic_concurrent": 4,
                        "openai_concurrent": 6,
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

        # Should execute without errors
        assert result.status == "success"


class TestErrorHandling:
    """End-to-end tests for error handling in parallel execution."""

    def test_partial_failure_recorded(self):
        """Partial failures in fan-out are properly recorded."""
        tracker = get_parallel_tracker()
        tracker.reset()

        workflow = WorkflowConfig(
            name="E2E Partial Failure",
            version="1.0",
            description="Test partial failure handling",
            steps=[
                StepConfig(
                    id="mixed_success",
                    type="fan_out",
                    params={
                        "items": ["ok1", "fail", "ok2"],
                        "max_concurrent": 1,
                        "fail_fast": False,
                        "step_template": {
                            "type": "shell",
                            "params": {
                                "command": 'if [ "${item}" = "fail" ]; then exit 1; fi && echo ${item}'
                            },
                        },
                    },
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        output = result.steps[0].output

        # Should have mix of success and failure
        assert output["successful"] == 2
        assert output["failed"] == 1

        # Tracker should record branch failures
        summary = tracker.get_summary()
        assert summary["counters"]["branches_failed"] >= 1

    def test_timeout_handling(self):
        """Step timeout is handled gracefully."""
        workflow = WorkflowConfig(
            name="E2E Timeout",
            version="1.0",
            description="Test timeout handling",
            steps=[
                StepConfig(
                    id="may_timeout",
                    type="fan_out",
                    timeout_seconds=1,  # Short timeout
                    params={
                        "items": ["quick"],
                        "step_template": {
                            "type": "shell",
                            "params": {"command": "echo ${item}"},  # Fast command
                        },
                    },
                ),
            ],
        )

        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Fast command should complete before timeout
        assert result.status == "success"
