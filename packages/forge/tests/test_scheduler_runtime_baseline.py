"""RUN-00 baseline tests — reproduce known scheduler/runtime defects.

These tests are intentionally expected to fail against the current codebase.
They establish the executable baseline for Animus Plan 2 of 3.  As RUN-01
through RUN-09 are implemented, each ``xfail`` should flip to ``xpass`` and
the marker can be removed.

All tests use real scheduler instances, real ``SQLiteBackend``, and real
``CitizenWorkerPool`` where possible.  Deterministic fake clocks are not yet
available, so tests use short bounded timeouts.
"""

from __future__ import annotations

import asyncio
import inspect
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest

from animus_forge.api import app
from animus_forge.missions.domain import (
    CitizenOutput,
    Mission,
    MissionStatus,
    Task,
    TaskContext,
    TaskStatus,
)
from animus_forge.missions.store import MissionLedger
from animus_forge.scheduler.containers import ContainerManager
from animus_forge.scheduler.cost_enforcer import CostEnforcer
from animus_forge.scheduler.lease import LeaseManager
from animus_forge.scheduler.metrics import SchedulerMetrics
from animus_forge.scheduler.mission_scheduler import MissionScheduler, SchedulerConfig
from animus_forge.scheduler.worker_pool import CitizenWorkerPool, PoolConfig
from animus_forge.state.backends import SQLiteBackend


@asynccontextmanager
async def managed_scheduler(scheduler: MissionScheduler) -> MissionScheduler:
    """Start a scheduler and guarantee it is stopped on exit."""
    await scheduler.start()
    try:
        yield scheduler
    finally:
        await scheduler.stop()


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


class FakeContainerManager(ContainerManager):
    """Container manager that sleeps long enough to test kill/shutdown races."""

    def __init__(self, sleep_seconds: float = 3.0):
        self.sleep_seconds = sleep_seconds
        self.calls: list[dict] = []
        self.running: dict[str, bool] = {}
        self.completed: dict[str, bool] = {}

    def is_available(self) -> bool:
        return True

    def run_task(self, **kwargs) -> dict:
        task_id = kwargs.get("task_id", "unknown")
        self.calls.append(kwargs)
        self.running[task_id] = True
        time.sleep(self.sleep_seconds)
        self.running[task_id] = False
        self.completed[task_id] = True
        return {
            "status": "completed",
            "summary": "mock container completed",
            "changed_files": [],
            "evidence": [],
            "risks": [],
            "confidence": 0.9,
        }


@pytest.fixture()
def slow_container_pool(lease_manager):
    container = FakeContainerManager(sleep_seconds=2.0)
    pool = CitizenWorkerPool(
        lease_manager,
        config=PoolConfig(max_workers=1, isolation_mode="container"),
        container_manager=container,
    )
    pool._test_container = container
    return pool


# ---------------------------------------------------------------------------
# RUN-00 baseline tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_scheduler_loop_survives_three_intervals(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics
):
    """The scheduler run loop must survive ordinary poll timeouts."""
    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=0.05),
    )
    async with managed_scheduler(scheduler):
        await asyncio.sleep(0.25)  # Five poll intervals

        assert scheduler.is_running, "scheduler stopped unexpectedly"
        dispatcher = scheduler._supervisor.snapshot().get("dispatcher")
        assert dispatcher is not None
        assert dispatcher["state"] != "failed", "dispatcher loop failed"


@pytest.mark.asyncio()
async def test_recovery_loop_survives_three_intervals(
    ledger, lease_manager, cost_enforcer, metrics
):
    """The worker-pool recovery loop must survive ordinary poll timeouts."""
    pool = CitizenWorkerPool(
        lease_manager,
        config=PoolConfig(max_workers=1, poll_interval_seconds=0.05),
    )
    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, enable_recovery=True),
    )
    async with managed_scheduler(scheduler):
        # Wait long enough for several recovery poll intervals to elapse.
        await asyncio.sleep(0.25)

        assert scheduler.is_running, "scheduler stopped unexpectedly"
        recovery = scheduler._supervisor.snapshot().get("recovery")
        assert recovery is not None
        assert recovery["state"] != "failed", "recovery loop failed"


def test_released_task_can_reacquire_lease(lease_manager):
    """After a lease is released the same task must be claimable again."""
    lease = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=120,
    )
    assert lease is not None

    released = lease_manager.release(lease.lease_id, outcome="completed")
    assert released is not None

    second = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-1",
        ttl_seconds=120,
    )
    assert second is not None, "released task could not acquire a new lease"
    assert second.lease_id != lease.lease_id


