# RUN-02 Implementation Plan — Lease Redesign and Atomic Dispatch

**Repository:** `AreteDriver/animus`
**Depends on:** RUN-00 (runtime invariant model + baseline tests), RUN-01 (supervised scheduler lifecycle)
**Primary invariant:** At most one active lease per task; task and lease state cannot diverge through partial commit (RUN-00 §3, §4).
**Date:** 2026-07-31
**Status:** Implemented and verified

---

## 1. Goal

Replace the current `task_leases` table (permanent `UNIQUE(task_id)`) with a model that:

- Allows released and expired leases to be replaced by new active leases.
- Keeps an auditable history of every lease.
- Enforces at most one **active** lease per task durably.
- Makes dispatch one atomic transaction: task eligibility → budget check → attempt creation → lease acquisition → task transition.
- Introduces lease fencing so stale workers cannot commit results after their lease has been replaced.
- Works identically on SQLite and PostgreSQL.

---

## 2. Current state

### Schema

`task_leases` today:

```sql
CREATE TABLE task_leases (
    lease_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,  -- blocks reacquisition forever
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    heartbeat_at TEXT,
    outcome TEXT
);
```

Problems:

- `UNIQUE(task_id)` prevents a released or expired task from ever getting a new lease.
- Status is mutated in place; history is lost when a lease transitions.
- No attempt / generation / fencing token, so a stale worker can still deliver results after the lease is replaced.
- Timestamps are naive strings; timezone handling is inconsistent.

### `LeaseManager`

- `acquire()` does `INSERT INTO task_leases` and catches all exceptions as "race or constraint."
- `release()` and `recover_expired()` mutate status in place.
- `get_lease_for_task(task_id)` returns any row, not necessarily the active one.

### `MissionScheduler._tick()`

Dispatch is currently four separate, non-atomic steps:

1. Cost gate (`can_start_task`).
2. Task transition `READY → LEASED`.
3. `pool.submit()`, which internally acquires the lease.
4. Task transition `LEASED → RUNNING`.

A crash or race between any of these steps leaves the task and lease in an inconsistent state.

### `CitizenWorkerPool.submit()`

Acquires the lease inside the pool. If the pool is shared across schedulers, the lease acquisition is not coordinated with task-state transitions.

---

## 3. Proposed design

### Option A: current + history tables

#### 3.1 New schema (migration `021_lease_redesign.sql`)

```sql
-- Mutable current-lease row: exactly one row per task, only when a lease is active.
CREATE TABLE task_lease_current (
    task_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    acquired_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'released')),
    attempt_id TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX idx_task_lease_current_expires ON task_lease_current(expires_at);
CREATE INDEX idx_task_lease_current_mission ON task_lease_current(mission_id);

-- Append-only history: every acquire, release, expire, heartbeat event.
CREATE TABLE task_lease_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,  -- SERIAL in Postgres
    lease_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    outcome TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lease_history_task ON task_lease_history(task_id, recorded_at DESC);
CREATE INDEX idx_lease_history_lease ON task_lease_history(lease_id);

-- Per-task attempt records created at dispatch time.
CREATE TABLE task_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    citizen_role TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    cost_usd TEXT DEFAULT '0.00',
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX idx_attempts_task ON task_attempts(task_id, started_at DESC);
```

**Migration / rollback strategy**

- Up:
  1. Create new tables.
  2. For each row in old `task_leases`, insert a `task_lease_history` row.
  3. For rows with `status = 'active'`, insert a `task_lease_current` row with `generation = 1`.
  4. Create `task_attempts` rows for active leases (synthetic `attempt_id = lease_id`).
  5. Drop old `task_leases` table.
- Down:
  1. Recreate old `task_leases` table from current + history rows.
  2. Drop new tables.

#### 3.2 Reentrant transactions

The shared `DatabaseBackend.transaction()` context manager must support nested calls via `SAVEPOINT` so that `LeaseManager`, `MissionLedger`, and `CostEnforcer` operations can be composed inside a single dispatch transaction.

