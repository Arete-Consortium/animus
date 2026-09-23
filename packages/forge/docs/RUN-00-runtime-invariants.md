# RUN-00 — Runtime Invariant Model and Executable Baseline

**Repository:** `AreteDriver/animus`
**Plan:** Animus Plan 2 of 3 — Scheduler, Citizen Runtime, and Reliability Hardening
**Scope:** Mission scheduler, `LeaseManager`, `CitizenWorkerPool`, `MissionLedger`, `CostEnforcer`, and scheduler API routes.
**Date:** 2026-07-31
**Status:** Baseline / design-only — production code intentionally unchanged.

---

## 1. Purpose

This document is the authoritative model produced by `RUN-00`. It defines the state machines, invariants, transition tables, and failure-injection matrix that later implementation packets (`RUN-01` through `RUN-09`) must preserve. It also maps every known current defect to an executable baseline test that fails today and must pass before the plan is complete.

---

## 2. Entity model

The runtime manipulates six durable entities:

| Entity | Identity | Purpose | Current table/file |
|---|---|---|---|
| `Mission` | `mission_id` | Bounded autonomous objective | `missions` (`MissionLedger`) |
| `Task` | `task_id` | Single citizen assignment within a mission | `tasks` (`MissionLedger`) |
| `Lease` | `lease_id` | Active claim on a task by a worker | `task_leases` (`LeaseManager`) |
| `Attempt` | `attempt_id` | One concrete execution of a task | *Not yet separate* (currently implied by `Task.current_attempt`) |
| `Checkpoint` | `checkpoint_id` | Persisted stage boundary within an attempt | `checkpoints` (`MissionLedger`) |
| `Result` | `result_id` or idempotency key | Accepted output of an attempt | *Not yet separate* (currently enqueued directly) |
| `BudgetReservation` | `reservation_id` | Reserved budget before dispatch | *Not yet separate* (currently only `cost_events`) |
| `ReviewVerdict` | `review_id` | Evidence-backed review decision | *Not yet separate* |

---

## 3. State machines

### 3.1 Mission lifecycle

```text
proposed → ready → running ──► waiting ──┐
    │         │       │        │         │
    ▼         ▼       ▼        ▼         ▼
cancelled   cancelled  review ◄───────────┘
              │    │    │
              ▼    ▼    ▼
           failed  approval_required → completed
                        │
                        ▼
                     failed / cancelled
```

Notes:
- `running → completed` is **forbidden** directly; a real `ReviewVerdict` is required.
- `review` is a stable waiting state, not a passthrough.
- Terminal states: `completed`, `failed`, `cancelled`, `quarantined`.

### 3.2 Task lifecycle

```text
pending ──► ready ──► leased ──► running ──► completed
              │        │          │
              ▼        ▼          ▼
          cancelled  ready      failed / blocked / waiting
                      (retry)      │
                                   ▼
                                ready (if attempts remain)
```

Notes:
- A task in `RUNNING` must hold the active lease.
- A task without an active lease cannot stay `RUNNING` beyond a recovery grace period.
- `CANCELLED` is terminal.

### 3.3 Lease lifecycle

```text
ACTIVE ──► RELEASED  (normal completion/failure)
    │
    ▼
EXPIRED  (heartbeat/timeout recovery)
```

Notes:
- At most one `ACTIVE` lease per `task_id` is enforced durably.
- Historical leases (`RELEASED`, `EXPIRED`) must remain auditable.
- A stale worker must not be able to commit a result after its lease is replaced.

### 3.4 Attempt lifecycle

```text
CREATED ──► DISPATCHED ──► RUNNING ──► COMPLETED
                              │
                              ▼
                          FAILED ──► RETRYABLE (if attempts remain)
```

Notes:
- `attempt_id` is unique and distinct from `task_id`.
- Every checkpoint and result is tagged by `attempt_id`.
- Retry creates a new `Attempt`, not a recycled identity.

### 3.5 Budget reservation lifecycle

```text
RESERVED ──► SETTLED  (actual usage recorded)
    │
    ▼
RELEASED/REFUNDED  (task failed or over-reserved)
```

Notes:
- Reservation is created before dispatch.
- Settlement happens at most once per result.
- Concurrent reservations count against available budget.

### 3.6 Review verdict lifecycle

```text
REQUESTED ──► SUBMITTED ──► ACCEPTED / REJECTED
```

