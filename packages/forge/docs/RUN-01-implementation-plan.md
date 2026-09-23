# RUN-01 Implementation Plan — Supervised Scheduler Lifecycle

**Repository:** `AreteDriver/animus`
**Depends on:** RUN-00 (runtime invariant model + baseline tests)
**Primary invariant:** Scheduler health reflects live supervised loops (RUN-00 §6).
**Date:** 2026-07-31
**Status:** Implemented

---

## 1. Goal

Make the mission scheduler's run loops deterministic, observable, and recoverable:

- Loops must not die on ordinary poll timeouts.
- Start/stop must be idempotent and race-safe.
- Lifecycle state must be public and stable.
- Health must reflect the actual state of each supervised loop, not a single event flag.
- Restart must reset state and resume cleanly.
- API routes must use the public lifecycle interface.

---

## 2. Current state

`MissionScheduler` currently has:

- `_stopped: asyncio.Event` used for all loop control and status.
- `_run_task`, `_result_consumer_task`, `_recovery_task` as raw `asyncio.Task` handles.
- `_run_loop()` and `CitizenWorkerPool.run_recovery_loop()` use `asyncio.wait_for(..., timeout=...)` **without catching** `asyncio.TimeoutError`, so the first normal timeout kills the loop.
- `start()` is silently idempotent because `pool.start()` returns early if `_initialised`, but it does not protect against STARTING/RUNNING races.
- `stop()` cancels tasks and calls `pool.stop()` with `wait=False`, then clears `_initialised`.
- `status()` returns `running: not self._stopped.is_set()` — a single flag.
- API routes read `state.mission_scheduler._stopped` directly.

`CitizenWorkerPool` currently has:

- `_shutdown_event = asyncio.Event()` set on `stop()` but never reset on `start()`.
- `run_recovery_loop()` has the same `asyncio.wait_for` timeout bug.

---

## 3. Proposed design

### 3.1 New module: `animus_forge.scheduler.lifecycle`

Introduce a small, reusable lifecycle abstraction.

```python
class SchedulerLifecycleState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    FAILED = "failed"

@dataclass
class LoopHandle:
    name: str
    task: asyncio.Task | None = None
    state: SchedulerLifecycleState = SchedulerLifecycleState.STOPPED
    last_tick_at: datetime | None = None
    last_error: str | None = None
    restart_count: int = 0

@dataclass
class SchedulerStatusSnapshot:
    lifecycle_state: SchedulerLifecycleState
    active_workers: int
    free_slots: int
    global_spend_usd: str
    global_cap_usd: str
    loops: dict[str, dict[str, Any]]
    last_tick_at: datetime | None
    last_error: str | None
    restart_count: int
    is_running: bool
    is_healthy: bool
    is_ready: bool

class LoopSupervisor:
    """Owns a set of named background coroutines and their lifecycle.

    Responsibilities:
    - start/stop a named loop
    - catch and record loop exceptions
    - apply a restart policy (none / fixed-count / always)
    - expose per-loop and aggregate health
    """

    def __init__(self, restart_policy: RestartPolicy | None = None): ...
    def register(self, name: str, coro_factory: Callable[[], Awaitable[None]]) -> None: ...
    async def start(self) -> None: ...
    async def stop(self, *, timeout: float | None = None) -> None: ...
    def snapshot(self) -> dict[str, dict[str, Any]]: ...
    @property
    def is_healthy(self) -> bool: ...
    @property
    def is_running(self) -> bool: ...
```

**Notes:**
- `coro_factory` is a zero-argument callable returning a coroutine. This lets the supervisor recreate a loop on restart.
- Restart policy options: `NEVER`, `ON_FAILURE` (default, with max_restarts), `ALWAYS`.
- A loop is "healthy" if all registered loops are in `RUNNING` state.
- A supervisor is "running" if at least one loop was started and not fully stopped.

### 3.2 Refactor `MissionScheduler`

Replace the three raw task handles with the `LoopSupervisor`:

```python
self._supervisor = LoopSupervisor(restart_policy=RestartPolicy.ON_FAILURE(max_restarts=3))
self._supervisor.register("dispatcher", self._run_loop)
self._supervisor.register("result_consumer", self._consume_results)
# recovery is registered only when config.enable_recovery is True
self._supervisor.register("recovery", self.pool.run_recovery_loop)
```

Change loop helpers:

```python
async def _wait_for_stop_or_timeout(self, timeout: float) -> None:
    try:
        await asyncio.wait_for(self._supervisor.stop_requested.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass

async def _run_loop(self) -> None:
    while self._supervisor.should_continue:
        try:
            dispatched = await self._tick()
            if dispatched:
                logger.info("Tick dispatched %d task(s)", dispatched)
            self._supervisor.mark_tick("dispatcher")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Scheduler tick failed")
            self._supervisor.record_error("dispatcher", str(exc))
        await self._wait_for_stop_or_timeout(self.config.poll_interval_seconds)
```

The existing `run_once()` path stays unchanged for tests.

New public interface on `MissionScheduler`:

```python
@property
def lifecycle_state(self) -> SchedulerLifecycleState: ...
@property
def is_running(self) -> bool: ...
@property
def is_ready(self) -> bool: ...
@property
def is_healthy(self) -> bool: ...
async def start(self) -> None: ...
async def stop(self) -> None: ...
def status(self) -> dict[str, Any]: ...  # public snapshot, no private fields
```

`start()` flow:
1. If `lifecycle_state` is `STARTING`, `RUNNING`, or `STOPPING`, return (idempotent) or raise a clear error. Proposed: idempotent return.
2. Set state to `STARTING`.
3. `await self.pool.start()`.
4. Reset supervisor state.
5. Start supervisor loops.
6. Set state to `RUNNING` if all loops started; `DEGRADED` if some failed but others are running; `FAILED` if all failed.

`stop()` flow:
1. If not running, return.
2. Set state to `STOPPING`.
3. Signal supervisor to stop.
4. `await self.pool.stop()`.
5. Wait for all loop tasks to complete (with timeout).
6. Set state to `STOPPED`.

### 3.3 Refactor `CitizenWorkerPool`

- Fix `run_recovery_loop()` to catch `asyncio.TimeoutError` on the normal poll timeout.
- Reset `_shutdown_event.clear()` at the start of `start()`.
- Make `start()` idempotent and safe to call after `stop()`.
- Add `is_running` property.

### 3.4 Update API routes

`packages/forge/src/animus_forge/api_routes/mission_scheduler.py`:

```python
@router.post("/scheduler/start")
async def start_scheduler(...):
    if state.mission_scheduler is None:
        raise bad_request("Mission scheduler not initialized")
    if state.mission_scheduler.is_running:
        return {"status": "already_running"}
    await state.mission_scheduler.start()
    return {"status": "started"}

@router.post("/scheduler/stop")
async def stop_scheduler(...):
    if state.mission_scheduler is None:
        raise bad_request("Mission scheduler not initialized")
    if not state.mission_scheduler.is_running:
        return {"status": "already_stopped"}
    await state.mission_scheduler.stop()
    return {"status": "stopped"}

@router.get("/scheduler/status")
def get_scheduler_status(...):
    if state.mission_scheduler is None:
        raise bad_request("Mission scheduler not initialized")
    return state.mission_scheduler.status()
```

No route reads `_stopped`.

### 3.5 Update tests

- `packages/forge/tests/test_api_mission_scheduler.py`: Replace `_stopped` mock access with `is_running` / lifecycle state mock.
- `packages/forge/tests/test_scheduler_phase5.py`: Update `status()` assertions to new snapshot shape.
- `packages/forge/tests/test_scheduler_runtime_baseline.py`: Several `xfail` tests should now pass:
  - `test_scheduler_loop_survives_three_intervals`
  - `test_recovery_loop_survives_three_intervals`
  - `test_pool_stop_start_cycle_restores_recovery`
  - `test_api_routes_inspect_private_stopped_field`
  - `test_api_with_real_scheduler_lifecycle`