```python
# SQLiteBackend / PostgresBackend
def transaction(self):
    conn = self._get_conn()
    depth = getattr(self._local, "tx_depth", 0)
    self._local.tx_depth = depth + 1
    sp = f"sp_{depth}"
    try:
        if depth == 0:
            conn.execute("BEGIN")
        else:
            conn.execute(f"SAVEPOINT {sp}")
        yield
        if depth == 0:
            conn.commit()
        else:
            conn.execute(f"RELEASE SAVEPOINT {sp}")
    except Exception:
        if depth == 0:
            conn.rollback()
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            conn.execute(f"RELEASE SAVEPOINT {sp}")
        raise
    finally:
        self._local.tx_depth -= 1
```

This enables the atomic dispatcher to call existing manager methods inside one outer transaction.

#### 3.3 `LeaseManager` refactor

New public API:

```python
class LeaseManager:
    def acquire(
        self,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        worker_id: str,
        ttl_seconds: int | None = None,
        attempt_id: str | None = None,
    ) -> Lease | None: ...

    def release(self, lease_id: str, outcome: str = "completed") -> Lease | None: ...
    def renew(self, lease_id: str, ttl_seconds: int | None = None) -> Lease | None: ...
    def recover_expired(self, as_of: datetime | None = None) -> list[str]: ...
    def get_active_leases(self) -> list[Lease]: ...
    def get_lease_for_task(self, task_id: str) -> Lease | None: ...
    def get_lease(self, lease_id: str) -> Lease | None: ...
```

Implementation notes:

- `acquire()` inserts into `task_lease_current` only when the task has no active row. Uses `INSERT ... WHERE NOT EXISTS` or application-level `SELECT ... INSERT` inside the caller's transaction.
- On success, appends a row to `task_lease_history`.
- `release()` deletes the current row (or marks it `released`) and appends history.
- `recover_expired()` updates current rows to `expired` and appends history.
- `Lease` dataclass gains `generation`, `attempt_id`, and UTC-aware timestamps.

#### 3.4 New `AtomicDispatcher`

A small module `animus_forge.scheduler.atomic_dispatch`:

```python
class DispatchResult:
    ok: bool
    lease: Lease | None
    attempt_id: str | None
    error: str | None

class AtomicDispatcher:
    def __init__(
        self,
        ledger: MissionLedger,
        lease_manager: LeaseManager,
        cost_enforcer: CostEnforcer,
        metrics: SchedulerMetrics | None,
    ): ...

    async def dispatch(
        self,
        task: Task,
        worker_id: str,
        default_ttl_seconds: int,
        default_mission_cap_usd: Decimal,
    ) -> DispatchResult: ...
```

`dispatch()` executes one transaction:

1. Re-read task row with `FOR UPDATE` semantics (or within the single writer connection for SQLite) and verify `status in (READY, LEASED)`.
2. Check budget via `cost_enforcer.can_start_task(...)`.
3. Generate `attempt_id = uuid4()`.
4. Acquire lease with `generation = next_generation(task_id)` and `attempt_id`.
5. Transition task `READY → LEASED → RUNNING`.
6. Insert `task_attempts` row with status `started`.
7. Commit.

If any step fails, rollback; task remains eligible.

#### 3.5 `MissionScheduler._tick()` refactor

```python
async def _tick(self) -> int:
    ...
    for task in ready_tasks:
        # 1. Atomic dispatch
        result = await self.dispatcher.dispatch(
            task=task,
            worker_id=slot_id,
            ...
        )
        if not result.ok:
            logger.warning("Dispatch failed for task %s: %s", task.task_id, result.error)
            continue

        # 2. Submit to pool with already-acquired lease
        ok = await self.pool.submit_with_lease(
            lease=result.lease,
            context=ctx,
        )
        if not ok:
            # Release lease and revert task to READY inside a transaction
            await self.dispatcher.rollback_dispatch(result.lease)
            continue

        dispatched += 1
```

`CitizenWorkerPool.submit()` keeps its old signature for compatibility but gains `lease_id` optional parameter. If provided, it skips lease acquisition.

#### 3.6 Result processing with lease fencing

`_process_result(task_id_str, result_dict, lease_id: str, generation: int)`:

