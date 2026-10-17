"""Persistent mission ledger backed by the shared DatabaseBackend.

Follows the same pattern as ``EvalStore`` and ``MissionStore``:
- SQLite by default (desktop mode)
- PostgreSQL support for team mode
- Schema initialised via ``executescript``
- JSON metadata columns for flexibility
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from animus_forge.missions.domain import (
    Artifact,
    Checkpoint,
    Mission,
    MissionStatus,
    Task,
    TaskStatus,
)
from animus_forge.missions.transitions import transition

if TYPE_CHECKING:
    from animus_forge.state.backends import DatabaseBackend

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    repository TEXT NOT NULL,
    objective TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_reference TEXT,
    risk_class TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'proposed',
    priority INTEGER DEFAULT 50,
    max_cost_usd TEXT DEFAULT '10.00',
    max_runtime_seconds INTEGER DEFAULT 3600,
    max_changed_files INTEGER DEFAULT 15,
    allowed_paths TEXT NOT NULL DEFAULT '[]',
    protected_paths TEXT NOT NULL DEFAULT '[]',
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    merge_policy TEXT NOT NULL DEFAULT 'human_required',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    citizen_role TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    dependencies TEXT NOT NULL DEFAULT '[]',
    inputs TEXT NOT NULL DEFAULT '{}',
    outputs_schema TEXT NOT NULL DEFAULT '{}',
    max_attempts INTEGER DEFAULT 3,
    current_attempt INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_priority ON missions(priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    inputs TEXT NOT NULL DEFAULT '{}',
    outputs TEXT NOT NULL DEFAULT '{}',
    artifacts TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_attempt ON checkpoints(task_id, attempt_id);
"""


