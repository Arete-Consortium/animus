"""RUN-00 baseline tests — reproduce known scheduler/runtime defects.

The original expected failures are now executable regression checks.

All tests use real scheduler instances, real ``SQLiteBackend``, and real
``CitizenWorkerPool`` where possible.  Deterministic fake clocks are not yet
available, so tests use short bounded timeouts.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


def dispatch_result(scheduler, task, *, status="completed", usage=None):
    """Dispatch without a worker so result delivery is deterministic and fenced."""
    dispatch = scheduler.dispatcher.dispatch(
        task,
        "test-worker",
        default_ttl_seconds=30,
        default_mission_cap_usd=Decimal("10"),
    )
    assert dispatch.ok, dispatch.error
    result = CitizenOutput(status=status, summary="fixture", usage=usage or []).model_dump(
        mode="json"
    )
    result["_scheduler_meta"] = {
        "lease_id": dispatch.lease.lease_id,
        "generation": dispatch.lease.generation,
        "attempt_id": dispatch.attempt_id,
    }
    return result


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

    async def run_task_async(self, **kwargs):
        task_id = kwargs["task_id"]
        self.calls.append(kwargs)
        self.running[task_id] = True
        process = SimpleNamespace(returncode=None)
        stopped = asyncio.Event()
        self._stopped = stopped

        async def communicate():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self.sleep_seconds)
                process.returncode = -9
                return b"", b"killed"
            except TimeoutError:
                self.completed[task_id] = True
                process.returncode = 0
                return json.dumps({"status": "completed", "summary": "fixture"}).encode(), b""
            finally:
                self.running[task_id] = False

        process.communicate = communicate
        return SimpleNamespace(container_id=task_id, process=process)

    async def kill_container(self, container_id):
        self._stopped.set()


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


@pytest.mark.usefixtures("lease_test_records")
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


@pytest.mark.usefixtures("lease_test_records")
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
@pytest.mark.usefixtures("lease_test_records")
async def test_kill_slot_terminates_container_task(slow_container_pool, lease_manager):
    """The implemented container kill path must stop work and release the slot."""
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

    # Wait beyond normal completion and verify that kill prevented completion.
    await asyncio.sleep(2.5)
    assert not container.running["t-kill"]
    assert not container.completed.get("t-kill", False)
    assert lease_manager.get_lease_for_task("t-kill") is None

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

    result = dispatch_result(
        scheduler,
        sample_task,
        usage=[
            {
                "provider": "openai",
                "model": "gpt-4o",
                "tokens_input": 1000,
                "tokens_output": 500,
                "cost_usd": "0.0075",
            }
        ],
    )
    await scheduler._process_result(str(sample_task.task_id), result)
    rows = cost_enforcer._backend.fetchall(
        "SELECT * FROM cost_events WHERE task_id = ?", (str(sample_task.task_id),)
    )
    assert len(rows) == 1
    event = rows[0]
    assert event["provider"] == "openai"
    assert event["model"] == "gpt-4o"
    assert event["usage_tokens_input"] == 1000
    assert event["usage_tokens_output"] == 500
    assert Decimal(event["cost_usd"]) == Decimal("0.0075")
    assert cost_enforcer.reserved() == 0


def test_concurrent_tasks_can_oversubscribe_budget(cost_enforcer):
    """can_start_task must consider outstanding reservations, not just past spend."""
    mission_id = "mission-1"
    cap = Decimal("1.00")

    # Mission has $1.00 cap. Two tasks each reserve $0.60 arrive "concurrently".
    ok1, _ = cost_enforcer.reserve(
        "attempt-1", mission_id, estimated_cost=Decimal("0.60"), mission_cap=cap
    )
    ok2, _ = cost_enforcer.reserve(
        "attempt-2", mission_id, estimated_cost=Decimal("0.60"), mission_cap=cap
    )

    # The second reservation cannot claim the first attempt's budget.
    assert not (ok1 and ok2), "concurrent tasks were allowed to oversubscribe budget"


@pytest.mark.asyncio()
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
        assert mission.status == MissionStatus.FAILED


@pytest.mark.asyncio()
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

    for expected_attempt in (1, 2):
        result = dispatch_result(scheduler, task, status="failed")
        await scheduler._process_result(str(task.task_id), result)
        assert ledger.get_task(task.task_id).current_attempt == expected_attempt
    task = ledger.get_task(task.task_id)
    assert task.status == TaskStatus.FAILED
    checkpoints = ledger.list_checkpoints(task.task_id)
    assert len({cp.attempt_id for cp in checkpoints}) == 2
    attempts = cost_enforcer._backend.fetchall("SELECT * FROM task_attempts")
    assert len(attempts) == 2
    assert all(a["status"] == "failed" and a["completed_at"] for a in attempts)


def test_api_routes_inspect_private_stopped_field():
    """Scheduler control endpoints must use a public lifecycle interface."""
    from animus_forge.api_routes import mission_scheduler as routes

    source = inspect.getsource(routes)
    assert "mission_scheduler._stopped" not in source, "API routes read private _stopped field"
    assert "is_running" in source, "API routes should use the public is_running interface"


@pytest.mark.asyncio()
@pytest.mark.parametrize("initial_shutdown", [False, True])
async def test_api_with_real_scheduler_lifecycle(
    ledger, lease_manager, worker_pool, cost_enforcer, metrics, monkeypatch, initial_shutdown
):
    """Exercise a real scheduler independently of prior API lifespan tests."""
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
    monkeypatch.setitem(api_state._app_state, "shutting_down", initial_shutdown)
    transport = ASGITransport(app=app)
    # ASGITransport does not run lifespan. Supply and restore the state needed
    # by this test instead of inheriting a previous TestClient's shutdown flag.
    with (
        patch.dict(api_state._app_state, {"shutting_down": False}),
        patch.object(api_state, "mission_scheduler", scheduler),
    ):
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/v1/scheduler/start", headers=headers)
                assert response.status_code == 200
                assert response.json()["status"] == "started"

                response = await client.get("/v1/scheduler/status", headers=headers)
                assert response.status_code == 200
                status = response.json()
                assert status["is_running"] is True
                assert "lifecycle_state" in status

                response = await client.post("/v1/scheduler/stop", headers=headers)
                assert response.status_code == 200
        finally:
            await scheduler.stop()
    assert api_state._app_state["shutting_down"] is initial_shutdown


@pytest.mark.asyncio()
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
    result = dispatch_result(
        scheduler,
        sample_task,
        usage=[
            {
                "provider": "test",
                "model": "fixture",
                "tokens_input": 10,
                "tokens_output": 5,
                "cost_usd": "0.001",
            }
        ],
    )
    for _ in range(2):
        await scheduler._process_result(str(sample_task.task_id), result)
    assert "_scheduler_meta" in result  # The consumer must not mutate the envelope.
    rows = cost_enforcer._backend.fetchall(
        "SELECT * FROM cost_events WHERE task_id = ?", (str(sample_task.task_id),)
    )
    assert len(rows) == 1
    assert cost_enforcer.mission_spend(str(sample_mission.mission_id)) == Decimal("0.001")
    assert len(ledger.list_checkpoints(sample_task.task_id)) == 1


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


def test_budget_reservation_serializes_separate_connections(tmp_path):
    """Two simultaneous writers cannot reserve the same remaining budget."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = str(tmp_path / "budget.db")
    enforcers = [CostEnforcer(SQLiteBackend(path), global_cap_usd=Decimal("1")) for _ in range(2)]
    barrier = Barrier(2)

    def reserve(index):
        barrier.wait(timeout=5)
        try:
            return enforcers[index].reserve(
                str(index), f"mission-{index}", Decimal("0.60"), mission_cap=Decimal("1")
            )[0]
        finally:
            enforcers[index]._backend.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(reserve, range(2))) == [False, True]
        assert enforcers[0].reserved() == Decimal("0.60")
    finally:
        for enforcer in enforcers:
            enforcer._backend.close()


