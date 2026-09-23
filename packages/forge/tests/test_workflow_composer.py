"""Tests for the workflow composer module."""

from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.composer import (
    SubWorkflowResult,
    WorkflowComposer,
    _now_ms,
    _resolve_value,
)
from animus_forge.workflow.executor import ExecutionResult, StepStatus
from animus_forge.workflow.loader import StepConfig, WorkflowConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(step_id="sub1", workflow_name="child-wf", **extra_params):
    """Create a StepConfig for a sub_workflow step."""
    params = {"workflow": workflow_name}
    params.update(extra_params)
    return StepConfig(id=step_id, type="shell", params=params)


def _make_execution_result(
    name="child-wf",
    status="success",
    outputs=None,
    total_tokens=100,
    error=None,
    steps=None,
):
    """Create a mock ExecutionResult."""
    result = ExecutionResult(workflow_name=name)
    result.status = status
    result.outputs = outputs or {"result": "done"}
    result.total_tokens = total_tokens
    result.error = error
    if steps is not None:
        result.steps = steps
    else:
        step_result = MagicMock()
        step_result.status = StepStatus.SUCCESS
        result.steps = [step_result]
    return result


def _make_workflow_config(name="child-wf", steps=None):
    """Create a basic WorkflowConfig."""
    return WorkflowConfig(
        name=name,
        version="1.0",
        description="Test workflow",
        steps=steps or [StepConfig(id="s1", type="shell", params={"command": "echo"})],
    )


# ---------------------------------------------------------------------------
# SubWorkflowResult dataclass
# ---------------------------------------------------------------------------


class TestSubWorkflowResult:
    """Tests for SubWorkflowResult dataclass."""

    def test_defaults(self):
        result = SubWorkflowResult(workflow_name="test", status="success")
        assert result.workflow_name == "test"
        assert result.status == "success"
        assert result.outputs == {}
        assert result.steps_executed == 0
        assert result.total_tokens == 0
        assert result.total_duration_ms == 0
        assert result.depth == 0

    def test_with_values(self):
        result = SubWorkflowResult(
            workflow_name="test",
            status="failed",
            outputs={"key": "val"},
            steps_executed=5,
            total_tokens=1000,
            total_duration_ms=2500,
            depth=3,
        )
        assert result.steps_executed == 5
        assert result.total_tokens == 1000
        assert result.depth == 3


# ---------------------------------------------------------------------------
# _resolve_value
# ---------------------------------------------------------------------------


class TestResolveValue:
    """Tests for the _resolve_value helper."""

    def test_non_string_passthrough(self):
        assert _resolve_value(42, {}) == 42
        assert _resolve_value([1, 2], {}) == [1, 2]
        assert _resolve_value(None, {}) is None
        assert _resolve_value({"k": "v"}, {}) == {"k": "v"}

    def test_exact_reference(self):
        ctx = {"name": "Alice"}
        assert _resolve_value("${name}", ctx) == "Alice"

    def test_exact_reference_missing(self):
        ctx = {}
        assert _resolve_value("${name}", ctx) == "${name}"

    def test_inline_substitution(self):
        ctx = {"greeting": "Hello", "target": "World"}
        result = _resolve_value("${greeting}, ${target}!", ctx)
        assert result == "Hello, World!"

    def test_inline_substitution_partial_missing(self):
        ctx = {"greeting": "Hello"}
        result = _resolve_value("${greeting}, ${target}!", ctx)
        assert result == "Hello, ${target}!"

    def test_no_references(self):
        assert _resolve_value("plain string", {}) == "plain string"

    def test_exact_reference_non_string_value(self):
        """Exact ${ref} can return non-string values from context."""
        ctx = {"data": [1, 2, 3]}
        result = _resolve_value("${data}", ctx)
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# _now_ms
# ---------------------------------------------------------------------------


class TestNowMs:
    """Tests for the _now_ms helper."""

    def test_returns_int(self):
        result = _now_ms()
        assert isinstance(result, int)

    def test_monotonic_increasing(self):
        a = _now_ms()
        b = _now_ms()
        assert b >= a


# ---------------------------------------------------------------------------
# WorkflowComposer init
# ---------------------------------------------------------------------------


