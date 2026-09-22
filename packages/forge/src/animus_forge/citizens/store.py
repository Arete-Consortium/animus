"""Persistent store for citizen mission records."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from animus_forge.citizens.mission import MissionConfig, MissionRecord, MissionState

if TYPE_CHECKING:
    from animus_forge.state.backends import DatabaseBackend

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS citizen_missions (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    eval_suite TEXT NOT NULL,
    workflow_template TEXT NOT NULL,
    max_iterations INTEGER DEFAULT 3,
    min_pass_rate REAL DEFAULT 0.9,
    max_variance REAL DEFAULT 0.1,
    state TEXT NOT NULL DEFAULT 'pending',
    current_iteration INTEGER DEFAULT 0,
    last_eval_run_id TEXT,
    last_pass_rate REAL DEFAULT 0.0,
    last_score_variance REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_missions_state ON citizen_missions(state);
CREATE INDEX IF NOT EXISTS idx_missions_updated ON citizen_missions(updated_at DESC);
"""


class MissionStore:
    """CRUD for mission records backed by a DatabaseBackend."""

    def __init__(self, backend: DatabaseBackend):
        self._backend = backend
        self._init_schema()

    def _init_schema(self) -> None:
        with self._backend.transaction():
            self._backend.executescript(_SCHEMA)

    def create(self, mission: MissionRecord) -> None:
        config = mission.config
        meta_json = json.dumps(mission.metadata) if mission.metadata else "{}"
        with self._backend.transaction():
            self._backend.execute(
                """
                INSERT INTO citizen_missions
                    (id, objective, eval_suite, workflow_template,
                     max_iterations, min_pass_rate, max_variance,
                     state, current_iteration, last_eval_run_id,
                     last_pass_rate, last_score_variance,
                     created_at, updated_at, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission.id,
                    config.objective,
                    config.eval_suite,
                    config.workflow_template,
                    config.max_iterations,
                    config.min_pass_rate,
                    config.max_variance,
                    mission.state.value,
                    mission.current_iteration,
                    mission.last_eval_run_id,
                    mission.last_pass_rate,
                    mission.last_score_variance,
                    mission.created_at.isoformat(),
                    mission.updated_at.isoformat(),
                    mission.error,
                    meta_json,
                ),
            )

    def update(self, mission: MissionRecord) -> None:
        mission.updated_at = datetime.now()
        meta_json = json.dumps(mission.metadata) if mission.metadata else "{}"
        with self._backend.transaction():
            self._backend.execute(
                """
                UPDATE citizen_missions
                SET state = ?, current_iteration = ?, last_eval_run_id = ?,
                    last_pass_rate = ?, last_score_variance = ?,
                    updated_at = ?, error = ?, metadata = ?
                WHERE id = ?
                """,
                (
                    mission.state.value,
                    mission.current_iteration,
                    mission.last_eval_run_id,
                    mission.last_pass_rate,
                    mission.last_score_variance,
                    mission.updated_at.isoformat(),
                    mission.error,
                    meta_json,
                    mission.id,
                ),
            )

    def get(self, mission_id: str) -> MissionRecord | None:
        row = self._backend.fetchone("SELECT * FROM citizen_missions WHERE id = ?", (mission_id,))
        if not row:
            return None
        return self._parse_row(row)

    def list_by_state(self, state: MissionState, limit: int = 20) -> list[MissionRecord]:
        rows = self._backend.fetchall(
            "SELECT * FROM citizen_missions WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
            (state.value, limit),
        )
        return [self._parse_row(r) for r in rows]

    def list_all(self, limit: int = 20) -> list[MissionRecord]:
        rows = self._backend.fetchall(
            "SELECT * FROM citizen_missions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [self._parse_row(r) for r in rows]

    def _parse_row(self, row: dict) -> MissionRecord:
        config = MissionConfig(
            objective=row["objective"],
            eval_suite=row["eval_suite"],
            workflow_template=row["workflow_template"],
            max_iterations=row["max_iterations"],
            min_pass_rate=row["min_pass_rate"],
            max_variance=row["max_variance"],
        )
        metadata: dict[str, Any] = {}
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        return MissionRecord(
            id=row["id"],
            config=config,
            state=MissionState(row["state"]),
            current_iteration=row["current_iteration"],
            last_eval_run_id=row.get("last_eval_run_id"),
            last_pass_rate=row.get("last_pass_rate", 0.0),
            last_score_variance=row.get("last_score_variance", 0.0),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error=row.get("error"),
            metadata=metadata,
        )
