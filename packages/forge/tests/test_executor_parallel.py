"""Tests for WorkflowExecutor parallel step execution."""

import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, "src")

from animus_forge.budget import BudgetConfig, BudgetManager
from animus_forge.state import CheckpointManager
from animus_forge.workflow import StepConfig, WorkflowConfig, WorkflowExecutor


class TestStepConfigDependsOn:
    """Tests for depends_on field in StepConfig."""

    def test_depends_on_default_empty(self):
        """depends_on defaults to empty list."""
        data = {"id": "step1", "type": "shell"}
        step = StepConfig.from_dict(data)
        assert step.depends_on == []

    def test_depends_on_string_converted_to_list(self):
        """String depends_on is converted to list."""
        data = {"id": "step1", "type": "shell", "depends_on": "step0"}
        step = StepConfig.from_dict(data)
        assert step.depends_on == ["step0"]

    def test_depends_on_list(self):
        """List depends_on is preserved."""
        data = {"id": "step1", "type": "shell", "depends_on": ["step0", "step2"]}
        step = StepConfig.from_dict(data)
        assert step.depends_on == ["step0", "step2"]


class TestExecutorParallelBasic:
    """Basic tests for _execute_parallel."""

    def test_empty_parallel_steps(self):
        """Empty parallel steps returns empty results."""
        workflow = WorkflowConfig(
            name="Empty Parallel",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={"steps": []},
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        assert result.steps[0].output["parallel_results"] == {}

    def test_single_parallel_step(self):
        """Single sub-step executes correctly."""
        workflow = WorkflowConfig(
            name="Single Parallel",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "echo1",
                                "type": "shell",
                                "params": {"command": "echo hello"},
                            }
                        ]
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert "echo1" in parallel_results
        assert "hello" in parallel_results["echo1"]["stdout"]


