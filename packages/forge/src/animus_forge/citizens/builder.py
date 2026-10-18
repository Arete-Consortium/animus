"""Builder Citizen — implements approved tasks in an isolated workspace.

The builder is the only citizen (in the initial three-citizen set) that may
modify repository files.  It is constrained by:
- path allowlists and denylists
- max changed files
- no protected path modifications
"""

from __future__ import annotations

import logging
import re

from animus_forge.citizens.base import Citizen
from animus_forge.missions.domain import CitizenOutput, Task, TaskContext

logger = logging.getLogger(__name__)


class BuilderCitizen(Citizen):
    """Implements tasks within workspace policy boundaries."""

    role = "builder"
    capabilities = {"implementation", "testing", "refactoring"}
    can_modify_code = True
    can_approve = False

    def __init__(self, workspace_manager=None):
        self.workspace_manager = workspace_manager

    def run(self, task: Task, context: TaskContext) -> CitizenOutput:
        """Execute a build task.

        In production this would invoke a coding model (local or frontier) with
        the bounded context packet.  For Phase 4 the implementation is
        deterministic so that tests and evals do not require a live provider.
        """
        # Validate path policy before any modification
        for path in context.relevant_files:
            if not self._is_path_allowed(path, context):
                return CitizenOutput(
                    status="failed",
                    summary=f"Path policy violation: {path}",
                    risks=[
                        {
                            "severity": "high",
                            "description": f"Attempted to access protected path: {path}",
                        }
                    ],
                    confidence=0.0,
                )

        # Simulate implementation
        changed_files = self._simulate_changes(task, context)

        return CitizenOutput(
            status="completed",
            summary=f"Built: {task.description}",
            changed_files=changed_files,
            evidence=[
                {
                    "type": "build",
                    "changed_files": changed_files,
                    "protected_paths_checked": True,
                }
            ],
            risks=[],
            follow_up_tasks=[],
            confidence=0.75,
        )

    def _is_path_allowed(self, path: str, context: TaskContext) -> bool:
        """Return True if *path* is inside allowed_paths and outside protected_paths."""
        # Check protected paths first (deny-list takes precedence)
        for protected in context.protected_paths:
            if self._match_pattern(path, protected):
                logger.warning("Protected path match: %s against %s", path, protected)
                return False

        # If allowlist is empty, allow everything that isn't protected
        if not context.allowed_paths:
            return True

        for allowed in context.allowed_paths:
            if self._match_pattern(path, allowed):
                return True

        return False

    @staticmethod
    def _match_pattern(path: str, pattern: str) -> bool:
        """Match a path against a glob-like pattern.

        Supports ``**`` (any depth) and ``*`` (single segment).
        """
        regex = (
            pattern.replace(".", r"\.")
            .replace("**", r"{{ANYDEPTH}}")
            .replace("*", r"[^/]*")
            .replace(r"{{ANYDEPTH}}", ".*")
        )
        # Anchor at start; allow partial match for any-depth patterns
        if "**/" in pattern or pattern.startswith("**"):
            return bool(re.search(regex, path))
        return bool(re.match(regex + r"($|/)", path))

    def _simulate_changes(self, task: Task, context: TaskContext) -> list[str]:
        """Produce a deterministic list of changed files for testing.

        Real implementation would generate actual code via a model.
        """
        # If the task mentions "fix" or "bug", simulate a source + test change
        desc_lower = task.description.lower()
        if "fix" in desc_lower or "bug" in desc_lower:
            return ["src/pagination.py", "tests/test_pagination.py"]
        return ["src/change.py"]
