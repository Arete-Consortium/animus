"""Core WorkflowExecutor class with orchestration logic.

Contains __init__, execute/execute_async entry points, sequential execution,
and helper methods for validation, budget, output storage, and finalization.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from animus_kernel.state.agent_context import MemoryConfig, WorkflowMemoryManager

from .executor_agents import AgentStepHandlerMixin
from .executor_ai import AIHandlersMixin
from .executor_approval import ApprovalHandlerMixin
from .executor_arete import AreteToolsHandlerMixin
from .executor_cost_audit import CostAuditHandlerMixin
from .executor_error import ErrorHandlerMixin
from .executor_integrations import IntegrationHandlersMixin
from .executor_loop import LoopHandlerMixin
from .executor_mcp import MCPHandlersMixin
from .executor_parallel_exec import ParallelGroupMixin
from .executor_patterns import DistributionPatternsMixin
from .executor_results import ExecutionResult, StepHandler, StepResult, StepStatus
from .executor_step import StepExecutionMixin
from .loader import StepConfig, WorkflowConfig

logger = logging.getLogger(__name__)


class WorkflowExecutor(
    StepExecutionMixin,
    ErrorHandlerMixin,
    ParallelGroupMixin,
    IntegrationHandlersMixin,
    AIHandlersMixin,
    MCPHandlersMixin,
    DistributionPatternsMixin,
    ApprovalHandlerMixin,
    LoopHandlerMixin,
    AreteToolsHandlerMixin,
    AgentStepHandlerMixin,
    CostAuditHandlerMixin,
):
    """Executes workflows with contract validation and state persistence.

    Integrates with:
    - ContractValidator for input/output validation
    - CheckpointManager for state persistence
    - BudgetManager for token tracking
    """

    def __init__(
        self,
        checkpoint_manager=None,
        contract_validator=None,
        budget_manager=None,
        dry_run: bool = False,
        error_callback: Callable[[str, str, Exception], None] | None = None,
        fallback_callbacks: dict[str, Callable[[StepConfig, dict, Exception], dict]] | None = None,
        memory_manager: WorkflowMemoryManager | None = None,
        memory_config: MemoryConfig | None = None,
        feedback_engine=None,
        execution_manager=None,
        arete_hooks=None,
        agent_memory=None,
    ):
        """Initialize executor.

        Args:
            checkpoint_manager: Optional CheckpointManager for state persistence
            contract_validator: Optional ContractValidator for contract validation
            budget_manager: Optional BudgetManager for token tracking
            dry_run: If True, use mock responses instead of real API calls
            error_callback: Optional callback for error notifications (step_id, workflow_id, error)
            fallback_callbacks: Dict of named callbacks for fallback handling
            memory_manager: Optional WorkflowMemoryManager for agent memory
            memory_config: Optional MemoryConfig for memory behavior
            feedback_engine: Optional FeedbackEngine for outcome tracking and learning
            execution_manager: Optional ExecutionManager for streaming execution logs
            arete_hooks: Optional AreteHooks for Arete Tool bridge integration
            agent_memory: Optional AgentMemory for persistent cross-workflow agent memory
        """
        self.checkpoint_manager = checkpoint_manager
        self.contract_validator = contract_validator
        self.budget_manager = budget_manager
        self.dry_run = dry_run
        self.error_callback = error_callback
        self.fallback_callbacks = fallback_callbacks or {}
        self.memory_manager = memory_manager
        self.memory_config = memory_config
        self.feedback_engine = feedback_engine
        self.execution_manager = execution_manager
        self.arete_hooks = arete_hooks
        self.agent_memory = agent_memory
        self._execution_id: str | None = None
        self._handlers: dict[str, StepHandler] = {
            "shell": self._execute_shell,
            "checkpoint": self._execute_checkpoint,
            "parallel": self._execute_parallel,
            "claude_code": self._execute_claude_code,
            "openai": self._execute_openai,
            "ollama": self._execute_ollama,
            "fan_out": self._execute_fan_out,
            "fan_in": self._execute_fan_in,
            "map_reduce": self._execute_map_reduce,
            # MCP handler
            "mcp_tool": self._execute_mcp_tool,
            # Approval gate
            "approval": self._execute_approval,
            # Loop
            "loop": self._execute_loop,
            # Integration handlers
            "github": self._execute_github,
            "notion": self._execute_notion,
            "gmail": self._execute_gmail,
            "slack": self._execute_slack,
            "calendar": self._execute_calendar,
            "browser": self._execute_browser,
            # Arete Tool handlers
            "signal_audit": self._execute_signal_audit,
            "autopsy_analyze": self._execute_autopsy_analyze,
            "verdict_capture": self._execute_verdict_capture,
            # Agent handlers
            "autonomy": self._execute_autonomy,
            "handoff": self._execute_handoff,
            # Cost audit (Effective-Tokens anomaly detector)
            "cost_audit": self._execute_cost_audit,
        }
        self._context: dict = {}
        self._current_workflow_id: str | None = None

    def register_handler(self, step_type: str, handler: StepHandler) -> None:
        """Register a custom step handler.

        Args:
            step_type: Step type name
            handler: Function that takes (StepConfig, context) and returns output dict
        """
        self._handlers[step_type] = handler

    def _emit_log(self, level: str, message: str, step_id: str | None = None) -> None:
        """Emit a log event to the execution manager (non-fatal)."""
        if not self.execution_manager or not self._execution_id:
            return
        try:
            from animus_kernel.executions.models import LogLevel

            self.execution_manager.add_log(
                self._execution_id, LogLevel(level), message, step_id=step_id
            )
        except Exception:
            logger.debug("Execution log emission failed", exc_info=True)

    def _emit_progress(self, step_index: int, total_steps: int, step_id: str) -> None:
        """Emit a progress update to the execution manager (non-fatal)."""
        if not self.execution_manager or not self._execution_id:
            return
        try:
            progress = int((step_index / total_steps) * 100) if total_steps else 0
            self.execution_manager.update_progress(
                self._execution_id, progress, current_step=step_id
            )
        except Exception:
            logger.debug("Execution progress emission failed", exc_info=True)

    def _validate_workflow_inputs(self, workflow: WorkflowConfig, result: ExecutionResult) -> bool:
        """Validate required workflow inputs, applying defaults where available.

        Args:
            workflow: WorkflowConfig to validate
            result: ExecutionResult to update on failure

        Returns:
            True if valid, False if missing required input
        """
        for input_name, input_spec in workflow.inputs.items():
            if input_spec.get("required", False) and input_name not in self._context:
                if "default" in input_spec:
                    self._context[input_name] = input_spec["default"]
                else:
                    result.status = "failed"
                    result.error = f"Missing required input: {input_name}"
                    return False
        return True

    def _find_resume_index(self, workflow: WorkflowConfig, resume_from: str) -> int:
        """Find the step index to resume from.

        Args:
            workflow: WorkflowConfig containing steps
            resume_from: Step ID to resume from

        Returns:
            Index of the step to resume from, or 0 if not found
        """
        if not resume_from:
            return 0
        for i, step in enumerate(workflow.steps):
            if step.id == resume_from:
                return i
        return 0

    def _budget_store(self):
        from animus_kernel.db import get_task_store

        return get_task_store()

    def _check_budget_exceeded(self, step: StepConfig, result: ExecutionResult) -> bool:
        """Check if token budget would be exceeded by step.

        Args:
            step: Step to check
            result: ExecutionResult to update if budget exceeded

        Returns:
            True if budget exceeded, False if OK to proceed
        """
        if not self.budget_manager:
            return False
        # Cost-weighted ceiling: if cumulative Effective-Tokens (or raw) has
        # already pushed status to EXCEEDED, halt before the next step. This is
        # what makes ET an enforced constraint, not a reported number.
        from animus_kernel.budget import BudgetStatus

        if getattr(self.budget_manager.status, "value", None) == BudgetStatus.EXCEEDED.value:
            result.status = "failed"
            result.error = "Budget exceeded (effective-tokens)"
            return True
        estimated_tokens = step.params.get("estimated_tokens", 1000)
        if not self.budget_manager.can_allocate(estimated_tokens):
            result.status = "failed"
            result.error = "Token budget exceeded"
            return True

        # Daily limit enforcement
        daily_limit = self.budget_manager.config.daily_token_limit
        if daily_limit > 0:
            try:
                rows = self._budget_store().get_daily_budget(days=1)
                today_total = sum(r.get("total_tokens", 0) for r in rows)
                if today_total >= daily_limit:
                    result.status = "failed"
                    result.error = "Daily token budget exceeded"
                    return True
            except Exception:
                logger.debug("Daily budget check failed", exc_info=True)

        return False

    def _record_step_completion(
        self, step: StepConfig, step_result: StepResult, result: ExecutionResult
    ) -> None:
        """Record step completion in result, budget manager, and feedback engine.

        Args:
            step: Completed step
            step_result: Step result to record
            result: ExecutionResult to update
        """
        result.steps.append(step_result)
        result.total_tokens += step_result.tokens_used
        result.total_duration_ms += step_result.duration_ms

        if self.budget_manager and step_result.tokens_used > 0:
            # C1-1 — pass the model + input/output split so Effective-Tokens is
            # cost-weighted (opus/output-heavy steps cost more ET than raw),
            # instead of collapsing to raw because the breakdown was dropped.
            self.budget_manager.record_usage(
                step.id,
                step_result.tokens_used,
                model=step_result.model,
                input_tokens=step_result.input_tokens,
                output_tokens=step_result.output_tokens,
            )

        # Feed step outcome into the intelligence layer
        if self.feedback_engine:
            try:
                self.feedback_engine.process_step_result(
                    step_id=step.id,
                    workflow_id=self._current_workflow_id or "",
                    agent_role=step.params.get("role", step.type),
                    provider=step.type,
                    model=step.params.get("model", ""),
                    step_result=step_result,
                    cost_usd=0.0,  # Cost tracked separately via cost_tracker
                    tokens_used=step_result.tokens_used,
                    skill_name=step.params.get("skill_name", ""),
                    skill_version=step.params.get("skill_version", ""),
                )
            except Exception as fb_err:
                logger.debug(f"Feedback engine error (non-fatal): {fb_err}")

        # Emit step completion to execution manager
        if self.execution_manager and self._execution_id:
            try:
                failed = 1 if step_result.status == StepStatus.FAILED else 0
                completed = 0 if failed else 1
                self.execution_manager.update_metrics(
                    self._execution_id,
                    tokens=step_result.tokens_used,
                    duration_ms=step_result.duration_ms,
                    steps_completed=completed,
                    steps_failed=failed,
                )
                status_label = step_result.status.value
                self._emit_log(
                    "info" if status_label == "success" else "warning",
                    f"Step {step.id} completed: {status_label} "
                    f"({step_result.tokens_used} tokens, {step_result.duration_ms}ms)",
                    step_id=step.id,
                )
            except Exception:
                logger.debug("Execution metrics emission failed", exc_info=True)

        # Record in task history (analytics, non-critical)
        try:
            self._budget_store().record_task(
                job_id=step.id,
                workflow_id=self._current_workflow_id or "",
                status=step_result.status.value,
                agent_role=step.params.get("role", step.type),
                model=step.params.get("model", ""),
                total_tokens=step_result.tokens_used,
                duration_ms=step_result.duration_ms,
                error=step_result.error,
            )
        except Exception:
            logger.debug("Task history recording failed", exc_info=True)

    def _store_step_outputs(self, step: StepConfig, step_result: StepResult) -> None:
        """Store step outputs in execution context.

        Args:
            step: Step with output keys
            step_result: Step result containing outputs

        For AI steps (claude_code, openai), the handler returns 'response' as the key.
        If the workflow defines custom output names, we map 'response' to the first
        output name, allowing intuitive workflow syntax like:
            outputs:
              - situation_analysis
        instead of forcing:
            outputs:
              - response
        """
        for i, output_key in enumerate(step.outputs):
            if output_key in step_result.output:
                # Direct match - use the value
                self._context[output_key] = step_result.output[output_key]
            elif i == 0 and "response" in step_result.output:
                # Map 'response' to the first custom output name for AI steps
                self._context[output_key] = step_result.output["response"]
            elif i == 0 and "stdout" in step_result.output:
                # Map 'stdout' to the first custom output name for shell steps
                self._context[output_key] = step_result.output["stdout"]

    def _finalize_workflow(
        self,
        result: ExecutionResult,
        workflow: WorkflowConfig,
        workflow_id: str | None,
        error: Exception | None = None,
    ) -> None:
        """Finalize workflow execution - update checkpoints and collect outputs.

        Args:
            result: ExecutionResult to finalize
            workflow: WorkflowConfig with output definitions
            workflow_id: Current workflow ID
            error: Exception if workflow failed with error
        """
        # Approval gate: workflow is suspended, not complete or failed
        if result.status == "awaiting_approval":
            from animus_kernel.state.persistence import WorkflowStatus

            if self.checkpoint_manager and workflow_id:
                try:
                    self.checkpoint_manager.persistence.update_status(
                        workflow_id, WorkflowStatus.AWAITING_APPROVAL
                    )
                except Exception:
                    logger.debug(
                        "Failed to update workflow to awaiting_approval",
                        exc_info=True,
                    )
            if self.execution_manager and self._execution_id:
                try:
                    self.execution_manager.pause_execution(self._execution_id)
                except Exception:
                    logger.debug(
                        "Failed to pause execution for approval gate",
                        exc_info=True,
                    )
            self._execution_id = None
            self._current_workflow_id = None
            return

        if error:
            result.status = "failed"
            result.error = str(error)
            if self.checkpoint_manager and workflow_id:
                self.checkpoint_manager.fail_workflow(str(error), workflow_id)
        else:
            if self.checkpoint_manager and workflow_id:
                if result.status == "success":
                    self.checkpoint_manager.complete_workflow(workflow_id)
                else:
                    self.checkpoint_manager.fail_workflow(
                        result.error or "Unknown error", workflow_id
                    )

        # Collect workflow outputs
        for output_name in workflow.outputs:
            if output_name in self._context:
                result.outputs[output_name] = self._context[output_name]

        result.completed_at = datetime.now(UTC)
        result.total_duration_ms = int(
            (result.completed_at - result.started_at).total_seconds() * 1000
        )

        # Save agent memories
        if self.memory_manager:
            try:
                self.memory_manager.save_all()
            except Exception as mem_err:
                logger.warning(f"Failed to save agent memories: {mem_err}")

        # Feed workflow outcome into the intelligence layer
        if self.feedback_engine:
            try:
                self.feedback_engine.process_workflow_result(
                    workflow_id=workflow_id or "",
                    workflow_name=workflow.name,
                    execution_result=result,
                )
            except Exception as fb_err:
                logger.debug(f"Feedback engine workflow processing error (non-fatal): {fb_err}")

        # Arete Tool post-workflow hooks
        if self.arete_hooks:
            try:
                self.arete_hooks.on_workflow_complete(
                    workflow_id=workflow_id or "",
                    status=result.status,
                )
            except Exception:
                logger.debug("Arete hooks post-workflow failed", exc_info=True)

        # Complete execution tracking
        if self.execution_manager and self._execution_id:
            try:
                error_msg = result.error if result.status != "success" else None
                self.execution_manager.complete_execution(self._execution_id, error=error_msg)
            except Exception:
                logger.debug("Execution tracking completion failed", exc_info=True)
        self._execution_id = None

        # Clear workflow ID
        self._current_workflow_id = None

    def execute(
        self,
        workflow: WorkflowConfig,
        inputs: dict | None = None,
        resume_from: str | None = None,
        enable_memory: bool = True,
    ) -> ExecutionResult:
        """Execute a workflow.

        Args:
            workflow: WorkflowConfig to execute
            inputs: Input values for the workflow
            resume_from: Optional step ID to resume from
            enable_memory: Enable agent memory (default True)

        Returns:
            ExecutionResult with status and outputs
        """
        result = ExecutionResult(workflow_name=workflow.name)
        self._context = inputs.copy() if inputs else {}

        if not self._validate_workflow_inputs(workflow, result):
            return result

        # Start workflow in checkpoint manager
        workflow_id = None
        if self.checkpoint_manager:
            workflow_id = self.checkpoint_manager.start_workflow(
                workflow.name,
                config={"inputs": self._context},
            )
        self._current_workflow_id = workflow_id

        # Create execution tracking record
        if self.execution_manager:
            try:
                execution = self.execution_manager.create_execution(
                    workflow_id=workflow_id or workflow.name,
                    workflow_name=workflow.name,
                    variables=self._context,
                )
                self._execution_id = execution.id
                self.execution_manager.start_execution(self._execution_id)
            except Exception:
                logger.debug("Execution tracking init failed", exc_info=True)

        # Initialize memory manager if enabled and not provided
        if enable_memory and not self.memory_manager:
            from animus_kernel.state import AgentMemory

            memory = AgentMemory()
            self.memory_manager = WorkflowMemoryManager(
                memory=memory,
                workflow_id=workflow_id,
                config=self.memory_config,
            )
        elif self.memory_manager and workflow_id:
            # Update workflow ID if manager exists
            self.memory_manager.workflow_id = workflow_id

        start_index = self._find_resume_index(workflow, resume_from)

        # Execute steps - use auto-parallel if enabled
        error = None
        try:
            if workflow.settings.auto_parallel:
                self._execute_with_auto_parallel(workflow, start_index, workflow_id, result)
            else:
                self._execute_sequential(workflow, start_index, workflow_id, result)
        except Exception as e:
            error = e

        self._finalize_workflow(result, workflow, workflow_id, error)
        return result

    def _execute_sequential(
        self,
        workflow: WorkflowConfig,
        start_index: int,
        workflow_id: str | None,
        result: ExecutionResult,
    ) -> None:
        """Execute workflow steps sequentially.

        Args:
            workflow: WorkflowConfig to execute
            start_index: Index to start from
            workflow_id: Current workflow ID
            result: ExecutionResult to update
        """
        total_steps = len(workflow.steps)
        for i, step in enumerate(workflow.steps[start_index:], start=start_index):
            if self._check_budget_exceeded(step, result):
                break

            self._emit_log("info", f"Starting step {step.id} ({step.type})", step_id=step.id)
            self._emit_progress(i, total_steps, step.id)

            step_result = self._execute_step(step, workflow_id)
            self._record_step_completion(step, step_result, result)

            if step_result.status == StepStatus.FAILED:
                action = self._handle_step_failure(step, step_result, result, workflow_id)
                if action == "abort":
                    break
                if action == "skip":
                    continue

            self._store_step_outputs(step, step_result)

            # Check if step is an approval gate that halted execution
            if step_result.output and step_result.output.get("status") == "awaiting_approval":
                self._handle_approval_halt(step, step_result, result, workflow)
                break
        else:
            result.status = "success"

    async def execute_async(
        self,
        workflow: WorkflowConfig,
        inputs: dict | None = None,
        resume_from: str | None = None,
    ) -> ExecutionResult:
        """Execute a workflow asynchronously.

        This is the async version of execute() for non-blocking execution.

        Args:
            workflow: WorkflowConfig to execute
            inputs: Input values for the workflow
            resume_from: Optional step ID to resume from

        Returns:
            ExecutionResult with status and outputs
        """
        result = ExecutionResult(workflow_name=workflow.name)
        self._context = inputs.copy() if inputs else {}

        if not self._validate_workflow_inputs(workflow, result):
            return result

        # Start workflow in checkpoint manager
        workflow_id = None
        if self.checkpoint_manager:
            workflow_id = self.checkpoint_manager.start_workflow(
                workflow.name,
                config={"inputs": self._context},
            )
        self._current_workflow_id = workflow_id

        # Create execution tracking record
        if self.execution_manager:
            try:
                execution = self.execution_manager.create_execution(
                    workflow_id=workflow_id or workflow.name,
                    workflow_name=workflow.name,
                    variables=self._context,
                )
                self._execution_id = execution.id
                self.execution_manager.start_execution(self._execution_id)
            except Exception:
                logger.debug("Execution tracking init failed", exc_info=True)

        start_index = self._find_resume_index(workflow, resume_from)

        # Execute steps - use auto-parallel if enabled
        error = None
        try:
            if workflow.settings.auto_parallel:
                await self._execute_with_auto_parallel_async(
                    workflow, start_index, workflow_id, result
                )
            else:
                await self._execute_sequential_async(workflow, start_index, workflow_id, result)
        except Exception as e:
            error = e

        self._finalize_workflow(result, workflow, workflow_id, error)
        return result

    async def _execute_sequential_async(
        self,
        workflow: WorkflowConfig,
        start_index: int,
        workflow_id: str | None,
        result: ExecutionResult,
    ) -> None:
        """Execute workflow steps sequentially (async version)."""
        total_steps = len(workflow.steps)
        for i, step in enumerate(workflow.steps[start_index:], start=start_index):
            if self._check_budget_exceeded(step, result):
                break

            self._emit_log("info", f"Starting step {step.id} ({step.type})", step_id=step.id)
            self._emit_progress(i, total_steps, step.id)

            step_result = await self._execute_step_async(step, workflow_id)
            self._record_step_completion(step, step_result, result)

            if step_result.status == StepStatus.FAILED:
                action = await self._handle_step_failure_async(
                    step, step_result, result, workflow_id
                )
                if action == "abort":
                    break
                if action == "skip":
                    continue

            self._store_step_outputs(step, step_result)

            # Check if step is an approval gate that halted execution
            if step_result.output and step_result.output.get("status") == "awaiting_approval":
                self._handle_approval_halt(step, step_result, result, workflow)
                break
        else:
            result.status = "success"

    def _handle_approval_halt(
        self,
        step: StepConfig,
        step_result: StepResult,
        result: ExecutionResult,
        workflow: WorkflowConfig,
    ) -> None:
        """Handle an approval gate halt.

        Computes the next step ID and updates the approval token,
        then sets the execution result to awaiting_approval.

        Args:
            step: The approval step that triggered the halt
            step_result: Result from the approval handler
            result: ExecutionResult to update
            workflow: WorkflowConfig for step lookup
        """
        # Compute next step ID for resume
        try:
            step_idx = next(i for i, s in enumerate(workflow.steps) if s.id == step.id)
            if step_idx + 1 < len(workflow.steps):
                next_step_id = workflow.steps[step_idx + 1].id
            else:
                next_step_id = ""
        except StopIteration:
            next_step_id = ""

        # Update the token with the correct next_step_id
        token = step_result.output.get("token", "")
        if token:
            try:
                store = self._approval_store()
                with store.backend.transaction():
                    store.backend.execute(
                        "UPDATE approval_tokens SET next_step_id = ? WHERE token = ?",
                        (next_step_id, token),
                    )
            except Exception:
                logger.debug("Failed to update approval token next_step_id", exc_info=True)

        result.status = "awaiting_approval"
        result.outputs["__approval_token"] = token
        result.outputs["__approval_prompt"] = step_result.output.get("prompt", "")
        result.outputs["__approval_preview"] = step_result.output.get("preview", {})

    def get_context(self) -> dict:
        """Get current execution context."""
        return self._context.copy()

    def set_context(self, context: dict) -> None:
        """Set execution context."""
        self._context = context.copy()