class TestExecutorParallelConcurrency:
    """Tests for concurrent execution."""

    def test_independent_steps_run_concurrently(self):
        """Independent sub-steps run in parallel (timing test)."""
        workflow = WorkflowConfig(
            name="Concurrent Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "max_workers": 4,
                        "steps": [
                            {
                                "id": "sleep1",
                                "type": "shell",
                                "params": {"command": "sleep 0.1"},
                            },
                            {
                                "id": "sleep2",
                                "type": "shell",
                                "params": {"command": "sleep 0.1"},
                            },
                            {
                                "id": "sleep3",
                                "type": "shell",
                                "params": {"command": "sleep 0.1"},
                            },
                            {
                                "id": "sleep4",
                                "type": "shell",
                                "params": {"command": "sleep 0.1"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # If running sequentially: 4 * 0.1 = 0.4s
        # If running in parallel: ~0.1s + overhead
        # Allow generous margin for CI/test environments
        assert elapsed < 0.35, f"Expected < 0.35s, got {elapsed}s (not running in parallel?)"


class TestExecutorParallelDependencies:
    """Tests for dependency handling."""

    def test_dependencies_respected(self):
        """Sub-steps with dependencies run in correct order."""
        workflow = WorkflowConfig(
            name="Dependency Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "first",
                                "type": "shell",
                                "params": {"command": "echo first"},
                            },
                            {
                                "id": "second",
                                "type": "shell",
                                "params": {"command": "echo second"},
                                "depends_on": ["first"],
                            },
                            {
                                "id": "third",
                                "type": "shell",
                                "params": {"command": "echo third"},
                                "depends_on": ["second"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert "first" in parallel_results
        assert "second" in parallel_results
        assert "third" in parallel_results
        # All should have succeeded
        assert "error" not in parallel_results["first"]
        assert "error" not in parallel_results["second"]
        assert "error" not in parallel_results["third"]

    def test_multiple_dependencies(self):
        """Sub-step with multiple dependencies waits for all."""
        workflow = WorkflowConfig(
            name="Multi-Dep Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "a",
                                "type": "shell",
                                "params": {"command": "echo a"},
                            },
                            {
                                "id": "b",
                                "type": "shell",
                                "params": {"command": "echo b"},
                            },
                            {
                                "id": "c",
                                "type": "shell",
                                "params": {"command": "echo c"},
                                "depends_on": ["a", "b"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert len(parallel_results) == 3


class TestExecutorParallelErrorHandling:
    """Tests for error handling in parallel execution."""

    def test_failure_recorded(self):
        """Failed sub-steps are recorded in results."""
        workflow = WorkflowConfig(
            name="Failure Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "good",
                                "type": "shell",
                                "params": {"command": "echo good"},
                            },
                            {
                                "id": "bad",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"  # Parallel step itself succeeds
        output = result.steps[0].output
        assert "bad" in output["failed"]
        assert "good" in output["successful"]

    def test_fail_fast_mode(self):
        """fail_fast mode aborts on first failure."""
        workflow = WorkflowConfig(
            name="Fail Fast Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "fail_fast": True,
                        "steps": [
                            {
                                "id": "bad",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                            {
                                "id": "good",
                                "type": "shell",
                                "params": {"command": "echo good"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Should fail due to fail_fast
        assert result.status == "failed"
        assert "Parallel step failed" in result.error

    def test_continue_on_failure(self):
        """Without fail_fast, other steps complete despite failure."""
        workflow = WorkflowConfig(
            name="Continue Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "fail_fast": False,
                        "steps": [
                            {
                                "id": "bad",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                            {
                                "id": "good",
                                "type": "shell",
                                "params": {"command": "echo good"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert "good" in output["successful"]
        assert "bad" in output["failed"]


class TestExecutorParallelContext:
    """Tests for context handling in parallel execution."""

    def test_context_variables_substituted(self):
        """Context variables are available in sub-steps."""
        workflow = WorkflowConfig(
            name="Context Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "echo_var",
                                "type": "shell",
                                "params": {"command": "echo ${test_var}"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow, inputs={"test_var": "hello_world"})

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert "hello_world" in parallel_results["echo_var"]["stdout"]

    def test_outputs_merged_to_context(self):
        """Outputs from parallel sub-steps are merged to main context."""
        workflow = WorkflowConfig(
            name="Output Merge Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "producer",
                                "type": "shell",
                                "params": {"command": "printf produced_value"},
                                "outputs": ["stdout"],
                            },
                        ],
                    },
                ),
                StepConfig(
                    id="consumer",
                    type="shell",
                    params={"command": "echo consumed: ${stdout}"},
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        # Check that stdout from parallel step was available to consumer
        assert "consumed: produced_value" in result.steps[1].output["stdout"]


class TestExecutorParallelStrategy:
    """Tests for execution strategy options."""

    def test_threading_strategy(self):
        """Threading strategy executes correctly."""
        workflow = WorkflowConfig(
            name="Threading Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "strategy": "threading",
                        "steps": [
                            {
                                "id": "step1",
                                "type": "shell",
                                "params": {"command": "echo threading"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"

    def test_asyncio_strategy(self):
        """Asyncio strategy executes correctly."""
        workflow = WorkflowConfig(
            name="Asyncio Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "strategy": "asyncio",
                        "steps": [
                            {
                                "id": "step1",
                                "type": "shell",
                                "params": {"command": "echo asyncio"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"

    def test_max_workers_respected(self):
        """max_workers limits concurrent execution."""
        # With max_workers=1, tasks run sequentially
        workflow = WorkflowConfig(
            name="Max Workers Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "max_workers": 1,
                        "steps": [
                            {
                                "id": "sleep1",
                                "type": "shell",
                                "params": {"command": "sleep 0.05"},
                            },
                            {
                                "id": "sleep2",
                                "type": "shell",
                                "params": {"command": "sleep 0.05"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()

        start = time.time()
        result = executor.execute(workflow)
        elapsed = time.time() - start

        assert result.status == "success"
        # With max_workers=1, should take at least 0.1s
        assert elapsed >= 0.08, f"Expected >= 0.08s, got {elapsed}s"


class TestExecutorParallelTokenTracking:
    """Tests for token tracking in parallel execution."""

    def test_tokens_aggregated(self):
        """Tokens from parallel sub-steps are aggregated."""
        workflow = WorkflowConfig(
            name="Token Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "claude1",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "test1"},
                            },
                            {
                                "id": "claude2",
                                "type": "claude_code",
                                "params": {"role": "builder", "prompt": "test2"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"
        # Both dry_run steps return estimated_tokens (default 1000 each)
        assert result.steps[0].output["tokens_used"] >= 2000


class TestExecutorParallelDryRun:
    """Tests for dry run mode with parallel execution."""

    def test_dry_run_parallel_claude(self):
        """Dry run works with parallel Claude steps."""
        workflow = WorkflowConfig(
            name="Dry Run Parallel",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "planner",
                                "type": "claude_code",
                                "params": {
                                    "role": "planner",
                                    "prompt": "Plan the feature",
                                },
                            },
                            {
                                "id": "reviewer",
                                "type": "claude_code",
                                "params": {
                                    "role": "reviewer",
                                    "prompt": "Review the code",
                                },
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert parallel_results["planner"]["dry_run"] is True
        assert parallel_results["reviewer"]["dry_run"] is True


class TestExecutorParallelCheckpoints:
    """Tests for checkpoint integration with parallel execution."""

    @pytest.fixture
    def checkpoint_manager(self):
        """Create a temporary checkpoint manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield CheckpointManager(db_path=db_path)

    def _get_workflow_id(self, checkpoint_manager):
        """Helper to get the first workflow ID from the database."""
        rows = checkpoint_manager.persistence.backend.fetchall("SELECT id FROM workflows LIMIT 1")
        return rows[0]["id"] if rows else None

    def test_parallel_substeps_checkpointed(self, checkpoint_manager):
        """Each parallel sub-step creates a checkpoint with compound stage name."""
        workflow = WorkflowConfig(
            name="Checkpoint Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task_a",
                                "type": "shell",
                                "params": {"command": "echo a"},
                            },
                            {
                                "id": "task_b",
                                "type": "shell",
                                "params": {"command": "echo b"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Get workflow ID from database
        workflow_id = self._get_workflow_id(checkpoint_manager)
        assert workflow_id is not None

        # Get all checkpoints
        checkpoints = checkpoint_manager.persistence.get_all_checkpoints(workflow_id)

        # Should have checkpoints for: parallel_step (parent) + 2 sub-steps
        # The parent step is checkpointed by _execute_step, sub-steps by _execute_parallel
        stage_names = [cp["stage"] for cp in checkpoints]

        # Check compound stage names exist
        assert "parallel_step.task_a" in stage_names
        assert "parallel_step.task_b" in stage_names

    def test_checkpoint_includes_timing(self, checkpoint_manager):
        """Checkpoints include duration_ms for sub-steps."""
        workflow = WorkflowConfig(
            name="Timing Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "slow_task",
                                "type": "shell",
                                "params": {"command": "sleep 0.05 && echo done"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Find the sub-step checkpoint
        workflow_id = self._get_workflow_id(checkpoint_manager)
        checkpoints = checkpoint_manager.persistence.get_all_checkpoints(workflow_id)

        sub_step_cp = next(
            (cp for cp in checkpoints if cp["stage"] == "parallel_step.slow_task"), None
        )
        assert sub_step_cp is not None
        # Duration should be at least 50ms
        assert sub_step_cp["duration_ms"] >= 40

    def test_checkpoint_includes_status(self, checkpoint_manager):
        """Checkpoints record success/failed status correctly."""
        workflow = WorkflowConfig(
            name="Status Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "good_task",
                                "type": "shell",
                                "params": {"command": "echo success"},
                            },
                            {
                                "id": "bad_task",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager)
        result = executor.execute(workflow)

        # Workflow succeeds (fail_fast=False by default)
        assert result.status == "success"

        # Check checkpoints
        workflow_id = self._get_workflow_id(checkpoint_manager)
        checkpoints = checkpoint_manager.persistence.get_all_checkpoints(workflow_id)

        good_cp = next((cp for cp in checkpoints if cp["stage"] == "parallel_step.good_task"), None)
        bad_cp = next((cp for cp in checkpoints if cp["stage"] == "parallel_step.bad_task"), None)

        assert good_cp is not None
        assert good_cp["status"] == "success"

        assert bad_cp is not None
        assert bad_cp["status"] == "failed"

    def test_checkpoint_tokens_tracked(self, checkpoint_manager):
        """Checkpoints record tokens_used for sub-steps."""
        workflow = WorkflowConfig(
            name="Token Checkpoint Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "claude_task",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "test"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager, dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Check checkpoint has tokens
        workflow_id = self._get_workflow_id(checkpoint_manager)
        checkpoints = checkpoint_manager.persistence.get_all_checkpoints(workflow_id)

        claude_cp = next(
            (cp for cp in checkpoints if cp["stage"] == "parallel_step.claude_task"),
            None,
        )
        assert claude_cp is not None
        # Dry run returns estimated_tokens (default 1000)
        assert claude_cp["tokens_used"] >= 1000

    def test_checkpoint_with_dependencies(self, checkpoint_manager):
        """Checkpoints work correctly with dependent sub-steps."""
        workflow = WorkflowConfig(
            name="Dependency Checkpoint Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "first",
                                "type": "shell",
                                "params": {"command": "echo first"},
                            },
                            {
                                "id": "second",
                                "type": "shell",
                                "params": {"command": "echo second"},
                                "depends_on": ["first"],
                            },
                            {
                                "id": "third",
                                "type": "shell",
                                "params": {"command": "echo third"},
                                "depends_on": ["second"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager)
        result = executor.execute(workflow)

        assert result.status == "success"

        # All three sub-steps should be checkpointed
        workflow_id = self._get_workflow_id(checkpoint_manager)
        checkpoints = checkpoint_manager.persistence.get_all_checkpoints(workflow_id)

        stage_names = [cp["stage"] for cp in checkpoints]
        assert "parallel_step.first" in stage_names
        assert "parallel_step.second" in stage_names
        assert "parallel_step.third" in stage_names

        # All should be successful
        for stage in [
            "parallel_step.first",
            "parallel_step.second",
            "parallel_step.third",
        ]:
            cp = next(c for c in checkpoints if c["stage"] == stage)
            assert cp["status"] == "success"

    def test_no_checkpoint_without_manager(self):
        """No errors when checkpoint_manager is not configured."""
        workflow = WorkflowConfig(
            name="No Checkpoint Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task",
                                "type": "shell",
                                "params": {"command": "echo test"},
                            },
                        ],
                    },
                ),
            ],
        )
        # No checkpoint_manager
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Should succeed without errors
        assert result.status == "success"

    def test_workflow_id_cleared_after_execution(self, checkpoint_manager):
        """_current_workflow_id is cleared after workflow completes."""
        workflow = WorkflowConfig(
            name="Cleanup Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task",
                                "type": "shell",
                                "params": {"command": "echo test"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(checkpoint_manager=checkpoint_manager)
        result = executor.execute(workflow)

        assert result.status == "success"
        # Workflow ID should be cleared
        assert executor._current_workflow_id is None


class TestExecutorParallelBudget:
    """Tests for budget tracking in parallel execution."""

    def test_budget_tracked_per_substep(self):
        """Each parallel sub-step records usage in budget manager."""
        budget_manager = BudgetManager(BudgetConfig(total_budget=100000))

        workflow = WorkflowConfig(
            name="Budget Track Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "claude1",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "test1"},
                            },
                            {
                                "id": "claude2",
                                "type": "claude_code",
                                "params": {"role": "builder", "prompt": "test2"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(budget_manager=budget_manager, dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Check budget was tracked per sub-step
        stats = budget_manager.get_stats()
        agents = stats["agents"]

        # Should have compound agent IDs
        assert "parallel_step.claude1" in agents
        assert "parallel_step.claude2" in agents

        # Each should have recorded usage
        assert agents["parallel_step.claude1"]["used"] >= 1000
        assert agents["parallel_step.claude2"]["used"] >= 1000

    def test_budget_usage_records_metadata(self):
        """Budget usage records include metadata about the step."""
        budget_manager = BudgetManager(BudgetConfig(total_budget=100000))

        workflow = WorkflowConfig(
            name="Metadata Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task1",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "test"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(budget_manager=budget_manager, dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Check usage history has metadata
        history = budget_manager.get_usage_history(agent_id="parallel_step.task1")
        assert len(history) >= 1

        record = history[0]
        assert record.metadata["parent_step"] == "parallel_step"
        assert record.metadata["sub_step"] == "task1"
        assert record.metadata["step_type"] == "claude_code"
        assert "duration_ms" in record.metadata

    def test_budget_exceeded_fails_substep(self):
        """Sub-step fails when its estimated_tokens exceeds remaining budget."""
        # Create budget manager with limited budget - enough for parent step check
        # but not enough for sub-step with high estimated_tokens
        budget_manager = BudgetManager(BudgetConfig(total_budget=2000, reserve_tokens=0))

        workflow = WorkflowConfig(
            name="Budget Exceeded Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        # Low estimate for parent step check (default 1000)
                        "estimated_tokens": 500,
                        "steps": [
                            {
                                "id": "big_task",
                                "type": "claude_code",
                                "params": {
                                    "role": "planner",
                                    "prompt": "test",
                                    # High estimate triggers budget check failure
                                    "estimated_tokens": 5000,
                                },
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(budget_manager=budget_manager, dry_run=True)
        result = executor.execute(workflow)

        # Parallel step succeeds (fail_fast=False), but sub-step recorded failure
        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert "error" in parallel_results["big_task"]
        assert "Budget exceeded" in parallel_results["big_task"]["error"]

    def test_budget_total_aggregated(self):
        """Total budget usage is aggregated from all sub-steps."""
        budget_manager = BudgetManager(BudgetConfig(total_budget=100000))

        workflow = WorkflowConfig(
            name="Aggregate Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task1",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "test1"},
                            },
                            {
                                "id": "task2",
                                "type": "claude_code",
                                "params": {"role": "builder", "prompt": "test2"},
                            },
                            {
                                "id": "task3",
                                "type": "claude_code",
                                "params": {"role": "reviewer", "prompt": "test3"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(budget_manager=budget_manager, dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Total should be sum of all sub-steps
        stats = budget_manager.get_stats()
        assert stats["used"] >= 3000  # At least 3 * 1000 tokens

    def test_no_budget_tracking_without_manager(self):
        """Works fine without budget manager configured."""
        workflow = WorkflowConfig(
            name="No Budget Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task",
                                "type": "shell",
                                "params": {"command": "echo test"},
                            },
                        ],
                    },
                ),
            ],
        )
        # No budget_manager
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"

    def test_budget_with_dependencies(self):
        """Budget tracking works with dependent sub-steps."""
        budget_manager = BudgetManager(BudgetConfig(total_budget=100000))

        workflow = WorkflowConfig(
            name="Dependency Budget Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "first",
                                "type": "claude_code",
                                "params": {"role": "planner", "prompt": "plan"},
                            },
                            {
                                "id": "second",
                                "type": "claude_code",
                                "params": {"role": "builder", "prompt": "build"},
                                "depends_on": ["first"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor(budget_manager=budget_manager, dry_run=True)
        result = executor.execute(workflow)

        assert result.status == "success"

        # Both should be tracked
        stats = budget_manager.get_stats()
        assert "parallel_step.first" in stats["agents"]
        assert "parallel_step.second" in stats["agents"]


class TestExecutorParallelRetry:
    """Tests for retry logic in parallel sub-step execution."""

    def test_retry_on_transient_failure(self):
        """Sub-step retries on transient failure."""
        # Create a workflow with a step that fails then succeeds
        # We'll use a custom handler to simulate this
        call_count = {"count": 0}

        def flaky_handler(step, context):
            call_count["count"] += 1
            if call_count["count"] < 2:
                raise RuntimeError("Transient failure")
            return {"stdout": "success", "returncode": 0}

        workflow = WorkflowConfig(
            name="Retry Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "flaky_task",
                                "type": "custom_flaky",
                                "max_retries": 3,
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("custom_flaky", flaky_handler)
        result = executor.execute(workflow)

        assert result.status == "success"
        # Handler was called twice (failed once, then succeeded)
        assert call_count["count"] == 2
        parallel_results = result.steps[0].output["parallel_results"]
        assert "flaky_task" in parallel_results
        assert parallel_results["flaky_task"]["retries"] == 1

    def test_retry_respects_max_retries(self):
        """Sub-step stops after max_retries is reached."""
        call_count = {"count": 0}

        def always_fails(step, context):
            call_count["count"] += 1
            raise RuntimeError("Always fails")

        workflow = WorkflowConfig(
            name="Max Retries Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "failing_task",
                                "type": "always_fail",
                                "max_retries": 2,  # Will try 3 times total (1 + 2 retries)
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("always_fail", always_fails)
        result = executor.execute(workflow)

        # Workflow succeeds (fail_fast=False), but sub-step failed
        assert result.status == "success"
        # 1 initial + 2 retries = 3 calls
        assert call_count["count"] == 3
        output = result.steps[0].output
        assert "failing_task" in output["failed"]

    def test_retry_exponential_backoff(self):
        """Retries use exponential backoff timing."""
        call_times = []

        def record_time_and_fail(step, context):
            call_times.append(time.time())
            raise RuntimeError("Fail for timing")

        workflow = WorkflowConfig(
            name="Backoff Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "timed_task",
                                "type": "timed_fail",
                                "max_retries": 2,
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("timed_fail", record_time_and_fail)
        result = executor.execute(workflow)

        assert result.status == "success"
        assert len(call_times) == 3

        # Check delays - exponential backoff: 2^0=1s, 2^1=2s
        # First retry after ~1s, second after ~2s
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # Allow generous margins for CI
        assert delay1 >= 0.9, f"First delay {delay1}s should be ~1s"
        assert delay2 >= 1.8, f"Second delay {delay2}s should be ~2s"

    def test_retry_success_after_failures(self):
        """Sub-step succeeds on retry after initial failures."""
        attempts = {"n": 0}

        def succeeds_on_third(step, context):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError(f"Attempt {attempts['n']} failed")
            return {"result": "success", "attempt": attempts["n"]}

        workflow = WorkflowConfig(
            name="Eventually Success Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "eventual_success",
                                "type": "third_time_charm",
                                "max_retries": 3,
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("third_time_charm", succeeds_on_third)
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        assert "eventual_success" in result.steps[0].output["successful"]
        assert parallel_results["eventual_success"]["result"] == "success"
        assert parallel_results["eventual_success"]["retries"] == 2

    def test_retry_tracking_in_output(self):
        """Output includes retry count for successful steps."""
        workflow = WorkflowConfig(
            name="Retry Tracking Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "echo_task",
                                "type": "shell",
                                "params": {"command": "echo success"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        parallel_results = result.steps[0].output["parallel_results"]
        # Successful on first try, so retries=0
        assert parallel_results["echo_task"]["retries"] == 0

    def test_no_retry_when_max_retries_zero(self):
        """No retry when max_retries=0."""
        call_count = {"count": 0}

        def fail_once(step, context):
            call_count["count"] += 1
            raise RuntimeError("Single failure")

        workflow = WorkflowConfig(
            name="No Retry Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "no_retry_task",
                                "type": "fail_once",
                                "max_retries": 0,  # No retries
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("fail_once", fail_once)
        result = executor.execute(workflow)

        assert result.status == "success"  # fail_fast=False
        # Only one attempt, no retries
        assert call_count["count"] == 1
        assert "no_retry_task" in result.steps[0].output["failed"]

    def test_total_retries_aggregated(self):
        """total_retries sums retries from all sub-steps."""
        call_counts = {"task1": 0, "task2": 0}

        def fail_twice_task1(step, context):
            call_counts["task1"] += 1
            if call_counts["task1"] < 3:
                raise RuntimeError("Task1 fail")
            return {"done": True}

        def fail_once_task2(step, context):
            call_counts["task2"] += 1
            if call_counts["task2"] < 2:
                raise RuntimeError("Task2 fail")
            return {"done": True}

        workflow = WorkflowConfig(
            name="Aggregate Retries Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task1",
                                "type": "task1_handler",
                                "max_retries": 3,
                            },
                            {
                                "id": "task2",
                                "type": "task2_handler",
                                "max_retries": 3,
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("task1_handler", fail_twice_task1)
        executor.register_handler("task2_handler", fail_once_task2)
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        # task1 had 2 retries, task2 had 1 retry = 3 total
        assert output["total_retries"] == 3


class TestExecutorParallelCancellation:
    """Tests for task cancellation in parallel execution."""

    def test_cancelled_field_in_output(self):
        """Output includes cancelled field."""
        workflow = WorkflowConfig(
            name="Cancel Field Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "steps": [
                            {
                                "id": "task1",
                                "type": "shell",
                                "params": {"command": "echo done"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        assert "cancelled" in output
        assert output["cancelled"] == []  # No cancellations

    def test_fail_fast_cancels_pending(self):
        """fail_fast=True cancels pending dependent tasks when failure occurs."""
        workflow = WorkflowConfig(
            name="Cancel Pending Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "fail_fast": True,
                        "steps": [
                            {
                                "id": "fail_first",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                            {
                                "id": "depends_on_fail",
                                "type": "shell",
                                "params": {"command": "echo never"},
                                "depends_on": ["fail_first"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Workflow fails due to fail_fast
        assert result.status == "failed"
        assert "Parallel step failed" in result.error

    def test_no_cancel_without_fail_fast(self):
        """Without fail_fast, all independent tasks complete."""
        workflow = WorkflowConfig(
            name="No Cancel Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "fail_fast": False,
                        "steps": [
                            {
                                "id": "slow_fail",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                            {
                                "id": "fast_success",
                                "type": "shell",
                                "params": {"command": "echo fast"},
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        assert result.status == "success"
        output = result.steps[0].output
        # Both ran - one failed, one succeeded
        assert "slow_fail" in output["failed"]
        assert "fast_success" in output["successful"]
        assert output["cancelled"] == []

    def test_dependent_tasks_not_started(self):
        """Tasks depending on failed tasks are not started."""
        workflow = WorkflowConfig(
            name="Not Started Test",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="parallel_step",
                    type="parallel",
                    params={
                        "fail_fast": True,
                        "steps": [
                            {
                                "id": "fast_fail",
                                "type": "shell",
                                "params": {"command": "exit 1"},
                            },
                            {
                                "id": "never_runs",
                                "type": "shell",
                                # This depends on the failed task, so never starts
                                "params": {"command": "echo never"},
                                "depends_on": ["fast_fail"],
                            },
                            {
                                "id": "also_never",
                                "type": "shell",
                                "params": {"command": "echo also"},
                                "depends_on": ["never_runs"],
                            },
                        ],
                    },
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)

        # Workflow fails due to fail_fast
        assert result.status == "failed"
        assert "Parallel step failed" in result.error