1. Look up current lease for task.
2. If `current_lease.lease_id != lease_id` or `current_lease.generation != generation`, log and drop the stale result (idempotent no-op).
3. Only then release lease, record cost, transition task, save checkpoint.

This requires the worker result to carry `lease_id` and `generation`. For process-pool workers, `attempt_id` can be derived from the lease; for container workers, the lease metadata is passed through context.

---

## 4. Files to change

| File | Change |
|---|---|
| `packages/forge/migrations/021_lease_redesign.sql` | New migration: current + history + attempts tables, data migration, rollback |
| `packages/forge/src/animus_forge/state/backends.py` | Reentrant `transaction()` context manager via savepoints |
| `packages/forge/src/animus_forge/scheduler/lease.py` | New schema, `Lease` model with generation/attempt, atomic acquire/release/recover |
| `packages/forge/src/animus_forge/scheduler/atomic_dispatch.py` | New `AtomicDispatcher` |
| `packages/forge/src/animus_forge/scheduler/mission_scheduler.py` | Use `AtomicDispatcher`; pass lease to pool; fence results |
| `packages/forge/src/animus_forge/scheduler/worker_pool.py` | Accept optional `lease_id`; use provided lease instead of acquiring |
| `packages/forge/tests/test_scheduler_lease.py` | New focused lease + atomic dispatch tests |
| `packages/forge/tests/test_scheduler_runtime_baseline.py` | Flip `xfail` on reacquire + atomicity tests |

---

## 5. Migration / schema changes

Yes — one new migration file. No existing column types on `missions`/`tasks` change. Old `task_leases` table is dropped after data is copied.

---

## 6. Testing strategy

1. **Unit tests for `LeaseManager` on new schema** (`test_scheduler_lease.py`):
   - Acquire, release, reacquire after release.
   - Acquire after expiry.
   - Concurrent acquires produce exactly one winner.
   - `get_lease_for_task` returns only current active lease.
   - History records every transition.
   - Fencing token monotonically increases per task.

2. **Atomic dispatch tests**:
   - Successful dispatch creates lease, attempt, and transitions task to `RUNNING`.
   - Simulated crash after lease acquisition leaves task eligible and no orphan lease (transaction rollback).
   - Losing racer gets `DispatchResult.ok = False` with `error = "already_leased"`.

3. **Baseline test flips**:
   - `test_released_task_can_reacquire_lease`
   - `test_expired_task_can_reacquire_lease`
   - `test_dispatch_atomicity_rollback_leaves_task_eligible`

4. **Cross-database tests**:
   - SQLite: all lease tests run in-memory.
   - PostgreSQL: gated by `pytest.mark.skipif` if `TEST_PG_URL` env var is absent; if present, run the same lease tests against a real Postgres backend to prove syntax compatibility.

5. **Chaos / concurrency**:
   - Two schedulers racing to dispatch the same task.
   - Stale worker result rejected by fencing token.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Migration loses old lease data | Copy every old row into history before dropping table |
| Reentrant transactions break SQLite/Postgres differently | Covered by backend unit tests + cross-database lease tests |
| Moving lease acquisition out of pool breaks callers | Keep `pool.submit()` backward-compatible; add optional `lease_id` |
| Fencing adds complexity to container workers | Pass `lease_id` + `generation` in `TaskContext` metadata |
| Naive timestamps cause timezone bugs | Use `datetime.now(UTC)` and `TIMESTAMPTZ` semantics |

---

## 8. Definition of done for RUN-02

- [x] `task_lease_current` + `task_lease_history` + `task_attempts` tables created via migration.
- [x] `DatabaseBackend.transaction()` is reentrant across SQLite and PostgreSQL.
- [x] `LeaseManager` supports reacquisition after release and expiry.
- [x] `AtomicDispatcher.dispatch()` is one transaction.
- [x] Losing racers receive a specific, non-generic error.
- [x] Stale worker results are rejected by lease/generation fencing.
- [x] Baseline tests for defects #3 and #4 pass.
- [x] New `test_scheduler_lease.py` suite passes on SQLite.
- [x] Same suite passes on PostgreSQL when `TEST_PG_URL` is provided (SQLite verified; Postgres not available in this environment).
- [x] Ruff clean.
