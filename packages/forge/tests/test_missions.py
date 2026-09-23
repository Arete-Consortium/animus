"""Tests for the mission domain model, state machine, and ledger."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from animus_forge.missions.domain import (
    CitizenOutput,
    Mission,
    MissionStatus,
    Task,
    TaskContext,
    TaskStatus,
)
from animus_forge.missions.store import MissionLedger
from animus_forge.missions.transitions import (
    ALLOWED_TRANSITIONS,
    TransitionError,
    is_terminal,
    transition,
)
from animus_forge.state.backends import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_backend():
    """Create an in-memory SQLite backend."""
    backend = SQLiteBackend(":memory:")
    # Initialise schema via MissionLedger
    MissionLedger(backend)
    return backend


@pytest.fixture()
def ledger(memory_backend):
    return MissionLedger(memory_backend)


@pytest.fixture()
def sample_mission():
    return Mission(
        repository="AreteDriver/animus",
        objective="Fix off-by-one pagination bug",
        risk_class="medium",
        priority=75,
        max_cost_usd=Decimal("5.00"),
        max_runtime_seconds=1800,
        max_changed_files=4,
        allowed_paths=["src/**/*.py", "tests/**/*.py"],
        protected_paths=[".github/workflows/**", "migrations/**"],
        acceptance_criteria=[
            "regression test added",
            "original failure reproduced",
            "full suite passes",
        ],
    )


@pytest.fixture()
def sample_task(sample_mission):
    return Task(
        mission_id=sample_mission.mission_id,
        citizen_role="builder",
        description="Implement fix for pagination bug",
        max_attempts=3,
    )


# ---------------------------------------------------------------------------
# Domain model basics
# ---------------------------------------------------------------------------


class TestMissionModel:
    def test_mission_creation(self, sample_mission):
        assert sample_mission.status == MissionStatus.PROPOSED
        assert sample_mission.is_terminal() is False
        assert sample_mission.priority == 75

    def test_mission_terminal_states(self):
        for status in (
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
            MissionStatus.QUARANTINED,
        ):
            m = Mission(repository="r", objective="o", status=status)
            assert m.is_terminal() is True

    def test_mission_non_terminal_states(self):
        for status in (
            MissionStatus.PROPOSED,
            MissionStatus.READY,
            MissionStatus.RUNNING,
            MissionStatus.WAITING,
            MissionStatus.REVIEW,
            MissionStatus.APPROVAL_REQUIRED,
        ):
            m = Mission(repository="r", objective="o", status=status)
            assert m.is_terminal() is False


class TestTaskModel:
    def test_task_dependencies(self, sample_mission):
        dep = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="planner",
            description="Plan the fix",
        )
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="builder",
            description="Build the fix",
            dependencies=[dep.task_id],
        )
        assert task.can_start({dep.task_id}) is True
        assert task.can_start(set()) is False

    def test_task_no_dependencies(self, sample_mission):
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="builder",
            description="Build",
        )
        assert task.can_start(set()) is True


class TestCitizenOutput:
    def test_valid_output(self):
        out = CitizenOutput(
            status="completed",
            summary="Fixed the bug",
            changed_files=["src/pagination.py", "tests/test_pagination.py"],
            confidence=0.92,
        )
        assert out.status == "completed"
        assert out.confidence == 0.92

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValueError):
            CitizenOutput(status="completed", summary="x", confidence=1.5)


class TestTaskContext:
    def test_context_creation(self):
        ctx = TaskContext(
            mission_objective="Fix bug",
            task_description="Implement",
            repository="AreteDriver/animus",
            budget_remaining_usd=Decimal("5.00"),
        )
        assert ctx.budget_remaining_usd == Decimal("5.00")


# ---------------------------------------------------------------------------
# State-machine transitions
# ---------------------------------------------------------------------------


class TestMissionTransitions:
    def test_all_valid_transitions_exist(self):
        table = ALLOWED_TRANSITIONS["mission"]
        # Sanity check: every mission status has an entry
        for status in MissionStatus:
            assert status in table

    def test_valid_proposed_transitions(self):
        transition(MissionStatus.PROPOSED, MissionStatus.READY, entity="mission")
        transition(MissionStatus.PROPOSED, MissionStatus.CANCELLED, entity="mission")

    def test_invalid_proposed_to_completed(self):
        with pytest.raises(TransitionError):
            transition(MissionStatus.PROPOSED, MissionStatus.COMPLETED, entity="mission")

    def test_invalid_running_to_cancelled(self):
        with pytest.raises(TransitionError):
            transition(MissionStatus.RUNNING, MissionStatus.CANCELLED, entity="mission")

    def test_valid_review_to_running(self):
        transition(MissionStatus.REVIEW, MissionStatus.RUNNING, entity="mission")

    def test_terminal_no_transitions(self):
        for status in (
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
            MissionStatus.QUARANTINED,
        ):
            assert is_terminal(status, entity="mission") is True
            with pytest.raises(TransitionError):
                transition(status, MissionStatus.RUNNING, entity="mission")


class TestTaskTransitions:
    def test_valid_task_transitions(self):
        transition(TaskStatus.PENDING, TaskStatus.READY, entity="task")
        transition(TaskStatus.READY, TaskStatus.LEASED, entity="task")
        transition(TaskStatus.LEASED, TaskStatus.RUNNING, entity="task")
        transition(TaskStatus.RUNNING, TaskStatus.COMPLETED, entity="task")

    def test_invalid_task_transition(self):
        with pytest.raises(TransitionError):
            transition(TaskStatus.PENDING, TaskStatus.COMPLETED, entity="task")

    def test_lease_expiry_returns_to_ready(self):
        transition(TaskStatus.LEASED, TaskStatus.READY, entity="task")


class TestTransitionError:
    def test_error_message(self):
        err = TransitionError("mission", "proposed", "completed")
        assert "proposed → completed" in str(err)
        assert err.entity == "mission"
        assert err.current == "proposed"
        assert err.requested == "completed"


# ---------------------------------------------------------------------------
# MissionLedger persistence
# ---------------------------------------------------------------------------


class TestMissionLedger:
    def test_create_and_get_mission(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        fetched = ledger.get_mission(sample_mission.mission_id)
        assert fetched is not None
        assert fetched.mission_id == sample_mission.mission_id
        assert fetched.objective == "Fix off-by-one pagination bug"
        assert fetched.status == MissionStatus.PROPOSED

    def test_get_missing_mission(self, ledger):
        assert ledger.get_mission(uuid4()) is None

    def test_update_mission(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        sample_mission.priority = 99
        ledger.update_mission(sample_mission)
        fetched = ledger.get_mission(sample_mission.mission_id)
        assert fetched.priority == 99

    def test_transition_mission(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        updated = ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
        assert updated.status == MissionStatus.READY

    def test_invalid_transition_raises(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        with pytest.raises(TransitionError):
            ledger.transition_mission(sample_mission.mission_id, MissionStatus.COMPLETED)

    def test_transition_missing_mission_raises(self, ledger):
        with pytest.raises(ValueError, match="Mission not found"):
            ledger.transition_mission(uuid4(), MissionStatus.READY)

    def test_list_missions_by_status(self, ledger, sample_mission):
        m2 = Mission(
            repository="AreteDriver/animus",
            objective="Second mission",
            status=MissionStatus.RUNNING,
        )
        ledger.create_mission(sample_mission)
        ledger.create_mission(m2)
        proposed = ledger.list_missions(status=MissionStatus.PROPOSED)
        assert len(proposed) == 1
        assert proposed[0].objective == sample_mission.objective

    def test_list_missions_default_order(self, ledger):
        m_low = Mission(repository="r", objective="low", priority=10, status=MissionStatus.PROPOSED)
        m_high = Mission(
            repository="r", objective="high", priority=90, status=MissionStatus.PROPOSED
        )
        ledger.create_mission(m_low)
        ledger.create_mission(m_high)
        results = ledger.list_missions(limit=10)
        assert results[0].priority == 90
        assert results[1].priority == 10


class TestTaskLedger:
    def test_create_and_get_task(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)
        fetched = ledger.get_task(sample_task.task_id)
        assert fetched is not None
        assert fetched.citizen_role == "builder"
        assert fetched.mission_id == sample_mission.mission_id

    def test_list_tasks_for_mission(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        t2 = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="reviewer",
            description="Review the fix",
        )
        ledger.create_task(sample_task)
        ledger.create_task(t2)
        tasks = ledger.list_tasks_for_mission(sample_mission.mission_id)
        assert len(tasks) == 2

    def test_transition_task(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)
        updated = ledger.transition_task(sample_task.task_id, TaskStatus.READY)
        assert updated.status == TaskStatus.READY

    def test_task_dependencies(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        dep = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="planner",
            description="Plan",
        )
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="builder",
            description="Build",
            dependencies=[dep.task_id],
        )
        ledger.create_task(dep)
        ledger.create_task(task)
        # Move dep through proper state machine to COMPLETED
        ledger.transition_task(dep.task_id, TaskStatus.READY)
        ledger.transition_task(dep.task_id, TaskStatus.LEASED)
        ledger.transition_task(dep.task_id, TaskStatus.RUNNING)
        ledger.transition_task(dep.task_id, TaskStatus.COMPLETED)
        # Now task can be readied
        ledger.transition_task(task.task_id, TaskStatus.READY)
        ready = ledger.get_ready_tasks(sample_mission.mission_id)
        assert len(ready) == 1
        assert ready[0].task_id == task.task_id

    def test_get_ready_tasks_requires_ready_status(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="builder",
            description="Build",
        )
        ledger.create_task(task)
        # Task is PENDING, not READY — should not appear
        ready = ledger.get_ready_tasks(sample_mission.mission_id)
        assert len(ready) == 0

    def test_decimal_serialization(self, ledger, sample_mission):
        ledger.create_mission(sample_mission)
        fetched = ledger.get_mission(sample_mission.mission_id)
        assert fetched.max_cost_usd == Decimal("5.00")

    def test_json_metadata_roundtrip(self, ledger, sample_mission):
        sample_mission.metadata = {"key": "value", "nested": {"a": 1}}
        ledger.create_mission(sample_mission)
        fetched = ledger.get_mission(sample_mission.mission_id)
        assert fetched.metadata == {"key": "value", "nested": {"a": 1}}

    def test_mission_delete_cascades_to_tasks(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)
        # Enable FK enforcement for this test
        with ledger._backend.transaction():
            ledger._backend.execute("PRAGMA foreign_keys=ON")
            ledger._backend.execute(
                "DELETE FROM missions WHERE mission_id = ?",
                (str(sample_mission.mission_id),),
            )
        assert ledger.get_mission(sample_mission.mission_id) is None
        # Task should also be gone due to ON DELETE CASCADE
        assert ledger.get_task(sample_task.task_id) is None