- Add focused `packages/forge/tests/test_scheduler_lifecycle.py` covering:
  - start/stop idempotency
  - restart after stop
  - status reflects dead subtask
  - cancellation does not emit unhandled task warnings
  - no orphaned background tasks after teardown

---

## 4. Files to change

| File | Change |
|---|---|
| `packages/forge/src/animus_forge/scheduler/lifecycle.py` | New module: `LoopSupervisor`, `SchedulerLifecycleState`, `RestartPolicy`, `SchedulerStatusSnapshot`, `LoopHandle` |
| `packages/forge/src/animus_forge/scheduler/__init__.py` | Export new public names |
| `packages/forge/src/animus_forge/scheduler/mission_scheduler.py` | Use `LoopSupervisor`; public lifecycle interface; fix `_run_loop` timeout handling |
| `packages/forge/src/animus_forge/scheduler/worker_pool.py` | Reset shutdown event on start; fix recovery loop timeout handling |
| `packages/forge/src/animus_forge/api_routes/mission_scheduler.py` | Use public `is_running` / `status()`; drop `_stopped` access |
| `packages/forge/tests/test_scheduler_phase5.py` | Update `status()` shape assertions |
| `packages/forge/tests/test_api_mission_scheduler.py` | Replace `_stopped` mock with `is_running` / lifecycle state |
| `packages/forge/tests/test_scheduler_runtime_baseline.py` | Remove `xfail` from tests now passing; keep tests that still document future work |
| `packages/forge/tests/test_scheduler_lifecycle.py` | New focused lifecycle tests |

---

## 5. Migration / schema changes

None. RUN-01 is purely in-memory lifecycle; no database schema changes.

---

## 6. Testing strategy

1. **Focused lifecycle tests** (`test_scheduler_lifecycle.py`) using real `MissionScheduler` instances.
2. **Existing scheduler tests** (`test_scheduler_phase5.py`) must still pass.
3. **API tests** (`test_api_mission_scheduler.py`) updated to use public interface.
4. **Baseline tests** (`test_scheduler_runtime_baseline.py`) flipped from `xfail` to `xpass`/pass where applicable.
5. **No mock-only lifecycle tests** — every start/stop/status test uses a real scheduler.
6. **Deterministic timing**: short poll intervals and bounded `asyncio.sleep`; no real clock waits for lifecycle behavior.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `LoopSupervisor` adds complexity | Keep it small and well-tested; only manages task lifecycle, not business logic |
| API route behavior changes | Update mock-based tests; preserve HTTP contract (`status` field values) |
| Existing tests assert old `status()` shape | Update assertions; old keys like `running` can remain with `lifecycle_state` added |
| `ProcessPoolExecutor` shutdown still uses `wait=False` | Out of scope for RUN-01; addressed in RUN-03 |
| Restart policy could loop forever | Cap `max_restarts`; transition to `FAILED` after cap |

---

## 8. Definition of done for RUN-01

- [x] `MissionScheduler._run_loop()` survives multiple normal poll timeouts.
- [x] `CitizenWorkerPool.run_recovery_loop()` survives multiple normal poll timeouts.
- [x] `start()` is idempotent and race-safe.
- [x] `stop()` awaits cancellation and leaves no orphaned loop tasks.
- [x] `start()` after `stop()` fully restores operation.
- [x] Public lifecycle state (`STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, `STOPPING`, `FAILED`) is exposed.
- [x] `status()` returns loop-level health: each supervised loop state, last tick, last error, restart count.
- [x] API routes use only public lifecycle methods/properties.
- [x] All existing scheduler tests pass.
- [x] New focused lifecycle tests pass.
- [x] Applicable RUN-00 baseline tests flip from `xfail` to pass.

## 9. Verification

```bash
source .venv/bin/activate
pytest packages/forge/tests/test_scheduler_lifecycle.py \
       packages/forge/tests/test_scheduler_phase5.py \
       packages/forge/tests/test_scheduler_runtime_baseline.py \
       packages/forge/tests/test_api_mission_scheduler.py
```

Result: **59 passed, 10 xfailed** (2026-07-31).  The remaining `xfail` cases
document RUN-02 through RUN-09 defects that are intentionally out of scope
for RUN-01.