Notes:
- A `REJECTED` verdict routes the mission to `RUNNING` (rework) or `FAILED`.
- Verdicts are idempotent and timestamped.

---

## 4. Invariants

### Core invariants (non-negotiable)

1. **At most one active lease per task.**
   Durable: the database must never contain two rows with `(task_id, status='active')`.

2. **Every execution has a unique `attempt_id`.**
   `attempt_id` must be generated before dispatch and must differ across retries.

3. **A task in `RUNNING` has an active lease.**
   Lease recovery must transition a task out of `RUNNING` when its lease expires or is released.

4. **A stale worker cannot commit a result.**
   Result processing must validate the lease fencing token / generation. A result from a replaced lease is rejected or safely ignored.

5. **A result and cost settlement are applied at most once.**
   Idempotency key prevents duplicate delivery from double-transitioning or double-spending.

6. **Scheduler health reflects live supervised loops.**
   `status()` must report `DEGRADED` or `FAILED` if a supervised loop dies, not rely on an event flag alone.

7. **Restart reconstructs recoverable state from durable storage.**
   A new scheduler process must resume eligible work without loss or re-invention.

8. **Budget is reserved before dispatch and settled from actual usage.**
   `can_start_task` must consider outstanding reservations; recorded cost must reflect provider/model/token usage, not a fixed estimate.

9. **Mission completion requires a real review verdict.**
   `REVIEW` is a stable waiting state. `COMPLETED` is reachable only through an accepted `ReviewVerdict`.

10. **No orphan process or container remains after timeout or shutdown.**
    `kill_slot()` and `stop()` must terminate the process tree/container and await cleanup.

11. **SQLite and PostgreSQL behavior must be defined and tested.**
    Concurrency-sensitive operations (leases, reservations) must be correct on both backends.

### Secondary invariants

12. **Transition tables are the only valid mutation paths.**
    No direct status assignment outside `transition_*` helpers.

13. **API routes do not read private fields.**
    `_stopped` is not a public interface.

14. **Duplicate events are safe.**
    Duplicate result, duplicate lease acquire attempt, duplicate review verdict: all must be idempotent or rejected cleanly.

15. **Canceled required task prevents mission completion.**
    Mission policy must define whether `CANCELLED` counts as success; default for required tasks is no.

---

## 5. Transition tables

### 5.1 Mission transitions

| From | To | Guard | Side effects |
|---|---|---|---|
| `PROPOSED` | `READY` | Mission accepted, tasks created | — |
| `PROPOSED` | `CANCELLED` | Operator cancel | — |
| `READY` | `RUNNING` | At least one task is `READY` | Start scheduler monitoring |
| `READY` | `CANCELLED` | Operator cancel before start | — |
| `RUNNING` | `WAITING` | All runnable tasks blocked/waiting | — |
| `RUNNING` | `REVIEW` | All tasks terminal | Require `ReviewVerdict` |
| `RUNNING` | `FAILED` | Any required task `FAILED` or mission error | Record error |
| `WAITING` | `RUNNING` | Unblocked task becomes `READY` | — |
| `WAITING` | `CANCELLED` | Operator cancel | — |
| `REVIEW` | `RUNNING` | Verdict rejected → rework | Reset relevant tasks to `READY` |
| `REVIEW` | `APPROVAL_REQUIRED` | Verdict accepted but policy requires human | — |
| `REVIEW` | `COMPLETED` | Verdict accepted and no approval required | Emit `MISSION_COMPLETED` |
| `REVIEW` | `FAILED` | Verdict rejected permanently | — |
| `APPROVAL_REQUIRED` | `COMPLETED` | Human approval granted | — |
| `APPROVAL_REQUIRED` | `FAILED` | Human rejects or timeout | — |

### 5.2 Task transitions

