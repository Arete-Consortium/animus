"""CitizenWorkerPool — manage a bounded number of worker processes for missions.

Each worker is a short-lived OS subprocess or container that loads a citizen,
executes one task, and exits.  The pool ensures we don't exceed system
resources and provides reliable timeout, termination, cleanup, and isolation
reporting.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from animus_forge.missions.domain import TaskContext
from animus_forge.scheduler.lease import Lease

if TYPE_CHECKING:
    from animus_forge.scheduler.containers import ContainerManager, ContainerTask
    from animus_forge.scheduler.lease import LeaseManager

from animus_forge.scheduler.worker_process import WorkerProcess

logger = logging.getLogger(__name__)


@dataclass
class WorkerSlot:
    """A slot in the pool, either idle or currently running a task."""

    slot_id: str
    lease_id: str | None = None
    lease_generation: int | None = None
    task_id: str | None = None
    citizen_role: str | None = None
    started_at: float | None = None
    pid: int | None = None
    container_id: str | None = None
    worker: WorkerProcess | None = None
    container_task: Any | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Set once the result has been handled so we cannot double-enqueue.
    handled: bool = False


@dataclass
class PoolConfig:
    """Tuning knobs for the worker pool."""

    max_workers: int = field(default_factory=lambda: max(2, os.cpu_count() or 2))
    worker_timeout_seconds: int = 300  # hard kill after this long
    poll_interval_seconds: float = 2.0
    isolation_mode: str = "process"  # "process" or "container"
    shutdown_behavior: str = "cancel"  # "cancel" or "drain"
    drain_timeout_seconds: float = 10.0


class CitizenWorkerPool:
    """Bounded pool of worker processes executing citizen tasks.

    Usage::

        pool = CitizenWorkerPool(lease_manager, config=PoolConfig(max_workers=4))
        await pool.start()
        # Submit tasks from the scheduler loop
        await pool.submit(task_id="...", citizen_role="builder", context=ctx)
        # Later …
        await pool.stop()
    """

    def __init__(
        self,
        lease_manager: LeaseManager,
        *,
        config: PoolConfig | None = None,
        container_manager: ContainerManager | None = None,
    ):
        self.lease = lease_manager
        self.config = config or PoolConfig()
        self.container = container_manager
        self._slots: dict[str, WorkerSlot] = {}
        self._shutdown_event = asyncio.Event()
        self._results_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future] = {}  # task_id → Future
        self._background_tasks: set[asyncio.Task] = set()
        self._initialised = False
        self._stopping = False

    async def start(self) -> None:
        if self._initialised:
            return
        self._shutdown_event.clear()
        self._stopping = False
        for i in range(self.config.max_workers):
            self._slots[str(i)] = WorkerSlot(slot_id=str(i))
        self._initialised = True
        logger.info("CitizenWorkerPool started with %d slots", self.config.max_workers)

    @property
    def is_running(self) -> bool:
        return self._initialised

    async def stop(self) -> None:
        if not self._initialised:
            return
        self._stopping = True
        self._shutdown_event.set()

        # Cancel or drain active workers.
        if self.config.shutdown_behavior == "drain":
            await self._drain_active(self.config.drain_timeout_seconds)
        else:
            await self._cancel_active()

        # Cancel any supervisor tasks we spawned.
        for t in list(self._background_tasks):
            t.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        self._initialised = False
        self._stopping = False
        logger.info("CitizenWorkerPool stopped")

    async def _drain_active(self, timeout: float) -> None:
        """Wait up to *timeout* seconds for active workers to finish."""
        active_slots = [s for s in self._slots.values() if s.task_id is not None]
        if not active_slots:
            return

        logger.info("Draining %d active worker(s) with %.1fs timeout", len(active_slots), timeout)
        pending_tasks: list[asyncio.Task] = [t for t in self._background_tasks if not t.done()]
        if pending_tasks:
            await asyncio.wait(pending_tasks, timeout=timeout)

        # Force-kill anything still running.
        await self._cancel_active()

    async def _cancel_active(self) -> None:
        """Terminate every active worker or container."""
        for slot in self._slots.values():
            if slot.task_id is None or slot.handled:
                continue

            if slot.worker is not None:
                await slot.worker.terminate()
            elif slot.container_task is not None:
                await self._kill_container_task(slot.container_task)

    async def _kill_container_task(self, container_task: ContainerTask) -> None:
        if self.container is None:
            return
        try:
            await self.container.kill_container(container_task.container_id)
        except Exception as exc:
            logger.warning("Failed to kill container %s: %s", container_task.container_id, exc)

    async def submit(
        self,
        task_id: str,
        citizen_role: str,
        context: TaskContext,
        *,
        mission_id: str = "unknown",
        ttl_seconds: int | None = None,
        lease: Lease | None = None,
        slot_id: str | None = None,
    ) -> str | None:
        """Try to submit a task to the pool.

        1. If *lease* is not provided, acquire a lease.
        2. If successful, dispatch to a worker subprocess or container.
        3. Return the lease_id so the scheduler can track it.

        Returns:
            Lease ID on success, ``None`` if no slot available, lease
            acquisition failed, or the pool is stopping.
        """
        if self._stopping or self._shutdown_event.is_set():
            logger.debug("Pool is stopping; rejecting task %s", task_id)
            return None

        if self.config.isolation_mode == "container" and self.container is None:
            logger.error("Container isolation requested without a container manager")
            return None

        # Find a free slot
        if slot_id is not None:
            free_slot = self._slots.get(slot_id)
            if free_slot is None or free_slot.lease_id is not None:
                logger.debug("Requested slot %s unavailable for task %s", slot_id, task_id)
                return None
        else:
            free_slot = next(
                (s for s in self._slots.values() if s.lease_id is None),
                None,
            )
            if not free_slot:
                logger.debug("No free worker slot for task %s", task_id)
                return None

        if lease is None:
            try:
                lease = self.lease.acquire(
                    task_id=task_id,
                    mission_id=mission_id,
                    citizen_role=citizen_role,
                    worker_id=free_slot.slot_id,
                    ttl_seconds=ttl_seconds or self.config.worker_timeout_seconds,
                )
            except Exception:
                logger.debug("Lease acquisition failed for task %s", task_id)
                return None
            if not lease:
                return None
        else:
            logger.debug("Using pre-acquired lease %s for task %s", lease.lease_id, task_id)

        free_slot.lease_id = lease.lease_id
        free_slot.lease_generation = lease.generation
        free_slot.task_id = task_id
        free_slot.citizen_role = citizen_role
        free_slot.started_at = time.time()
        free_slot.done_event.clear()
        free_slot.handled = False

        if self.config.isolation_mode == "container" and self.container is not None:
            supervisor = asyncio.create_task(
                self._supervise_container(
                    task_id=task_id,
                    mission_id=mission_id,
                    citizen_role=citizen_role,
                    context=context,
                    slot_id=free_slot.slot_id,
                    ttl_seconds=ttl_seconds or self.config.worker_timeout_seconds,
                )
            )
        else:
            worker = WorkerProcess(
                task_id=task_id,
                mission_id=mission_id,
                citizen_role=citizen_role,
                description=context.task_description or "",
                context_json=context.model_dump(mode="json"),
                timeout_seconds=float(ttl_seconds or self.config.worker_timeout_seconds),
            )
            free_slot.worker = worker
            started = await worker.start()
            if not started:
                self._reset_slot(free_slot)
                return None
            free_slot.pid = worker.pid

            supervisor = asyncio.create_task(
                self._supervise_process(
                    task_id=task_id,
                    slot_id=free_slot.slot_id,
                )
            )

        self._pending[task_id] = asyncio.get_event_loop().create_future()
        self._background_tasks.add(supervisor)
        supervisor.add_done_callback(lambda t: self._background_tasks.discard(t))

        logger.info(
            "Task %s (%s) dispatched to slot %s, lease %s",
            task_id,
            citizen_role,
            free_slot.slot_id,
            lease.lease_id,
        )
        return lease.lease_id

    async def _supervise_process(self, task_id: str, slot_id: str) -> None:
        """Wait for a process worker and enqueue its result exactly once."""
        slot = self._slots[slot_id]
        worker = slot.worker
        if worker is None:
            return

        try:
            result = await worker.wait()
        except Exception as exc:
            logger.error("Supervisor exception for task %s: %s", task_id, exc)
            result = None
            result_dict = {
                "status": "failed",
                "summary": f"Supervisor exception: {exc}",
                "changed_files": [],
                "evidence": [{"type": "supervisor_error", "detail": str(exc)}],
                "risks": [{"severity": "critical", "description": str(exc)}],
                "confidence": 0.0,
            }
        else:
            result_dict = self._worker_result_to_dict(result)

        await self._finish_task(task_id, slot_id, result_dict)

    async def _supervise_container(
        self,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        context: TaskContext,
        slot_id: str,
        ttl_seconds: int,
    ) -> None:
        """Wait for a container worker and enqueue its result exactly once."""
        if self.container is None:
            result_dict = {
                "status": "failed",
                "summary": "Container mode requested but no ContainerManager provided",
                "changed_files": [],
                "evidence": [],
                "risks": [{"severity": "critical", "description": "No container manager"}],
                "confidence": 0.0,
            }
            await self._finish_task(task_id, slot_id, result_dict)
            return

        try:
            container_task = await self.container.run_task_async(
                task_id=task_id,
                mission_id=mission_id,
                citizen_role=citizen_role,
                description=context.task_description or "",
                context_json=context.model_dump(mode="json"),
            )
        except Exception as exc:
            logger.error("Failed to start container for task %s: %s", task_id, exc)
            result_dict = {
                "status": "failed",
                "summary": f"Container start failed: {exc}",
                "changed_files": [],
                "evidence": [{"type": "container_start_error", "detail": str(exc)}],
                "risks": [{"severity": "critical", "description": str(exc)}],
                "confidence": 0.0,
            }
            await self._finish_task(task_id, slot_id, result_dict)
            return

        slot = self._slots[slot_id]
        slot.container_task = container_task
        slot.container_id = container_task.container_id

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                container_task.process.communicate(),
                timeout=float(ttl_seconds),
            )
            returncode = container_task.process.returncode
            if returncode != 0:
                stderr = stderr_b.decode("utf-8", errors="replace").strip()
                result_dict = {
                    "status": "failed",
                    "summary": f"Container exited {returncode}: {stderr[:200]}",
                    "changed_files": [],
                    "evidence": [{"type": "container_stderr", "detail": stderr[:500]}],
                    "risks": [{"severity": "critical", "description": stderr[:500]}],
                    "confidence": 0.0,
                }
            else:
                import json

                stdout = stdout_b.decode("utf-8", errors="replace").strip()
                lines = [line for line in stdout.splitlines() if line.strip()]
                if not lines:
                    result_dict = {
                        "status": "failed",
                        "summary": "Empty container output",
                        "changed_files": [],
                        "evidence": [],
                        "risks": [{"severity": "critical", "description": "No JSON output"}],
                        "confidence": 0.0,
                    }
                else:
                    try:
                        result_dict = json.loads(lines[-1])
                    except json.JSONDecodeError as exc:
                        result_dict = {
                            "status": "failed",
                            "summary": f"Invalid JSON from container: {exc}",
                            "changed_files": [],
                            "evidence": [{"type": "raw_output", "detail": stdout[:500]}],
                            "risks": [{"severity": "critical", "description": str(exc)}],
                            "confidence": 0.0,
                        }
        except TimeoutError:
            logger.warning("Container task %s timed out after %ss", task_id, ttl_seconds)
            await self._kill_container_task(container_task)
            result_dict = {
                "status": "failed",
                "summary": f"Container task timed out after {ttl_seconds}s",
                "changed_files": [],
                "evidence": [],
                "risks": [{"severity": "critical", "description": "Container timeout"}],
                "confidence": 0.0,
                "_timed_out": True,
                "_killed": True,
            }
        except Exception as exc:
            logger.error("Container supervisor exception for task %s: %s", task_id, exc)
            result_dict = {
                "status": "failed",
                "summary": f"Container supervisor exception: {exc}",
                "changed_files": [],
                "evidence": [{"type": "supervisor_error", "detail": str(exc)}],
                "risks": [{"severity": "critical", "description": str(exc)}],
                "confidence": 0.0,
            }

        await self._finish_task(task_id, slot_id, result_dict)

    def _worker_result_to_dict(self, result: Any) -> dict[str, Any]:
        from animus_forge.scheduler.worker_process import WorkerResult

        if isinstance(result, WorkerResult):
            if result.ok and result.data is not None:
                result_dict = dict(result.data)
            else:
                result_dict = {
                    "status": "failed",
                    "summary": result.error or "Worker failed",
                    "changed_files": [],
                    "evidence": [{"type": "worker_error", "detail": result.error}],
                    "risks": [
                        {"severity": "critical", "description": result.error or "Worker failed"}
                    ],
                    "confidence": 0.0,
                }
            result_dict["_killed"] = result.killed
            result_dict["_timed_out"] = result.timed_out
            result_dict["_returncode"] = result.returncode
            return result_dict

        # Fallback for unexpected types.
        return {
            "status": "failed",
            "summary": f"Unexpected worker result type: {type(result)}",
            "changed_files": [],
            "evidence": [],
            "risks": [
                {
                    "severity": "critical",
                    "description": f"Unexpected worker result type: {type(result)}",
                }
            ],
            "confidence": 0.0,
        }

    async def _finish_task(self, task_id: str, slot_id: str, result_dict: dict[str, Any]) -> None:
        """Enqueue the result and free the slot exactly once."""
        slot = self._slots[slot_id]

        # Guard against double completion (timeout + natural finish).
        if slot.handled:
            logger.debug(
                "Task %s already handled in slot %s; ignoring duplicate finish", task_id, slot_id
            )
            return
        slot.handled = True

        lease_id = slot.lease_id
        lease_generation = slot.lease_generation
        container_id = slot.container_id
        pid = slot.pid

        self._reset_slot(slot)
        self._pending.pop(task_id, None)

        # Embed scheduler metadata so the result consumer can fence stale results.
        meta = {"lease_id": lease_id, "generation": lease_generation}
        for key in ("_killed", "_timed_out", "_returncode"):
            if key in result_dict:
                meta[key.removeprefix("_")] = result_dict.pop(key)
        if container_id:
            meta["container_id"] = container_id
        if pid:
            meta["pid"] = pid
        result_dict["_scheduler_meta"] = meta

        await self._results_queue.put((task_id, result_dict))

    def _reset_slot(self, slot: WorkerSlot) -> None:
        slot.lease_id = None
        slot.lease_generation = None
        slot.task_id = None
        slot.citizen_role = None
        slot.started_at = None
        slot.pid = None
        slot.container_id = None
        slot.worker = None
        slot.container_task = None
        slot.done_event.clear()

    async def results(self) -> asyncio.Queue[tuple[str, dict]]:
        """Return the queue of completed task results."""
        return self._results_queue

    def active_count(self) -> int:
        """Number of currently running workers."""
        return sum(1 for s in self._slots.values() if s.lease_id is not None)

    def free_count(self) -> int:
        return sum(1 for s in self._slots.values() if s.lease_id is None)

    def reserve_slot(self) -> str | None:
        """Return the id of a currently idle slot, if any."""
        for slot in self._slots.values():
            if slot.lease_id is None:
                return slot.slot_id
        return None

    def kill_slot(self, slot_id: str) -> bool:
        """Hard-kill a worker slot and its process/container tree.

        Returns:
            ``True`` if the slot was occupied and is now reset.
        """
        slot = self._slots.get(slot_id)
        if not slot or not slot.lease_id:
            return False

        task_id = slot.task_id
        if task_id:
            logger.warning("Force-killing slot %s task %s", slot_id, task_id)

        if slot.worker is not None:
            asyncio.create_task(slot.worker.terminate())
        elif slot.container_task is not None:
            asyncio.create_task(self._kill_container_task(slot.container_task))

        # Release lease so task becomes recoverable.
        if slot.lease_id:
            try:
                self.lease.release(slot.lease_id, outcome="killed")
            except Exception:
                logger.exception("Failed to release lease %s on kill", slot.lease_id)

        self._finish_slot_reset_only(slot)
        return True

    def _finish_slot_reset_only(self, slot: WorkerSlot) -> None:
        """Reset bookkeeping without enqueueing a result (used by kill_slot)."""
        task_id = slot.task_id
        slot.handled = True
        self._reset_slot(slot)
        self._pending.pop(task_id, None)

    async def run_recovery_loop(self, interval: float | None = None) -> None:
        """Background coroutine that recovers expired leases.

        Should be ``await``-ed or ``asyncio.create_task``-ed by the
        scheduler during its own run loop.
        """
        interval = interval or self.config.poll_interval_seconds
        while not self._shutdown_event.is_set():
            recovered = self.lease.recover_expired()
            if recovered:
                logger.warning("Recovered %d expired tasks: %s", len(recovered), recovered)
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
            except TimeoutError:
                pass

    def isolation_status(self) -> dict[str, Any]:
        """Return current isolation and slot status for observability."""
        runtime_available = bool(
            self.container and getattr(self.container, "is_available", lambda: False)()
        )
        slots = []
        for slot in self._slots.values():
            slots.append(
                {
                    "slot_id": slot.slot_id,
                    "task_id": slot.task_id,
                    "citizen_role": slot.citizen_role,
                    "pid": slot.pid,
                    "container_id": slot.container_id,
                    "lease_id": slot.lease_id,
                    "busy": slot.lease_id is not None,
                }
            )
        return {
            "mode": self.config.isolation_mode,
            "runtime_available": runtime_available,
            "max_workers": self.config.max_workers,
            "active_workers": self.active_count(),
            "free_slots": self.free_count(),
            "shutdown_behavior": self.config.shutdown_behavior,
            "slots": slots,
        }