class TestWorkflowComposerInit:
    """Tests for WorkflowComposer initialization."""

    def test_default_max_depth(self):
        composer = WorkflowComposer()
        assert composer.max_depth == 5

    def test_custom_max_depth(self):
        composer = WorkflowComposer(max_depth=3)
        assert composer.max_depth == 3


# ---------------------------------------------------------------------------
# execute_sub_workflow
# ---------------------------------------------------------------------------


class TestExecuteSubWorkflow:
    """Tests for WorkflowComposer.execute_sub_workflow."""

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_basic_execution(self, mock_load):
        """Sub-workflow executes and returns outputs."""
        mock_load.return_value = _make_workflow_config()
        mock_executor = MagicMock()
        mock_executor.execute.return_value = _make_execution_result()
        mock_executor.dry_run = False
        mock_executor.checkpoint_manager = None
        mock_executor.budget_manager = None
        mock_executor.feedback_engine = None

        composer = WorkflowComposer()
        step = _make_step()

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            MockExec.return_value = mock_executor
            result = composer.execute_sub_workflow(step, {"parent_var": "value"}, depth=1)

        assert "result" in result
        assert "_sub_workflow_result" in result
        sub_result = result["_sub_workflow_result"]
        assert isinstance(sub_result, SubWorkflowResult)
        assert sub_result.status == "success"

    def test_missing_workflow_param_raises(self):
        """Step without 'workflow' param raises ValueError."""
        composer = WorkflowComposer()
        step = StepConfig(id="sub1", type="shell", params={})

        with pytest.raises(ValueError, match="missing"):
            composer.execute_sub_workflow(step, {}, depth=1)

    def test_empty_workflow_param_raises(self):
        """Empty workflow name raises ValueError."""
        composer = WorkflowComposer()
        step = StepConfig(id="sub1", type="shell", params={"workflow": ""})

        with pytest.raises(ValueError, match="missing"):
            composer.execute_sub_workflow(step, {}, depth=1)

    def test_depth_exceeds_max_raises(self):
        """Exceeding max depth raises RecursionError."""
        composer = WorkflowComposer(max_depth=3)
        step = _make_step()

        with pytest.raises(RecursionError, match="depth 4 exceeds maximum"):
            composer.execute_sub_workflow(step, {}, depth=4)

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_pass_context(self, mock_load):
        """pass_context=True propagates parent context to child."""
        mock_load.return_value = _make_workflow_config()

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = _make_execution_result()
            mock_executor.dry_run = False
            mock_executor.checkpoint_manager = None
            mock_executor.budget_manager = None
            mock_executor.feedback_engine = None
            MockExec.return_value = mock_executor

            composer = WorkflowComposer()
            step = _make_step(
                pass_context=True,
                inputs={"extra": "val"},
            )
            parent_ctx = {"parent_key": "parent_val"}

            composer.execute_sub_workflow(step, parent_ctx, depth=1)

            # Check the inputs passed to execute
            call_args = mock_executor.execute.call_args
            inputs = call_args.kwargs.get("inputs", call_args[1].get("inputs", {}))
            assert "parent_key" in inputs
            assert "extra" in inputs

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_variable_substitution_in_inputs(self, mock_load):
        """Input values with ${ref} are resolved from parent context."""
        mock_load.return_value = _make_workflow_config()

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = _make_execution_result()
            mock_executor.dry_run = False
            mock_executor.checkpoint_manager = None
            mock_executor.budget_manager = None
            mock_executor.feedback_engine = None
            MockExec.return_value = mock_executor

            composer = WorkflowComposer()
            step = _make_step(inputs={"code": "${builder_output}"})
            parent_ctx = {"builder_output": "print('hello')"}

            composer.execute_sub_workflow(step, parent_ctx, depth=1)

            call_args = mock_executor.execute.call_args
            inputs = call_args.kwargs.get("inputs", call_args[1].get("inputs", {}))
            assert inputs.get("code") == "print('hello')"

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_failed_sub_workflow(self, mock_load):
        """Failed sub-workflow returns failed status."""
        mock_load.return_value = _make_workflow_config()

        failed_result = _make_execution_result(
            status="failed",
            error="Step s1 failed",
            steps=[],
        )

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = failed_result
            mock_executor.dry_run = False
            mock_executor.checkpoint_manager = None
            mock_executor.budget_manager = None
            mock_executor.feedback_engine = None
            MockExec.return_value = mock_executor

            composer = WorkflowComposer()
            step = _make_step()
            result = composer.execute_sub_workflow(step, {}, depth=1)

            sub_result = result["_sub_workflow_result"]
            assert sub_result.status == "failed"

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_child_registers_sub_workflow_handler(self, mock_load):
        """Child executor gets sub_workflow handler for nested execution."""
        mock_load.return_value = _make_workflow_config()

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = _make_execution_result()
            mock_executor.dry_run = False
            mock_executor.checkpoint_manager = None
            mock_executor.budget_manager = None
            mock_executor.feedback_engine = None
            MockExec.return_value = mock_executor

            composer = WorkflowComposer()
            step = _make_step()
            composer.execute_sub_workflow(step, {}, depth=1)

            # Verify register_handler was called with "sub_workflow"
            mock_executor.register_handler.assert_called_once()
            args = mock_executor.register_handler.call_args
            assert args[0][0] == "sub_workflow"

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_inherits_parent_managers(self, mock_load):
        """Child executor inherits parent's managers."""
        mock_load.return_value = _make_workflow_config()

        mock_parent = MagicMock()
        mock_parent.checkpoint_manager = MagicMock()
        mock_parent.budget_manager = MagicMock()
        mock_parent.feedback_engine = MagicMock()
        mock_parent.dry_run = True

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_child = MagicMock()
            mock_child.execute.return_value = _make_execution_result()
            MockExec.return_value = mock_child

            composer = WorkflowComposer()
            step = _make_step()
            composer.execute_sub_workflow(step, {}, depth=1, parent_executor=mock_parent)

            # Verify WorkflowExecutor was constructed with parent's managers
            constructor_kwargs = MockExec.call_args.kwargs
            assert constructor_kwargs["checkpoint_manager"] is mock_parent.checkpoint_manager
            assert constructor_kwargs["budget_manager"] is mock_parent.budget_manager
            assert constructor_kwargs["feedback_engine"] is mock_parent.feedback_engine
            assert constructor_kwargs["dry_run"] is True


