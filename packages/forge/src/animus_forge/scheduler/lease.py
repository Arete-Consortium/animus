"""Lease manager — atomic task claim with heartbeats, expiry recovery, and history.

Every task assigned to a citizen gets a lease.  The lease has a TTL; if the
worker dies or hangs, the lease expires and the task returns to READY for
another worker to claim.

The schema separates mutable current state from append-only history:

- ``task_lease_current`` holds zero or one row per task, only while a lease is
  active.
- ``task_lease_history`` records every acquire, release, expiry, and heartbeat
  event.
- ``task_attempts`` records each dispatch attempt, including the lease and
  generation used to fence stale worker results.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from animus_forge.state.backends import DatabaseBackend

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_lease_current (
    task_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    heartbeat_at TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'released')),
    attempt_id TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_lease_current_expires ON task_lease_current(expires_at);
CREATE INDEX IF NOT EXISTS idx_task_lease_current_mission ON task_lease_current(mission_id);

CREATE TABLE IF NOT EXISTS task_lease_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lease_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    heartbeat_at TEXT,
    status TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    outcome TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lease_history_task ON task_lease_history(task_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_lease_history_lease ON task_lease_history(lease_id);

CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'completed', 'failed', 'cancelled')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    cost_usd TEXT DEFAULT '0.00',
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attempts_task ON task_attempts(task_id, started_at DESC);
"""


class LeaseStatus(StrEnum):
    """Lease lifecycle states."""

    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


class LeaseAcquireError(Exception):
    """Raised when a lease cannot be acquired for a known reason."""

    def __init__(self, reason: str, task_id: str):
        super().__init__(f"Lease acquire failed for {task_id}: {reason}")
        self.reason = reason
        self.task_id = task_id


class Lease:
    """Runtime representation of a task lease."""

    def __init__(
        self,
        lease_id: str,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        worker_id: str,
        generation: int,
        attempt_id: str,
        acquired_at: datetime,
        expires_at: datetime,
        status: LeaseStatus = LeaseStatus.ACTIVE,
        heartbeat_at: datetime | None = None,
        outcome: str | None = None,
    ):
        self.lease_id = lease_id
        self.task_id = task_id
        self.mission_id = mission_id
        self.citizen_role = citizen_role
        self.worker_id = worker_id
        self.generation = generation
        self.attempt_id = attempt_id
        self.acquired_at = acquired_at
        self.expires_at = expires_at
        self.status = status
        self.heartbeat_at = heartbeat_at
        self.outcome = outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "citizen_role": self.citizen_role,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "attempt_id": self.attempt_id,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None,
            "outcome": self.outcome,
        }


