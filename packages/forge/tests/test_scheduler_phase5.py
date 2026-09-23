"""Tests for Phase 5 scheduler components: LeaseManager, CostEnforcer, WorkerPool, MissionScheduler."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from animus_forge.missions.domain import (
    Mission,
    MissionStatus,
    Task,
    TaskContext,
    TaskStatus,
)
from animus_forge.missions.store import MissionLedger
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
    # FKs must be explicitly enabled per connection for SQLite
    with b.transaction():
        b.execute("PRAGMA foreign_keys=ON")
    return b


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


# ---------------------------------------------------------------------------
# LeaseManager
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("lease_test_records")
class TestLeaseManager:
    def test_acquire_lease(self, lease_manager):
        lease = lease_manager.acquire(
            task_id="task-1",
            mission_id="mission-1",
            citizen_role="builder",
            worker_id="slot-0",
            ttl_seconds=120,
        )
        assert lease is not None
        assert lease.task_id == "task-1"
        assert lease.status == LeaseStatus.ACTIVE
        assert lease.expires_at > lease.acquired_at

    def test_acquire_duplicate_fails(self, lease_manager):
        lease_manager.acquire(
            task_id="task-1", mission_id="mission-1", citizen_role="b", worker_id="w1"
        )
        with pytest.raises(LeaseAcquireError) as exc_info:
            lease_manager.acquire(
                task_id="task-1", mission_id="mission-1", citizen_role="b", worker_id="w2"
            )
        assert exc_info.value.reason == "already_leased"

    def test_renew_extends_expiry(self, lease_manager):
        lease = lease_manager.acquire(
            task_id="t1", mission_id="m", citizen_role="b", worker_id="w1", ttl_seconds=10
        )
        original_expiry = lease.expires_at
        # Wait a tiny bit so renew actually changes the timestamp
        import time

        time.sleep(0.05)
        renewed = lease_manager.renew(lease.lease_id, ttl_seconds=20)
        assert renewed is not None
        assert renewed.expires_at > original_expiry

    def test_release_marks_released(self, lease_manager):
        lease = lease_manager.acquire(
            task_id="t1", mission_id="m", citizen_role="b", worker_id="w1"
        )
        released = lease_manager.release(lease.lease_id, outcome="completed")
        assert released is not None
        assert released.status == LeaseStatus.RELEASED
        assert released.outcome == "completed"

    def test_recover_expired(self, lease_manager):
        lease = lease_manager.acquire(
            task_id="t1", mission_id="m", citizen_role="b", worker_id="w1", ttl_seconds=1
        )
        # Fast-forward past expiry
        future = datetime.now(UTC) + timedelta(seconds=5)
        recovered = lease_manager.recover_expired(as_of=future)
        assert recovered == ["t1"]

        # Expired leases are removed from current and recorded in history.
        assert lease_manager.get_lease(lease.lease_id) is None
        history = lease_manager.history_for_task("t1")
        assert any(h["status"] == LeaseStatus.EXPIRED for h in history)

    def test_get_active_leases(self, lease_manager):
        lease_manager.acquire(task_id="t1", mission_id="m", citizen_role="b", worker_id="w1")
        lease_manager.acquire(task_id="t2", mission_id="m", citizen_role="b", worker_id="w2")
        active = lease_manager.get_active_leases()
        assert len(active) == 2

    def test_get_lease_for_task(self, lease_manager):
        lease = lease_manager.acquire(
            task_id="t1", mission_id="m", citizen_role="b", worker_id="w1"
        )
        fetched = lease_manager.get_lease_for_task("t1")
        assert fetched is not None
        assert fetched.lease_id == lease.lease_id


# ---------------------------------------------------------------------------
# CostEnforcer
# ---------------------------------------------------------------------------


class TestCostEnforcer:
    def test_record_and_retrieve(self, cost_enforcer):
        cost_enforcer.record(
            mission_id="m1",
            operation="llm_call",
            provider="openai",
            model="gpt-4o",
            tokens_input=1000,
            tokens_output=500,
        )
        spend = cost_enforcer.mission_spend("m1")
        assert spend > Decimal("0")

    def test_estimate_cost(self, cost_enforcer):
        cost = cost_enforcer.estimate_cost("openai", "gpt-4o", 1_000_000, 0)
        assert cost == Decimal("5.00")

    def test_mission_remaining(self, cost_enforcer):
        cost_enforcer.record(mission_id="m1", operation="x", cost_usd=Decimal("2.00"))
        remaining = cost_enforcer.mission_remaining("m1", cap=Decimal("5.00"))
        assert remaining == Decimal("3.00")

    def test_can_start_task_under_budget(self, cost_enforcer):
        ok, reason = cost_enforcer.can_start_task(
            "m1", estimated_cost=Decimal("1.00"), mission_cap=Decimal("5.00")
        )
        assert ok is True
        assert reason == "ok"

    def test_can_start_task_over_budget(self, cost_enforcer):
        cost_enforcer.record(mission_id="m1", operation="x", cost_usd=Decimal("9.50"))
        ok, reason = cost_enforcer.can_start_task(
            "m1", estimated_cost=Decimal("1.00"), mission_cap=Decimal("10.00")
        )
        assert ok is False
        assert "budget exhausted" in reason

    def test_spend_report(self, cost_enforcer):
        cost_enforcer.record(mission_id="m1", operation="a", cost_usd=Decimal("1.00"))
        cost_enforcer.record(mission_id="m2", operation="b", cost_usd=Decimal("2.00"))
        report = cost_enforcer.spend_report()
        assert Decimal(report["global_spend_usd"]) == Decimal("3.00")
        assert len(report["by_mission"]) == 2

    def test_set_rate(self, cost_enforcer):
        cost_enforcer.set_rate("custom", "model-a", Decimal("1.50"))
        cost = cost_enforcer.estimate_cost("custom", "model-a", 1_000_000, 0)
        assert cost == Decimal("1.50")


# ---------------------------------------------------------------------------
# CitizenWorkerPool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
@pytest.mark.usefixtures("lease_test_records")
class TestCitizenWorkerPool:
    async def test_worker_exit_metadata_is_separate_from_citizen_output(self, worker_pool):
        await worker_pool.start()
        try:
            await worker_pool._finish_task(
                "task-1",
                "0",
                {
                    "status": "completed",
                    "summary": "done",
                    "_killed": False,
                    "_timed_out": False,
                    "_returncode": 0,
                },
            )
            _, result = await (await worker_pool.results()).get()
            meta = result.pop("_scheduler_meta")
            assert result == {"status": "completed", "summary": "done"}
            assert meta["killed"] is False
            assert meta["timed_out"] is False
            assert meta["returncode"] == 0
        finally:
            await worker_pool.stop()

    async def test_start_stop(self, worker_pool):
        await worker_pool.start()
        assert worker_pool.active_count() == 0
        assert worker_pool.free_count() == 2
        await worker_pool.stop()

    async def test_submit_and_result(self, worker_pool, sample_mission):
        await worker_pool.start()
        ctx = TaskContext(
            mission_objective=sample_mission.objective,
            task_description="Plan the fix",
            repository=sample_mission.repository,
        )
        lease_id = await worker_pool.submit(
            task_id="task-1",
            citizen_role="planner",
            context=ctx,
            mission_id="mission-1",
            ttl_seconds=30,
        )
        assert lease_id is not None

        # Wait for result
        result = await asyncio.wait_for(
            (await worker_pool.results()).get(),
            timeout=10.0,
        )
        assert result[0] == "task-1"
        assert "status" in result[1]
        await worker_pool.stop()

    async def test_pool_full_returns_none(self, worker_pool):
        await worker_pool.start()
        ctx = TaskContext(
            mission_objective="o",
            task_description="d",
            repository="r",
        )
        # Fill both slots with long-running (or slow) tasks
        lease1 = await worker_pool.submit("t1", "planner", ctx, mission_id="m", ttl_seconds=300)
        lease2 = await worker_pool.submit("t2", "planner", ctx, mission_id="m", ttl_seconds=300)
        assert lease1 is not None
        assert lease2 is not None

        # Third should fail (no slot)
        lease3 = await worker_pool.submit("t3", "planner", ctx, mission_id="m", ttl_seconds=300)
        assert lease3 is None
        await worker_pool.stop()

    async def test_kill_slot(self, worker_pool):
        await worker_pool.start()
        ctx = TaskContext(
            mission_objective="o",
            task_description="d",
            repository="r",
        )
        await worker_pool.submit("t1", "planner", ctx, mission_id="m", ttl_seconds=300)
        assert worker_pool.active_count() == 1

        killed = worker_pool.kill_slot("0")
        assert killed is True
        assert worker_pool.active_count() == 0
        await worker_pool.stop()

    async def test_recovery_loop(self, worker_pool, lease_manager):
        await worker_pool.start()
        # Create an expired lease manually
        lease = lease_manager.acquire(
            task_id="t-expired",
            mission_id="m",
            citizen_role="b",
            worker_id="w1",
            ttl_seconds=1,
        )
        assert lease is not None
        # Fast-forward
        recovered = lease_manager.recover_expired(as_of=datetime.now(UTC) + timedelta(seconds=10))
        assert recovered == ["t-expired"]
        await worker_pool.stop()

    async def test_container_mode_dispatches_via_manager(self, lease_manager):
        """When isolation_mode='container', submit delegates to ContainerManager."""

        class FakeContainerManager:
            def __init__(self):
                self.calls = []

            def is_available(self):
                return True

            async def run_task_async(self, **kwargs):
                self.calls.append(kwargs)
                output = {"status": "success", "summary": "mock container"}
                process = SimpleNamespace(
                    communicate=AsyncMock(return_value=(json.dumps(output).encode(), b"")),
                    returncode=0,
                )
                return SimpleNamespace(container_id="fixture-container", process=process)

        fake = FakeContainerManager()
        pool = CitizenWorkerPool(
            lease_manager,
            config=PoolConfig(max_workers=1, isolation_mode="container"),
            container_manager=fake,
        )
        await pool.start()
        ctx = TaskContext(
            mission_objective="o",
            task_description="d",
            repository="r",
        )
        lease_id = await pool.submit("t1", "planner", ctx, mission_id="m", ttl_seconds=300)
        assert lease_id is not None

        result = await asyncio.wait_for(
            (await pool.results()).get(),
            timeout=5.0,
        )
        assert result[0] == "t1"
        assert result[1]["status"] == "success"
        assert len(fake.calls) == 1
        assert fake.calls[0]["citizen_role"] == "planner"
        await pool.stop()


# ---------------------------------------------------------------------------
# MissionScheduler integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestMissionScheduler:
    async def test_run_once_no_ready_tasks(
        self, ledger, lease_manager, worker_pool, cost_enforcer, metrics
    ):
        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_manager,
            worker_pool=worker_pool,
            cost_enforcer=cost_enforcer,
            metrics=metrics,
            config=SchedulerConfig(poll_interval_seconds=0.1),
        )
        await scheduler.start()
        dispatched = await scheduler.run_once()
        assert dispatched == 0
        await scheduler.stop()

    async def test_run_once_dispatches_task(
        self,
        ledger,
        lease_manager,
        worker_pool,
        cost_enforcer,
        metrics,
        sample_mission,
        sample_task,
    ):
        # Setup: create mission and ready task
        sample_mission.status = MissionStatus.PROPOSED
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)
        # Transition mission to RUNNING so scheduler picks it up
        ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
        ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_manager,
            worker_pool=worker_pool,
            cost_enforcer=cost_enforcer,
            metrics=metrics,
            config=SchedulerConfig(poll_interval_seconds=0.1, default_task_ttl_seconds=30),
        )
        await scheduler.start()
        dispatched = await scheduler.run_once()
        assert dispatched == 1

        # Task should now be RUNNING
        task = ledger.get_task(sample_task.task_id)
        assert task.status == TaskStatus.RUNNING

        await scheduler.stop()

    async def test_result_completes_task(
        self,
        ledger,
        lease_manager,
        worker_pool,
        cost_enforcer,
        metrics,
        sample_mission,
        sample_task,
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
            config=SchedulerConfig(poll_interval_seconds=0.1, default_task_ttl_seconds=30),
        )
        await scheduler.start()
        await scheduler.run_once()

        # Wait for the result to be processed
        await asyncio.sleep(3.0)

        task = ledger.get_task(sample_task.task_id)
        # Should be COMPLETED (planner succeeds trivially)
        assert task.status == TaskStatus.COMPLETED, task.error

        await scheduler.stop()

    async def test_mission_awaits_review_when_all_tasks_done(
        self, ledger, lease_manager, worker_pool, cost_enforcer, metrics, sample_mission
    ):
        ledger.create_mission(sample_mission)
        t1 = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="planner",
            description="Plan",
            status=TaskStatus.READY,
        )
        t2 = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="planner",
            description="Also plan",
            status=TaskStatus.READY,
        )
        ledger.create_task(t1)
        ledger.create_task(t2)
        ledger.transition_mission(sample_mission.mission_id, MissionStatus.READY)
        ledger.transition_mission(sample_mission.mission_id, MissionStatus.RUNNING)

        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_manager,
            worker_pool=worker_pool,
            cost_enforcer=cost_enforcer,
            metrics=metrics,
            config=SchedulerConfig(poll_interval_seconds=0.1, default_task_ttl_seconds=30),
        )
        await scheduler.start()
        # Two ticks to dispatch both
        await scheduler.run_once()
        await scheduler.run_once()

        # Wait for both to finish
        await asyncio.sleep(4.0)

        mission = ledger.get_mission(sample_mission.mission_id)
        assert mission.status == MissionStatus.REVIEW

        await scheduler.stop()

    async def test_cost_gate_blocks_task(
        self,
        ledger,
        lease_manager,
        worker_pool,
        cost_enforcer,
        metrics,
        sample_mission,
        sample_task,
    ):
        # Exhaust budget
        cost_enforcer.record(
            mission_id=str(sample_mission.mission_id),
            operation="x",
            cost_usd=Decimal("10.00"),
        )
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
            config=SchedulerConfig(
                default_mission_cap_usd=Decimal("10.00"), poll_interval_seconds=0.1
            ),
        )
        await scheduler.start()
        dispatched = await scheduler.run_once()
        assert dispatched == 0
        await scheduler.stop()

    async def test_status_snapshot(
        self, ledger, lease_manager, worker_pool, cost_enforcer, metrics
    ):
        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_manager,
            worker_pool=worker_pool,
            cost_enforcer=cost_enforcer,
        )
        await scheduler.start()
        snap = scheduler.status()
        assert snap["is_running"] is True
        assert snap["active_workers"] == 0
        assert snap["free_slots"] == 2
        await scheduler.stop()


class TestSchedulerMetrics:
    def test_record_and_count(self, backend, metrics):
        metrics.record("task_dispatched", mission_id="m1", task_id="t1")
        metrics.record("task_dispatched", mission_id="m1", task_id="t2")
        metrics.record("result_processed", mission_id="m1", task_id="t1", value="completed")
        assert metrics.count("task_dispatched") == 2
        assert metrics.count("result_processed") == 1
        assert metrics.count("mission_completed") == 0

    def test_summary(self, backend, metrics):
        metrics.record("task_dispatched", mission_id="m1")
        metrics.record("task_dispatched", mission_id="m2")
        metrics.record("result_processed", mission_id="m1")
        summary = metrics.summary()
        assert summary.get("task_dispatched") == 2
        assert summary.get("result_processed") == 1

    def test_by_mission(self, backend, metrics):
        metrics.record("task_dispatched", mission_id="m1", task_id="t1")
        metrics.record("result_processed", mission_id="m1", task_id="t1", value="completed")
        metrics.record("task_dispatched", mission_id="m2", task_id="t2")
        events = metrics.by_mission("m1")
        assert len(events) == 2
        assert all(e["mission_id"] == "m1" for e in events)

    def test_status_includes_metrics(
        self, ledger, lease_manager, worker_pool, cost_enforcer, metrics
    ):
        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_manager,
            worker_pool=worker_pool,
            cost_enforcer=cost_enforcer,
            metrics=metrics,
            config=SchedulerConfig(poll_interval_seconds=0.1),
        )
        metrics.record("task_dispatched", mission_id="m1")
        snap = scheduler.status()
        assert "metrics_summary" in snap
        assert snap["metrics_summary"].get("task_dispatched") == 1

    def test_reset(self, backend, metrics):
        metrics.record("task_dispatched", mission_id="m1")
        assert metrics.count("task_dispatched") == 1
        metrics.reset()
        assert metrics.count("task_dispatched") == 0


class TestCheckpointPersistence:
    async def test_checkpoint_saved_on_completion(
        self,
        ledger,
        lease_manager,
        worker_pool,
        cost_enforcer,
        metrics,
        sample_mission,
        sample_task,
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
            config=SchedulerConfig(poll_interval_seconds=0.1, default_task_ttl_seconds=30),
        )
        await scheduler.start()
        await scheduler.run_once()
        await asyncio.sleep(3.0)

        checkpoints = ledger.list_checkpoints(sample_task.task_id)
        assert len(checkpoints) >= 1
        assert checkpoints[-1].stage == "completed"
        await scheduler.stop()

    def test_get_latest_checkpoint(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)

        attempt = uuid4()
        ledger.save_checkpoint(sample_task.task_id, attempt, "stage_1", inputs={"step": 1})
        ledger.save_checkpoint(sample_task.task_id, attempt, "stage_2", inputs={"step": 2})

        latest = ledger.get_latest_checkpoint(sample_task.task_id)
        assert latest is not None
        assert latest.stage == "stage_2"

    def test_checkpoint_includes_artifacts(self, ledger, sample_mission, sample_task):
        ledger.create_mission(sample_mission)
        ledger.create_task(sample_task)

        attempt = uuid4()
        ledger.save_checkpoint(
            sample_task.task_id,
            attempt,
            "build",
            outputs={"files": ["src/a.py"]},
            artifacts=[{"name": "patch", "path": "/tmp/patch.diff", "sha256": "abc123"}],
        )

        checkpoints = ledger.list_checkpoints(sample_task.task_id)
        assert len(checkpoints) == 1
        assert checkpoints[0].artifacts[0].name == "patch"
        assert checkpoints[0].artifacts[0].sha256 == "abc123"
