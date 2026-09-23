"""End-to-end workflow validation tests.

Tests real YAML workflow definitions through the executor with mocked AI providers,
verifying: YAML load → input validation → step execution → context passing → output collection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from animus_forge.budget.manager import BudgetConfig, BudgetManager
from animus_forge.workflow.executor import (
    StepConfig,
    StepStatus,
    WorkflowExecutor,
    reset_circuit_breakers,
)
from animus_forge.workflow.loader import (
    ConditionConfig,
    WorkflowConfig,
    load_workflow,
)

WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"

# Workflows with known validation issues
KNOWN_INVALID_YAMLS: set[str] = set()


@pytest.fixture(autouse=True)
def _clean_circuit_breakers():
    """Reset circuit breakers between tests."""
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


def _all_yaml_paths() -> list[Path]:
    return sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _valid_yaml_paths() -> list[Path]:
    return [p for p in _all_yaml_paths() if p.stem not in KNOWN_INVALID_YAMLS]


# ---------------------------------------------------------------------------
# 1. YAML Loading Validation
# ---------------------------------------------------------------------------


class TestWorkflowYAMLLoading:
    """Load all YAML workflows and verify structural validity."""

    @pytest.fixture(params=_valid_yaml_paths(), ids=lambda p: p.stem)
    def workflow_path(self, request) -> Path:
        return request.param

    def test_loads_without_error(self, workflow_path: Path):
        wf = load_workflow(workflow_path, trusted_dir=WORKFLOWS_DIR)
        assert wf.name, f"{workflow_path.name}: missing name"
        assert len(wf.steps) >= 1, f"{workflow_path.name}: no steps"

    def test_all_step_types_recognized(self, workflow_path: Path):
        from animus_forge.workflow.loader import VALID_STEP_TYPES

        wf = load_workflow(workflow_path, trusted_dir=WORKFLOWS_DIR)
        for step in wf.steps:
            assert step.type in VALID_STEP_TYPES, (
                f"{workflow_path.name}: step '{step.id}' has unknown type '{step.type}'"
            )

    def test_all_steps_have_ids(self, workflow_path: Path):
        wf = load_workflow(workflow_path, trusted_dir=WORKFLOWS_DIR)
        ids = [s.id for s in wf.steps]
        assert all(ids), f"{workflow_path.name}: step with empty id"
        assert len(ids) == len(set(ids)), f"{workflow_path.name}: duplicate step ids"

    @pytest.mark.parametrize(
        "stem", sorted(KNOWN_INVALID_YAMLS) if KNOWN_INVALID_YAMLS else ["_skip_"]
    )
    def test_invalid_workflows_raise_on_load(self, stem: str):
        """Workflows with known validation issues should fail."""
        if stem == "_skip_":
            pytest.skip("No known invalid YAMLs")
        path = WORKFLOWS_DIR / f"{stem}.yaml"
        if not path.exists():
            pytest.skip(f"{stem}.yaml not found")
        with pytest.raises(ValueError):
            load_workflow(path, trusted_dir=WORKFLOWS_DIR)


# ---------------------------------------------------------------------------
# 2. Feature Build E2E (dry_run)
# ---------------------------------------------------------------------------


class TestFeatureBuildE2E:
    """Execute feature-build.yaml end-to-end in dry_run mode."""

    @pytest.fixture
    def workflow(self) -> WorkflowConfig:
        return load_workflow(WORKFLOWS_DIR / "feature-build.yaml", trusted_dir=WORKFLOWS_DIR)

    def _make_inputs(self, tmp_path: Path) -> dict:
        (tmp_path / "test_dummy.py").write_text("def test_pass(): assert True\n")
        return {
            "feature_request": "Add user authentication",
            "codebase_path": str(tmp_path),
            # Single token avoids shlex.quote splitting issues
            "test_command": "true",
        }

    def test_dry_run_all_steps_execute(self, workflow, tmp_path):
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow, inputs=self._make_inputs(tmp_path))
        # Review step has condition on test_results containing "passed",
        # but shell `true` outputs empty string, so review gets skipped.
        # Expect 5 successful + 1 skipped = 6 total steps.
        assert result.status == "success", f"Workflow failed: {result.error}"
        assert len(result.steps) == 6

    def test_dry_run_step_outputs_populated(self, workflow, tmp_path):
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow, inputs=self._make_inputs(tmp_path))
        for sr in result.steps:
            if sr.status != StepStatus.SKIPPED:
                assert sr.output is not None, f"Step {sr.step_id} has no output"

    def test_variable_substitution(self, workflow, tmp_path):
        inputs = self._make_inputs(tmp_path)
        inputs["feature_request"] = "Add OAuth2 login"
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow, inputs=inputs)
        # The plan step's prompt should contain the substituted feature request
        plan_step = result.steps[0]
        assert "Add OAuth2 login" in plan_step.output.get("prompt", "")

    def test_missing_required_input_fails(self, workflow):
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow, inputs={})
        assert result.status == "failed"
        assert "Missing required input" in result.error


# ---------------------------------------------------------------------------
# 3. Feature Build Mocked — realistic AI responses
# ---------------------------------------------------------------------------


class TestFeatureBuildMocked:
    """Feature-build with patched AI returning role-appropriate responses."""

    @pytest.fixture
    def workflow(self) -> WorkflowConfig:
        return load_workflow(WORKFLOWS_DIR / "feature-build.yaml", trusted_dir=WORKFLOWS_DIR)

    @staticmethod
    def _mock_claude(step: StepConfig, context: dict) -> dict:
        role = step.params.get("role", "builder")
        responses = {
            "planner": "## Plan\n1. Create auth module\n2. Add login endpoint",
            "builder": "```python\ndef login(user, pw): ...\n```",
            "tester": "```python\ndef test_login(): assert login('a','b')\n```",
            "reviewer": "LGTM. Code quality: 8/10. Approved.",
        }
        return {
            "role": role,
            "prompt": step.params.get("prompt", ""),
            "response": responses.get(role, "OK"),
            "tokens_used": 500,
            "model": "mock",
        }

    def test_context_flows_plan_to_review(self, workflow, tmp_path):
        (tmp_path / "test_dummy.py").write_text("def test_pass(): assert True\n")

        with patch.object(WorkflowExecutor, "_execute_claude_code", side_effect=self._mock_claude):
            executor = WorkflowExecutor()
            result = executor.execute(
                workflow,
                inputs={
                    "feature_request": "Add auth",
                    "codebase_path": str(tmp_path),
                    "test_command": "true",
                },
            )

        # Workflow succeeds (review may be skipped due to condition)
        assert result.status == "success", f"Workflow failed: {result.error}"
        plan_output = result.steps[0].output
        assert "Plan" in plan_output.get("response", "")

    def test_review_skipped_when_tests_fail(self, workflow, tmp_path):
        """Review step has condition: test_results contains 'passed'.
        If test_command fails, workflow aborts (run_tests on_failure: abort)."""
        (tmp_path / "test_dummy.py").write_text("def test_pass(): assert True\n")

        with patch.object(WorkflowExecutor, "_execute_claude_code", side_effect=self._mock_claude):
            executor = WorkflowExecutor()
            result = executor.execute(
                workflow,
                inputs={
                    "feature_request": "Add auth",
                    "codebase_path": str(tmp_path),
                    "test_command": "false",
                },
            )

        assert result.status == "failed"


# ---------------------------------------------------------------------------
# 4. Code Review E2E (dry_run) — workflow has invalid 'in' operator
# ---------------------------------------------------------------------------


class TestCodeReviewE2E:
    """Code-review.yaml now loads successfully with 'in' operator support."""

    def test_loads_and_dry_runs(self):
        wf = load_workflow(WORKFLOWS_DIR / "code-review.yaml", trusted_dir=WORKFLOWS_DIR)
        assert wf.name
        assert len(wf.steps) >= 1
        executor = WorkflowExecutor(dry_run=True)
        # Provide minimal inputs so it doesn't fail on missing required inputs
        inputs = {}
        for name, spec in wf.inputs.items():
            if spec.get("required") and "default" not in spec:
                inputs[name] = f"test_{name}"
        result = executor.execute(wf, inputs=inputs)
        # Workflow should at least start (may fail on missing context, but shouldn't error on load)
        assert result.status in ("success", "failed")


# ---------------------------------------------------------------------------
# 5. Conditional Execution
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    """Test that conditions properly skip steps."""

    def test_false_condition_skips_step(self):
        """Condition checks context key 'status'. When value doesn't match, step is skipped."""
        workflow = WorkflowConfig(
            name="conditional-test",
            version="1.0",
            description="Test conditional skip",
            steps=[
                StepConfig(
                    id="setup",
                    type="shell",
                    params={"command": "echo hello"},
                    outputs=["stdout"],  # Maps to shell stdout key
                ),
                StepConfig(
                    id="conditional",
                    type="shell",
                    params={"command": "echo skipped"},
                    condition=ConditionConfig(
                        field="stdout",
                        operator="contains",
                        value="NOPE",
                    ),
                    outputs=["cond_out"],
                ),
                StepConfig(
                    id="final",
                    type="shell",
                    params={"command": "echo done"},
                    outputs=["final_out"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "success"

        step_map = {s.step_id: s for s in result.steps}
        assert step_map["setup"].status == StepStatus.SUCCESS
        assert step_map["conditional"].status == StepStatus.SKIPPED
        assert step_map["final"].status == StepStatus.SUCCESS

    def test_true_condition_runs_step(self):
        """When condition matches, step executes normally."""
        workflow = WorkflowConfig(
            name="conditional-true-test",
            version="1.0",
            description="Test conditional run",
            inputs={},
            steps=[
                StepConfig(
                    id="producer",
                    type="shell",
                    params={"command": "echo hello"},
                    outputs=["stdout"],  # Direct match to shell output key
                ),
                StepConfig(
                    id="consumer",
                    type="shell",
                    params={"command": "echo consumed"},
                    condition=ConditionConfig(
                        field="stdout",
                        operator="contains",
                        value="hello",
                    ),
                    outputs=["result"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "success"
        step_map = {s.step_id: s for s in result.steps}
        assert step_map["consumer"].status == StepStatus.SUCCESS


# ---------------------------------------------------------------------------
# 6. Error Recovery E2E
# ---------------------------------------------------------------------------


class TestErrorRecoveryE2E:
    """Test mixed failure strategies across steps."""

    def test_skip_on_failure_continues(self):
        workflow = WorkflowConfig(
            name="error-recovery",
            version="1.0",
            description="Test error recovery strategies",
            steps=[
                StepConfig(
                    id="failing_skip",
                    type="shell",
                    params={"command": "exit 1"},
                    on_failure="skip",
                    outputs=["skip_out"],
                ),
                StepConfig(
                    id="after_skip",
                    type="shell",
                    params={"command": "echo survived"},
                    outputs=["survived"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "success"
        step_map = {s.step_id: s for s in result.steps}
        assert step_map["failing_skip"].status == StepStatus.FAILED
        assert step_map["after_skip"].status == StepStatus.SUCCESS

    def test_abort_on_failure_stops(self):
        workflow = WorkflowConfig(
            name="abort-test",
            version="1.0",
            description="Test abort stops workflow",
            steps=[
                StepConfig(
                    id="failing_abort",
                    type="shell",
                    params={"command": "exit 1"},
                    on_failure="abort",
                    outputs=["out"],
                ),
                StepConfig(
                    id="never_reached",
                    type="shell",
                    params={"command": "echo nope"},
                    outputs=["nope"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "failed"
        step_ids = [s.step_id for s in result.steps]
        assert "never_reached" not in step_ids


# ---------------------------------------------------------------------------
# 7. Context Propagation
# ---------------------------------------------------------------------------


class TestContextPropagation:
    """Verify output from step N feeds into step N+1 via variable substitution."""

    def test_shell_stdout_flows_to_next_shell(self):
        """Shell output key 'stdout' is stored in context when outputs=['stdout']."""
        workflow = WorkflowConfig(
            name="context-propagation",
            version="1.0",
            description="Test context flow between steps",
            steps=[
                StepConfig(
                    id="step1",
                    type="shell",
                    params={"command": "printf MAGIC_VALUE_42"},
                    outputs=["stdout"],  # Direct match to shell output key
                ),
                StepConfig(
                    id="step2",
                    type="shell",
                    params={
                        "command": "echo received: ${stdout}",
                        "escape_variables": False,
                    },
                    outputs=["stdout"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "success"
        step2 = result.steps[1]
        stdout = step2.output.get("stdout", "")
        assert "MAGIC_VALUE_42" in stdout

    def test_shell_to_ai_context_flow(self):
        """Shell stdout stored as 'stdout' feeds into AI step prompt via ${stdout}."""
        workflow = WorkflowConfig(
            name="shell-to-ai",
            version="1.0",
            description="Test shell to AI context",
            steps=[
                StepConfig(
                    id="read",
                    type="shell",
                    params={"command": "echo file_content_here"},
                    outputs=["stdout"],  # Maps to shell stdout key
                ),
                StepConfig(
                    id="analyze",
                    type="claude_code",
                    params={
                        "role": "reviewer",
                        "prompt": "Review this code: ${stdout}",
                        "estimated_tokens": 100,
                    },
                    outputs=["review"],
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)
        assert result.status == "success"
        ai_step = result.steps[1]
        assert "file_content_here" in ai_step.output.get("prompt", "")

    def test_ai_response_maps_to_custom_output_name(self):
        """AI step 'response' key maps to first custom output name."""
        workflow = WorkflowConfig(
            name="ai-output-mapping",
            version="1.0",
            description="Test AI output name mapping",
            steps=[
                StepConfig(
                    id="plan",
                    type="claude_code",
                    params={
                        "role": "planner",
                        "prompt": "Create a plan",
                        "estimated_tokens": 100,
                    },
                    outputs=["plan_text"],
                ),
                StepConfig(
                    id="build",
                    type="claude_code",
                    params={
                        "role": "builder",
                        "prompt": "Build from: ${plan_text}",
                        "estimated_tokens": 100,
                    },
                    outputs=["code"],
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(workflow)
        assert result.status == "success"
        build_step = result.steps[1]
        # plan_text should have been substituted (not remain as ${plan_text})
        assert "${plan_text}" not in build_step.output.get("prompt", "")


# ---------------------------------------------------------------------------
# 8. Token Budget Enforcement
# ---------------------------------------------------------------------------


class TestTokenBudgetEnforcement:
    """Test that budget limits halt execution."""

    def test_budget_exceeded_stops_workflow(self):
        budget = BudgetManager(config=BudgetConfig(total_budget=100))
        workflow = WorkflowConfig(
            name="budget-test",
            version="1.0",
            description="Test budget enforcement",
            token_budget=100,
            steps=[
                StepConfig(
                    id="cheap",
                    type="shell",
                    params={"command": "echo ok"},
                    outputs=["out"],
                ),
                StepConfig(
                    id="expensive",
                    type="claude_code",
                    params={
                        "prompt": "Do something expensive",
                        "estimated_tokens": 5000,
                    },
                    outputs=["result"],
                ),
            ],
        )
        executor = WorkflowExecutor(dry_run=True, budget_manager=budget)
        result = executor.execute(workflow)
        assert result.status == "failed"
        assert "budget" in result.error.lower()

    def test_budget_exceeded_halts_real_run(self):
        """C1-15 — the dry-run test above only exercises the estimate gate. This
        runs a REAL (non-dry-run) workflow where step 1 actually records usage
        that exhausts the budget, and asserts step 2 is halted by the live
        budget check — the path that matters in production."""
        budget = BudgetManager(config=BudgetConfig(total_budget=100, reserve_tokens=0))

        def _big_spender(step: StepConfig, context: dict) -> dict:
            # A real step result: records 5000 tokens against a 100 budget.
            return {
                "role": step.params.get("role", "builder"),
                "prompt": step.params.get("prompt", ""),
                "response": "did expensive work",
                "tokens_used": 5000,
                "model": "claude-opus-4-8",
                "input_tokens": 1000,
                "output_tokens": 4000,
            }

        workflow = WorkflowConfig(
            name="budget-real-run",
            version="1.0",
            description="Real-run budget halt",
            token_budget=100,
            steps=[
                StepConfig(
                    id="first",
                    type="claude_code",
                    params={"prompt": "burn the budget", "estimated_tokens": 10},
                    outputs=["a"],
                ),
                StepConfig(
                    id="second",
                    type="claude_code",
                    params={"prompt": "should never run", "estimated_tokens": 10},
                    outputs=["b"],
                ),
            ],
        )

        with patch.object(WorkflowExecutor, "_execute_claude_code", side_effect=_big_spender):
            executor = WorkflowExecutor(budget_manager=budget)  # NOT dry_run
            result = executor.execute(workflow)

        # Step 1 really ran and recorded usage; the budget is now exhausted.
        assert budget.usage_percent >= 100
        # Cost-weighting reached the manager (C1-1): opus output-heavy ET >> raw.
        assert budget.effective_used > 5000
        # The workflow halted on budget, and step 2 did not succeed.
        assert result.status == "failed"
        assert "budget" in (result.error or "").lower()
        second = next((s for s in result.steps if s.step_id == "second"), None)
        assert second is None or second.status.value != "success"


# ---------------------------------------------------------------------------
# 9. Condition Operators
# ---------------------------------------------------------------------------


class TestConditionOperators:
    """Test each condition operator in isolation."""

    def test_in_operator_with_list(self):
        cond = ConditionConfig(field="status", operator="in", value=["active", "pending"])
        assert cond.evaluate({"status": "active"}) is True
        assert cond.evaluate({"status": "closed"}) is False

    def test_in_operator_with_string(self):
        cond = ConditionConfig(field="char", operator="in", value="abcdef")
        assert cond.evaluate({"char": "c"}) is True
        assert cond.evaluate({"char": "z"}) is False

    def test_not_empty_operator(self):
        cond = ConditionConfig(field="data", operator="not_empty")
        assert cond.evaluate({"data": "hello"}) is True
        assert cond.evaluate({"data": [1]}) is True
        assert cond.evaluate({"data": ""}) is False
        assert cond.evaluate({"data": []}) is False
        assert cond.evaluate({"data": 0}) is False
        assert cond.evaluate({}) is False  # missing field

    def test_contains_operator(self):
        cond = ConditionConfig(field="text", operator="contains", value="pass")
        assert cond.evaluate({"text": "all tests passed"}) is True
        assert cond.evaluate({"text": "failed"}) is False

    def test_not_equals_operator(self):
        cond = ConditionConfig(field="x", operator="not_equals", value=0)
        assert cond.evaluate({"x": 1}) is True
        assert cond.evaluate({"x": 0}) is False

    def test_greater_than_operator(self):
        cond = ConditionConfig(field="score", operator="greater_than", value=80)
        assert cond.evaluate({"score": 90}) is True
        assert cond.evaluate({"score": 70}) is False

    def test_less_than_operator(self):
        cond = ConditionConfig(field="score", operator="less_than", value=50)
        assert cond.evaluate({"score": 30}) is True
        assert cond.evaluate({"score": 60}) is False


# ---------------------------------------------------------------------------
# 10. Shell Output Mapping
# ---------------------------------------------------------------------------


class TestShellOutputMapping:
    """Verify shell stdout maps to custom output names."""

    def test_custom_output_name_maps_to_stdout(self):
        """outputs: [code_content] should receive the shell stdout value."""
        workflow = WorkflowConfig(
            name="shell-output-mapping",
            version="1.0",
            description="Test shell output mapping to custom name",
            steps=[
                StepConfig(
                    id="read_file",
                    type="shell",
                    params={"command": "printf CUSTOM_CONTENT_123"},
                    outputs=["code_content"],
                ),
                StepConfig(
                    id="use_content",
                    type="shell",
                    params={
                        "command": "echo got: ${code_content}",
                        "escape_variables": False,
                    },
                    outputs=["result"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        result = executor.execute(workflow)
        assert result.status == "success"
        step2 = result.steps[1]
        assert "CUSTOM_CONTENT_123" in step2.output.get("stdout", "")


# ---------------------------------------------------------------------------
# 11. Retry E2E
# ---------------------------------------------------------------------------


class TestRetryE2E:
    """Test retry logic with mocked handlers."""

    def test_retry_succeeds_on_second_attempt(self):
        """Handler fails once then succeeds — step should succeed with retries=1."""
        call_count = 0

        def flaky_handler(step: StepConfig, context: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient failure")
            return {"response": "ok", "tokens_used": 0}

        workflow = WorkflowConfig(
            name="retry-test",
            version="1.0",
            description="Test retry recovery",
            steps=[
                StepConfig(
                    id="flaky",
                    type="claude_code",
                    params={"prompt": "do thing", "estimated_tokens": 10},
                    max_retries=2,
                    outputs=["result"],
                ),
            ],
        )
        executor = WorkflowExecutor()
        executor.register_handler("claude_code", flaky_handler)
        result = executor.execute(workflow)
        assert result.status == "success", f"Expected success, got: {result.error}"
        assert result.steps[0].retries == 1


# ---------------------------------------------------------------------------
# 12. Checkpoint with YAML
# ---------------------------------------------------------------------------


class TestCheckpointWithYAML:
    """Test checkpoint and resume using feature-build.yaml."""

    def test_checkpoint_and_resume(self, tmp_path):
        from animus_forge.state.checkpoint import CheckpointManager

        wf = load_workflow(WORKFLOWS_DIR / "feature-build.yaml", trusted_dir=WORKFLOWS_DIR)
        db_path = str(tmp_path / "checkpoint.db")
        cm = CheckpointManager(db_path=db_path)

        (tmp_path / "test_dummy.py").write_text("def test_pass(): assert True\n")
        inputs = {
            "feature_request": "Add auth",
            "codebase_path": str(tmp_path),
            "test_command": "true",
        }

        # Run full workflow with checkpoints in dry_run
        executor = WorkflowExecutor(dry_run=True, checkpoint_manager=cm)
        result = executor.execute(wf, inputs=inputs)
        assert result.status == "success", f"First run failed: {result.error}"

        # Resume from last step (simulates restart) — should also succeed
        last_step_id = wf.steps[-1].id
        executor2 = WorkflowExecutor(dry_run=True, checkpoint_manager=cm)
        result2 = executor2.execute(wf, inputs=inputs, resume_from=last_step_id)
        assert result2.status == "success", f"Resume failed: {result2.error}"