class LeaseManager:
    """Atomic lease operations backed by DatabaseBackend.

    Args:
        backend: Shared ``DatabaseBackend``.
        default_ttl_seconds: Default lease TTL if not overridden per-acquire.
    """

    def __init__(self, backend: DatabaseBackend, default_ttl_seconds: int = 300):
        self._backend = backend
        self.default_ttl_seconds = default_ttl_seconds
        self._init_schema()

    def _init_schema(self) -> None:
        with self._backend.transaction():
            self._backend.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(
        self,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        worker_id: str,
        ttl_seconds: int | None = None,
        attempt_id: str | None = None,
    ) -> Lease:
        """Atomically acquire a lease for *task_id*.

        Raises:
            LeaseAcquireError: If the task already has an active lease or is
                otherwise ineligible.

        Returns:
            The new ``Lease``.
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl)
        lease_id = str(uuid.uuid4())
        attempt_id = attempt_id or str(uuid.uuid4())

        with self._backend.transaction():
            # Re-check inside the transaction so callers can compose this into
            # a larger atomic dispatch transaction.
            existing = self._backend.fetchone(
                "SELECT lease_id FROM task_lease_current WHERE task_id = ?",
                (task_id,),
            )
            if existing is not None:
                raise LeaseAcquireError("already_leased", task_id)

            generation = self._next_generation(task_id)

            self._backend.execute(
                """
                INSERT INTO task_lease_current
                    (task_id, lease_id, mission_id, citizen_role, worker_id,
                     generation, acquired_at, expires_at, status, heartbeat_at, attempt_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    lease_id,
                    mission_id,
                    citizen_role,
                    worker_id,
                    generation,
                    now.isoformat(),
                    expires.isoformat(),
                    LeaseStatus.ACTIVE,
                    now.isoformat(),
                    attempt_id,
                ),
            )
            self._append_history(
                lease_id=lease_id,
                task_id=task_id,
                mission_id=mission_id,
                citizen_role=citizen_role,
                worker_id=worker_id,
                generation=generation,
                acquired_at=now,
                expires_at=expires,
                heartbeat_at=now,
                status=LeaseStatus.ACTIVE,
                attempt_id=attempt_id,
                outcome=None,
            )

        logger.info(
            "Lease %s (gen %d) acquired for task %s by worker %s (expires %s)",
            lease_id,
            generation,
            task_id,
            worker_id,
            expires,
        )
        return Lease(
            lease_id=lease_id,
            task_id=task_id,
            mission_id=mission_id,
            citizen_role=citizen_role,
            worker_id=worker_id,
            generation=generation,
            attempt_id=attempt_id,
            acquired_at=now,
            expires_at=expires,
            status=LeaseStatus.ACTIVE,
            heartbeat_at=now,
        )

    def renew(self, lease_id: str, ttl_seconds: int | None = None) -> Lease | None:
        """Renew an existing active lease (heartbeat).

        Returns:
            The updated ``Lease``, or ``None`` if the lease is gone or no longer active.
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl)

        with self._backend.transaction():
            row = self._backend.fetchone(
                "SELECT * FROM task_lease_current WHERE lease_id = ? AND status = ?",
                (lease_id, LeaseStatus.ACTIVE),
            )
            if not row:
                return None

            self._backend.execute(
                """
                UPDATE task_lease_current
                SET expires_at = ?, heartbeat_at = ?
                WHERE lease_id = ?
                """,
                (expires.isoformat(), now.isoformat(), lease_id),
            )

            self._append_history(
                lease_id=lease_id,
                task_id=row["task_id"],
                mission_id=row["mission_id"],
                citizen_role=row["citizen_role"],
                worker_id=row["worker_id"],
                generation=row["generation"],
                acquired_at=datetime.fromisoformat(row["acquired_at"]),
                expires_at=expires,
                heartbeat_at=now,
                status=LeaseStatus.ACTIVE,
                attempt_id=row["attempt_id"],
                outcome=None,
            )

        lease = self._parse_row(row)
        lease.expires_at = expires
        lease.heartbeat_at = now
        logger.debug("Lease %s renewed, expires %s", lease_id, expires)
        return lease

    def release(self, lease_id: str, outcome: str = "completed") -> Lease | None:
        """Release a lease (task completed or failed).

        Returns:
            The released ``Lease``, or ``None`` if not currently active.
        """
        with self._backend.transaction():
            row = self._backend.fetchone(
                "SELECT * FROM task_lease_current WHERE lease_id = ?",
                (lease_id,),
            )
            if not row:
                return None

            self._backend.execute(
                "DELETE FROM task_lease_current WHERE lease_id = ?",
                (lease_id,),
            )
            self._append_history(
                lease_id=lease_id,
                task_id=row["task_id"],
                mission_id=row["mission_id"],
                citizen_role=row["citizen_role"],
                worker_id=row["worker_id"],
                generation=row["generation"],
                acquired_at=datetime.fromisoformat(row["acquired_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                heartbeat_at=datetime.fromisoformat(row["heartbeat_at"])
                if row.get("heartbeat_at")
                else None,
                status=LeaseStatus.RELEASED,
                attempt_id=row["attempt_id"],
                outcome=outcome,
            )

        lease = self._parse_row(row)
        lease.status = LeaseStatus.RELEASED
        lease.outcome = outcome
        logger.info("Lease %s released with outcome %s", lease_id, outcome)
        return lease

    def recover_expired(self, as_of: datetime | None = None) -> list[str]:
        """Find expired leases, mark them EXPIRED, and remove current rows.

        Returns:
            List of ``task_id`` strings that were recovered.
        """
        now = as_of or datetime.now(UTC)
        with self._backend.transaction():
            rows = self._backend.fetchall(
                "SELECT * FROM task_lease_current WHERE status = ? AND expires_at < ?",
                (LeaseStatus.ACTIVE, now.isoformat()),
            )
            recovered: list[str] = []
            for r in rows:
                recovered.append(r["task_id"])
                self._backend.execute(
                    "DELETE FROM task_lease_current WHERE lease_id = ?",
                    (r["lease_id"],),
                )
                self._append_history(
                    lease_id=r["lease_id"],
                    task_id=r["task_id"],
                    mission_id=r["mission_id"],
                    citizen_role=r["citizen_role"],
                    worker_id=r["worker_id"],
                    generation=r["generation"],
                    acquired_at=datetime.fromisoformat(r["acquired_at"]),
                    expires_at=datetime.fromisoformat(r["expires_at"]),
                    heartbeat_at=datetime.fromisoformat(r["heartbeat_at"])
                    if r.get("heartbeat_at")
                    else None,
                    status=LeaseStatus.EXPIRED,
                    attempt_id=r["attempt_id"],
                    outcome=None,
                )

        if recovered:
            logger.info("Recovered %d expired lease(s): %s", len(recovered), recovered)
        return recovered

    def get_active_leases(self) -> list[Lease]:
        """Return all currently active leases."""
        rows = self._backend.fetchall(
            "SELECT * FROM task_lease_current WHERE status = ? ORDER BY acquired_at",
            (LeaseStatus.ACTIVE,),
        )
        return [self._parse_row(r) for r in rows]

    def get_lease_for_task(self, task_id: str) -> Lease | None:
        """Fetch the active current lease for a task, if any."""
        row = self._backend.fetchone(
            "SELECT * FROM task_lease_current WHERE task_id = ?",
            (task_id,),
        )
        return self._parse_row(row) if row else None

    def get_lease(self, lease_id: str) -> Lease | None:
        """Fetch a lease by ID from the current table."""
        row = self._backend.fetchone(
            "SELECT * FROM task_lease_current WHERE lease_id = ?",
            (lease_id,),
        )
        return self._parse_row(row) if row else None

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        """Fetch an attempt record by ID."""
        row = self._backend.fetchone(
            "SELECT * FROM task_attempts WHERE attempt_id = ?",
            (attempt_id,),
        )
        return dict(row) if row else None

    def history_for_task(self, task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return lease history rows for a task, newest first."""
        rows = self._backend.fetchall(
            """
            SELECT * FROM task_lease_history
            WHERE task_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (task_id, limit),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_generation(self, task_id: str) -> int:
        row = self._backend.fetchone(
            "SELECT COALESCE(MAX(generation), 0) + 1 AS next_gen FROM task_lease_history WHERE task_id = ?",
            (task_id,),
        )
        return row["next_gen"] if row else 1

    def _append_history(
        self,
        *,
        lease_id: str,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        worker_id: str,
        generation: int,
        acquired_at: datetime,
        expires_at: datetime,
        heartbeat_at: datetime | None,
        status: LeaseStatus,
        attempt_id: str,
        outcome: str | None,
    ) -> None:
        recorded_at = datetime.now(UTC)
        self._backend.execute(
            """
            INSERT INTO task_lease_history
                (lease_id, task_id, mission_id, citizen_role, worker_id, generation,
                 acquired_at, expires_at, heartbeat_at, status, attempt_id, outcome, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease_id,
                task_id,
                mission_id,
                citizen_role,
                worker_id,
                generation,
                acquired_at.isoformat(),
                expires_at.isoformat(),
                heartbeat_at.isoformat() if heartbeat_at else None,
                status,
                attempt_id,
                outcome,
                recorded_at.isoformat(),
            ),
        )

    @staticmethod
    def _parse_row(row: dict) -> Lease:
        return Lease(
            lease_id=row["lease_id"],
            task_id=row["task_id"],
            mission_id=row["mission_id"],
            citizen_role=row["citizen_role"],
            worker_id=row["worker_id"],
            generation=row["generation"],
            attempt_id=row["attempt_id"],
            acquired_at=datetime.fromisoformat(row["acquired_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            status=LeaseStatus(row["status"]),
            heartbeat_at=datetime.fromisoformat(row["heartbeat_at"])
            if row.get("heartbeat_at")
            else None,
            outcome=row.get("outcome"),
        )