# ---------------------------------------------------------------------------
# resolve_workflow_graph
# ---------------------------------------------------------------------------


class TestResolveWorkflowGraph:
    """Tests for WorkflowComposer.resolve_workflow_graph."""

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_single_workflow(self, mock_load):
        """Single workflow with no sub-workflows."""
        mock_load.return_value = _make_workflow_config("root")
        composer = WorkflowComposer()
        result = composer.resolve_workflow_graph("root")
        assert result == ["root"]

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_two_level_hierarchy(self, mock_load):
        """Root -> child sub-workflow."""
        root_wf = WorkflowConfig(
            name="root",
            version="1.0",
            description="",
            steps=[
                StepConfig(
                    id="sub",
                    type="shell",
                    params={"workflow": "child"},
                ),
            ],
        )
        # Make the sub step look like a sub_workflow type
        root_wf.steps[0].type = "shell"

        # For resolve_workflow_graph, it checks step.type == "sub_workflow"
        root_sub_step = StepConfig(
            id="sub",
            type="shell",
            params={"workflow": "child"},
        )
        # Force type to sub_workflow (bypass Literal validation)
        object.__setattr__(root_sub_step, "type", "sub_workflow")

        root_wf_real = WorkflowConfig(
            name="root",
            version="1.0",
            description="",
            steps=[root_sub_step],
        )
        child_wf = _make_workflow_config("child")

        mock_load.side_effect = lambda name: {
            "root": root_wf_real,
            "child": child_wf,
        }[name]

        composer = WorkflowComposer()
        result = composer.resolve_workflow_graph("root")
        assert "root" in result
        assert "child" in result

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_circular_reference_raises(self, mock_load):
        """Circular workflow reference raises ValueError."""
        # A -> B -> A
        step_a = StepConfig(id="sub_b", type="shell", params={"workflow": "B"})
        object.__setattr__(step_a, "type", "sub_workflow")

        step_b = StepConfig(id="sub_a", type="shell", params={"workflow": "A"})
        object.__setattr__(step_b, "type", "sub_workflow")

        wf_a = WorkflowConfig(name="A", version="1.0", description="", steps=[step_a])
        wf_b = WorkflowConfig(name="B", version="1.0", description="", steps=[step_b])

        mock_load.side_effect = lambda name: {"A": wf_a, "B": wf_b}[name]

        composer = WorkflowComposer()
        with pytest.raises(ValueError, match="[Cc]ircular"):
            composer.resolve_workflow_graph("A")

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_missing_workflow_handled(self, mock_load):
        """Missing workflow during graph resolution doesn't crash."""
        step = StepConfig(id="sub", type="shell", params={"workflow": "missing"})
        object.__setattr__(step, "type", "sub_workflow")

        root_wf = WorkflowConfig(name="root", version="1.0", description="", steps=[step])

        def load_side_effect(name):
            if name == "root":
                return root_wf
            raise FileNotFoundError(f"Workflow {name} not found")

        mock_load.side_effect = load_side_effect
        composer = WorkflowComposer()
        result = composer.resolve_workflow_graph("root")
        assert "root" in result

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_visited_dedup(self, mock_load):
        """Workflows referenced multiple times only appear once."""
        # A -> B, A -> C, both B and C -> shared
        step_b = StepConfig(id="sub_b", type="shell", params={"workflow": "B"})
        object.__setattr__(step_b, "type", "sub_workflow")
        step_c = StepConfig(id="sub_c", type="shell", params={"workflow": "C"})
        object.__setattr__(step_c, "type", "sub_workflow")

        step_shared_from_b = StepConfig(
            id="sub_shared", type="shell", params={"workflow": "shared"}
        )
        object.__setattr__(step_shared_from_b, "type", "sub_workflow")
        step_shared_from_c = StepConfig(
            id="sub_shared", type="shell", params={"workflow": "shared"}
        )
        object.__setattr__(step_shared_from_c, "type", "sub_workflow")

        wf_a = WorkflowConfig(name="A", version="1.0", description="", steps=[step_b, step_c])
        wf_b = WorkflowConfig(name="B", version="1.0", description="", steps=[step_shared_from_b])
        wf_c = WorkflowConfig(name="C", version="1.0", description="", steps=[step_shared_from_c])
        wf_shared = _make_workflow_config("shared")

        mock_load.side_effect = lambda name: {
            "A": wf_a,
            "B": wf_b,
            "C": wf_c,
            "shared": wf_shared,
        }[name]

        composer = WorkflowComposer()
        result = composer.resolve_workflow_graph("A")
        # "shared" should appear only once despite being referenced by both B and C
        assert result.count("shared") == 1


