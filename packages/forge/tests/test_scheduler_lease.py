"""Focused tests for RUN-02 lease redesign and atomic dispatch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from animus_forge.scheduler.atomic_dispatch import AtomicDispatcher
from animus_forge.scheduler.cost_enforcer import CostEnforcer
from animus_forge.scheduler.lease import LeaseAcquireError, LeaseManager, LeaseStatus
from animus_forge.scheduler.metrics import SchedulerMetrics
from animus_forge.scheduler.mission_scheduler import MissionScheduler, SchedulerConfig
from animus_forge.scheduler.worker_pool import CitizenWorkerPool, PoolConfig
from animus_forge.state.backends import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend():
    b = SQLiteBackend(":memory:")
    with b.transaction():
        b.execute("PRAGMA foreign_keys=ON")
    yield b
    b.close()


@pytest.fixture()
def ledger(backend):
    return MissionLedger(backend)


@pytest.fixture()
def lease_manager(backend):
    return LeaseManager(backend, default_ttl_seconds=60)


@pytest.fixture()
def cost_enforcer(backend):
    return CostEnforcer(backend)


@pytest.fixture()
def worker_pool(lease_manager):
    return CitizenWorkerPool(lease_manager, config=PoolConfig(max_workers=2))


@pytest.fixture()
def metrics(backend):
    return SchedulerMetrics(backend)


@pytest.fixture()
def sample_mission():
    return Mission(
        repository="AreteDriver/animus",
        objective="Fix off-by-one pagination bug",
        status=MissionStatus.PROPOSED,
        max_cost_usd=Decimal("5.00"),
    )


@pytest.fixture()
def sample_task(sample_mission):
    return Task(
        mission_id=sample_mission.mission_id,
        citizen_role="planner",
        description="Plan the fix",
        status=TaskStatus.READY,
    )


@pytest.fixture()
def dispatcher(ledger, lease_manager, cost_enforcer):
    return AtomicDispatcher(
        ledger=ledger,
        lease_manager=lease_manager,
        cost_enforcer=cost_enforcer,
    )


# ---------------------------------------------------------------------------
# LeaseManager schema and lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("lease_test_records")
def test_acquire_creates_current_row_and_history(lease_manager):
    lease = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=120,
    )
    assert lease.status == LeaseStatus.ACTIVE
    assert lease.generation == 1

    current = lease_manager.get_lease_for_task("task-1")
    assert current is not None
    assert current.lease_id == lease.lease_id

    history = lease_manager.history_for_task("task-1")
    assert len(history) == 1
    assert history[0]["lease_id"] == lease.lease_id
    assert history[0]["status"] == LeaseStatus.ACTIVE


@pytest.mark.usefixtures("lease_test_records")
def test_acquire_already_leased_raises(lease_manager):
    lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=120,
    )
    with pytest.raises(LeaseAcquireError) as exc_info:
        lease_manager.acquire(
            task_id="task-1",
            mission_id="mission-1",
            citizen_role="builder",
            worker_id="slot-1",
            ttl_seconds=120,
        )
    assert exc_info.value.reason == "already_leased"
    assert exc_info.value.task_id == "task-1"


@pytest.mark.usefixtures("lease_test_records")
def test_release_moves_row_to_history(lease_manager):
    lease = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=120,
    )
    released = lease_manager.release(lease.lease_id, outcome="completed")
    assert released is not None
    assert released.status == LeaseStatus.RELEASED
    assert released.outcome == "completed"

    assert lease_manager.get_lease_for_task("task-1") is None
    history = lease_manager.history_for_task("task-1")
    assert len(history) == 2  # active + released
    assert history[0]["status"] == LeaseStatus.RELEASED


@pytest.mark.usefixtures("lease_test_records")
def test_generation_increments_on_reacquire(lease_manager):
    lease = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=120,
    )
    lease_manager.release(lease.lease_id, outcome="completed")
    second = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-1",
        ttl_seconds=120,
    )
    assert second.generation == 2


@pytest.mark.usefixtures("lease_test_records")
def test_recover_expired_creates_history_and_allows_reacquire(lease_manager):
    _ = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=1,
    )
    recovered = lease_manager.recover_expired(as_of=datetime.now(UTC) + timedelta(seconds=5))
    assert recovered == ["task-1"]
    assert lease_manager.get_lease_for_task("task-1") is None

    history = lease_manager.history_for_task("task-1")
    assert any(h["status"] == LeaseStatus.EXPIRED for h in history)

    second = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-1",
        ttl_seconds=120,
    )
    assert second is not None
    assert second.generation == 2


# ---------------------------------------------------------------------------
# AtomicDispatcher
# ---------------------------------------------------------------------------


def test_atomic_dispatch_success(dispatcher, ledger, lease_manager, sample_mission, sample_task):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    result = dispatcher.dispatch(
        task=sample_task,
        worker_id="slot-0",
        default_ttl_seconds=120,
        default_mission_cap_usd=Decimal("10.00"),
    )
    assert result.ok
    assert result.lease is not None
    assert result.attempt_id is not None

    task = ledger.get_task(sample_task.task_id)
    assert task.status == TaskStatus.RUNNING

    lease = lease_manager.get_lease_for_task(str(sample_task.task_id))
    assert lease is not None
    assert lease.attempt_id == result.attempt_id
    assert lease.generation == 1

    attempt = lease_manager.get_attempt(result.attempt_id)
    assert attempt is not None
    assert attempt["status"] == "started"
    assert attempt["generation"] == 1


def test_atomic_dispatch_rejects_already_leased(
    dispatcher, ledger, lease_manager, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    first = dispatcher.dispatch(
        task=sample_task,
        worker_id="slot-0",
        default_ttl_seconds=120,
        default_mission_cap_usd=Decimal("10.00"),
    )
    assert first.ok

    # Simulate a stale/racing view where the task still appears READY while
    # its lease row remains active. The atomic dispatcher must be blocked by
    # the current lease, not just by task status.
    task = ledger.get_task(sample_task.task_id)
    task.status = TaskStatus.READY
    ledger.update_task(task)

    second = dispatcher.dispatch(
        task=sample_task,
        worker_id="slot-1",
        default_ttl_seconds=120,
        default_mission_cap_usd=Decimal("10.00"),
    )
    assert not second.ok
    assert "already_leased" in second.error


def test_atomic_dispatch_rejects_exhausted_budget(
    dispatcher, ledger, lease_manager, cost_enforcer, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    # Record a cost event that exhausts the mission cap.
    cost_enforcer.record(
        mission_id=str(sample_mission.mission_id),
        task_id=str(uuid4()),
        operation="citizen_task",
        cost_usd=Decimal("10.00"),
    )

    result = dispatcher.dispatch(
        task=sample_task,
        worker_id="slot-0",
        default_ttl_seconds=120,
        default_mission_cap_usd=Decimal("10.00"),
        estimated_cost_usd=Decimal("0.01"),
    )
    assert not result.ok
    assert "budget" in result.error

    task = ledger.get_task(sample_task.task_id)
    assert task.status == TaskStatus.READY
    assert lease_manager.get_lease_for_task(str(sample_task.task_id)) is None


@pytest.mark.parametrize("transition_error", [False, True])
def test_atomic_dispatch_rollback_on_transition_failure(
    dispatcher, ledger, sample_mission, sample_task, transition_error
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    original = ledger.transition_task

    def failing_transition(task_id, to_status, error=None):
        if to_status == TaskStatus.RUNNING:
            if transition_error:
                from animus_forge.missions.transitions import TransitionError

                raise TransitionError("task", "leased", "running")
            raise RuntimeError("simulated transition failure")
        return original(task_id, to_status, error)

    from unittest.mock import patch

    with patch.object(ledger, "transition_task", side_effect=failing_transition):
        result = dispatcher.dispatch(
            task=sample_task,
            worker_id="slot-0",
            default_ttl_seconds=120,
            default_mission_cap_usd=Decimal("10.00"),
        )

    assert not result.ok
    task = ledger.get_task(sample_task.task_id)
    assert task.status == TaskStatus.READY
    assert task.current_attempt == 0
    assert dispatcher.cost.reserved() == 0
    assert (
        dispatcher._backend.fetchone(
            "SELECT 1 FROM task_lease_current WHERE task_id = ?",
            (str(sample_task.task_id),),
        )
        is None
    )
    assert (
        dispatcher._backend.fetchone(
            "SELECT 1 FROM task_attempts WHERE task_id = ?",
            (str(sample_task.task_id),),
        )
        is None
    )


# ---------------------------------------------------------------------------
# Worker pool with pre-acquired lease
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_pool_submit_uses_preacquired_lease(
    dispatcher, ledger, lease_manager, worker_pool, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    result = dispatcher.dispatch(
        task=sample_task,
        worker_id="0",
        default_ttl_seconds=120,
        default_mission_cap_usd=Decimal("10.00"),
    )
    assert result.ok

    await worker_pool.start()
    try:
        ctx = TaskContext(
            mission_objective=sample_mission.objective,
            task_description=sample_task.description,
            repository=sample_mission.repository,
        )
        lease_id = await worker_pool.submit(
            task_id=str(sample_task.task_id),
            citizen_role=sample_task.citizen_role,
            context=ctx,
            mission_id=str(sample_mission.mission_id),
            lease=result.lease,
            slot_id="0",
        )
        assert lease_id == result.lease.lease_id
        assert worker_pool.active_count() == 1
    finally:
        await worker_pool.stop()


# ---------------------------------------------------------------------------
# End-to-end scheduler atomicity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_scheduler_tick_atomically_dispatches(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0),
    )
    await scheduler.start()
    try:
        dispatched = await scheduler.run_once()
        assert dispatched == 1

        task = ledger.get_task(sample_task.task_id)
        assert task.status == TaskStatus.RUNNING

        lease = lease_manager.get_lease_for_task(str(sample_task.task_id))
        assert lease is not None
        assert lease.attempt_id is not None
        assert lease.generation == 1
    finally:
        await scheduler.stop()


@pytest.mark.asyncio()
async def test_scheduler_double_tick_does_not_double_dispatch(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0),
    )
    await scheduler.start()
    try:
        assert await scheduler.run_once() == 1
        assert await scheduler.run_once() == 0  # already leased/running
    finally:
        await scheduler.stop()


@pytest.mark.asyncio()
async def test_scheduler_stale_result_is_fenced(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, default_task_ttl_seconds=30),
    )
    await scheduler.start()
    try:
        await scheduler.run_once()
        task = ledger.get_task(sample_task.task_id)
        assert task.status == TaskStatus.RUNNING

        lease = lease_manager.get_lease_for_task(str(sample_task.task_id))
        # Manually release and retry the task, simulating a slow stale result.
        lease_manager.release(lease.lease_id, outcome="completed")
        ledger.transition_task(sample_task.task_id, TaskStatus.READY)

        # A new lease would have a different lease_id / generation.
        new_lease = lease_manager.acquire(
            task_id=str(sample_task.task_id),
            mission_id=str(sample_mission.mission_id),
            citizen_role=sample_task.citizen_role,
            worker_id="1",
            ttl_seconds=30,
        )
        assert new_lease.lease_id != lease.lease_id
        assert new_lease.generation == 2

        # Old result arrives with the old lease_id/generation from the worker pool.
        stale_result = CitizenOutput(
            status="completed",
            summary="stale result",
            confidence=0.9,
        ).model_dump(mode="json")
        stale_result["_scheduler_meta"] = {
            "lease_id": lease.lease_id,
            "generation": lease.generation,
        }
        await scheduler._process_result(str(sample_task.task_id), stale_result)

        # The stale result must not overwrite the new active lease or transition the task.
        current = lease_manager.get_lease_for_task(str(sample_task.task_id))
        assert current is not None
        assert current.lease_id == new_lease.lease_id
        assert current.generation == 2

        task = ledger.get_task(sample_task.task_id)
        assert task.status == TaskStatus.READY
    finally:
        await scheduler.stop()


def test_failed_pool_submit_releases_reservation_once(
    dispatcher, ledger, sample_mission, sample_task
):
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)
    result = dispatcher.dispatch(
        sample_task,
        "fixture",
        default_ttl_seconds=30,
        default_mission_cap_usd=Decimal("10"),
    )
    assert result.ok
    assert dispatcher.cost.reserved() == Decimal("0.10")
    dispatcher.rollback_dispatch(result.lease)
    dispatcher.rollback_dispatch(result.lease)
    task = ledger.get_task(sample_task.task_id)
    assert task.status == TaskStatus.READY
    assert task.current_attempt == 0
    assert dispatcher.cost.reserved() == 0
    assert dispatcher.lease.get_attempt(result.attempt_id)["status"] == "cancelled"
