"""Resume token store for approval gates in workflow execution.

When a workflow hits an approval step, execution halts and a compact
token is returned. External callers (e.g. Animus) hold the token and
resume later with approve/reject.

Follows the TaskStore pattern — wraps a shared DatabaseBackend singleton.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta

from animus_forge.state.backends import DatabaseBackend

logger = logging.getLogger(__name__)

_approval_store: ResumeTokenStore | None = None


class ResumeTokenStore:
    """SQLite-backed resume token storage for approval gates.

    Provides CRUD + expiry for approval tokens. Uses the shared
    DatabaseBackend via get_database().
    """

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def create_token(
        self,
        *,
        execution_id: str,
        workflow_id: str,
        step_id: str,
        next_step_id: str,
        prompt: str = "",
        preview: dict | None = None,
        context: dict | None = None,
        timeout_hours: int = 24,
    ) -> str:
        """Create and persist a new approval token.

        Args:
            execution_id: ID of the paused execution
            workflow_id: ID of the workflow being executed
            step_id: ID of the approval step that triggered the halt
            next_step_id: ID of the step to resume from after approval
            prompt: Human-readable approval prompt
            preview: Outputs from referenced steps to show the approver
            context: Full execution context at halt time
            timeout_hours: Hours until the token expires

        Returns:
            16-character hex token string
        """
        token = secrets.token_hex(8)
        timeout_at = datetime.now() + timedelta(hours=timeout_hours)

        preview_json = json.dumps(preview) if preview else None
        context_json = json.dumps(context, default=str) if context else None

        with self.backend.transaction():
            self.backend.execute(
                """
                INSERT INTO approval_tokens
                    (token, execution_id, workflow_id, step_id, next_step_id,
                     status, prompt, preview, context, timeout_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    token,
                    execution_id,
                    workflow_id,
                    step_id,
                    next_step_id,
                    prompt,
                    preview_json,
                    context_json,
                    timeout_at.isoformat(),
                ),
            )
        return token

    def get_by_token(self, token: str) -> dict | None:
        """Load token data. Returns None if expired or missing."""
        row = self.backend.fetchone(
            "SELECT * FROM approval_tokens WHERE token = ?",
            (token,),
        )
        if not row:
            return None

        result = dict(row)

        # Lazy expiry check
        if result.get("timeout_at"):
            try:
                timeout = datetime.fromisoformat(result["timeout_at"])
                if timeout < datetime.now():
                    self._expire_token(token)
                    return None
            except (ValueError, TypeError):
                pass  # Invalid date format — treat as no timeout

        # Parse JSON fields
        for field in ("preview", "context"):
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep raw string if not valid JSON

        return result

    def approve(self, token: str, approved_by: str = "api") -> bool:
        """Mark a token as approved.

        Returns True if the token existed and was pending.
        """
        with self.backend.transaction():
            cursor = self.backend.execute(
                """
                UPDATE approval_tokens
                SET status = 'approved', decided_at = ?, decided_by = ?
                WHERE token = ? AND status = 'pending'
                """,
                (datetime.now().isoformat(), approved_by, token),
            )
        return cursor.rowcount > 0

    def reject(self, token: str, rejected_by: str = "api") -> bool:
        """Mark a token as rejected.

        Returns True if the token existed and was pending.
        """
        with self.backend.transaction():
            cursor = self.backend.execute(
                """
                UPDATE approval_tokens
                SET status = 'rejected', decided_at = ?, decided_by = ?
                WHERE token = ? AND status = 'pending'
                """,
                (datetime.now().isoformat(), rejected_by, token),
            )
        return cursor.rowcount > 0

    def expire_stale(self) -> int:
        """Bulk-expire tokens past their timeout. Returns count expired."""
        with self.backend.transaction():
            cursor = self.backend.execute(
                """
                UPDATE approval_tokens
                SET status = 'expired'
                WHERE status = 'pending' AND timeout_at < ?
                """,
                (datetime.now().isoformat(),),
            )
        return cursor.rowcount

    def get_by_execution(self, execution_id: str) -> list[dict]:
        """Get all tokens for an execution."""
        rows = self.backend.fetchall(
            """
            SELECT * FROM approval_tokens
            WHERE execution_id = ?
            ORDER BY created_at DESC
            """,
            (execution_id,),
        )
        results = []
        for row in rows:
            result = dict(row)
            for field in ("preview", "context"):
                if result.get(field):
                    try:
                        result[field] = json.loads(result[field])
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep raw string if not valid JSON
            results.append(result)
        return results

    def _expire_token(self, token: str) -> None:
        """Mark a single token as expired."""
        with self.backend.transaction():
            self.backend.execute(
                "UPDATE approval_tokens SET status = 'expired' WHERE token = ?",
                (token,),
            )


def get_approval_store() -> ResumeTokenStore:
    """Get or create the global ResumeTokenStore singleton."""
    global _approval_store
    if _approval_store is None:
        from animus_forge.state.database import get_database

        _approval_store = ResumeTokenStore(get_database())
    return _approval_store


def reset_approval_store() -> None:
    """Reset the global ResumeTokenStore singleton (for testing)."""
    global _approval_store
    _approval_store = None