@pytest.mark.parametrize("amount", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_reservations_rejected(cost_enforcer, amount):
    with pytest.raises(ValueError):
        cost_enforcer.reserve("attempt", "mission", amount)
    assert cost_enforcer.reserved() == 0


def test_zero_cap_and_global_projected_spend(cost_enforcer):
    assert not cost_enforcer.reserve("zero", "mission", Decimal("0.01"), mission_cap=Decimal("0"))[
        0
    ]
    cost_enforcer.global_cap = Decimal("0.50")
    cost_enforcer.record("another-mission", "fixture", cost_usd=Decimal("0.45"))
    assert not cost_enforcer.reserve("global", "mission", Decimal("0.10"))[0]


@pytest.mark.asyncio()
async def test_result_transaction_rolls_back_and_accepts_redelivery(
    ledger, lease_manager, worker_pool, cost_enforcer, sample_mission, sample_task
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
    )
    result = dispatch_result(scheduler, sample_task)
    with patch.object(ledger, "save_checkpoint", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError, match="write failed"):
            await scheduler._process_result(str(sample_task.task_id), result)
    assert cost_enforcer._backend.fetchall("SELECT * FROM cost_events") == []
    assert cost_enforcer.reserved() == Decimal("0.10")
    assert lease_manager.get_lease_for_task(str(sample_task.task_id)) is not None
    assert ledger.get_task(sample_task.task_id).status == TaskStatus.RUNNING
    await scheduler._process_result(str(sample_task.task_id), result)
    assert ledger.get_task(sample_task.task_id).status == TaskStatus.COMPLETED
    assert len(ledger.list_checkpoints(sample_task.task_id)) == 1
    assert cost_enforcer.reserved() == 0


@pytest.mark.asyncio()
@pytest.mark.parametrize("bad_meta", [None, {}, {"attempt_id": "wrong"}])
async def test_unfenced_result_cannot_settle_current_attempt(
    ledger, lease_manager, worker_pool, cost_enforcer, sample_mission, sample_task, bad_meta
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
    )
    result = dispatch_result(scheduler, sample_task)
    if bad_meta and "attempt_id" in bad_meta:
        result["_scheduler_meta"].update(bad_meta)
    else:
        result["_scheduler_meta"] = bad_meta
    await scheduler._process_result(str(sample_task.task_id), result)
    assert ledger.get_task(sample_task.task_id).status == TaskStatus.RUNNING
    assert ledger.list_checkpoints(sample_task.task_id) == []
    assert cost_enforcer._backend.fetchall("SELECT * FROM cost_events") == []
    assert cost_enforcer.reserved() == Decimal("0.10")


@pytest.mark.asyncio()
@pytest.mark.parametrize("failure", ["malformed", "killed"])
async def test_unknown_usage_retains_reservation(
    ledger, lease_manager, worker_pool, cost_enforcer, sample_mission, sample_task, failure
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
    )
    result = dispatch_result(scheduler, sample_task, status="failed")
    attempt_id = result["_scheduler_meta"]["attempt_id"]
    if failure == "malformed":
        result["usage"] = [{"provider": "missing-fields"}]
    else:
        result["_scheduler_meta"]["killed"] = True
    await scheduler._process_result(str(sample_task.task_id), result)
    assert cost_enforcer.reserved() == Decimal("0.10")
    assert cost_enforcer._backend.fetchall("SELECT * FROM cost_events") == []
    assert lease_manager.get_attempt(attempt_id)["cost_usd"] is None


@pytest.mark.asyncio()
@pytest.mark.parametrize("mode", ["process", "container"])
@pytest.mark.parametrize(
    "failure",
    ["crash", "malformed", "empty", "non_object", "supervisor", "citizen", "known_failure", "none"],
)
async def test_worker_protocol_failure_preserves_unknown_cost(
    ledger,
    lease_manager,
    worker_pool,
    cost_enforcer,
    sample_mission,
    sample_task,
    mode,
    failure,
    monkeypatch,
    capsys,
):
    """Infrastructure failures cannot masquerade as a worker's zero-cost result."""
    from animus_forge.scheduler import worker_main
    from animus_forge.scheduler.worker_process import WorkerResult

    ledger.create_mission(sample_mission)
    ledger.create_task(sample_task)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
    ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)
    scheduler = MissionScheduler(ledger, lease_manager, worker_pool, cost_enforcer)
    envelope = dispatch_result(scheduler, sample_task)
    meta = envelope["_scheduler_meta"]
    await worker_pool.start()
    try:
        slot = worker_pool._slots["0"]
        slot.task_id = str(sample_task.task_id)
        slot.lease_id = meta["lease_id"]
        slot.lease_generation = meta["generation"]
        slot.attempt_id = meta["attempt_id"]
        data = {"status": "completed", "summary": "local"}
        if failure in ("citizen", "known_failure"):

            class FixtureCitizen:
                def run(self, **kwargs):
                    if failure == "citizen":
                        raise RuntimeError("provider charge happened before crash")
                    return CitizenOutput(status="failed", summary="local validation rejected")

            monkeypatch.setitem(worker_main._CITIZEN_REGISTRY, "planner", FixtureCitizen)
            monkeypatch.setattr(
                worker_main.sys,
                "stdin",
                io.StringIO(
                    json.dumps(
                        {
                            "citizen_role": "planner",
                            "task_id": str(sample_task.task_id),
                            "mission_id": str(sample_mission.mission_id),
                            "context": {
                                "mission_objective": "test",
                                "task_description": "test",
                                "repository": "test",
                            },
                        }
                    )
                ),
            )
            worker_main.main()
            data = json.loads(capsys.readouterr().out)
        if mode == "process":
            result = WorkerResult(
                ok=failure in ("none", "non_object", "citizen", "known_failure"),
                data=[] if failure == "non_object" else data,
                error=None if failure == "none" else "Worker protocol failure",
                returncode=1 if failure == "crash" else 0,
            )
            slot.worker = SimpleNamespace(wait=AsyncMock(return_value=result))
            if failure == "supervisor":
                slot.worker.wait.side_effect = RuntimeError("read failed")
            await worker_pool._supervise_process(str(sample_task.task_id), slot.slot_id)
        else:
            stdout = {
                "crash": b"",
                "malformed": b"not JSON",
                "empty": b"",
                "non_object": b"[]",
                "supervisor": b"",
                "none": b'{"status": "completed", "summary": "local"}',
                "citizen": json.dumps(data).encode(),
                "known_failure": json.dumps(data).encode(),
            }[failure]
            process = SimpleNamespace(
                returncode=1 if failure == "crash" else 0,
                communicate=AsyncMock(
                    return_value=(stdout, b"fixture crash" if failure == "crash" else b"")
                ),
            )
            if failure == "supervisor":
                process.communicate.side_effect = RuntimeError("read failed")
            worker_pool.container = SimpleNamespace(
                run_task_async=AsyncMock(
                    return_value=SimpleNamespace(container_id="fixture", process=process)
                )
            )
            await worker_pool._supervise_container(
                str(sample_task.task_id),
                str(sample_mission.mission_id),
                "planner",
                TaskContext(mission_objective="test", task_description="test", repository="test"),
                slot.slot_id,
                30,
            )
        task_id, payload = (await worker_pool.results()).get_nowait()
        await scheduler._process_result(task_id, payload)
        attempt = lease_manager.get_attempt(meta["attempt_id"])
        if failure in ("none", "known_failure"):
            assert cost_enforcer.reserved() == 0
            assert attempt["cost_usd"] == "0"
            expected_status = TaskStatus.COMPLETED if failure == "none" else TaskStatus.READY
            assert ledger.get_task(sample_task.task_id).status == expected_status
        else:
            assert cost_enforcer.reserved() == Decimal("0.10")
            assert attempt["cost_usd"] is None
            assert cost_enforcer._backend.fetchall("SELECT * FROM cost_events") == []
            assert ledger.get_task(sample_task.task_id).status == TaskStatus.READY
            assert (
                ledger.get_latest_checkpoint(sample_task.task_id).outputs["usage_complete"] is False
            )
    finally:
        await worker_pool.stop()
