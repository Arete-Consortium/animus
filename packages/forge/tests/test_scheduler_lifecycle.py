"""Focused tests for the supervised scheduler lifecycle primitives."""

from __future__ import annotations

import asyncio

import pytest

from animus_forge.scheduler.lifecycle import (
    LoopSupervisor,
    RestartConfig,
    RestartPolicy,
    SchedulerLifecycleState,
)


@pytest.mark.asyncio()
async def test_supervisor_start_stop_transitions():
    """LoopSupervisor moves through STOPPED -> STARTING -> RUNNING -> STOPPED."""
    started = asyncio.Event()

    async def body():
        started.set()
        while True:
            try:
                await asyncio.wait_for(asyncio.Event().wait(), timeout=0.05)
            except TimeoutError:
                sup.mark_tick("body")

    sup = LoopSupervisor()
    sup.register("body", body)

    assert sup.state == SchedulerLifecycleState.STOPPED
    assert not sup.is_running
    assert not sup.is_healthy

    await sup.start()
    assert sup.state in (SchedulerLifecycleState.STARTING, SchedulerLifecycleState.RUNNING)
    assert sup.is_running

    await asyncio.wait_for(started.wait(), timeout=1.0)
    # Once the loop has ticked, the aggregate state should be RUNNING.
    await asyncio.sleep(0.15)
    assert sup.state == SchedulerLifecycleState.RUNNING
    assert sup.is_healthy

    await sup.stop(timeout=1.0)
    assert sup.state == SchedulerLifecycleState.STOPPED
    assert not sup.is_running
    assert not sup.is_healthy


@pytest.mark.asyncio()
async def test_supervisor_idempotent_start_stop():
    """Multiple start/stop calls are safe."""

    async def body():
        while True:
            try:
                await asyncio.wait_for(asyncio.Event().wait(), timeout=0.05)
            except TimeoutError:
                sup.mark_tick("body")

    sup = LoopSupervisor()
    sup.register("body", body)

    await sup.start()
    await sup.start()
    assert sup.is_running

    await sup.stop(timeout=1.0)
    await sup.stop(timeout=1.0)
    assert sup.state == SchedulerLifecycleState.STOPPED


@pytest.mark.asyncio()
async def test_supervisor_restarts_failed_loop():
    """ON_FAILURE restarts a loop that raises until max_restarts."""
    fail_count = 0

    async def flaky():
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 2:
            raise RuntimeError(f"planned failure {fail_count}")
        while True:
            try:
                await asyncio.wait_for(asyncio.Event().wait(), timeout=0.05)
            except TimeoutError:
                sup.mark_tick("flaky")

    sup = LoopSupervisor(
        restart_config=RestartConfig(
            policy=RestartPolicy.ON_FAILURE,
            max_restarts=3,
            delay_seconds=0.05,
        ),
    )
    sup.register("flaky", flaky)

    await sup.start()
    await asyncio.sleep(0.4)

    assert sup.is_running
    snap = sup.snapshot()["flaky"]
    assert snap["restart_count"] == 2
    assert snap["state"] == "running"
    assert sup.state == SchedulerLifecycleState.DEGRADED

    await sup.stop(timeout=1.0)


@pytest.mark.asyncio()
async def test_supervisor_reports_failure_when_restarts_exhausted():
    """After max_restarts the supervisor enters FAILED."""

    async def always_fails():
        raise RuntimeError("boom")

    sup = LoopSupervisor(
        restart_config=RestartConfig(
            policy=RestartPolicy.ON_FAILURE,
            max_restarts=2,
            delay_seconds=0.01,
        ),
    )
    sup.register("always_fails", always_fails)

    await sup.start()
    await asyncio.sleep(0.2)

    assert sup.state == SchedulerLifecycleState.FAILED
    assert not sup.is_running
    assert not sup.is_healthy
    assert "RuntimeError" in (sup.last_error or "")

    await sup.stop(timeout=1.0)


@pytest.mark.asyncio()
async def test_supervisor_never_restart_policy():
    """NEVER restart policy marks the loop FAILED on first failure."""

    async def always_fails():
        raise RuntimeError("boom")

    sup = LoopSupervisor(
        restart_config=RestartConfig(
            policy=RestartPolicy.NEVER,
            max_restarts=0,
            delay_seconds=0.0,
        ),
    )
    sup.register("always_fails", always_fails)

    await sup.start()
    await asyncio.sleep(0.05)

    assert sup.state == SchedulerLifecycleState.FAILED
    snap = sup.snapshot()["always_fails"]
    assert snap["state"] == "failed"
    assert snap["restart_count"] == 0

    await sup.stop(timeout=1.0)


@pytest.mark.asyncio()
async def test_supervisor_snapshot_includes_all_loops():
    """snapshot() exposes per-loop state and aggregate tick/error info."""

    async def body():
        while True:
            try:
                await asyncio.wait_for(asyncio.Event().wait(), timeout=0.05)
            except TimeoutError:
                sup.mark_tick("body")

    sup = LoopSupervisor()
    sup.register("body", body)
    await sup.start()
    await asyncio.sleep(0.15)

    snap = sup.snapshot()
    assert set(snap.keys()) == {"body"}
    assert snap["body"]["state"] == "running"
    assert snap["body"]["last_tick_at"] is not None
    assert snap["body"]["restart_count"] == 0
    assert sup.last_tick_at is not None

    await sup.stop(timeout=1.0)
