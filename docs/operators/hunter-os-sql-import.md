# Hunter OS operator SQL import

The importer stages the four legacy Hunter candidates in the existing scoped SQL
registry. It preserves their review holds: envelope `candidate` / `unverified`,
payload `review`, and unknown effective dates. Shared chat's `HunterOSRepository`
continues to exclude them. There is no approval switch in this API.

The 101 forum blocks remain in the complete source preview inside the plan. This
step does not invent canonical records for them or publish them to Discord. It
also does not migrate Chroma, access general memory, or change n8n workflows.

## Prepare a review plan

Install matching packages, including SQL dependencies:

```sh
python -m pip install -e packages/types -e packages/contracts -e 'packages/core[postgres]'
```

Use the deployment's secret mechanism to set `ANIMUS_DATABASE_URL`. Do not put the
URL in command arguments or reports. The existing registry must already pass the
[compatibility preflight](hunter-os-persistence.md); these commands do not create
or migrate tables. SQLite requires an absolute, non-URI database filename. Relative
URLs and in-memory SQLite are refused because they do not identify a persistent
operator destination unambiguously.

```sh
python -m animus.hunter_os.import_cli --owner owner-configured-by-operator \
  plan --as-of 2026-09-24 --output hunter-import-plan.json
```

The default source is the packaged staged snapshot. For a revised source bundle,
place `--source-root /absolute/path/to/sources` before the subcommand, both when
planning and applying. The complete manifest/hash validation from the
[offline preview](hunter-os-import-preview.md) runs again. Output must be a new
file outside the source bundle.

Inspect the plan before apply. It contains the destination fingerprint, owner,
source preview (in `preview_json`), proposed create/update/unchanged/conflict
operations, and each expected version/envelope fingerprint. The embedded preview
contains every source byte, mapping and audit finding. Destination credentials are
not serialized. Destination binding is a configuration check, not a signature or
authentication mechanism; keep these commands restricted to trusted operators.

Current records outside the Hunter scope remain invisible to planning. A proposed
create can therefore encounter an unavailable global ID at apply; the entire
batch then rolls back with a sanitized conflict. The importer never reveals the
foreign record or reuses a deleted/historical ID.

## Apply only the inspected plan

```sh
python -m animus.hunter_os.import_cli --owner owner-configured-by-operator \
  apply-review --plan hunter-import-plan.json
```

This is an explicit database write. It re-derives every payload from the checked
sources, checks the plan's source bytes and destination, and refuses structural
conflicts, missing/duplicate candidate identities, changed converter output, or
existing records not owned by this importer in candidate/unverified/review state.
The reviewed plan cannot supply replacement game facts or approval metadata.

A single transaction writes all changed registry versions, evidence-bearing
ledger events and outbox entries. Evidence includes the original YAML bytes,
source commit/path/hash, repository/origin, source verification claims and field
mappings. Each registry version carries the corresponding source-evidence stamp;
this does not make that content verified. Forum prose stays in the plan artifact,
which should be retained with the import result.

PostgreSQL locks existing rows in stable ID order; SQLite obtains its write
reservation before reading. Current-record ownership is checked under that lock.
Changes require both the planned version and whole-envelope fingerprint, with a
SQL compare-and-swap before superseding a version. Global identity uniqueness
protects simultaneous creates. A failure anywhere rolls back the entire batch.
There is no schema change and no application-level deletion path.

An exact match of the current envelope is a no-op, including a replay of an
already applied plan after a lost response. No-op entries create no version,
ledger event or outbox item. A YAML comment or origin revision change creates a new
version to preserve changed source evidence even if the game payload is identical.
A later audit date or unrelated forum edit does not reversion unchanged records.

Exit `0` means planning/apply completed; inspect the JSON outcome. Planning can
succeed with reported conflicts, which apply will refuse. Exit `1` is a sanitized
operation failure; argument errors use `2`. If apply cannot confirm completion,
inspect the registry or replay the same plan against the same inputs. Do not infer
rollback solely from a connection error during commit or a lost output stream.

## Python API

```python
from datetime import date
from animus.durability.postgres_store import DurableObjectStore
from animus.durability.scope import ObjectScope
from animus.hunter_os.importer import HunterOSImporter

store = DurableObjectStore(scope=ObjectScope.hunter("owner-configured-by-operator"))
operator = HunterOSImporter(store)
plan = operator.plan(as_of=date(2026, 9, 24))
# Inspect and retain plan.to_json() before this separately authorized write:
result = operator.apply(plan)
```

Keep this operator capability separate from the read-only chat repository. Database
credentials remain trusted application authority; these guards are not database
row-level security. Store a copy of the plan and result for operational recovery.

## Rehearsal and review evidence

An independently built wheel was installed in a fresh environment and its CLI ran
with Python isolated mode outside the checkout. In a migration-created disposable
SQLite database, planning left all three tables empty; first apply produced four
registry versions, four ledger events and four outbox entries. Replaying the exact
plan left all three counts at four. All four records remained ineligible for chat.
The temporary database was removed after the rehearsal.

Independent review identified an ambiguous relative-SQLite destination binding;
the implementation now rejects relative, in-memory and URI SQLite URLs. Follow-up
review verified that fix and the current-record protection check inside the
transaction. PostgreSQL 14/15/16 CI now includes the importer suite.

## Remaining gates

This implementation does not authorize applying to a live host. Live schema and
backup/restore inspection, Stheno access, source-content review, Chroma dependency
resolution, presenter/chat isolation and hosted checks remain deployment work.