# ---------------------------------------------------------------------------
# register_with_executor
# ---------------------------------------------------------------------------


class TestRegisterWithExecutor:
    """Tests for WorkflowComposer.register_with_executor."""

    def test_registers_handler(self):
        """Registers a sub_workflow handler with the executor."""
        mock_executor = MagicMock()
        composer = WorkflowComposer()
        composer.register_with_executor(mock_executor)

        mock_executor.register_handler.assert_called_once()
        args = mock_executor.register_handler.call_args
        assert args[0][0] == "sub_workflow"
        assert callable(args[0][1])

    @patch("animus_kernel.executor.composer.load_workflow")
    def test_registered_handler_invokes_composer(self, mock_load):
        """The registered handler delegates to execute_sub_workflow."""
        mock_load.return_value = _make_workflow_config()

        with patch("animus_kernel.executor.composer.WorkflowExecutor") as MockExec:
            mock_child = MagicMock()
            mock_child.execute.return_value = _make_execution_result()
            MockExec.return_value = mock_child

            real_executor = MagicMock()
            real_executor.checkpoint_manager = None
            real_executor.budget_manager = None
            real_executor.feedback_engine = None
            real_executor.dry_run = False

            composer = WorkflowComposer()

            # Capture the handler
            handler = None

            def capture_handler(step_type, fn):
                nonlocal handler
                handler = fn

            real_executor.register_handler.side_effect = capture_handler
            composer.register_with_executor(real_executor)

            assert handler is not None
            step = _make_step()
            result = handler(step, {"ctx_key": "ctx_val"})
            assert "_sub_workflow_result" in result
