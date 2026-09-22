# RUN-03 Implementation Plan — Real Worker Lifecycle and Termination

**Repository:** `AreteDriver/animus`
**Depends on:** RUN-00 (baseline tests), RUN-01 (supervised lifecycle), RUN-02 (atomic lease redesign)
**Primary invariant:** A killed or timed-out worker's entire process tree is terminated; shutdown leaves no orphan process or container.
**Date:** 2026-07-31
**Status:** Awaiting approval

---

## 1. Goal

Replace the current `ProcessPoolExecutor`-based worker pool with explicitly managed per-slot subprocesses (and container processes) so that:

- Every running worker has a tracked OS PID / container ID.
- A hung, crashed, or spawned-child worker can be terminated reliably.
- `kill_slot()` and per-task timeouts kill the entire process group / tree.
- Scheduler shutdown drains or cancels pending work and proves no children remain.
- The actual isolation mode and fallback status are observable.

---

## 2. Current state

### `CitizenWorkerPool`

- Uses `concurrent.futures.ProcessPoolExecutor` with `spawn` context.
- Tracks slots only by bookkeeping (`lease_id`, `task_id`, `started_at`).
- Has no access to the worker PID; cannot terminate a single worker's process tree.
- `kill_slot()` cancels the `asyncio.Future` and releases the lease, but the underlying process may keep running (documented by `test_kill_slot_does_not_terminate_container_task`).
- `stop()` calls `executor.shutdown(wait=False)`, which sends `SIGTERM` to pool workers but does not await them or kill spawned grandchildren.
- Container mode delegates to `ContainerManager.run_task()`, which runs `docker run` synchronously; the pool has no handle to the container ID and cannot kill it.

### `ContainerManager`

- Builds a `docker`/`podman run` command and runs it with `subprocess.run()`.
- Does not return the container ID.
- Timeout is handled by `subprocess.run(timeout=...)`, but the container may not be removed.

### Tests

- `test_kill_slot_does_not_terminate_container_task` currently asserts the *defect* (task keeps running after `kill_slot`).
- No tests cover real process killing, spawned children, shutdown cleanup, or isolation reporting.

---

## 3. Proposed design

### 3.1 Replace `ProcessPoolExecutor` with explicit subprocess workers

For process isolation, run each citizen task as a standalone `asyncio` subprocess instead of a `ProcessPoolExecutor` job. This gives us:

- The real PID.
- A fresh process group so we can kill the whole tree.
- Independent stdout/stderr pipes for structured output.
- Explicit `terminate()` → bounded wait → `kill()` semantics.

New helper module `animus_forge.scheduler.worker_process`:

```python
class WorkerProcess:
    task_id: str
    mission_id: str
    citizen_role: str
    pid: int | None
    process: asyncio.subprocess.Process | None
    started_at: float
    cancelled: bool

    async def start(self, ...) -> None: ...
    async def wait(self, timeout: float | None = None) -> dict[str, Any]: ...
    async def terminate(self, grace_period_seconds: float = 5.0) -> None: ...
```

The worker entry point becomes an executable Python module (`animus_forge.scheduler.worker_main`) rather than a top-level function passed to the executor. It reads a JSON payload from stdin, writes the result as JSON to stdout, and exits.

### 3.2 Track PID and container ID per slot

Extend `WorkerSlot`:

```python
@dataclass
class WorkerSlot:
    slot_id: str
    lease_id: str | None = None
    lease_generation: int | None = None
    task_id: str | None = None
    citizen_role: str | None = None
    started_at: float | None = None
    pid: int | None = None            # OS process id
    container_id: str | None = None   # container id, if container mode
    worker: WorkerProcess | None = None
```

### 3.3 Implement graceful terminate → wait → hard kill

For process mode:

1. Send `SIGTERM` to the process group (negative PID).
2. Wait up to `grace_period_seconds`.
3. If still alive, send `SIGKILL` to the process group.
4. Wait again briefly and reap the process.
5. Record outcome as `killed`.

For container mode:

1. Call `docker kill <container_id>`.
2. Call `docker rm -f <container_id>` to ensure cleanup.
3. Record outcome as `killed`.

### 3.4 Per-task timeout supervision

When a task is submitted, start a watchdog coroutine. If the task does not complete within `ttl_seconds`:

1. Mark the lease as expired via `lease_manager`.
2. Terminate the worker process / container using the terminate logic above.
3. Enqueue a synthetic `timeout` result.
4. Ensure the slot is freed exactly once (guard against double callback).

### 3.5 Result callback safety

Current `_on_task_done` can be triggered both by the future completing naturally and by the watchdog. We will:

- Use an `asyncio.Event` per slot (`_done_event`) so that only the first completion path enqueues a result.
- The watchdog calls `terminate()` and then waits for the natural callback, or enqueues a timeout result if the callback never fires.

### 3.6 Container mode changes

Modify `ContainerManager` to return both the result and the container ID. Two options:

**Option A:** Add `run_task_async()` returning `(container_id, result)`.
**Option B:** Make `run_task()` return a dict with `_container_id` key.

