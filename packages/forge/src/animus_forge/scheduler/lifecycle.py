"""Supervised lifecycle primitives for long-running scheduler loops.

Provides a small, reusable abstraction for starting, stopping, and observing
background coroutines.  A ``LoopSupervisor`` owns a set of named loops, records
their health, and applies a configurable restart policy when a loop exits
unexpectedly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class SchedulerLifecycleState(StrEnum):
    """Canonical scheduler lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    FAILED = "failed"


class RestartPolicy(StrEnum):
    """How the supervisor reacts when a supervised loop exits abnormally."""

    NEVER = "never"
    ON_FAILURE = "on_failure"


@dataclass
class RestartConfig:
    """Configuration for loop restart behavior."""

    policy: RestartPolicy = RestartPolicy.ON_FAILURE
    max_restarts: int = 3
    delay_seconds: float = 0.5


@dataclass
class LoopHandle:
    """Runtime handle for one supervised loop."""

    name: str
    coro_factory: Callable[[], Awaitable[None]]
    task: asyncio.Task | None = None
    state: SchedulerLifecycleState = SchedulerLifecycleState.STOPPED
    last_tick_at: datetime | None = None
    last_error: str | None = None
    restart_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
        }


@dataclass
class SchedulerStatusSnapshot:
    """Public health snapshot for a supervised scheduler."""

    lifecycle_state: SchedulerLifecycleState
    loops: dict[str, dict[str, Any]]
    active_workers: int = 0
    free_slots: int = 0
    global_spend_usd: str = "0.00"
    global_cap_usd: str = "0.00"
    last_tick_at: datetime | None = None
    last_error: str | None = None
    restart_count: int = 0
    metrics_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "lifecycle_state": self.lifecycle_state.value,
            "is_running": self.lifecycle_state
            in (
                SchedulerLifecycleState.STARTING,
                SchedulerLifecycleState.RUNNING,
                SchedulerLifecycleState.DEGRADED,
                SchedulerLifecycleState.STOPPING,
            ),
            "is_ready": self.lifecycle_state == SchedulerLifecycleState.RUNNING,
            "is_healthy": self.lifecycle_state == SchedulerLifecycleState.RUNNING,
            "loops": self.loops,
            "active_workers": self.active_workers,
            "free_slots": self.free_slots,
            "global_spend_usd": self.global_spend_usd,
            "global_cap_usd": self.global_cap_usd,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
        }
        if self.metrics_summary is not None:
            result["metrics_summary"] = self.metrics_summary
        return result


