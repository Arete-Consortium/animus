# Memory System Reference

> How Animus stores, retrieves, and manages memories.

---

## Overview

The memory system is the persistent layer of Animus. It stores conversations, facts, procedures, and entities across sessions, enabling long-term context and learning.

**Source of truth:** `packages/core/animus/memory/layer.py`

---

## Memory Types

Memories are categorized by how they are acquired and what they represent:

| Type | Purpose | Example |
|---|---|---|
| **EPISODIC** | Events and conversations | "User asked about database migration on Tuesday" |
| **SEMANTIC** | Facts and knowledge | "User prefers dark mode" |
| **PROCEDURAL** | Workflows and patterns | "Morning routine: check email, review calendar" |
| **ACTIVE** | Current session state | Live context that hasn't been consolidated yet |

**Default type:** `SEMANTIC` (used when none is specified).

---

## Memory Structure

Each memory is a structured record with the following fields:

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Unique identifier (auto-generated) |
| `content` | string | The memory text (may be redacted for secrets) |
| `memory_type` | `MemoryType` | One of: `EPISODIC`, `SEMANTIC`, `PROCEDURAL`, `ACTIVE` |
| `created_at` | datetime | When the memory was first stored |
| `updated_at` | datetime | Last modification time |
| `tags` | list of strings | Normalized lowercase tags for filtering |
| `source` | string | How it was acquired: `stated`, `inferred`, `learned` |
| `confidence` | float (0.0–1.0) | Certainty level (default: 1.0) |
| `subtype` | string or None | Optional refinement (e.g., `fact`, `preference`, `workflow`) |
| `version` | int | Version number (starts at 1, increments on update) |
| `parent_id` | string or None | Previous version's ID (for versioned updates) |
| `change_summary` | string or None | Human-readable description of what changed |
| `provenance` | string | Origin: `direct`, `sync`, `consolidation`, `import`, `mcp` |
| `sensitivity` | `Sensitivity` | Disclosure tier (see below) |
| `tier` | `MemoryTier` | Temperature-based retention tier (see below) |
| `access_count` | int | How many times this memory has been recalled |
| `last_accessed` | datetime or None | Most recent recall time |

---

## Sensitivity (Disclosure Tiers)

Sensitivity controls which parts of the system can access a memory. This is especially important for integrations and MCP tools that may egress data.

| Tier | Meaning | Use Case |
|---|---|---|
| **PUBLIC** | Safe to share externally | General facts, public project names |
| **PERSONAL** | User-specific but not sensitive | Preferences, habits |
| **CONFIDENTIAL** | Sensitive internal information | API keys (should be redacted anyway), business plans |
| **SECRET** | Highly sensitive | Passwords, tokens, private keys |

**Default:** `PUBLIC`. Callers handling private material should set this explicitly.

**Security contract:**
- Internal reads (CLI, learning loop) may pass `allowed_tiers=None` to see everything.
- Any surface that can egress data (MCP tools, automation) **must** use `recall_for_egress()`, which pins results to `PUBLIC` only.

---

## Temperature Tiers

Temperature tiers control retention priority and retrieval speed. The `TierManager` automatically promotes frequently accessed memories and demotes stale ones.

| Tier | Retrieval Speed | Retention Policy |
|---|---|---|
| **HOT** | Fastest | Active session context; kept in fast paths |
| **WARM** | Fast | Default tier; recently accessed |
| **COLD** | Slower | Archival; retrieved only on explicit request |

**Automatic management:**
- Accessing a memory bumps its tier toward `HOT`
- Periodic review demotes stale `HOT` → `WARM` and `WARM` → `COLD`
- Call `run_tier_review()` to trigger this manually

---

## MemoryLayer API

The `MemoryLayer` is the public façade over a pluggable storage backend.

### Initialization

```python
from animus.memory import MemoryLayer

memory = MemoryLayer(
    data_dir=Path.home() / ".animus",
    backend="local",  # "json" is an alias; "durable" requires SQL setup
)
```

### Core Methods

#### `remember(content, memory_type=SEMANTIC, ...)`

Store a new memory.

| Parameter | Default | Description |
|---|---|---|
| `content` | required | Text to store |
| `memory_type` | `SEMANTIC` | Type of memory |
| `metadata` | `{}` | Additional key-value data |
| `tags` | `[]` | Tags to attach |
| `source` | `"stated"` | How acquired |
| `confidence` | `1.0` | Confidence 0.0–1.0 |
| `subtype` | `None` | Optional refinement |
| `provenance` | `"direct"` | Origin |
| `sensitivity` | `PUBLIC` | Disclosure tier |
| `tier` | `WARM` | Temperature tier |

**Returns:** `Memory` object with auto-generated ID and timestamps.

#### `remember_fact(subject, predicate, obj, ...)`

Store a structured semantic fact (subject-predicate-object).

```python
memory.remember_fact(
    subject="User",
    predicate="prefers",
    obj="dark mode",
    category="preference",
)
```

#### `remember_procedure(name, trigger, steps, ...)`

Store a procedural memory (workflow).

```python
memory.remember_procedure(
    name="morning-routine",
    trigger="waking up",
    steps=["check email", "review calendar", "plan day"],
)
```

#### `recall(query, ...)`

Retrieve relevant memories with optional filters.