I recommend **Option A**: keep `run_task()` backward-compatible, add `run_task_async()` that returns `(container_id, asyncio.Future)` or a small dataclass. The pool starts the container with `asyncio.create_subprocess_exec` using `docker run --cidfile`, reads the container ID from the cidfile, and later kills it via `docker kill/rm`.

This avoids the blocking `subprocess.run()` and gives the pool full control.

### 3.7 Shutdown behavior

`PoolConfig` gains:

```python
shutdown_behavior: str = "cancel"  # "cancel" or "drain"
drain_timeout_seconds: float = 10.0
```

`stop()`:

1. Set `_shutdown_event` and mark pool as stopping (stop accepting new work; `submit` returns `None`).
2. For each active slot:
   - If `shutdown_behavior == "drain"`, wait up to `drain_timeout_seconds` for natural completion.
   - Otherwise (or drain timeout exceeded), terminate the worker / kill the container.
3. Cancel all pending asyncio tasks.
4. Optionally verify no orphan processes/containers (best-effort log warning).

### 3.8 Isolation reporting

Add `CitizenWorkerPool.isolation_status()`:

```python
{
    "mode": "process" | "container",
    "runtime_available": bool,
    "max_workers": int,
    "active_workers": int,
    "slots": [{"slot_id": ..., "task_id": ..., "pid": ..., "container_id": ...}],
}
```

Expose this in `MissionScheduler.status()`.

---

## 4. Files to change

| File | Change |
|---|---|
| `packages/forge/src/animus_forge/scheduler/worker_process.py` | New subprocess worker wrapper with terminate/kill logic |
| `packages/forge/src/animus_forge/scheduler/worker_main.py` | New CLI entry point for subprocess citizen execution |
| `packages/forge/src/animus_forge/scheduler/containers.py` | Return container ID; add async run + kill helpers |
| `packages/forge/src/animus_forge/scheduler/worker_pool.py` | Replace executor with per-slot subprocesses/containers; timeout watchdog; shutdown drain/cancel |
| `packages/forge/src/animus_forge/scheduler/mission_scheduler.py` | Include isolation status in `status()` |
| `packages/forge/tests/test_scheduler_worker.py` | New focused worker lifecycle tests |
| `packages/forge/tests/test_scheduler_runtime_baseline.py` | Flip `test_kill_slot_does_not_terminate_container_task` to assert termination |
| `packages/forge/tests/test_scheduler_phase5.py` | Update `test_kill_slot` and `test_container_mode_dispatches_via_manager` for new APIs |

---

## 5. Migration / schema changes

No schema changes. RUN-02 already added `task_attempts`. We will store terminal worker status in the result dict and possibly update the attempt record, but no new tables are required.

---

## 6. Testing strategy

1. **Worker process unit tests** (`test_scheduler_worker.py`):
   - Normal completion.
   - Python exception inside citizen.
   - Process crash (`sys.exit(1)`).
   - Hung worker terminated by timeout.
   - Worker spawning a child process; verify child is killed too.
   - `kill_slot()` terminates process tree.
   - Duplicate callback does not double-enqueue or double-free slot.

2. **Container mode tests**:
   - Fake `ContainerManager` returns container ID; pool can kill it.
   - Container runtime unavailable falls back to process mode (or reports `runtime_available: False`).

3. **Shutdown tests**:
   - `stop()` while a slow worker is running leaves no active slots.
   - `stop()` with `drain` behavior waits for completion.
   - `stop()` with `cancel` behavior terminates workers immediately.

4. **Baseline flip**:
   - `test_kill_slot_does_not_terminate_container_task` becomes `test_kill_slot_terminates_container_task` and asserts the container is marked killed / no longer running.

5. **Process-table verification** (best effort):
   - After `stop()`, assert no PID associated with the worker entry point remains via `psutil` or `/proc` scan (optional, gated by platform).

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Replacing ProcessPoolExecutor introduces instability | Keep worker entry point simple; reuse existing citizen classes; extensive tests |
| Process group kill unsupported on Windows | Use `job_object` or `taskkill /T`; initially target Linux per project scope, document Windows limitation |
| Container mode needs docker/podman in CI | Tests use `FakeContainerManager`; real runtime tests gated by availability |
| Timeout watchdog races with natural completion | `asyncio.Event` guard ensures one completion path wins |
| Orphan processes from spawned children | Kill process group (negative PID) on Linux; verify in tests |
| `stop()` hangs waiting for unresponsive worker | Bounded wait + force kill + cancel pending futures |

---

## 8. Definition of done for RUN-03

- [ ] `ProcessPoolExecutor` replaced with explicit subprocess / container management.
- [ ] Each slot tracks PID and/or container ID.
- [ ] `kill_slot()` terminates the entire process tree or container.
- [ ] Per-task timeout terminates worker and enqueues timeout result.
- [ ] Result callbacks cannot double-free slots or double-enqueue results.
- [ ] Shutdown supports `cancel` and `drain` behaviors with no orphan children.
- [ ] Isolation status is observable via `MissionScheduler.status()`.
- [ ] `test_kill_slot_does_not_terminate_container_task` flipped to assert real termination.
- [ ] New `test_scheduler_worker.py` passes.
- [ ] Full scheduler suite still passes (75 passed / 7 xfail baseline maintained).
- [ ] Ruff clean.
