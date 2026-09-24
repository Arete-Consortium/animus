# Hunter OS typed repository

This is step 2 of the [SQL plan](HUNTER_OS_SQL_AUDIT.md), stacked on the persistence foundation. It adds domain validation and read interfaces. It does not import the four source records, connect the bot, render cards, or publish content.

## Domain contract

`animus.hunter_os.models` defines frozen Core dataclasses for nine discriminated record types:

| Type | Structured fields |
| --- | --- |
| `monster` | Variant, weaknesses, separate target roles, preparation, fight plan, capture rule |
| `special_encounter` | Evidenced mechanics, phases/transitions, capture rule, timeline completeness |
| `weapon_type` | Weapon family, platform controls, rules, core loop, exact-weapon requirement |
| `exact_weapon` | Exact upgrade identity, weapon family, optional tree/parent IDs, exact horn features or ammo table |
| `hunting_horn_tree` | Exact weapon references and evidenced overview; cannot satisfy exact-horn queries |
| `guide` | Explicit presentation topic, named sections, relationships |
| `farm_route` | Target item IDs, locations, evidenced methods, conditions |
| `item_reference` | Evidenced uses and acquisition |
| `skill_reference` | Unique skill levels, evidenced effects and restrictions |

All records retain game, schema version, logical ID, verification state/date, patch metadata, variant, sources, relationships, review reasons, notes and tags. `SourceRef` has a document, section, content SHA-256, optional URL/revision and note. Nested features identify their evidence through source IDs in the same record.

Use `parse_record(payload)` at JSON/SQL boundaries and `record_payload(record)` before a future write. Plain dataclass construction is not a validation boundary. Parsing rejects unknown fields, invalid dates, other games/schema versions, string booleans and scalar coercion. Normalization converts JSON arrays/dates to typed values; unknown values remain null or explicitly unknown. Errors exclude input values. Returned records are detached from SQL; changing a nested dictionary does not persist it.

The schema intentionally represents incomplete review records. The deterministic audit decides eligibility separately. A valid schema or source hash does not independently verify a game fact or establish source reliability. Sources and labels still require human/source review during import.

## Eligibility

Normal retrieval requires all of the following:

- The SQL envelope is in the fixed public Hunter scope and matches the payload ID, artifact type and schema version.
- The envelope workflow is `approved` and epistemic state is `supported`.
- The record is not marked `review` and has no unresolved review reasons.
- Verification date is known, valid and no later than the audit date.
- Source IDs are unique, each source has a section locator and content hash, and feature-level references resolve.
- The record satisfies its family-specific completeness checks.

Exact horns require the exact upgrade name, notes, melodies/effects, Echo Bubble and Special Performance. Each feature needs source references; melody notes must belong to that horn. A tree overview never proves a particular upgrade's songs.

Ammo has three states: `supported`, `unsupported`, `unknown`. Confirmed rows need evidence. Unknown/unsupported rows cannot assert handling properties. Duplicate ammo/level pairs are held. Queries match confirmed support at the requested level only; omitted reload, recoil and rapid-fire details stay unknown. `rapid_fire=false` remains distinct from null. Partially known tables carry an explicit warning.

Patch-sensitive records are held by default. An operator may supply `EligibilityPolicy(max_patch_age_days=..., current_patch=...)`. The age limit is inclusive; when a current patch is supplied, missing/mismatched patch versions are held. `as_of` is optional for reproducible audits; without it the audit uses the current UTC date on every read. A permitted patch-sensitive record always retains a warning and never receives unconditional automatic publication eligibility.

An incomplete special-encounter timeline retains a warning even when its other data is eligible. Declaring a timeline complete requires populated phases. Horn-tree summaries also retain a warning about exact-weapon inference.

## Read interface

```python
from animus.durability.postgres_store import DurableObjectStore
from animus.durability.scope import ObjectScope
from animus.hunter_os.repository import HunterOSRepository, HunterOSReviewRepository

store = DurableObjectStore(scope=ObjectScope.hunter("owner-configured-by-operator"))
repo = HunterOSRepository(store)
review = HunterOSReviewRepository(store)  # operator wiring only

entry = repo.get("mhw-monster-rathian")  # None until imported and eligible
matches = repo.search("encore", limit=6)
monster = repo.monster("mhw-monster-rathian", variant="normal")
horns = repo.horns_with_effects(["canonical-effect-id"])
bowguns = repo.bowguns_with_ammo("canonical-ammo-id", level=1)
operator_entry = review.inspect("mhw-monster-rathian")
versions = review.history("mhw-monster-rathian", limit=20)
```

`weapon_type(id)` and `exact_weapon(id)` also require the correct record family. These examples describe API shape; they do not assert that those records, effect IDs, or ammo IDs have been imported.

Every `HunterEntry` carries its typed record, durable version, effective/transaction timestamps and `AuditReport`. Consumers must preserve the report's caveats and source references in grounding/presentation. The future bot must translate missing or unavailable data into an unknown/unavailable response without falling through to general memory. No language model, memory provider, Discord client or network retrieval is part of this module.

The chat-facing class exposes reads only. The separately constructed operator class can inspect held records and bounded history, while retaining the same SQL privacy scope. Neither adapter exposes mutations. The underlying database credentials still belong to trusted application code; this is not process isolation or database row-level security.

Current records that are deleted or reclassified outside the public Hunter scope also become unavailable through history. Exact IDs and variants are required; normal/tempered/Guardian/special encounters are not silently substituted.

Search returns at most 50 records (default 6), accepts at most 200 query characters and uses stable name/ID tie-breaking. It searches structured Hunter content without ranking source titles or verification metadata. A SQL limit bounds candidate loading (default 1,000; operator maximum 10,000); overflow raises `HunterUnavailableError` rather than returning a silently incomplete result set. Specialist queries use the same bound, applied to exact weapons only. History is capped at 50 versions. Synchronous SQL must run outside a future Discord event loop.

Malformed in-scope payloads or envelope mismatches raise `HunterDataError`; database and schema failures raise a sanitized `HunterUnavailableError`. Query failures never consult another store. These exceptions must be handled at the future bot boundary; the repository itself sends no messages.

## Validation and next work

Tests use synthetic facts and isolated migration-created SQLite/PostgreSQL schemas. They exercise all nine types, strict parsing, incomplete evidence, patch policy, exact horn/ammo queries, variants, private sentinels, malformed envelopes, bounded search, history revocation and sanitized failures. CI's PostgreSQL 14/15/16 jobs now run both the persistence and domain suites.

The [offline import preview](../operators/hunter-os-import-preview.md) now maps the four staged YAML candidates, preserves source bytes/provenance and inventories all 101 forum blocks. It holds every item for review. The [operator SQL importer](../operators/hunter-os-sql-import.md) now stages validated candidates atomically with provenance, ledger and outbox records; unchanged replay is a no-op. These operator writes do not approve records or expose them to chat. Relationships are validated as IDs here; target existence and cross-record consistency belong to that import/repository integration work. Existing PR #129's YAML loader and chat modules must be adapted deliberately to this API, not merged wholesale.

No live database was read or changed and no game facts were newly verified in this step. Merge readiness also requires resolving the persistence PR's remaining repository-wide CI failures and dependency security findings.