| Parameter | Default | Description |
|---|---|---|
| `query` | required | Search query |
| `memory_type` | `None` | Filter by type |
| `tags` | `None` | Filter by tags (all must match) |
| `source` | `None` | Filter by source |
| `min_confidence` | `0.0` | Minimum confidence |
| `limit` | `10` | Max results |
| `allowed_tiers` | `None` | Sensitivity filter (set for egress safety) |
| `tier` | `None` | Temperature tier filter |

**Returns:** List of `Memory` objects, sorted by relevance.

#### `recall_by_tags(tags, ...)`

Retrieve memories that have ALL specified tags.

```python
memories = memory.recall_by_tags(["preference", "ui"])
```

#### `get_memory(memory_id)`

Get a single memory by full or partial ID prefix.

```python
mem = memory.get_memory("a1b2c3d4")
```

#### `forget(memory_id)` → `bool`

Delete a memory by ID or partial prefix. Returns `True` if deleted.

#### `update_memory(memory)` → `bool`

Update an existing memory in place. Sets `updated_at` automatically.

#### `update_with_version(memory_id, ...)` → `Memory | None`

Create a **new version** of a memory rather than mutating in place.

| Parameter | Description |
|---|---|
| `memory_id` | ID of the memory to version |
| `content` | New content (or `None` to keep parent's) |
| `tags` | New tags (or `None` to keep parent's) |
| `metadata` | New metadata (or `None` to keep parent's) |
| `change_summary` | Description of what changed (auto-generated if omitted) |
| `provenance` | Origin of this version |

**Returns:** The newly created `Memory` with incremented `version` and `parent_id` pointing to the old one.

This is the preferred way to update memories because it preserves history.

### Tag Management

| Method | Description |
|---|---|
| `add_tag(memory_id, tag)` → `bool` | Add a tag to a memory |
| `remove_tag(memory_id, tag)` → `bool` | Remove a tag |
| `get_all_tags()` → `dict[str, int]` | All tags with usage counts |

### Tier Management

| Method | Description |
|---|---|
| `promote_memory(memory_id)` → `bool` | Move memory up one tier (max `HOT`) |
| `demote_memory(memory_id)` → `bool` | Move memory down one tier (min `COLD`) |
| `run_tier_review()` → `(int, int)` | Review all tiers; returns `(demoted_count, promoted_count)` |

### Egress-Safe Reads

These methods automatically restrict results to `PUBLIC` sensitivity. Use them for any data that may leave the local system (MCP tools, webhooks, etc.).

| Method | Description |
|---|---|
| `recall_for_egress(query, ...)` | Safe version of `recall()` |
| `recall_by_tags_for_egress(tags, ...)` | Safe version of `recall_by_tags()` |

### Export / Import / Backup

| Method | Description |
|---|---|
| `export_memories()` → `str` | Export all memories as JSON string |
| `import_memories(data)` → `int` | Import from JSON string; returns count imported |
| `backup(path)` | Create a ZIP backup at the given path |

---

## Storage Backends

| Backend | Requirements | Characteristics |
|---|---|---|
| **local** / **json** | None | Simple file-based storage; default for new installations |
| **durable** | `sqlalchemy`, PostgreSQL | ACID, bitemporal ledger, audit trail; production-grade |

**Backend selection:** Set `memory.backend` in config or `ANIMUS_MEMORY_BACKEND` env var.
Legacy `chroma` values fail closed. Follow the operator retirement plan and verify
backup, import parity, retrieval behavior, and rollback before changing a deployment.

### Durable Backend (PostgreSQL)

The `durable` backend upstreams the `DurableObjectStore` from `animus-mind` and provides:

- **ACID transactions** via PostgreSQL (or SQLite for testing)
- **Bitemporal recording** — every change is ledgered with valid time + transaction time
- **Optimistic concurrency** — version-based conflict detection on updates
- **Audit trail** — `get_ledger_events()` returns the complete history of any memory
- **Schema compliance** — validates against `animus_contracts` schemas on write

**Usage:**

```python
from animus.memory.layer import MemoryLayer

layer = MemoryLayer(
    backend="durable",
    database_url="postgresql://...",
    workspace_id="ws-production",
)
```

Or via environment variables (see `animus/config.py` for full list).

**Type mappings:**

| Memory Type | Stored As |
|---|---|
| `SEMANTIC` | `cognitive_role="memory"` |
| `EPISODIC` | `cognitive_role="knowledge"` |
| `PROCEDURAL` | `cognitive_role="intelligence"` |

The original UUID is preserved in the payload for round-trip fidelity; the backend uses a schema-compliant `object_id` (`mem-{stripped_uuid}`).

---

## Entity Linking

When `entities.enabled = true` in config, the memory layer automatically extracts and links entities mentioned in memory content.

Example: Storing "Review pull request from Alice on the Animus project" automatically creates/links:
- Entity: `Alice` (type: `person`)
- Entity: `Animus` (type: `project`)

Entity memories are then cross-referenced when you query `/entity Alice`.

---

## Redaction

The memory layer automatically redacts secrets during ingestion. Detected secrets are stored with metadata:

- `_redaction_count`: Number of secrets removed
- `_redaction_types`: Types of secrets found

**Note:** Redaction happens at storage time. If a secret slips through, rotate it immediately — the memory system is not a secrets vault.

---

## See Also

- [CLI Commands Reference](cli-commands.md) — REPL commands for memory operations
- [Tools Reference](tools.md) — Built-in tools including memory tools
- [Configuration](../operators/configuration.md) — Memory backend and tuning
