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
