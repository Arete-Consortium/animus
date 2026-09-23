# CI repair and deployment profiles

The Hunter persistence and repository changes depend on CI repairs for MCP v1
compatibility, dependency installation, Docker image loading, test isolation,
formatting, and type-gate execution.

## Memory compatibility and remaining security gate

Core's base and `[postgres]` installs exclude ChromaDB. Chroma is a legacy opt-in
`[chroma]` extra (also included in `[all]` for compatibility). The default configured
backend is unchanged. If it is Chroma and the dependency is absent, startup fails
with an actionable error; it must never silently show a different memory store.
For a new JSON-based installation explicitly set `ANIMUS_MEMORY_BACKEND=json`.
Hunter SQL repositories do not instantiate the personal memory layer.

Existing Chroma installations must retain their dependency and data until a
separate migration is planned. Do not change an existing backend to clear CI.
No live memory settings or stored records were modified by this repair.
The existing HTTP-first/embedded-fallback behavior is retained for compatibility;
it is not an embedded-only deployment, and loopback is not proof of safety.

The security matrix audits both Core base and Core with Chroma. Chroma 1.5.9 has
open advisories and no verified patched release at the time of this repair.
The extra's audit remains blocking, with no new ignores. Before a production
migration, inventory the active client/server mode and data location, back up the
source, export/import with record-count and representative-retrieval verification,
and retain a tested rollback. A base-profile pass does not clear the legacy profile.