class LoopSupervisor:
    """Owns a set of named background loops and their lifecycle.

    Usage::

        supervisor = LoopSupervisor()
        supervisor.register("dispatcher", dispatcher_coro_factory)
        supervisor.register("consumer", consumer_coro_factory)
        await supervisor.start()
        # ... later ...
        await supervisor.stop()

    Each loop is started as an ``asyncio.Task`` via its coroutine factory.  If a
    loop raises an exception (other than ``asyncio.CancelledError`` during a
    stop), the supervisor records the error and applies the configured restart
    policy.
    """

    def __init__(
        self,
        *,
        restart_config: RestartConfig | None = None,
    ):
        self._loops: dict[str, LoopHandle] = {}
        self._restart_config = restart_config or RestartConfig()
        self._stop_event = asyncio.Event()
        self._state = SchedulerLifecycleState.STOPPED

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        coro_factory: Callable[[], Awaitable[None]],
    ) -> None:
        """Register a named loop."""
        if name in self._loops:
            raise ValueError(f"Loop already registered: {name}")
        self._loops[name] = LoopHandle(name=name, coro_factory=coro_factory)

    def unregister(self, name: str) -> bool:
        """Remove a registered loop if it is not currently running."""
        handle = self._loops.get(name)
        if handle is None:
            return False
        if handle.state in (SchedulerLifecycleState.RUNNING, SchedulerLifecycleState.STARTING):
            raise RuntimeError(f"Cannot unregister running loop: {name}")
        del self._loops[name]
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def state(self) -> SchedulerLifecycleState:
        return self._state

    @property
    def stop_requested(self) -> asyncio.Event:
        """Event loops can watch to determine when to exit."""
        return self._stop_event

    @property
    def should_continue(self) -> bool:
        """Convenience for loop ``while`` conditions."""
        return not self._stop_event.is_set()

    async def start(self) -> None:
        """Start all registered loops."""
        if self._state in (SchedulerLifecycleState.STARTING, SchedulerLifecycleState.RUNNING):
            return

        self._state = SchedulerLifecycleState.STARTING
        self._stop_event.clear()

        for handle in self._loops.values():
            await self._start_loop(handle)

        self._recompute_state()
        logger.info("LoopSupervisor entered state %s", self._state.value)

    async def stop(self, *, timeout: float | None = 5.0) -> None:
        """Signal all loops to stop and await their tasks."""
        if self._state in (SchedulerLifecycleState.STOPPED, SchedulerLifecycleState.STOPPING):
            return

        previous_state = self._state
        self._state = SchedulerLifecycleState.STOPPING
        self._stop_event.set()

        # Cancel any loop that does not exit promptly.
        tasks: list[asyncio.Task] = []
        for handle in self._loops.values():
            if handle.task and not handle.task.done():
                handle.task.cancel()
                tasks.append(handle.task)

        if tasks and timeout is not None:
            try:
                await asyncio.wait(tasks, timeout=timeout)
            except asyncio.CancelledError:
                pass

        for handle in self._loops.values():
            if handle.task and not handle.task.done():
                logger.warning("Loop %s did not stop within %ss", handle.name, timeout)
            handle.state = SchedulerLifecycleState.STOPPED
            handle.task = None

        if previous_state != SchedulerLifecycleState.STOPPING:
            self._state = SchedulerLifecycleState.STOPPED
        logger.info("LoopSupervisor stopped")

    # ------------------------------------------------------------------
    # Loop observation helpers
    # ------------------------------------------------------------------

    def mark_tick(self, name: str) -> None:
        """Record that a loop completed a successful iteration."""
        handle = self._loops.get(name)
        if handle is None:
            return
        handle.last_tick_at = datetime.now(UTC)
        self._recompute_state()

    def record_error(self, name: str, error: str) -> None:
        """Record an error for a loop without changing its state."""
        handle = self._loops.get(name)
        if handle is None:
            return
        handle.last_error = error
        handle.last_tick_at = datetime.now(UTC)
        logger.error("Loop %s error: %s", name, error)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a dict of loop-name → loop-status dict."""
        return {name: handle.to_dict() for name, handle in self._loops.items()}

    @property
    def is_healthy(self) -> bool:
        """True if all registered loops are currently RUNNING."""
        if not self._loops:
            return False
        return all(h.state == SchedulerLifecycleState.RUNNING for h in self._loops.values())

    @property
    def is_running(self) -> bool:
        """True if the supervisor has been started and not fully stopped."""
        return self._state in (
            SchedulerLifecycleState.STARTING,
            SchedulerLifecycleState.RUNNING,
            SchedulerLifecycleState.DEGRADED,
            SchedulerLifecycleState.STOPPING,
        )

    @property
    def last_error(self) -> str | None:
        """Most recent error across all loops."""
        errors = [h.last_error for h in self._loops.values() if h.last_error]
        return errors[-1] if errors else None

    @property
    def last_tick_at(self) -> datetime | None:
        """Most recent tick across all loops."""
        ticks = [h.last_tick_at for h in self._loops.values() if h.last_tick_at]
        return max(ticks) if ticks else None

    @property
    def restart_count(self) -> int:
        """Total restart attempts across all loops."""
        return sum(h.restart_count for h in self._loops.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _start_loop(self, handle: LoopHandle) -> None:
        """Start one loop and attach a done callback."""
        handle.state = SchedulerLifecycleState.STARTING
        handle.task = asyncio.create_task(
            self._run_loop(handle),
            name=f"supervisor-loop-{handle.name}",
        )

    async def _run_loop(self, handle: LoopHandle) -> None:
        """Wrapper that runs the loop coroutine and applies restart policy."""
        while True:
            handle.state = SchedulerLifecycleState.RUNNING
            self._recompute_state()
            try:
                await handle.coro_factory()
            except asyncio.CancelledError:
                logger.debug("Loop %s cancelled", handle.name)
                handle.state = SchedulerLifecycleState.STOPPED
                break
            except Exception as exc:
                handle.last_error = f"{type(exc).__name__}: {exc}"
                handle.last_tick_at = datetime.now(UTC)
                logger.exception("Loop %s failed", handle.name)

                if self._stop_event.is_set() or self._restart_config.policy == RestartPolicy.NEVER:
                    handle.state = SchedulerLifecycleState.FAILED
                    break

                if handle.restart_count >= self._restart_config.max_restarts:
                    logger.error("Loop %s exceeded max restarts", handle.name)
                    handle.state = SchedulerLifecycleState.FAILED
                    break

                handle.restart_count += 1
                handle.state = SchedulerLifecycleState.DEGRADED
                logger.info(
                    "Restarting loop %s (%d/%d) in %ss",
                    handle.name,
                    handle.restart_count,
                    self._restart_config.max_restarts,
                    self._restart_config.delay_seconds,
                )
                await asyncio.sleep(self._restart_config.delay_seconds)
            else:
                # Loop exited cleanly without cancellation.
                if self._stop_event.is_set():
                    logger.debug("Loop %s exited cleanly during stop", handle.name)
                    handle.state = SchedulerLifecycleState.STOPPED
                    break

                logger.warning("Loop %s exited cleanly", handle.name)
                if self._restart_config.policy == RestartPolicy.NEVER:
                    handle.state = SchedulerLifecycleState.FAILED
                    break
                if handle.restart_count >= self._restart_config.max_restarts:
                    handle.state = SchedulerLifecycleState.FAILED
                    break
                handle.restart_count += 1
                handle.state = SchedulerLifecycleState.DEGRADED
                await asyncio.sleep(self._restart_config.delay_seconds)

        self._recompute_state()

    def _recompute_state(self) -> None:
        """Recompute aggregate state from loop states and tick history."""
        if not self._loops:
            self._state = SchedulerLifecycleState.STOPPED
            return

        if self._state == SchedulerLifecycleState.STOPPING:
            # Stay in STOPPING until stop() completes.
            return

        states = {h.state for h in self._loops.values()}
        any_failed = SchedulerLifecycleState.FAILED in states
        any_running = SchedulerLifecycleState.RUNNING in states
        any_starting = SchedulerLifecycleState.STARTING in states
        any_degraded = SchedulerLifecycleState.DEGRADED in states

        if any_failed:
            self._state = SchedulerLifecycleState.FAILED
            return

        # Startup phase: no loop has completed a tick yet.
        has_ticked = any(h.last_tick_at is not None for h in self._loops.values())
        if not has_ticked:
            if any_running or any_starting or any_degraded:
                self._state = SchedulerLifecycleState.STARTING
                return
            # Loops are present but none have ever ticked and none are active.
            self._state = SchedulerLifecycleState.STOPPED
            return

        # Past initial startup. A loop that restarted is still considered active
        # as long as it is running or transitioning (starting/degraded).
        any_active = any_running or any_starting or any_degraded
        if not any_active:
            # All loops stopped unexpectedly without reaching FAILED.
            self._state = SchedulerLifecycleState.FAILED
            return

        any_restarted = any(h.restart_count > 0 for h in self._loops.values())
        if any_restarted:
            self._state = SchedulerLifecycleState.DEGRADED
        else:
            self._state = SchedulerLifecycleState.RUNNING
