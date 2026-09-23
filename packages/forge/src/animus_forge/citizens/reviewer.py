"""Reviewer Citizen — evaluates builder output and approves or rejects.

The reviewer must independently inspect the diff and test results.  It may
not rely on the builder's self-description.
"""

from __future__ import annotations

from animus_forge.citizens.base import Citizen
from animus_forge.missions.domain import CitizenOutput, Task, TaskContext


class ReviewerCitizen(Citizen):
    """Reviews implementation output and produces structured findings."""

    role = "reviewer"
    capabilities = {"review", "correctness", "security", "maintainability"}
    can_modify_code = False
    can_approve = False  # approval requires human gate in Phase 4

    def run(self, task: Task, context: TaskContext) -> CitizenOutput:
        """Review the work described in *task* and *context*.

        In production this would invoke a frontier model (different family
        from the builder for independence) to reason about correctness and
        scope discipline.  For Phase 4 the logic is deterministic so that
        tests and evals do not require a live provider.
        """
        # Simulate review based on context clues
        approval, findings = self._simulate_review(task, context)

        if approval:
            return CitizenOutput(
                status="completed",
                summary="Review passed: no defects found.",
                evidence=[{"type": "review", "verdict": "approved", "findings": findings}],
                confidence=0.88,
            )

        return CitizenOutput(
            status="needs_repair",
            summary=f"Review rejected: {len(findings)} finding(s).",
            evidence=[{"type": "review", "verdict": "rejected", "findings": findings}],
            risks=[{"severity": f["severity"], "description": f["description"]} for f in findings],
            follow_up_tasks=[f"repair: {f['description']}" for f in findings],
            confidence=0.88,
        )

    def _simulate_review(self, task: Task, context: TaskContext) -> tuple[bool, list[dict]]:
        """Return deterministic review result for testing.

        Real implementation would use an LLM + static analysis tools.
        """
        findings: list[dict] = []

        # Check for protected path violations in evidence
        for ev in context.prior_attempts:
            if isinstance(ev, dict) and ev.get("type") == "build":
                for path in ev.get("changed_files", []):
                    for protected in context.protected_paths:
                        if protected.replace("**", "").replace("*", "") in path:
                            findings.append(
                                {
                                    "severity": "critical",
                                    "description": f"Protected path modified: {path}",
                                }
                            )

        # Check scope discipline: too many files changed
        changed = []
        for ev in context.prior_attempts:
            if isinstance(ev, dict) and ev.get("type") == "build":
                changed = ev.get("changed_files", [])

        if len(changed) > 15:
            findings.append(
                {
                    "severity": "medium",
                    "description": f"Too many files changed: {len(changed)}",
                }
            )

        # If the task description hints at an intentional defect, flag it
        if "unsafe" in task.description.lower():
            findings.append(
                {
                    "severity": "high",
                    "description": "Unsafe implementation pattern detected.",
                }
            )

        return len(findings) == 0, findings