| From | To | Guard | Side effects |
|---|---|---|---|
| `PENDING` | `READY` | Dependencies completed | — |
| `PENDING` | `CANCELLED` | Mission/task cancelled | — |
| `READY` | `LEASED` | Lease acquired atomically | Create `Attempt`, reserve budget |
| `READY` | `BLOCKED` | Dependency failed / external block | — |
| `READY` | `CANCELLED` | Operator cancel | — |
| `LEASED` | `RUNNING` | Worker confirmed dispatched | — |
| `LEASED` | `READY` | Lease lost before run (race/expire) | Release reservation |
| `LEASED` | `FAILED` | Pre-run validation fails | Release reservation |
| `RUNNING` | `WAITING` | Citizen requests external input | — |
| `RUNNING` | `COMPLETED` | Result accepted, attempt terminal | Settle cost, save checkpoint |
| `RUNNING` | `FAILED` | Result rejected, max attempts not reached | Release reservation, retry |
| `RUNNING` | `READY` | Retry after failure (attempts remain) | Increment attempt, new `Attempt` |
| `RUNNING` | `BLOCKED` | External dependency discovered | — |
| `WAITING` | `RUNNING` | External input received | — |
| `WAITING` | `BLOCKED` | External dependency unresolved | — |
| `WAITING` | `CANCELLED` | Operator cancel | — |
| `BLOCKED` | `READY` | Blocker resolved | — |
| `BLOCKED` | `CANCELLED` | Operator cancel | — |

### 5.3 Lease transitions

| From | To | Guard | Side effects |
|---|---|---|---|
| (none) | `ACTIVE` | No active lease for `task_id` | Insert row, link to `Attempt` |
| `ACTIVE` | `RELEASED` | Worker reports completion/failure | Update task status |
| `ACTIVE` | `EXPIRED` | `expires_at < now` and no heartbeat | Recover task to `READY` |

### 5.4 Budget event transitions

| Event | Precondition | Postcondition |
|---|---|---|
| `RESERVE` | Task eligible, available budget ≥ estimated cost | Reservation row exists, available budget reduced |
| `SETTLE` | Result accepted, actual usage known | Cost row inserted, reservation closed |
| `REFUND` | Task failed or over-reserved | Unused reservation released |
| `ADJUST` | Operator reconciliation | Corrective row inserted |

---

## 6. Failure-injection matrix

| Scenario | Expected durable outcome | Current risk |
|---|---|---|
| Scheduler process restart with ready/leased/running tasks | Eligible tasks resume; leases expire and recover | Loop may die silently; in-memory state lost |
| Database unavailable during dispatch | Dispatch fails visibly; task stays `READY` | Broad `except Exception` swallows errors |
| Database unavailable during result processing | Result not lost (or retryable); task stays `RUNNING` until recovered | Result may be dropped |
| Worker crash before result | Lease expires, task retried, no orphan process | `ProcessPoolExecutor` may leave zombie |
| Worker completes after lease expiry | Result rejected (stale lease) | Result accepted against old task state |
| Duplicate result delivery | Applied once; duplicate ignored | May double-transition or double-record cost |
| Scheduler crash after cost settlement but before task transition | Recovery sees settled cost and reapplies transition | State may diverge |
| Scheduler crash after transition but before ack | Duplicate result is idempotent | Result may be reprocessed |
| Two scheduler instances racing | One wins; loser gets explicit conflict | Both may acquire/lease due to non-atomic dispatch |
| Budget exhausted under concurrency | Overspend prevented by reservation | Fixed `$0.10` estimate, no reservation |
| Container runtime disappears mid-run | Task fails/retries; container cleaned up | Container may leak |
| Reviewer failure/unavailable | Mission stays in `REVIEW` | Mission auto-completes through `REVIEW` |
| Clock jump forward/backward | Expiry and heartbeat remain consistent | `datetime.now()` comparisons drift |
| Large mission with dependency graph + retries | Retries create new attempts, dependencies honored | Attempt count semantics ambiguous |
| Graceful shutdown deadline exceeded | Hard kill of process tree | `wait=False` does not await termination |

---

## 7. Known defect-to-test mapping