def test_expired_task_can_reacquire_lease(lease_manager):
    """After a lease expires the same task must be claimable again."""
    from datetime import UTC, datetime, timedelta

    lease = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-0",
        ttl_seconds=1,
    )
    assert lease is not None

    recovered = lease_manager.recover_expired(as_of=datetime.now(UTC) + timedelta(seconds=5))
    assert recovered == ["task-1"]

    second = lease_manager.acquire(
        task_id="task-1",
        mission_id="mission-1",
        citizen_role="builder",
        worker_id="slot-1",
        ttl_seconds=120,
    )
    assert second is not None, "expired task could not acquire a new lease"


@pytest.mark.asyncio()
async def test_dispatch_atomicity_rollback_leaves_task_eligible(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """If dispatch partially fails the task must remain eligible and no orphan lease persists."""
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

    # Force the RUNNING transition to fail after the lease has been acquired.
    original_transition = ledger.transition_task

    def failing_transition(task_id, to_status, error=None):
        if to_status == TaskStatus.RUNNING:
            raise RuntimeError("simulated crash after lease acquisition")
        return original_transition(task_id, to_status, error)

    async with managed_scheduler(scheduler):
        with patch.object(ledger, "transition_task", side_effect=failing_transition):
            await scheduler.run_once()

        task = ledger.get_task(sample_task.task_id)
        # The task must still be eligible for dispatch (READY or LEASED), and there
        # must be no active lease left behind.
        assert task.status in (TaskStatus.READY, TaskStatus.LEASED), f"task stuck in {task.status}"

        active = lease_manager.get_active_leases()
        active_for_task = [lease for lease in active if lease.task_id == str(sample_task.task_id)]
        assert len(active_for_task) == 0, (
            "orphan active lease remains after partial dispatch failure"
        )


@pytest.mark.asyncio()
async def test_kill_slot_does_not_terminate_container_task(slow_container_pool, lease_manager):
    """Current defect: kill_slot clears bookkeeping but the underlying work continues.

    This test documents the current behavior so it can be flipped to assert
    termination once RUN-03 is implemented.
    """
    pool = slow_container_pool
    container = pool._test_container
    await pool.start()

    ctx = TaskContext(
        mission_objective="o",
        task_description="d",
        repository="r",
    )
    lease_id = await pool.submit(
        task_id="t-kill",
        citizen_role="planner",
        context=ctx,
        mission_id="m",
        ttl_seconds=300,
    )
    assert lease_id is not None
    assert pool.active_count() == 1

    # Allow the container task to start.
    await asyncio.sleep(0.2)

    killed = pool.kill_slot("0")
    assert killed is True
    assert pool.active_count() == 0

    # Current behavior: the container work is still running after kill_slot returns.
    assert not container.completed.get("t-kill", False), (
        "kill_slot unexpectedly terminated the task"
    )

    # Wait for the natural completion to prove the task was not killed.
    await asyncio.sleep(2.5)
    assert container.completed.get("t-kill", False), "test setup did not run task long enough"

    await pool.stop()


@pytest.mark.asyncio()
async def test_pool_stop_start_cycle_restores_recovery(
    ledger, lease_manager, slow_container_pool, cost_enforcer, metrics
):
    """After scheduler stop/start the recovery loop must run again."""
    pool = slow_container_pool
    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, enable_recovery=True),
    )

    await scheduler.start()
    assert scheduler.is_running

    # Stop the scheduler and its supervised recovery loop.
    await scheduler.stop()
    assert not pool.is_running

    # Restart; the recovery loop should be able to poll again.
    await scheduler.start()
    assert scheduler.is_running

    loop_ran = asyncio.Event()

    def recover_once(*args, **kwargs):
        loop_ran.set()
        return []

    with patch.object(pool.lease, "recover_expired", side_effect=recover_once):
        await asyncio.wait_for(loop_ran.wait(), timeout=1.0)

    await scheduler.stop()