Sources: [upstream releases](https://github.com/chroma-core/chroma/releases),
[RCE advisory](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c),
[authorization advisory](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr),
[RBAC advisory](https://github.com/advisories/GHSA-xph7-9rjv-w5fr).

## Type and secret gates

`scripts/mypy-ratchet.py` runs the canonical baseline command once per package,
writes `packages/<package>/mypy-report.txt`, and enforces the unchanged allowances.
Tool failures, unknown packages, and unexplained nonzero exits fail closed.
`--init` can only lower allowances. Unit regressions exercise the gate itself.
The previous raw mypy steps stopped before this documented ratchet could run.

Kernel coverage consumes the JSON report from the successful test step, preserving
the existing 21.3% floor and avoiding a second test run with different imports.
Missing or malformed reports fail closed.

Gitleaks 8.30.1 is downloaded from its upstream release, verified against a pinned
SHA-256, and scans all fetched Git history with redacted output. It does not need
the commercial GitHub-action license and still fails on secret findings.

## Hosted checks

CI and security workflows run for Hunter branch pushes and stacked pull requests,
as well as main. Docker uses separate amd64/arm64 jobs with `load: true` before
import and CLI smoke tests. No image is published by these checks.

## Forge MCP composition

Kernel MCP execution now asks the embedding application for a connector registry
and transport. Forge supplies its existing manager and client through its executor
adapter, including all three public WorkflowExecutor import paths. Kernel without
these adapters fails explicitly; it does not import Forge or own its credentials.
This fixes imports of the nonexistent `animus_kernel.mcp` package left by the split.
The AreteGuard fixture now uses the actual schema migrations instead of a stale
inline copy of the original eval schema.

## Forge follow-up repairs

The full Forge suite exposed additional split-package defects. Service clients
and autonomy loops now have explicit application adapters, and Forge's CLI/API
instantiate the composed Forge executor. Kernel integration dry runs need no
client; actual integration execution without an adapter fails explicitly.
Forge's daily budget check uses its own task store, while effective-token status
is compared by value across package boundaries. The loader accepts the service
step types already registered by the executor.

Shell steps support an explicit `working_directory`, resolved independently of
the command. The feature-build workflow uses it instead of `cd ... && ...`.
Execution still uses `shell=False`; metacharacter, executable-path, interpreter
flag, and command-allowlist checks remain in place. The changed workflow passes
agent-lint with a score of 100/100.

Forge SQLite connections enable foreign keys so declared cascades are enforced.
This does not migrate or delete existing data; future writes are checked against
the declared constraints. Test fixtures now target the actual Kernel owner of
re-exported code, commit their setup transactions, and normalize platform paths.
Test cleanup collects young objects after every case and the full heap every 25
cases, retaining the existing 32 GB process memory limit.

Approval tokens and memory-recall access updates now commit their writes. Approval
creation, decisions, and the executor's next-step pointer survive subsequent
transactions; regression coverage reopens the connection to verify durability.
Fresh migration 021 creates the mission/task parents before copying lease rows,
so the normal migration sequence also works with foreign keys enabled. Existing
applied migrations are not replayed by this change.

Cloud API factories, approval storage, and task-history writes use Forge-owned
adapters. Dashboard and executor parallel metrics share the Kernel tracker instead
of maintaining two independent singletons. YAML orchestration smoke tests mock
retry sleeps while preserving the execution result checks; real shell tests retain
the command-chaining rejection and use supported single commands.

Worker exit diagnostics now travel inside scheduler metadata, so strict citizen
output validation no longer turns successful subprocess results into failures.
Container mode refuses dispatch when its manager is absent, before acquiring a
lease or starting a host process. Regressions cover that denial, existing command
log redaction, and container termination through the current async interface.
Lease, schedule, and webhook fixtures now create their referenced parent records;
evolution-metric fixtures commit their setup writes.

## Scheduler expected-failure repairs

The seven RUN-00 expected failures now run as normal regressions. Citizen results
can carry validated per-call provider, model, input/output token counts, and actual
cost. The deterministic built-in citizens report no LLM calls and remain local,
zero-cost workers. Tests supply synthetic usage explicitly instead of attributing
OpenAI usage to a local planner.

Dispatch reserves estimated cost durably in the same transaction as its lease,
new attempt identity, attempt count, and task transitions. A database lock row
serializes budget admission across connections. Both mission and global limits
include outstanding reservations and the proposed cost; an explicit zero cap is
honored. Migration 022 creates the reservation tables, and initialization preserves
existing holds. Result acceptance requires the current lease, generation, and
attempt ID. Cost, checkpoint, attempt outcome, lease release, and task status commit
together. Repeated/stale/unfenced results have no side effects. Failed dispatch
rollback releases its hold without consuming an execution attempt.

Checkpoints reference the actual attempt UUID. `max_attempts` counts executions,
including the first attempt, and each retry gets a fresh identity. A cancelled
required task fails its mission. Successful tasks move the mission to `REVIEW`;
the scheduler no longer grants its own review verdict or completes the mission.
An authorized review decision remains necessary to advance that state.

Reservations are admission estimates, not an upper bound on a provider's final
bill. Actual charges are recorded even if higher than the estimate. Expired,
killed, timed-out, or malformed results with unknown charges retain their hold
for reconciliation; they must not silently be treated as free work. No automated
reconciliation or new live LLM integration is introduced by this repair.

## Running the code-execution checks from macOS

This Mac accepts the CPU and file-size ceilings but rejects the 512 MiB
`RLIMIT_AS` address-space ceiling with `ValueError: current limit exceeds maximum
limit`. The four affected tests are the timeout, memory-bomb, normal-code, and
crash-scoring checks in `TestCodeExecutionSandbox`. Importing Python's `resource`
module does not establish that every limit works on the current OS; see the
[Python resource documentation](https://docs.python.org/3/library/resource.html).

Run this evaluator and its resource-limit tests under Linux (for example, in
Docker Desktop's Linux VM). Do not remove or swallow the memory-limit error and
then execute unbounded code on macOS. The native evaluator has not been switched
to a Docker backend by this change, so these four native macOS tests remain
platform failures until the evaluation process is run under Linux.

For a focused check from the repository root, using the existing local image:

```sh
PATH="/Users/aretedriver/.docker/bin:$PATH" .venv/bin/python scripts/verify-code-sandbox.py --image animus-kernel:ci-repair
```

The script copies only its verifier and the two evaluation source files into a
temporary container. It requires an existing Linux image containing Python and
pydantic; it does not pull images or install packages. It disables network access,
sets memory/CPU/PID limits, executes the real metric's four behavioral checks, and
removes its own container. It checks the evaluation module, not the full Forge
suite. For normal use, run the Forge evaluation process/tests inside the Linux
environment as well.

On the latest local verification, Docker Desktop left even a minimal Python
`print()` container in `Created` and timed out starting it. The new verifier could
therefore not complete. An earlier isolated Linux run passed the four equivalent
checks, but this is not evidence that the current Docker runtime is healthy.
If startup remains stalled, restart Docker Desktop after safely stopping or
scheduling downtime for running n8n services, then rerun the command above. This
repair did not restart Docker or alter those services.