| # | Defect (from plan §2) | Baseline test | Expected result today |
|---|---|---|---|
| 1 | `_run_loop()` exits on first normal timeout | `test_scheduler_loop_survives_three_intervals` | Fails / loop dies |
| 2 | `run_recovery_loop()` exits on first normal timeout | `test_recovery_loop_survives_three_intervals` | Fails / loop dies |
| 3 | `task_id` permanently unique prevents reacquisition | `test_released_task_can_reacquire_lease` | Fails (`None` returned) |
| 3 | Same, via expiry | `test_expired_task_can_reacquire_lease` | Fails |
| 4 | Lease acquisition + task transition not atomic | `test_dispatch_atomicity_race_rollback` | Fails / state diverges |
| 5 | `kill_slot()` does not prove process termination | `test_kill_slot_terminates_process_tree` | Fails / orphan remains |
| 6 | Pool shutdown `wait=False` leaves orphans | `test_pool_shutdown_leaves_no_orphans` | Fails |
| 7 | Shutdown event not reset on restart | `test_pool_stop_start_cycle_restores_recovery` | Fails |
| 8 | Fixed `$0.10` estimate; zero cost common | `test_recorded_cost_reflects_actual_usage` | Fails (cost is zero/estimate) |
| 9 | Budget reservation not atomic | `test_concurrent_tasks_cannot_oversubscribe_budget` | Fails |
| 10 | Review is ceremonial | `test_mission_cannot_complete_without_review_verdict` | Fails (auto-completes) |
| 11 | Canceled tasks satisfy `all_done` without failure | `test_cancelled_required_task_prevents_completion` | Fails |
| 12 | Checkpoint `attempt_id` uses `task_id` | `test_checkpoint_attempt_id_is_not_task_id` | Fails |
| 13 | Retry/attempt-count semantics ambiguous | `test_retry_creates_distinct_attempt_id` | Fails |
| 14 | API routes inspect `_stopped` | `test_api_uses_public_lifecycle_interface` | Fails (uses private field) |
| 15 | Route tests use mocks | `test_api_with_real_scheduler_lifecycle` | Fails or not representative |
| 16 | Duplicate/restart/partial-write semantics missing | `test_duplicate_result_is_idempotent` | Fails |

---

## 8. Evidence packet summary

```text
Task ID: RUN-00
Invariant addressed: All core invariants (§4)
State diagram changes: Mission, Task, Lease, Attempt, BudgetReservation, ReviewVerdict defined above
Schema or migration changes: None in RUN-00; later tasks require:
  - attempts table
  - task_lease_current / task_lease_history (or partial unique index)
  - budget_reservations table
  - results table with idempotency key
  - review_verdicts table
Failure reproduction: packages/forge/tests/test_scheduler_runtime_baseline.py
Implementation summary: Design-only packet; no production code changed
Concurrency assumptions: SQLite with FKs enabled; PostgreSQL for cross-backend verification required in RUN-02/05/08
Idempotency strategy: Idempotency keys on results and budget settlements; lease uniqueness on task_id
Tests and chaos cases: 17 baseline tests covering all 16 known defects; deterministic SQLite; no chaos tooling yet
SQLite results: 15 xfailed, 2 passed (2026-07-31). `python -m pytest packages/forge/tests/test_scheduler_runtime_baseline.py` runs in ~28s.
PostgreSQL results: Not yet run (requires RUN-02/05/08)
Restart/recovery results: Not yet implemented
Performance impact: N/A
Known limitations: Model is aspirational; current code does not satisfy it; split-brain race requires deterministic concurrency tooling in RUN-08
Rollback/migration reversal: N/A
Engineering verdict: Baseline established; implementation can proceed in dependency order
Red-team/reliability verdict: Pending RUN-08
```

---

## 9. Exit criteria

- [x] Authoritative model of runtime entities and state machines documented.
- [x] Transition tables with guards and side effects defined.
- [x] Invariant list covers all 16 known defects plus cross-database behavior.
- [x] Failure-injection matrix maps failure modes to expected outcomes.
- [x] Baseline tests reproduce current defects with deterministic or bounded timeouts.
- [x] Baseline tests executed and failures captured (see companion test file).

---

## 10. Next packets

| Packet | Depends on | Primary invariant |
|---|---|---|
| RUN-01 | RUN-00 | Health reflects live supervised loops (§6) |
| RUN-02 | RUN-00 | At most one active lease; atomic dispatch (§1, §3) |
| RUN-03 | RUN-01, RUN-02 | No orphan process/container (§10) |
| RUN-04 | RUN-02, RUN-03 | Unique attempts; idempotent results (§2, §5) |
| RUN-05 | RUN-02, RUN-04 | Budget reservation + settlement (§8) |
| RUN-06 | RUN-04 | Real review verdict (§9) |
| RUN-07 | RUN-01–RUN-06 | Stable public API/observability (§13, §6) |
| RUN-08 | RUN-07 | Chaos, concurrency, recovery campaign |
| RUN-09 | RUN-08 | Final evidence and verdict |
