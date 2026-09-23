"""Pydantic domain models for the mission ledger.

Every unit of autonomous work exists as an explicit persisted object.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MissionStatus(str, Enum):
    """Canonical mission lifecycle states."""

    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    REVIEW = "review"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


class TaskStatus(str, Enum):
    """Canonical task lifecycle states."""

    PENDING = "pending"
    READY = "ready"
    LEASED = "leased"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Artifact(BaseModel):
    """Named output produced by a citizen during a task attempt."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    sha256: str | None = None
    size_bytes: int = 0
    mime_type: str = "application/octet-stream"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Checkpoint(BaseModel):
    """Persisted stage boundary within a task attempt.

    Checkpoints allow a fresh worker to resume from the last safe point.
    """

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: UUID = Field(default_factory=uuid4)
    attempt_id: UUID
    stage: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class TaskContext(BaseModel):
    """Bounded context packet delivered to a citizen when running a task.

    Contains only the information the citizen needs — not the whole repository.
    """

    model_config = ConfigDict(extra="forbid")

    mission_objective: str
    task_description: str
    repository: str
    base_commit: str | None = None
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    prior_attempts: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint: dict[str, Any] | None = None
    budget_remaining_usd: Decimal = Field(default=Decimal("10.00"))
    output_schema: dict[str, Any] | None = None


class CitizenUsage(BaseModel):
    """Provider-reported usage for one call, including its actual charge."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tokens_input: int = Field(ge=0, strict=True)
    tokens_output: int = Field(ge=0, strict=True)
    cost_usd: Decimal = Field(ge=0, allow_inf_nan=False)


class CitizenOutput(BaseModel):
    """Structured output returned by every citizen after running a task.

    The runtime validates this schema before accepting the stage.
    """

    model_config = ConfigDict(extra="forbid")

    status: str  # "completed" | "failed" | "needs_repair"
    summary: str
    usage: list[CitizenUsage] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    follow_up_tasks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Task(BaseModel):
    """A single unit of work within a mission, assigned to one citizen role.

    Tasks form a dependency graph. A task becomes ``READY`` only when all
    dependency tasks are ``COMPLETED``.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    citizen_role: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[UUID] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs_schema: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = 3
    current_attempt: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def can_start(self, completed_task_ids: set[UUID]) -> bool:
        """Return True if all dependency tasks are completed."""
        return all(dep in completed_task_ids for dep in self.dependencies)


class Mission(BaseModel):
    """Durable mission record — the canonical unit of autonomous work.

    A mission owns a task graph, acceptance criteria, and policy constraints.
    Citizens execute tasks; the mission persists until all tasks complete or
    it reaches a terminal state.
    """

    model_config = ConfigDict(extra="forbid")

    mission_id: UUID = Field(default_factory=uuid4)
    repository: str
    objective: str
    source_type: str = "manual"  # e.g. "github_issue", "manual", "daemon"
    source_reference: str | None = None
    risk_class: str = "medium"  # low | medium | high | critical
    status: MissionStatus = MissionStatus.PROPOSED
    priority: int = Field(ge=0, le=100, default=50)
    max_cost_usd: Decimal = Field(default=Decimal("10.00"))
    max_runtime_seconds: int = 3600
    max_changed_files: int = 15
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    merge_policy: str = "human_required"  # human_required | autonomous
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_terminal(self) -> bool:
        """Return True if the mission has reached a terminal state."""
        return self.status in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
            MissionStatus.QUARANTINED,
        }