@pytest.mark.asyncio()
@pytest.mark.xfail(
    reason="RUN-00 defect #8: cost recorded without actual provider/model/token usage"
)
async def test_recorded_cost_reflects_actual_usage(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """Cost events must record actual provider, model, and token usage."""
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

    # The worker result currently carries no provider/model/token metadata,
    # so the scheduler records a zero-cost local/default event.  The intended
    # design propagates actual usage from the worker result.
    async with managed_scheduler(scheduler):
        await scheduler.run_once()
        await asyncio.sleep(3.0)

        rows = cost_enforcer._backend.fetchall(
            "SELECT * FROM cost_events WHERE mission_id = ? AND task_id = ?",
            (str(sample_mission.mission_id), str(sample_task.task_id)),
        )
        assert len(rows) == 1, f"expected single cost event, got {len(rows)}"
        event = rows[0]
        assert event["provider"] == "openai", f"provider not recorded: {event['provider']}"
        assert event["model"] == "gpt-4o", f"model not recorded: {event['model']}"
        assert event["usage_tokens_input"] == 1000
        assert event["usage_tokens_output"] == 500
        assert Decimal(event["cost_usd"]) > Decimal("0")


@pytest.mark.xfail(reason="RUN-00 defect #9: budget reservation is not atomic")
def test_concurrent_tasks_can_oversubscribe_budget(cost_enforcer):
    """can_start_task must consider outstanding reservations, not just past spend."""
    mission_id = "mission-1"
    cap = Decimal("1.00")

    # Mission has $1.00 cap. Two tasks each reserve $0.60 arrive "concurrently".
    ok1, _ = cost_enforcer.can_start_task(
        mission_id, estimated_cost=Decimal("0.60"), mission_cap=cap
    )
    ok2, _ = cost_enforcer.can_start_task(
        mission_id, estimated_cost=Decimal("0.60"), mission_cap=cap
    )

    # Without reservations, both are approved even though their combined
    # estimated cost ($1.20) exceeds the cap.
    assert not (ok1 and ok2), "concurrent tasks were allowed to oversubscribe budget"


@pytest.mark.asyncio()
@pytest.mark.xfail(reason="RUN-00 defect #10: REVIEW is a ceremonial passthrough state")
async def test_mission_completes_without_review_verdict(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """A mission must not reach COMPLETED without a real ReviewVerdict."""
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
    async with managed_scheduler(scheduler):
        await scheduler.run_once()
        await asyncio.sleep(3.5)

        mission = ledger.get_mission(sample_mission.mission_id)
        assert mission.status != MissionStatus.COMPLETED, "mission completed without review verdict"
        # The intended behavior is to land in REVIEW and wait for a verdict.
        assert mission.status == MissionStatus.REVIEW, f"expected REVIEW, got {mission.status}"


@pytest.mark.asyncio()
@pytest.mark.xfail(reason="RUN-00 defect #11: cancelled required task satisfies all_done")
async def test_cancelled_required_task_allows_completion(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission
):
    """A required cancelled task must prevent mission completion."""
    ledger.create_mission(sample_mission)
    cancelled_task = Task(
        mission_id=sample_mission.mission_id,
        citizen_role="planner",
        description="Required task that gets cancelled",
        status=TaskStatus.READY,
    )
    normal_task = Task(
        mission_id=sample_mission.mission_id,
        citizen_role="planner",
        description="Normal task that will complete",
        status=TaskStatus.READY,
    )
    ledger.create_task(cancelled_task)
    ledger.create_task(normal_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    # Cancel the required task before the scheduler runs completion logic.
    ledger.transition_task(cancelled_task.task_id, TaskStatus.CANCELLED)

    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, default_task_ttl_seconds=30),
    )
    async with managed_scheduler(scheduler):
        # Dispatch the normal task; when it completes, _check_mission_completion runs.
        await scheduler.run_once()
        await asyncio.sleep(3.5)

        mission = ledger.get_mission(sample_mission.mission_id)
        assert mission.status != MissionStatus.COMPLETED, (
            "mission completed despite cancelled required task"
        )


@pytest.mark.asyncio()
@pytest.mark.xfail(reason="RUN-00 defect #12: checkpoint attempt_id is set to task_id")
async def test_checkpoint_attempt_id_is_not_task_id(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """Checkpoints must reference the execution attempt, not the task identity."""
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
    async with managed_scheduler(scheduler):
        await scheduler.run_once()
        await asyncio.sleep(3.5)

        checkpoints = ledger.list_checkpoints(sample_task.task_id)
        assert len(checkpoints) >= 1
        for cp in checkpoints:
            assert cp.attempt_id != sample_task.task_id, "checkpoint attempt_id equals task_id"


@pytest.mark.asyncio()
@pytest.mark.xfail(reason="RUN-00 defect #13: retry semantics do not create distinct attempt_id")
async def test_retry_does_not_create_distinct_attempt_id(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission
):
    """A retry must produce a new attempt with a distinct attempt_id."""
    ledger.create_mission(sample_mission)
    task = Task(
        mission_id=sample_mission.mission_id,
        citizen_role="planner",
        description="Task that will fail and retry",
        status=TaskStatus.READY,
        max_attempts=2,
    )
    ledger.create_task(task)
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

    # Force the result to fail so a retry happens.
    async def fake_fail_result(task_id, result_dict):
        fail_output = CitizenOutput(
            status="failed",
            summary="forced failure",
            risks=[{"severity": "high", "description": "forced"}],
        )
        await MissionScheduler._process_result(
            scheduler, task_id, fail_output.model_dump(mode="json")
        )

    async with managed_scheduler(scheduler):
        with patch.object(scheduler, "_process_result", side_effect=fake_fail_result):
            await scheduler.run_once()
            await asyncio.sleep(2.0)

        task = ledger.get_task(task.task_id)
        assert task.current_attempt > 0, "task was not retried"

        checkpoints = ledger.list_checkpoints(task.task_id)
        attempt_ids = {cp.attempt_id for cp in checkpoints}
        assert len(attempt_ids) >= 2, f"retry reused the same attempt_id: {attempt_ids}"


def test_api_routes_inspect_private_stopped_field():
    """Scheduler control endpoints must use a public lifecycle interface."""
    from animus_forge.api_routes import mission_scheduler as routes

    source = inspect.getsource(routes)
    assert "mission_scheduler._stopped" not in source, "API routes read private _stopped field"
    assert "is_running" in source, "API routes should use the public is_running interface"


@pytest.mark.asyncio()
async def test_api_with_real_scheduler_lifecycle(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics
):
    """The scheduler API must work against a real scheduler instance."""
    from httpx import ASGITransport, AsyncClient

    from animus_forge import api_state
    from animus_forge.api_routes.auth import create_access_token

    token = create_access_token("test-user")
    headers = {"Authorization": f"Bearer {token}"}

    scheduler = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=0.1),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # The app lifespan creates and starts its own scheduler.  Stop it so
        # we can substitute the test scheduler cleanly.
        await client.post("/v1/scheduler/stop", headers=headers)

        # Inject the test scheduler and exercise it through the API.
        api_state.mission_scheduler = scheduler

        response = await client.post("/v1/scheduler/start", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

        # Real status must reflect the running scheduler.
        response = await client.get("/v1/scheduler/status", headers=headers)
        assert response.status_code == 200
        status = response.json()
        assert status["is_running"] is True
        # Health should expose a public lifecycle state, not a private flag.
        assert "lifecycle_state" in status

        response = await client.post("/v1/scheduler/stop", headers=headers)
        assert response.status_code == 200

    api_state.mission_scheduler = None


@pytest.mark.asyncio()
@pytest.mark.xfail(reason="RUN-00 defect #16: duplicate result is not idempotent")
async def test_duplicate_result_records_cost_twice(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """Delivering the same result twice must not double-spend budget."""
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
    async with managed_scheduler(scheduler):
        await scheduler.run_once()
        await asyncio.sleep(3.5)

        task = ledger.get_task(sample_task.task_id)
        assert task.status == TaskStatus.COMPLETED

        # Re-deliver the exact same completed result.
        completed_output = CitizenOutput(
            status="completed",
            summary="duplicate result",
            confidence=0.9,
        )
        await scheduler._process_result(
            str(sample_task.task_id), completed_output.model_dump(mode="json")
        )

        rows = cost_enforcer._backend.fetchall(
            "SELECT * FROM cost_events WHERE mission_id = ? AND task_id = ?",
            (str(sample_mission.mission_id), str(sample_task.task_id)),
        )
        assert len(rows) == 1, f"duplicate result caused {len(rows)} cost events instead of 1"


@pytest.mark.asyncio()
async def test_two_schedulers_maintain_single_active_lease(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission, sample_task
):
    """Baseline invariant: even with multiple schedulers, a task has at most one active lease.

    The current unique constraint on ``task_leases.task_id`` provides this
    protection in the simple case.  The non-atomic dispatch window is covered by
    ``test_dispatch_atomicity_rollback_leaves_task_eligible``; true
    split-brain behavior will be exercised in RUN-08 with deterministic
    concurrency tooling.
    """
    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

    scheduler_a = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=worker_pool,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, default_task_ttl_seconds=30),
    )
    pool_b = CitizenWorkerPool(lease_manager, config=PoolConfig(max_workers=1))
    scheduler_b = MissionScheduler(
        ledger=ledger,
        lease_manager=lease_manager,
        worker_pool=pool_b,
        cost_enforcer=cost_enforcer,
        metrics=metrics,
        config=SchedulerConfig(poll_interval_seconds=1.0, default_task_ttl_seconds=30),
    )

    async with managed_scheduler(scheduler_a):
        async with managed_scheduler(scheduler_b):
            await asyncio.gather(scheduler_a.run_once(), scheduler_b.run_once())

            active = lease_manager.get_active_leases()
            task_leases = [lease for lease in active if lease.task_id == str(sample_task.task_id)]
            assert len(task_leases) <= 1, (
                f"race allowed {len(task_leases)} active leases for one task"
            )