class MissionLedger:
    """CRUD and state-transition logic for missions and tasks.

    Args:
        backend: Shared ``DatabaseBackend`` (SQLite or PostgreSQL).
    """

    def __init__(self, backend: DatabaseBackend):
        self._backend = backend
        self._init_schema()

    def _init_schema(self) -> None:
        with self._backend.transaction():
            self._backend.executescript(_SCHEMA)

    # =====================================================================
    # Mission CRUD
    # =====================================================================

    def create_mission(self, mission: Mission) -> None:
        """Insert a new mission record."""
        with self._backend.transaction():
            self._backend.execute(
                """
                INSERT INTO missions
                    (mission_id, repository, objective, source_type, source_reference,
                     risk_class, status, priority, max_cost_usd, max_runtime_seconds,
                     max_changed_files, allowed_paths, protected_paths,
                     acceptance_criteria, merge_policy, created_at, updated_at,
                     error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._mission_to_row(mission),
            )

    def get_mission(self, mission_id: UUID) -> Mission | None:
        """Fetch a mission by UUID."""
        row = self._backend.fetchone(
            "SELECT * FROM missions WHERE mission_id = ?",
            (str(mission_id),),
        )
        return self._parse_mission_row(row) if row else None

    def update_mission(self, mission: Mission) -> None:
        """Update mission fields (full replace)."""
        mission.updated_at = datetime.now()
        with self._backend.transaction():
            self._backend.execute(
                """
                UPDATE missions SET
                    repository = ?, objective = ?, source_type = ?, source_reference = ?,
                    risk_class = ?, status = ?, priority = ?, max_cost_usd = ?,
                    max_runtime_seconds = ?, max_changed_files = ?, allowed_paths = ?,
                    protected_paths = ?, acceptance_criteria = ?, merge_policy = ?,
                    created_at = ?, updated_at = ?, error = ?, metadata = ?
                WHERE mission_id = ?
                """,
                self._mission_to_row(mission)[1:] + (str(mission.mission_id),),
            )

    def transition_mission(
        self,
        mission_id: UUID,
        to_status: MissionStatus,
        error: str | None = None,
    ) -> Mission:
        """Atomically transition a mission to a new state.

        Validates the transition, updates the row, and returns the updated
        mission.

        Raises:
            TransitionError: If the transition is illegal.
            ValueError: If the mission does not exist.
        """
        mission = self.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")

        transition(mission.status, to_status, entity="mission")
        mission.status = to_status
        if error is not None:
            mission.error = error
        self.update_mission(mission)
        logger.info("Mission %s transitioned %s → %s", mission_id, mission.status, to_status)
        return mission

    def list_missions(
        self,
        status: MissionStatus | None = None,
        limit: int = 20,
    ) -> list[Mission]:
        """List missions, optionally filtered by status."""
        if status:
            rows = self._backend.fetchall(
                "SELECT * FROM missions WHERE status = ? ORDER BY priority DESC, updated_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            rows = self._backend.fetchall(
                "SELECT * FROM missions ORDER BY priority DESC, updated_at DESC LIMIT ?",
                (limit,),
            )
        return [self._parse_mission_row(r) for r in rows]

    # =====================================================================
    # Task CRUD
    # =====================================================================

    def create_task(self, task: Task) -> None:
        """Insert a new task record."""
        with self._backend.transaction():
            self._backend.execute(
                """
                INSERT INTO tasks
                    (task_id, mission_id, citizen_role, description, status,
                     dependencies, inputs, outputs_schema, max_attempts,
                     current_attempt, created_at, updated_at, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._task_to_row(task),
            )

    def get_task(self, task_id: UUID) -> Task | None:
        """Fetch a task by UUID."""
        row = self._backend.fetchone(
            "SELECT * FROM tasks WHERE task_id = ?",
            (str(task_id),),
        )
        return self._parse_task_row(row) if row else None

    def update_task(self, task: Task) -> None:
        """Update task fields (full replace)."""
        task.updated_at = datetime.now()
        with self._backend.transaction():
            self._backend.execute(
                """
                UPDATE tasks SET
                    mission_id = ?, citizen_role = ?, description = ?, status = ?,
                    dependencies = ?, inputs = ?, outputs_schema = ?, max_attempts = ?,
                    current_attempt = ?, created_at = ?, updated_at = ?, error = ?,
                    metadata = ?
                WHERE task_id = ?
                """,
                self._task_to_row(task)[1:] + (str(task.task_id),),
            )

    def transition_task(
        self,
        task_id: UUID,
        to_status: TaskStatus,
        error: str | None = None,
    ) -> Task:
        """Atomically transition a task to a new state.

        Raises:
            TransitionError: If the transition is illegal.
            ValueError: If the task does not exist.
        """
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        transition(task.status, to_status, entity="task")
        task.status = to_status
        if error is not None:
            task.error = error
        self.update_task(task)
        logger.info("Task %s transitioned %s → %s", task_id, task.status, to_status)
        return task

    def list_tasks_for_mission(self, mission_id: UUID) -> list[Task]:
        """Return all tasks belonging to a mission."""
        rows = self._backend.fetchall(
            "SELECT * FROM tasks WHERE mission_id = ? ORDER BY created_at",
            (str(mission_id),),
        )
        return [self._parse_task_row(r) for r in rows]

    def get_ready_tasks(self, mission_id: UUID) -> list[Task]:
        """Return tasks in READY state whose dependencies are all COMPLETED."""
        all_tasks = self.list_tasks_for_mission(mission_id)
        completed = {t.task_id for t in all_tasks if t.status == TaskStatus.COMPLETED}
        return [t for t in all_tasks if t.status == TaskStatus.READY and t.can_start(completed)]

    def count_active_missions(self) -> int:
        """Count missions currently in RUNNING state."""
        row = self._backend.fetchone(
            "SELECT COUNT(*) AS count FROM missions WHERE status = ?",
            (MissionStatus.RUNNING.value,),
        )
        return row["count"] if row else 0

    def increment_attempt(self, task_id: UUID) -> None:
        """Bump the attempt counter for a task."""
        with self._backend.transaction():
            self._backend.execute(
                "UPDATE tasks SET current_attempt = current_attempt + 1 WHERE task_id = ?",
                (str(task_id),),
            )

    def get_task_by_id(self, task_id: str) -> Task | None:
        """Fetch a task by string ID (convenience)."""
        return self.get_task(UUID(task_id))

    def list_tasks(self, mission_id: UUID | None = None) -> list[Task]:
        """Return tasks, optionally filtered by mission."""
        if mission_id:
            return self.list_tasks_for_mission(mission_id)
        rows = self._backend.fetchall("SELECT * FROM tasks ORDER BY created_at")
        return [self._parse_task_row(r) for r in rows]

    # =====================================================================
    # Checkpoint persistence
    # =====================================================================

    def save_checkpoint(
        self,
        task_id: UUID,
        attempt_id: UUID,
        stage: str,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist a checkpoint for a task attempt."""
        from animus_forge.missions.domain import Checkpoint

        checkpoint = Checkpoint(
            attempt_id=attempt_id,
            stage=stage,
            inputs=inputs or {},
            outputs=outputs or {},
            artifacts=[Artifact(**a) for a in (artifacts or [])],
        )
        with self._backend.transaction():
            self._backend.execute(
                """
                INSERT INTO checkpoints
                    (checkpoint_id, task_id, attempt_id, stage, inputs, outputs, artifacts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(checkpoint.checkpoint_id),
                    str(task_id),
                    str(attempt_id),
                    checkpoint.stage,
                    json.dumps(checkpoint.inputs),
                    json.dumps(checkpoint.outputs),
                    json.dumps([a.model_dump(mode="json") for a in checkpoint.artifacts]),
                    checkpoint.created_at.isoformat(),
                ),
            )

    def get_latest_checkpoint(
        self, task_id: UUID, attempt_id: UUID | None = None
    ) -> Checkpoint | None:
        """Fetch the most recent checkpoint for a task (optionally filtered by attempt)."""
        if attempt_id:
            row = self._backend.fetchone(
                """
                SELECT * FROM checkpoints
                WHERE task_id = ? AND attempt_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(task_id), str(attempt_id)),
            )
        else:
            row = self._backend.fetchone(
                """
                SELECT * FROM checkpoints
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(task_id),),
            )
        return self._parse_checkpoint_row(row) if row else None

    def list_checkpoints(self, task_id: UUID) -> list[Checkpoint]:
        """Return all checkpoints for a task, oldest first."""
        rows = self._backend.fetchall(
            """
            SELECT * FROM checkpoints
            WHERE task_id = ?
            ORDER BY created_at
            """,
            (str(task_id),),
        )
        return [self._parse_checkpoint_row(r) for r in rows]

    @staticmethod
    def _parse_checkpoint_row(row: dict) -> Checkpoint:
        from animus_forge.missions.domain import Checkpoint

        return Checkpoint(
            checkpoint_id=UUID(row["checkpoint_id"]),
            attempt_id=UUID(row["attempt_id"]),
            stage=row["stage"],
            inputs=json.loads(row["inputs"]),
            outputs=json.loads(row["outputs"]),
            artifacts=[Artifact(**a) for a in json.loads(row["artifacts"])],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # =====================================================================
    # Serialization helpers
    # =====================================================================

    @staticmethod
    def _mission_to_row(mission: Mission) -> tuple:

        return (
            str(mission.mission_id),
            mission.repository,
            mission.objective,
            mission.source_type,
            mission.source_reference,
            mission.risk_class,
            mission.status.value,
            mission.priority,
            str(mission.max_cost_usd),
            mission.max_runtime_seconds,
            mission.max_changed_files,
            json.dumps(mission.allowed_paths),
            json.dumps(mission.protected_paths),
            json.dumps(mission.acceptance_criteria),
            mission.merge_policy,
            mission.created_at.isoformat(),
            mission.updated_at.isoformat(),
            mission.error,
            json.dumps(mission.metadata),
        )

    @staticmethod
    def _parse_mission_row(row: dict) -> Mission:
        return Mission(
            mission_id=UUID(row["mission_id"]),
            repository=row["repository"],
            objective=row["objective"],
            source_type=row["source_type"],
            source_reference=row.get("source_reference"),
            risk_class=row["risk_class"],
            status=MissionStatus(row["status"]),
            priority=row["priority"],
            max_cost_usd=Decimal(row["max_cost_usd"]),
            max_runtime_seconds=row["max_runtime_seconds"],
            max_changed_files=row["max_changed_files"],
            allowed_paths=json.loads(row["allowed_paths"]),
            protected_paths=json.loads(row["protected_paths"]),
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            merge_policy=row["merge_policy"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error=row.get("error"),
            metadata=json.loads(row.get("metadata", "{}")),
        )

    @staticmethod
    def _task_to_row(task: Task) -> tuple:
        return (
            str(task.task_id),
            str(task.mission_id),
            task.citizen_role,
            task.description,
            task.status.value,
            json.dumps([str(d) for d in task.dependencies]),
            json.dumps(task.inputs),
            json.dumps(task.outputs_schema),
            task.max_attempts,
            task.current_attempt,
            task.created_at.isoformat(),
            task.updated_at.isoformat(),
            task.error,
            json.dumps(task.metadata),
        )

    @staticmethod
    def _parse_task_row(row: dict) -> Task:
        deps_raw = json.loads(row["dependencies"])
        dependencies = [UUID(d) for d in deps_raw] if deps_raw else []

        return Task(
            task_id=UUID(row["task_id"]),
            mission_id=UUID(row["mission_id"]),
            citizen_role=row["citizen_role"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            dependencies=dependencies,
            inputs=json.loads(row["inputs"]),
            outputs_schema=json.loads(row["outputs_schema"]),
            max_attempts=row["max_attempts"],
            current_attempt=row["current_attempt"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error=row.get("error"),
            metadata=json.loads(row.get("metadata", "{}")),
        )
