"""Atomic dispatch — one transaction for task lease, attempt, and transition.

Dispatching a task is the most critical multi-object mutation in the runtime.
This module wraps the following into a single durable transaction:

1. Re-read the task and confirm it is eligible (READY / LEASED).
2. Confirm the mission is running and budgets allow the estimated cost.
3. Create a new ``task_attempts`` row.
4. Acquire a lease.
5. Transition the task from READY → LEASED → RUNNING.

If any step fails, the entire transaction is rolled back and the task remains
eligible for another scheduler tick.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from animus_forge.missions.domain import MissionStatus, Task, TaskStatus
from animus_forge.missions.store import MissionLedger
from animus_forge.missions.transitions import TransitionError
from animus_forge.scheduler.cost_enforcer import CostEnforcer
from animus_forge.scheduler.lease import Lease, LeaseManager, LeaseStatus

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Outcome of a single atomic dispatch attempt."""

    ok: bool
    lease: Lease | None = None
    attempt_id: str | None = None
    error: str | None = None


class AtomicDispatcher:
    """Dispatch a task inside one database transaction."""

    def __init__(
        self,
        ledger: MissionLedger,
        lease_manager: LeaseManager,
        cost_enforcer: CostEnforcer,
        metrics: Any | None = None,
    ):
        self.ledger = ledger
        self.lease = lease_manager
        self.cost = cost_enforcer
        self.metrics = metrics

    def dispatch(
        self,
        task: Task,
        worker_id: str,
        *,
        default_ttl_seconds: int,
        default_mission_cap_usd: Decimal,
        estimated_cost_usd: Decimal = Decimal("0.10"),
    ) -> DispatchResult:
        """Attempt to atomically lease and start *task*.

        Returns:
            ``DispatchResult`` with ``ok=True`` and a populated lease on success,
            or ``ok=False`` with a specific ``error`` string on failure.
        """
        try:
            with self._backend.transaction():
                # 1. Re-read task and mission inside the transaction.
                fresh_task = self.ledger.get_task(task.task_id)
                if fresh_task is None:
                    return DispatchResult(ok=False, error="task_not_found")
                if fresh_task.status != TaskStatus.READY:
                    return DispatchResult(ok=False, error="task_not_eligible")

                mission = self.ledger.get_mission(task.mission_id)
                if mission is None:
                    return DispatchResult(ok=False, error="mission_not_found")
                if mission.status != MissionStatus.RUNNING:
                    return DispatchResult(ok=False, error="mission_not_running")

                # 2. Budget gate.
                ok, reason = self.cost.can_start_task(
                    str(task.mission_id),
                    estimated_cost=estimated_cost_usd,
                    mission_cap=default_mission_cap_usd,
                )
                if not ok:
                    return DispatchResult(ok=False, error=f"budget:{reason}")

                # 3. Create attempt record.
                attempt_id = str(uuid.uuid4())
                now = datetime.now(UTC)

                # 4. Acquire lease inline (single transaction with the rest).
                existing = self._backend.fetchone(
                    "SELECT lease_id FROM task_lease_current WHERE task_id = ?",
                    (str(task.task_id),),
                )
                if existing is not None:
                    return DispatchResult(ok=False, error="already_leased")

                generation = self._next_generation(str(task.task_id))
                lease_id = str(uuid.uuid4())
                expires = now + timedelta(seconds=default_ttl_seconds)

                self._backend.execute(
                    """
                    INSERT INTO task_lease_current
                        (task_id, lease_id, mission_id, citizen_role, worker_id,
                         generation, acquired_at, expires_at, status, heartbeat_at, attempt_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(task.task_id),
                        lease_id,
                        str(task.mission_id),
                        task.citizen_role,
                        worker_id,
                        generation,
                        now.isoformat(),
                        expires.isoformat(),
                        LeaseStatus.ACTIVE,
                        now.isoformat(),
                        attempt_id,
                    ),
                )
                self._append_lease_history(
                    lease_id=lease_id,
                    task_id=str(task.task_id),
                    mission_id=str(task.mission_id),
                    citizen_role=task.citizen_role,
                    worker_id=worker_id,
                    generation=generation,
                    acquired_at=now,
                    expires_at=expires,
                    heartbeat_at=now,
                    status=LeaseStatus.ACTIVE,
                    attempt_id=attempt_id,
                    outcome=None,
                )

                # 5. Record attempt and transition task LEASED → RUNNING.
                self._backend.execute(
                    """
                    INSERT INTO task_attempts
                        (attempt_id, task_id, mission_id, citizen_role, lease_id,
                         generation, status, started_at, cost_usd)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        str(task.task_id),
                        str(task.mission_id),
                        task.citizen_role,
                        lease_id,
                        generation,
                        "started",
                        now.isoformat(),
                        "0.00",
                    ),
                )

                try:
                    self.ledger.transition_task(
                        task_id=task.task_id,
                        to_status=TaskStatus.LEASED,
                    )
                    self.ledger.transition_task(
                        task_id=task.task_id,
                        to_status=TaskStatus.RUNNING,
                    )
                except TransitionError as exc:
                    return DispatchResult(
                        ok=False, error=f"transition:{exc.current}->{exc.requested}"
                    )

            logger.info(
                "Atomically dispatched task %s attempt %s lease %s (gen %d)",
                task.task_id,
                attempt_id,
                lease_id,
                generation,
            )
            lease = Lease(
                lease_id=lease_id,
                task_id=str(task.task_id),
                mission_id=str(task.mission_id),
                citizen_role=task.citizen_role,
                worker_id=worker_id,
                generation=generation,
                attempt_id=attempt_id,
                acquired_at=now,
                expires_at=expires,
                status=LeaseStatus.ACTIVE,
                heartbeat_at=now,
            )
            return DispatchResult(ok=True, lease=lease, attempt_id=attempt_id)

        except Exception as exc:
            logger.exception("Atomic dispatch failed for task %s", task.task_id)
            return DispatchResult(ok=False, error=f"exception:{type(exc).__name__}:{exc}")

    def rollback_dispatch(self, lease: Lease, *, outcome: str = "rollback") -> None:
        """Release a lease and revert the task to READY after a failed pool submit.

        This is a best-effort cleanup; it runs inside its own transaction.
        """
        try:
            with self._backend.transaction():
                self.lease.release(lease.lease_id, outcome=outcome)
                task = self.ledger.get_task_by_id(lease.task_id)
                if task and task.status == TaskStatus.RUNNING:
                    self.ledger.transition_task(
                        task_id=task.task_id,
                        to_status=TaskStatus.READY,
                    )
                self._backend.execute(
                    "UPDATE task_attempts SET status = ? WHERE attempt_id = ?",
                    ("cancelled", lease.attempt_id),
                )
            logger.warning(
                "Rolled back dispatch for task %s lease %s attempt %s",
                lease.task_id,
                lease.lease_id,
                lease.attempt_id,
            )
        except Exception:
            logger.exception(
                "Rollback dispatch failed for task %s lease %s",
                lease.task_id,
                lease.lease_id,
            )

    @property
    def _backend(self):
        """Return the shared database backend."""
        return self.ledger._backend

    def _next_generation(self, task_id: str) -> int:
        row = self._backend.fetchone(
            "SELECT COALESCE(MAX(generation), 0) + 1 AS next_gen FROM task_lease_history WHERE task_id = ?",
            (task_id,),
        )
        return row["next_gen"] if row else 1

    def _append_lease_history(
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
