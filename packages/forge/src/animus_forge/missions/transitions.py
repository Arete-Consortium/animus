"""State-machine transitions for missions and tasks.

All state changes pass through deterministic transition tables.  Arbitrary
status mutation is forbidden — every transition is validated before it is
applied.
"""

from __future__ import annotations

from animus_forge.missions.domain import MissionStatus, TaskStatus


class TransitionError(ValueError):
    """Raised when an illegal state transition is requested."""

    def __init__(self, entity: str, current: str, requested: str):
        super().__init__(f"Illegal {entity} transition: {current} → {requested}")
        self.entity = entity
        self.current = current
        self.requested = requested


# ---------------------------------------------------------------------------
# Mission transitions
# ---------------------------------------------------------------------------

ALLOWED_MISSION_TRANSITIONS: dict[MissionStatus, set[MissionStatus]] = {
    MissionStatus.PROPOSED: {
        MissionStatus.READY,
        MissionStatus.CANCELLED,
    },
    MissionStatus.READY: {
        MissionStatus.RUNNING,
        MissionStatus.CANCELLED,
    },
    MissionStatus.RUNNING: {
        MissionStatus.WAITING,
        MissionStatus.REVIEW,
        MissionStatus.FAILED,
        MissionStatus.QUARANTINED,
    },
    MissionStatus.WAITING: {
        MissionStatus.RUNNING,
        MissionStatus.CANCELLED,
    },
    MissionStatus.REVIEW: {
        MissionStatus.RUNNING,  # repair loop
        MissionStatus.APPROVAL_REQUIRED,
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
    },
    MissionStatus.APPROVAL_REQUIRED: {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    },
    MissionStatus.COMPLETED: set(),  # terminal
    MissionStatus.FAILED: set(),  # terminal
    MissionStatus.CANCELLED: set(),  # terminal
    MissionStatus.QUARANTINED: set(),  # terminal
}

# ---------------------------------------------------------------------------
# Task transitions
# ---------------------------------------------------------------------------

ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.READY,
        TaskStatus.CANCELLED,
    },
    TaskStatus.READY: {
        TaskStatus.LEASED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.LEASED: {
        TaskStatus.RUNNING,
        TaskStatus.READY,  # lease expired / worker died
        TaskStatus.FAILED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.WAITING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.BLOCKED,
        TaskStatus.READY,  # retry after failure
    },
    TaskStatus.WAITING: {
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.READY,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.FAILED: set(),  # terminal
    TaskStatus.CANCELLED: set(),  # terminal
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS = {
    "mission": ALLOWED_MISSION_TRANSITIONS,
    "task": ALLOWED_TASK_TRANSITIONS,
}


def transition(
    current: MissionStatus | TaskStatus,
    requested: MissionStatus | TaskStatus,
    *,
    entity: str = "mission",
) -> MissionStatus | TaskStatus:
    """Validate and return the requested transition.

    Args:
        current: The current state.
        requested: The desired next state.
        entity: ``"mission"`` or ``"task"``.

    Returns:
        The requested state (unchanged) if the transition is legal.

    Raises:
        TransitionError: If the transition is not in the allowed table.
    """
    table = ALLOWED_TRANSITIONS.get(entity)
    if table is None:
        raise ValueError(f"Unknown entity type: {entity}")

    allowed = table.get(current, set())
    if requested not in allowed:
        raise TransitionError(entity, current.value, requested.value)

    return requested


def is_terminal(status: MissionStatus | TaskStatus, *, entity: str = "mission") -> bool:
    """Return True if the state is terminal (no outgoing transitions)."""
    table = ALLOWED_TRANSITIONS.get(entity)
    if table is None:
        raise ValueError(f"Unknown entity type: {entity}")
    return len(table.get(status, set())) == 0
