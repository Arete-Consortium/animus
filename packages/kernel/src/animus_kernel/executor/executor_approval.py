"""Approval gate handler for workflow executor.

Mixin class providing the approval step type. When an approval step
is hit, execution halts and a resume token is returned to the caller.
"""

from __future__ import annotations

import logging

from .loader import StepConfig

logger = logging.getLogger(__name__)


class ApprovalHandlerMixin:
    """Mixin providing approval gate step execution.

    Expects the following attributes from the host class:
    - _context: dict
    - _execution_id: str | None
    - _current_workflow_id: str | None
    """

    def _approval_store(self):
        raise RuntimeError("Approval persistence requires an application adapter")

    def _execute_approval(self, step: StepConfig, context: dict) -> dict:
        """Execute an approval gate step.

        Creates a resume token, serializes context and preview data,
        and returns output signaling the workflow should halt.

        Args:
            step: StepConfig with type="approval"
            context: Current execution context

        Returns:
            Dict with status="awaiting_approval", token, prompt, preview
        """
        prompt = step.params.get("prompt", "Approval required")
        timeout_hours = step.params.get("timeout_hours", 24)

        # Gather preview outputs from referenced steps
        preview_from = step.params.get("preview_from", [])
        preview = {}
        for ref_step_id in preview_from:
            if ref_step_id in context:
                preview[ref_step_id] = context[ref_step_id]

        store = self._approval_store()
        token = store.create_token(
            execution_id=self._execution_id or "",
            workflow_id=self._current_workflow_id or "",
            step_id=step.id,
            next_step_id="",  # Updated by executor_core after this returns
            prompt=prompt,
            preview=preview,
            context=context,
            timeout_hours=timeout_hours,
        )

        logger.info("Approval gate '%s' halted execution", step.id)

        return {
            "status": "awaiting_approval",
            "token": token,
            "prompt": prompt,
            "preview": preview,
            "timeout_hours": timeout_hours,
        }
