# Animus Memory Architecture — Gap Specs

> **SUPERSEDED — historical design only.** Do not use this document as a
> current implementation plan. Its original ChromaDB directions were retired
> from supported Core. Current work must target the supported local JSON or
> durable SQL stores described in `docs/architecture/memory.md` and
> `docs/roadmap/roadmap-to-10.md`.


**Status:** Superseded historical draft
**Scope:** Two missing specs identified via competitive analysis (OpenClaw 3-tier memory)
**Author:** ARETE

---

## Gap 1: Memory Promotion Logic

### Problem

The HOT/WARM/COLD tier structure is specced. The *mechanism that moves memory between tiers* is not. Without explicit promotion logic, agents either keep everything hot (context bloat) or lose context permanently (the exact problem we're solving).

### Policy

Memory tier assignment is governed by three signals:

| Signal | Description |
|---|---|
| **Access frequency** | How often this memory node is retrieved |
| **Recency** | When it was last accessed |
| **Explicit tag** | Human or agent-set priority override |

### Tier Definitions

| Tier | Storage | TTL Before Review | Promotion Trigger | Demotion Trigger |
|---|---|---|---|---|
| **HOT** | Active context window | Current session | N/A (entry point) | Session end → WARM or discard |
| **WARM** | Supported configured store | 30 days idle | Accessed 3+ times in 7 days OR explicit tag | 30 days no access → COLD |
| **COLD** | Supported configured store | Indefinite | Explicit retrieval request | N/A — permanent unless deleted |

### Promotion Flow

```
Session ends
    │
    ▼
HOT context reviewed by Utrennyaya (conversation coherence aspect)
    │
    ├─ Significant fact / decision / preference detected?
    │       │
    │       └─► Write to WARM with metadata tag
    │
    └─ Transient exchange (small talk, lookups)?
            │
            └─► Discard

Every 30 days (cron or Polunochnaya review):
    │
    ├─ WARM nodes with 0 access in 30 days → promote to COLD
    └─ COLD nodes explicitly retrieved → promote to WARM
```

### Metadata Schema

Every memory node carries:

```json
{
  "id": "uuid",
  "content": "...",
  "tier": "HOT | WARM | COLD",
  "created_at": "ISO8601",
  "last_accessed": "ISO8601",
  "access_count": 0,
  "tags": [],
  "source": "episodic | semantic | procedural",
  "promoted_by": "agent_id | human",
  "signature": "Ed25519 signed by Core"
}
```

### Zorya Responsibility

- **Utrennyaya** — runs end-of-session HOT review, writes to WARM
- **Polunochnaya** — runs 30-day audit, demotes stale WARM to COLD, surfaces patterns
- **Vechernyaya** — monitors procedural memory specifically (code patterns, workflow drift)

---

## Gap 2: Context Compaction Spec

### Problem

When the active context window approaches its limit, older messages vanish silently. The agent loses information without knowing it lost it. "Lossless" compaction requires an explicit spec for: what gets summarized, by whom, stored where, and how it's flagged for re-expansion.

### Trigger

Compaction fires when active context reaches **75% of model context window limit**.

Threshold is configurable per model:

```yaml
compaction:
  trigger_threshold: 0.75   # % of context window
  summary_model: "same"     # use current active model for summarization
  max_summary_tokens: 512   # per compacted block
  expansion_on_demand: true
```

### Compaction Process

```
Context window at 75%
    │
    ▼
Identify compaction candidates:
  - Messages older than N turns (default: 10)
  - Already-resolved sub-tasks
  - Non-critical exchanges
    │
    ▼
Utrennyaya generates summary block:
  - Key decisions made
  - Facts established
  - Open threads still active
  - Timestamp range covered
    │
    ▼
Summary block written to WARM memory with metadata:
  - type: "compaction_summary"
  - covers_turns: [start, end]
  - expansion_available: true
  - original_turns_ref: [message_ids]
    │
    ▼
Original turns moved to COLD (not deleted)
    │
    ▼
Summary injected into active context as single node
  "[COMPACTED: turns 1-10 — see memory node uuid for expansion]"
```

### Expansion on Demand

When agent or user references something in a compacted block:

```
User: "What did we decide about X earlier?"
    │
    ▼
Retrieval detects reference to compacted range
    │
    ▼
COLD fetch of original turns OR summary expansion
    │
    ▼
Inject relevant excerpt back into context
  "[EXPANDED from compaction uuid]"
```

### Integrity Guarantee

- Original turns are **never deleted**, only moved to COLD
- Compaction summaries are Ed25519 signed at write time
- Expansion always available via explicit retrieval
- Compaction event logged to Quorum signal bus

### "Lossless" Definition

> No information is permanently destroyed. Compression is lossy by definition, but the originals are preserved and retrievable. "Lossless" in this spec means: *no unrecoverable information loss*.

This is the honest version of what OpenClaw calls "lossless." Summaries lose nuance. The originals don't.

---

## Implementation Notes

### Phase Gate

Both specs require:

1. A supported `MemoryLayer` store (`local`/`json` or explicitly configured `durable`) with tier metadata
2. Utrennyaya as an active agent process (not just a model label) — **deferred until Mac Studio**
3. Quorum signal bus for compaction event logging — **deferred until Quorum build sprint**

### MVP Shortcut

Before Mac Studio, a simplified version is buildable:

- Promotion: scheduled code reads supported-store access metadata and moves nodes by threshold
- Compaction: single-model summary call at 75% context, store result, clear old turns
- No Zorya required — just scheduled Python scripts

This gets the behavior without the full architecture. Swap in Zorya aspects when hardware arrives.

---

## Related Docs

- `ANIMUS_WHITEPAPER.md` — full memory layer spec
- `QUORUM_WHITEPAPER.md` — signal bus and stigmergic coordination
- `ZORYA_ARCHITECTURE.md` — three-aspect Ollama ensemble spec
