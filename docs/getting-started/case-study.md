# Case Study: Animus

*Personal AI Framework for Cognitive Sovereignty*

> ℹ️ **Point-in-time snapshot (early 2026).** The metrics below (18K LOC, 333
> tests, 5 packages) reflect an early build and are **not current** — the
> monorepo has since grown to four shipped packages with ~14K+ tests. See the
> repo `README.md` for live counts and [`../architecture/canonical-principles.md`](../architecture/canonical-principles.md) for which
> documents are authoritative. The "AES-256 at rest" line is a design target,
> **not implemented** (stores persist plaintext). Chroma references below record
> the historical implementation and are not current installation or backend
> selection guidance; Core now fails closed on legacy Chroma configuration.

---

## Executive Summary

Animus is an open-source framework for building a **personal AI** — one that persists, learns, and serves a single user by design. Unlike cloud AI assistants that forget everything between sessions, Animus implements a local-first exocortex with persistent memory, cross-device sync, and guardrailed self-learning.

**By the numbers:**

| Metric | Value |
|--------|-------|
| Lines of code | 18,000+ |
| Tests | 333 across 10 files |
| Memory types | 4 (episodic, semantic, procedural, active) |
| Interfaces | 4 (CLI, API, voice, WebSocket sync) |
| Integrations | 7 (Ollama, Calendar, Gmail, Todoist, Whisper, ChromaDB, sync) |
| Development phases | 5 of 6 complete |

---

## The Problem

Current AI assistants are **rented, not owned**. They're stateless, cloud-dependent, and generic:

| Gap | Impact |
|-----|--------|
| **No memory** | Every conversation starts from zero |
| **No personalization** | Responses are generic, not adapted to you |
| **No sovereignty** | Your data lives on corporate servers, used for training |
| **No continuity** | Context doesn't follow you across devices |
| **No learning** | The AI never gets better at helping *you* specifically |
| **Vendor risk** | Terms of service can change; features can be revoked |

> "You don't own it. You rent access."

---

## The Solution

Animus inverts the model: **an AI that is yours**.

```
┌─────────────────────────────────────────────────────────────┐
│                     Interface Layer                         │
│     CLI (Rich)  ·  API (FastAPI)  ·  Voice (Whisper)       │
│                    ·  Sync (WebSocket)                      │
├─────────────────────────────────────────────────────────────┤
│                    Cognitive Layer                          │
│         Model-agnostic reasoning (Ollama/Claude/OpenAI)     │
│              Tool use  ·  Analysis modes                    │
├─────────────────────────────────────────────────────────────┤
│                     Memory Layer                            │
│     Episodic  ·  Semantic  ·  Procedural  ·  Active        │
│                  ChromaDB vector storage                    │
├─────────────────────────────────────────────────────────────┤
│                    Learning Layer                           │
│       Pattern detection  ·  Guardrails  ·  Rollback        │
├─────────────────────────────────────────────────────────────┤
│                      Core Layer                             │
│        Identity  ·  Security  ·  Preferences                │
└─────────────────────────────────────────────────────────────┘
```

**Key capabilities:**

- **Persistent memory** — Four types matching human cognition: episodic (what happened), semantic (what you know), procedural (how you work), active (current context)
- **Local-first** — Ollama for inference, ChromaDB for storage, works offline
- **Cross-device sync** — WebSocket + Zeroconf for seamless context handoff
- **Voice interface** — Whisper STT + TTS for hands-free operation
- **Guardrailed learning** — Pattern detection bounded by immutable safety rules
- **Integrations** — Google Calendar, Gmail, Todoist via OAuth2

---

## Architecture Decisions

### 1. Local-First by Design

**Decision:** All core functionality runs locally. Cloud AI is optional.

**Rationale:** Personal AI handles sensitive data — decisions, health, finances, relationships. Cloud dependency creates privacy risk and single point of failure. Local-first means:
- Works offline
- Data stays on-device
- No third party trains on your information
- No vendor can revoke access

### 2. Four Memory Types

**Decision:** Implement episodic, semantic, procedural, and active context as distinct systems.

**Rationale:** Human cognition uses different memory types for different purposes:

| Type | Purpose | Example |
|------|---------|---------|
| Episodic | What happened | "Last Tuesday you decided to use PostgreSQL" |
| Semantic | What you know | "User prefers concise responses" |
| Procedural | How you work | "Deploy process: test → stage → prod" |
| Active | Current session | "We're discussing the auth refactor" |

Conflating these into a single vector store loses the structure that makes retrieval useful.

### 3. Guardrailed Learning

**Decision:** Bound all learning with immutable safety rules.

**Rationale:** A personal AI that learns your patterns is powerful but dangerous without constraints:

```python
# Core guardrails (immutable)
- Cannot take actions that harm user
- Cannot exfiltrate data without consent
- Cannot modify its own guardrails
- All learning must be transparent
- All learning must be reversible
```

