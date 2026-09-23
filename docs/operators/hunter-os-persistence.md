# Hunter OS registry foundation

This change prepares Animus's shared SQL registry for a future Hunter OS repository. It does not import Hunter records, wire Discord, or verify game facts. The application scope is not database row-level security: code with raw database credentials remains trusted. Do not hand a generic memory store, raw engine, or scoped write interface to shared chat.

## Supported database layouts

| Existing state | Action |
| --- | --- |
| Empty database | Apply Alembic migrations through `002`. |
| Canonical migration `001` registry and Kernel-style ledger | Back up, test the backup in isolation, then apply `002` during an approved maintenance window. |
| Current `002` layout | Run the read-only preflight. |
| Older Core-created ledger with `event_id` / `event_type` columns | Stop. An explicit, separately reviewed conversion preserving all events is required. This migration does not convert that layout. |
| Mixed columns, existing unexpected outbox, or duplicate current objects | Stop and prepare a recovery plan. Migration `002` refuses these states before changing tables. |

`create_tables()` is an empty-database convenience, not an upgrade mechanism. It refuses incompatible existing tables. The compatibility preflight checks required columns and registry uniqueness; it does not certify migration history, every column type, data quality, or deployment routing. Do not stamp a Core-created database as migration `001` to bypass the checks.

## Install and inspect

Install the matching monorepo packages in the operator's virtual environment:

```sh
python -m pip install -e packages/types -e packages/contracts -e 'packages/core[postgres]' 'alembic>=1.13,<2'
```

Use the deployment's existing secret mechanism to supply `ANIMUS_DATABASE_URL`; do not paste credentials into command arguments or reports. From the repository root:

```sh
python -m animus.durability.cli preflight
```

Exit codes: `0` compatible, `1` incompatible metadata, `2` configuration or connection failure. The command reads schema metadata and does not create tables. An incompatible result before upgrading `001` is expected. Connection errors are summarized without their raw exception text.

After backup/restore verification and operator approval, stop writers and apply the migration:

```sh
python -m alembic -c database/alembic.ini upgrade head
python -m animus.durability.cli preflight
```

Migration `002` keeps registry payloads and existing Kernel ledger rows, adds tags and Core's transactional outbox, and enforces one current row per globally unique object ID. SQLite primary keys are corrected from BIGINT to INTEGER so generated IDs work. PostgreSQL retains its existing BIGSERIAL keys.

Do not use downgrade as routine production rollback. The `002` downgrade refuses populated outbox evidence or nonempty tags; removing those records merely to pass the guard would destroy evidence. Prefer a tested backup restoration or a reviewed forward migration.

## Application boundary

```python
from animus.durability.postgres_store import DurableObjectStore
from animus.durability.scope import ObjectScope

store = DurableObjectStore(scope=ObjectScope.hunter("owner-configured-by-operator"))
store.preflight()
```

The immutable server-selected scope fixes owner, `hunter-os` workspace, Monster Hunter Wilds domain, public security, `hunter_os` schema, allowed artifact types, and active lifecycle. SQL filters cover current reads, version/time reads, lists, ledger access and mutations. Historical public versions are hidden when their current object becomes private, deleted, or otherwise outside the scope. Global outbox worker methods are denied on scoped stores.

For Core's `DurableObjectStore`, the legacy `owner_id` and `workspace_id` constructor arguments alone **do not restrict queries**. Existing unscoped callers remain trusted internal clients. The Hunter adapter must inject this explicit scope and later expose a narrower read interface to chat.

Kernel's `DurableMemoryStore` restricts every read and mutation to its configured owner/workspace and the `memory-v1` schema, `memory` artifact type, and `user` domain. Broad memory searches and tag listings therefore exclude Hunter payloads before deserialization. Attempts to store a memory under a foreign object ID, including a historical ID, fail without replacing records or emitting events. Existing deployments must retain their configured owner/workspace; this change does not move or rewrite memories.

Scoped writes require the contracts package. Scoped updates also require `expected_version`; stale or concurrent changes fail atomically. Registry rows, Core ledger envelopes and outbox entries commit together. Both object/version and current-object uniqueness are enforced by the database. Object IDs are global, not reusable per owner. Use compliant stable IDs such as `mhw-monster-rathian`.

Effective timestamps must be timezone-aware. Hunter `valid_from` / `valid_to` remain null when unknown; imports must not invent effective dates from verification or import time. `recorded_at` tracks the transaction time. Overlapping effective intervals return the latest recorded version applicable to the requested world time. Legacy unscoped callers retain their existing write-time validity behavior.

The physical ledger follows migration `001`: `event_kind`, `actor_refs`, `object_refs`, `event_data`, `idempotency_key` and temporal fields. Core stores its existing event dictionary, including version and integrity hash, inside `event_data`; `event_kind` is the Core event type and `idempotency_key` is its event ID. Core's public ledger API returns the existing envelope and excludes Kernel events. Kernel keeps writing its native events. Direct SQL consumers expecting the older Core physical columns need migration before use.

## Verification and remaining gates

The regression suite exercises SQLite and, when `HUNTER_TEST_DATABASE_URL` is set, PostgreSQL in a randomly named temporary schema. Use a disposable test database; the suite creates and drops only its test schemas and never reads `ANIMUS_DATABASE_URL` as a test target.

```sh
python -m pytest packages/core/tests/test_registry_compatibility.py packages/core/tests/test_kernel_registry_isolation.py -q
```

CI runs the integration suite on PostgreSQL 14, 15 and 16. Local verification used PostgreSQL 16. Tests cover migration data preservation and refusal, Core/Kernel coexistence, privacy filters, deleted/reclassified history, compare-and-swap races, rollback on outbox failure, temporal boundaries, logging and operator preflight.

The [typed repository and domain audits](../projects/HUNTER_OS_REPOSITORY.md) now build on this foundation in a separate review step. The generic envelope alone does not validate exact Hunting Horn songs, ammo tables, sources, or publish eligibility; consumers must use the typed repository. The [four-record import preview](hunter-os-import-preview.md) is implemented and also stages the 101 forum blocks. The atomic, idempotent SQL importer remains next. Live database inspection, legacy-layout conversion if needed, bot ownership and end-to-end shared-chat isolation remain deployment gates.
