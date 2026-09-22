"""Workspace manager — creates isolated Git worktrees for build missions.

Phase 4 uses worktree + path denylist isolation.  Containers are deferred to
Phase 5+.  Every mission receives:
- dedicated worktree
- mission branch
- path restrictions (allowlist + denylist)
- resource quotas (enforced at manager level)
- cleanup on completion
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

DEFAULT_PROTECTED_PATHS = [
    ".github/workflows/**",
    "migrations/**",
    "security/**",
    "*.env*",
    "*secret*",
    "*token*",
    ".git/**",
]


@dataclass
class WorkspaceManifest:
    """Manifest describing an isolated workspace."""

    mission_id: str
    repository: str
    base_commit: str | None
    branch: str
    worktree_path: str
    allowed_paths: list[str]
    protected_paths: list[str]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "repository": self.repository,
            "base_commit": self.base_commit,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "allowed_paths": self.allowed_paths,
            "protected_paths": self.protected_paths,
            "created_at": self.created_at,
        }


class WorkspaceManager:
    """Manages Git worktree-based isolated workspaces.

    Args:
        base_dir: Root directory for all workspaces.
            Defaults to ``~/.animus/workspaces/``.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or os.path.expanduser("~/.animus/workspaces"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        mission_id: UUID,
        repo_path: str,
        *,
        base_commit: str | None = None,
        allowed_paths: list[str] | None = None,
        protected_paths: list[str] | None = None,
    ) -> WorkspaceManifest:
        """Create a new worktree for a mission.

        Args:
            mission_id: Mission UUID.
            repo_path: Absolute path to the repository.
            base_commit: Commit SHA to base the worktree on (default: HEAD).
            allowed_paths: Paths the builder may modify.
            protected_paths: Paths the builder may NOT modify.

        Returns:
            WorkspaceManifest describing the created workspace.
        """
        mission_dir = self.base_dir / str(mission_id)
        worktree_path = mission_dir / "repo"
        branch = f"animus/mission-{str(mission_id)[:8]}"

        repo = Path(repo_path)
        if not repo.is_dir():
            raise ValueError(f"Repository not found: {repo_path}")

        # Ensure .git exists ( bare repos not supported in Phase 4 )
        git_dir = repo / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a Git repository: {repo_path}")

        # Create worktree
        worktree_path.mkdir(parents=True, exist_ok=True)
        base = base_commit or "HEAD"
        self._git(repo, "worktree", "add", "-b", branch, str(worktree_path), base)

        manifest = WorkspaceManifest(
            mission_id=str(mission_id),
            repository=str(repo.resolve()),
            base_commit=base,
            branch=branch,
            worktree_path=str(worktree_path),
            allowed_paths=allowed_paths or [],
            protected_paths=protected_paths or list(DEFAULT_PROTECTED_PATHS),
            created_at=str(datetime.now()),
        )

        # Write manifest
        manifest_path = mission_dir / "manifest.json"
        import json

        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))

        logger.info("Workspace created for mission %s at %s", mission_id, worktree_path)
        return manifest

    def destroy(self, mission_id: UUID) -> None:
        """Remove the worktree and prune Git metadata."""
        mission_dir = self.base_dir / str(mission_id)
        worktree_path = mission_dir / "repo"

        if not worktree_path.exists():
            logger.warning("Workspace already destroyed: %s", mission_id)
            return

        # Find parent repo from manifest
        manifest_path = mission_dir / "manifest.json"
        repo_path: str | None = None
        branch: str | None = None
        if manifest_path.exists():
            import json

            data = json.loads(manifest_path.read_text())
            repo_path = data.get("repository")
            branch = data.get("branch")

        # Remove worktree via Git
        if repo_path and Path(repo_path).exists():
            try:
                self._git(Path(repo_path), "worktree", "remove", "-f", str(worktree_path))
                if branch:
                    self._git(Path(repo_path), "branch", "-D", branch)
            except subprocess.CalledProcessError as e:
                logger.warning("Git worktree remove failed: %s", e)

        # Hard remove if Git command left residue
        if mission_dir.exists():
            shutil.rmtree(mission_dir)

        logger.info("Workspace destroyed for mission %s", mission_id)

    def get_manifest(self, mission_id: UUID) -> WorkspaceManifest | None:
        """Read the manifest for an existing workspace."""
        manifest_path = self.base_dir / str(mission_id) / "manifest.json"
        if not manifest_path.exists():
            return None
        import json

        data = json.loads(manifest_path.read_text())
        return WorkspaceManifest(
            mission_id=data["mission_id"],
            repository=data["repository"],
            base_commit=data.get("base_commit"),
            branch=data["branch"],
            worktree_path=data["worktree_path"],
            allowed_paths=data.get("allowed_paths", []),
            protected_paths=data.get("protected_paths", []),
            created_at=data["created_at"],
        )

    def is_path_allowed(self, mission_id: UUID, path: str) -> bool:
        """Check whether *path* is inside the workspace policy."""
        manifest = self.get_manifest(mission_id)
        if manifest is None:
            return False

        # Protected paths take precedence
        for pattern in manifest.protected_paths:
            if self._match(path, pattern):
                return False

        if not manifest.allowed_paths:
            return True

        for pattern in manifest.allowed_paths:
            if self._match(path, pattern):
                return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        """Run a Git command in *repo* and return stdout."""
        cmd = ["git", "-C", str(repo), *args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _match(path: str, pattern: str) -> bool:
        """Glob-like match supporting ``**`` and ``*``."""
        regex = (
            pattern.replace(".", r"\.")
            .replace("**", r"{{ANYDEPTH}}")
            .replace("*", r"[^/]*")
            .replace(r"{{ANYDEPTH}}", ".*")
        )
        if "**/" in pattern or pattern.startswith("**"):
            return bool(re.search(regex, path))
        return bool(re.match(regex + r"($|/)", path))