The three-tier system (immutable core → system defaults → user preferences) ensures learned behavior can never erode safety.

### 4. Phased Development

**Decision:** Build in six phases, each delivering a working system.

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation — basic conversation + memory | ✅ Complete |
| 1 | Memory architecture — 4 memory types | ✅ Complete |
| 2 | Cognitive capabilities — tools, analysis | ✅ Complete |
| 3 | Multi-interface — voice + API + sync | ✅ Complete |
| 4 | Integration — calendar, email, tasks | ✅ Complete |
| 5 | Self-learning — pattern detection, guardrails | ✅ Complete |
| 6 | Ambient — wearable, vehicle integration | 🔜 Future |

**Rationale:** Building the full vision at once would be a multi-year monolith. Each phase ships a complete, testable system. Feedback informs later design.

---

## Technical Implementation

### Memory System

ChromaDB stores vector embeddings for semantic search. Each memory entry is typed, timestamped, and tagged:

```python
memory.remember(
    content="User prefers concise responses",
    memory_type="semantic",
    tags=["preference", "communication"],
    confidence=0.9,
)

# Retrieval with type-weighted scoring
context = memory.recall("How should I communicate?", limit=5)
```

Episodic memories decay over time; semantic memories remain stable.

### Cross-Device Sync

WebSocket-based synchronization with Zeroconf for automatic discovery:

```
Device A ──────────────────────────────────────► Device B
          [memory delta, encrypted, signed]
```

- Eventual consistency with last-write-wins
- Device priority ordering for conflicts
- End-to-end encryption on all sync traffic

### Learning System

Pattern detection with explicit approval workflow:

```python
# Scan memories for patterns
patterns = learning.scan_and_learn()

# Review what was learned (transparency)
pending = learning.get_pending_learnings()

# Approve or reject
learning.approve(pending[0].id)

# Rollback if needed
learning.rollback.restore(checkpoint_id)
```

---

## Competitive Position

| Aspect | ChatGPT/Claude | Local LLM UIs | Voice Assistants | Animus |
|--------|----------------|---------------|------------------|--------|
| Memory | None | None | Limited | 4 types, persistent |
| Data location | Cloud | Local | Cloud | Local-first |
| Cross-device | Via account | None | Via account | P2P sync |
| Learning | Hidden | None | Hidden | Transparent, reversible |
| Sovereignty | Vendor-owned | Partial | Vendor-owned | User-owned |
| Offline | No | Yes | No | Yes |

**Unique position:** The only open-source, local-first personal AI with guardrailed self-learning and structured memory types.

---

## Results & Metrics

| Category | Metric |
|----------|--------|
| **Code** | 18,000+ lines of Python |
| **Tests** | 333 test functions |
| **Coverage** | Comprehensive (all major components) |
| **Modules** | 41 source files across 5 packages |
| **Docs** | 5 major documents (Architecture, Roadmap, Use Cases, Safety, Connectivity) |

**Engineering practices:**
- Full type hints (mypy validated)
- Comprehensive test suite (pytest)
- Consistent formatting (ruff)
- Protocol-based extensibility
- Security-first design (tier-scoped egress, DLP redaction, audit logging;
  AES-256 at rest is a design target, not yet implemented)

---

## Tech Stack

```
Python 3.10+  ·  Ollama (Llama 3.2, Mistral)  ·  ChromaDB
FastAPI  ·  OpenAI Whisper  ·  Rich CLI  ·  WebSockets
Zeroconf  ·  Google Calendar/Gmail API  ·  Todoist API
pytest  ·  Ruff  ·  mypy
```

---

## Demo Points

For interviews and walkthroughs:

1. **Memory recall** — Show multi-turn conversation where Animus remembers context from previous sessions
2. **Learning system** — Demonstrate pattern detection → approval → application flow
3. **Guardrails** — Show how immutable constraints prevent unsafe learned behavior
4. **Cross-device** — Sync context between two devices in real-time
5. **Voice mode** — Hands-free interaction with STT/TTS

---

## Why This Matters

**For AI Engineering roles:**
- Demonstrates understanding of LLM limitations and how to work around them
- Shows production patterns: type safety, testing, security, modularity
- Implements non-trivial systems: vector search, sync protocols, learning with rollback

**For Solutions Engineering roles:**
- End-to-end product thinking: problem → architecture → implementation → interfaces
- Multiple integration points (OAuth, APIs, WebSockets)
- Clear documentation and explainability

**For Developer Relations roles:**
- Open-source project with comprehensive docs
- Teaches concepts through working code
- Designed for extensibility and community contribution

---

## Links

- **Repository:** [github.com/your-org/animus](https://github.com/your-org/animus)
- **Architecture:** [docs/../architecture/overview.md](../architecture/overview.md)
- **Use Cases:** [docs/use-cases.md](use-cases.md)
- **Safety Model:** [docs/../reference/safety.md](../reference/safety.md)
- **Roadmap:** [docs/../roadmap/current.md](../roadmap/current.md)
