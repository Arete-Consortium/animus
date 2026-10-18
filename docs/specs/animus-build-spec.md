# Animus — Complete Build Specification

> **SUPERSEDED — historical design only. DO NOT IMPLEMENT.** This March 2026
> build plan predates the current package layout and security boundary. Its
> ChromaDB instructions describe a retired Core runtime and must not be used for
> new code, dependencies, configuration, or tests. Current Core work follows
> `docs/architecture/memory.md`, `docs/operators/chroma-retirement-plan.md`, and
> `docs/roadmap/roadmap-to-10.md`; supported storage is local JSON or explicitly
> configured durable SQL. The legacy Chroma adapter is migration-only.

**For:** Claude Code / Animus self-directed development
**Repo:** `your-org/Animus` (private → alpha on Phase 1b completion)
**Architecture:** Three-layer cognitive system — Core / Forge / Quorum
**Philosophy:** Sovereign, local-first, self-improving AI exocortex
**Last updated:** 2026-03-04

---

## What Animus Is

Animus is not a chatbot. It is a cognitive architecture — a persistent, self-improving AI system that belongs to one person, runs on their hardware, and compounds intelligence over time.

Three layers, each with a distinct responsibility:

```
┌──────────────────────────────────────────────────────┐
│  CORE — identity, memory, interface                  │
│  The user-facing layer. Persistent memory.           │
│  Identity files. CLI + dashboard. Self-improvement.  │
├──────────────────────────────────────────────────────┤
│  FORGE — orchestration, workflows, budget, gates     │
│  The execution layer. YAML-defined pipelines.        │
│  Agent archetypes. Token budget. Quality gates.      │
│  Arete Tools run here as native workflows.           │
├──────────────────────────────────────────────────────┤
│  QUORUM — stigmergic coordination via intent graph   │
│  The coordination layer. No central supervisor.      │
│  Agents read/write a shared Intent Graph (SQLite).   │
│  Boid rules: separation, alignment, cohesion.        │
│  Stability scores replace pheromone concentration.   │
└──────────────────────────────────────────────────────┘
```

**Naming history** (for context, not for use in code):
- Forge was previously called Gorgon
- Quorum was previously called Convergent
- Use Core / Forge / Quorum everywhere in code and docs

---

## Monorepo Structure

```
Animus/
├── CLAUDE.md                      ← this file + arete-tools directives
├── README.md
├── pyproject.toml                 ← workspace root
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 ← ruff + mypy + pytest on push
│   │   └── release.yml            ← PyPI publish on tag
├── core/                          ← Animus Core package
│   ├── pyproject.toml
│   ├── src/animus_core/
│   │   ├── __init__.py
│   │   ├── cli.py                 ← Typer CLI entry point
│   │   ├── config/
│   │   │   ├── schema.py          ← Pydantic settings model
│   │   │   ├── manager.py         ← read/write/chmod 600
│   │   │   └── defaults.py
│   │   ├── memory/
│   │   │   ├── episodic.py        ← ChromaDB: what happened
│   │   │   ├── semantic.py        ← ChromaDB: what things mean
│   │   │   ├── procedural.py      ← SQLite: how to do things
│   │   │   └── manager.py         ← unified memory interface
│   │   ├── identity/
│   │   │   ├── manager.py         ← read/write identity files
│   │   │   ├── assembler.py       ← build system prompt from files
│   │   │   └── files/             ← templates for wizard generation
│   │   │       ├── CORE_VALUES.md.jinja2
│   │   │       ├── IDENTITY.md.jinja2
│   │   │       ├── CONTEXT.md.jinja2
│   │   │       ├── PREFERENCES.md.jinja2
│   │   │       ├── LEARNED.md.jinja2
│   │   │       └── GOALS.md.jinja2
│   │   ├── self/
│   │   │   ├── reflector.py       ← daily summarization → LEARNED.md
│   │   │   ├── writer.py          ← in-conversation identity file writes
│   │   │   ├── proposals.py       ← queue significant changes for approval
│   │   │   └── scheduler.py       ← cron management for reflection loop
│   │   ├── llm/
│   │   │   ├── ollama.py          ← local model interface
│   │   │   ├── anthropic.py       ← cloud fallback
│   │   │   └── router.py          ← local-first routing logic
│   │   ├── dashboard/
│   │   │   ├── app.py             ← FastAPI + HTMX, localhost:7700
│   │   │   ├── routes/
│   │   │   │   ├── chat.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── identity.py
│   │   │   │   ├── proposals.py   ← approve/reject self-improvement proposals
│   │   │   │   └── status.py
│   │   │   └── templates/         ← Jinja2 HTML templates
│   │   ├── wizard/
│   │   │   └── setup.py           ← Rich terminal onboarding wizard
│   │   └── daemon/
│   │       ├── installer.py       ← OS-aware service registration
│   │       ├── linux.py           ← systemd unit
│   │       ├── macos.py           ← launchd plist
│   │       └── windows.py         ← Windows service
│   └── tests/
├── forge/                         ← Animus Forge package
│   ├── pyproject.toml
│   ├── src/animus_forge/
│   │   ├── __init__.py
│   │   ├── engine.py              ← workflow executor
│   │   ├── loader.py              ← YAML workflow parser + validator
│   │   ├── budget.py              ← token + cost tracking, hard ceilings
│   │   ├── checkpoint.py          ← SQLite resume on failure
│   │   ├── agents/
│   │   │   ├── base.py            ← Agent base contract (all agents implement)
│   │   │   └── archetypes/        ← researcher, writer, reviewer, analyst, etc.
│   │   ├── gates/                 ← quality checkpoints between workflow steps
│   │   │   ├── base.py
│   │   │   ├── signal_gate.py     ← Signal quality audit gate
│   │   │   └── autopsy_gate.py    ← Autopsy post-run failure analysis gate
│   │   └── workflows/             ← built-in YAML workflow definitions
│   │       ├── signal-audit.yaml
│   │       ├── autopsy-analysis.yaml
│   │       └── verdict-capture.yaml
│   └── tests/
├── quorum/                         ← Animus Quorum package (Rust core + Python bindings)
│   ├── pyproject.toml
│   ├── Cargo.toml                  ← Rust workspace for perf-critical operations
│   ├── src/animus_quorum/
│   │   ├── __init__.py
│   │   ├── intent_graph.py        ← SQLite-backed directed graph of agent decisions
│   │   ├── intent_node.py         ← IntentNode schema: agent_id, type, subject, stability, evidence
│   │   ├── stability.py           ← StabilityScorer: 0.0 (speculative) → 1.0 (committed)
│   │   ├── resolver.py            ← IntentResolver: semantic query before each agent decision
│   │   ├── boid_rules.py          ← Separation / Alignment / Cohesion applied to agent decisions
│   │   ├── conflict.py            ← conflict detection + stability-precedence resolution
│   │   └── identity.py            ← Agent identity: signed writes, credential verification
│   └── tests/
└── tools/                         ← SHARED CORE LOGIC for Arete Tools
    ├── signal/
    │   └── core/                  ← imported by standalone CLI + Forge gate
    ├── verdict/
    │   └── core/
    ├── autopsy/
    │   └── core/
    ├── calibrate/
    │   └── core/
    └── provenance/
        └── core/
```

---

## Phase Map

### Phase 1a — Talk (MVP)
**Goal:** Animus can have a persistent, context-aware conversation with you.

```
✓ Ollama running locally (local-first LLM)
✓ Identity files generated by wizard (6 markdown files)
✓ ChromaDB memory storing every interaction (episodic + semantic)
✓ System prompt assembled from identity files + retrieved memories
✓ FastAPI dashboard at localhost:7700
✓ CLI entry point: animus chat, animus setup, animus status
```

**Done when:** `animus setup` completes wizard, `animus chat` opens a conversation that remembers the previous one.

---

### Phase 1b — Learn (Self-Improvement Threshold)
**Goal:** Animus improves with use. Memory distills. Identity evolves.

```
+ Reflection loop: daily cron summarizes interactions → LEARNED.md
+ Write tool: Animus can edit IDENTITY/CONTEXT/PREFERENCES/GOALS.md
+ Proposal system: significant changes queued in dashboard for approval
+ Feedback: thumbs up/down in chat → preference signals in LEARNED.md
+ CORE_VALUES.md: hard-locked, Animus cannot write to it ever
```

**Done when:** After 24 hours of use, LEARNED.md contains distilled observations. Animus adjusts its behavior based on feedback without explicit reprogramming.

**This is the threshold.** Past Phase 1b, Animus participates in its own development.

---

### Phase 2 — Act (Forge Integration)
**Goal:** Animus delegates multi-step tasks to Forge pipelines.

```
+ Forge engine running and connected to Core
+ Arete Tools wired as native Forge workflows:
    signal-audit.yaml     → runs on every agent output
    autopsy-analysis.yaml → runs after every Forge workflow
    verdict-capture.yaml  → logs Forge architectural decisions
+ Budget tracking: Animus knows cost of every Forge execution
+ Checkpoint/resume: failed workflows restart from last checkpoint
+ Dashboard: Forge status card, workflow history, cost tracker
```

**Done when:** `animus run signal-audit report.md` executes a Forge pipeline with budget tracking and produces an audit report.

---

### Phase 3 — Scale (Quorum Integration)
**Goal:** Agents coordinate via ambient intent awareness — no supervisor, no message-passing.

Quorum is the computational implementation of biological stigmergy. Agents don't talk to each other. They read the Intent Graph before decisions and write to it after decisions. Coordination emerges from shared perception, not communication.

**Three boid rules adapted to agent decisions:**
- **Separation** — don't duplicate another agent's intent. If an IntentNode exists for a component, don't build a competing version.
- **Alignment** — adopt compatible interfaces. If neighboring agents converge on a data model, align with it.
- **Cohesion** — converge on shared abstractions. Move toward the emerging architectural consensus.

**Stability Score replaces pheromone concentration:**
- `0.0` = speculative (agent has declared intent, no evidence yet)
- `0.5` = validated (another agent has consumed/aligned with this intent)
- `1.0` = committed (code merged, tests passing, multiple dependents)
- Stability decays for unvalidated intents over time (pheromone evaporation analog)
- Autopsy failure classifications reduce stability for the responsible agent

```
+ Intent Graph operational (SQLite, concurrent reads, serialized writes)
+ IntentNode schema: agent_id, intent_type, subject, details, stability, evidence, timestamp
+ StabilityScorer: increases on consumption by others, decays without validation
+ IntentResolver: semantic query over graph before each major agent decision point
+ BoidRules: separation/alignment/cohesion enforced at resolver level
+ Agent Identity: signed writes — each agent has a credential, writes are verified
+ ConflictDetector: flags contradicting intents, resolves via stability precedence
+ Autopsy → Quorum bridge: failure classifications update agent stability scores
+ Dashboard: Quorum status card, intent graph visualization, stability heatmap
```

**Done when:** A Forge workflow with 3+ parallel agents completes correctly with no orchestrator. Each agent queries the intent graph before decisions, writes results after. Coherent output emerges from local rules, not a coordinator.

**The key test:** Remove all message-passing between agents. The system still produces coherent output because agents are reading shared state, not talking to each other.

---

## Identity Files

Six markdown files define who Animus is and who it serves. Lives at `~/.config/animus/identity/`.

```
CORE_VALUES.md    ← LOCKED. Written once during setup. Never auto-edited.
IDENTITY.md       ← Who you are. Name, role, background, goals.
CONTEXT.md        ← Current projects, priorities, what's top of mind.
PREFERENCES.md    ← Tone, format, response style, what you like/dislike.
LEARNED.md        ← What Animus has learned. Written by reflection loop.
GOALS.md          ← Short and long term goals. You write. Animus references.
```

### System Prompt Assembly (every LLM call)

```python
def build_system_prompt(identity_dir: Path, memory_context: str) -> str:
    """Assemble system prompt from identity files + retrieved memory."""
    core       = read(identity_dir / "CORE_VALUES.md")   # always first
    identity   = read(identity_dir / "IDENTITY.md")
    context    = read(identity_dir / "CONTEXT.md")
    prefs      = read(identity_dir / "PREFERENCES.md")
    learned    = read(identity_dir / "LEARNED.md")
    goals      = read(identity_dir / "GOALS.md")

    return f"""
{core}

## Who I'm Talking To
{identity}

## Current Context
{context}

## Goals
{goals}

## Communication Preferences
{prefs}

## What I've Learned About You
{learned}

## Relevant Memory From Previous Conversations
{memory_context}
""".strip()
```

### CORE_VALUES.md — Enforcement

`IdentityManager.write(filename, content)` must raise `PermissionError` if `filename == "CORE_VALUES.md"`. No exceptions. No config flag to override this. The lock is in code, not config.

```python
def write(self, filename: str, content: str) -> None:
    if filename == "CORE_VALUES.md":
        raise PermissionError(
            "CORE_VALUES.md is immutable. "
            "Edit manually or run: animus setup --reset-values"
        )
    # ... write logic
```

---

## Memory Architecture

Three memory types, each with distinct storage and retrieval:

### Episodic Memory (ChromaDB)
*What happened — conversations, events, decisions, outcomes*

```python
# Store every interaction
episodic.store(
    text=f"User: {user_message}\nAnimus: {response}",
    metadata={
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "feedback": None,  # set by thumbs up/down
    }
)

# Retrieve relevant past interactions
results = episodic.query(
    query_text=current_message,
    n_results=5,
    where={"feedback": {"$ne": "negative"}}  # filter out bad responses
)
```

### Semantic Memory (ChromaDB)
*What things mean in your context — project knowledge, relationships, preferences*

```python
# Populated from CONTEXT.md, GOALS.md, and extracted conversation facts
semantic.store(
    text="Animus is a three-layer cognitive architecture: Core, Forge, Quorum",
    metadata={"domain": "technical", "project": "animus", "source": "conversation"}
)
```

### Procedural Memory (SQLite)
*How to do things — learned workflows, repeated patterns, command sequences*

```sql
CREATE TABLE procedures (
    id TEXT PRIMARY KEY,
    trigger_pattern TEXT,
    procedure_description TEXT,
    steps JSON,
    success_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    last_used TIMESTAMP
);
```

---

## Self-Improvement Loop (Phase 1b)

Four mechanisms that together cross the self-improvement threshold:

### 1. Reflection Loop

```python
# src/animus_core/self/reflector.py
class Reflector:
    def run(self) -> None:
        """Daily summarization of interactions → LEARNED.md."""
        recent = self.memory.episodic.get_recent(hours=24)
        if len(recent) < self.config.reflection_min_interactions:
            return

        current_learned = self.identity.read("LEARNED.md")

        prompt = f"""
You are Animus, reviewing your last 24 hours of interactions with your user.

Recent interactions:
{format_interactions(recent)}

Current LEARNED.md:
{current_learned}

Task: What new preferences, patterns, or facts did you observe?
What worked well? What caused friction? What should you remember?

Write an updated LEARNED.md that incorporates new observations.
Be specific. Use their actual words and behaviors as evidence.
Do not pad. Do not generalize. Only write what you actually observed.

Return ONLY the updated LEARNED.md content. No preamble.
"""
        updated = self.llm.complete(prompt)
        self.identity.write("LEARNED.md", updated)
```

### 2. Write Tool (in-conversation updates)

When Animus detects a clear preference during conversation, it proposes an immediate update:

```python
# Triggered when Animus detects: "I prefer X", "always do Y", "never do Z"
def propose_identity_update(
    file: str,
    change: str,
    reason: str,
    significance: str  # "minor" | "significant"
) -> None:
    if significance == "minor":
        # Write directly to PREFERENCES.md or LEARNED.md
        self.identity.append(file, f"\n- {change}")
    else:
        # Queue for dashboard approval
        self.proposals.queue(file=file, change=change, reason=reason)
```

### 3. Proposal System

Significant changes queue for human approval in the dashboard:

```python
# src/animus_core/self/proposals.py
class ProposalQueue:
    def queue(self, file: str, change: str, reason: str) -> str:
        proposal_id = ulid()
        self.db.execute("""
            INSERT INTO proposals (id, file, change, reason, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, [proposal_id, file, change, reason, datetime.utcnow()])
        return proposal_id

    def approve(self, proposal_id: str) -> None:
        proposal = self.db.get(proposal_id)
        self.identity.append(proposal.file, proposal.change)
        self.db.update(proposal_id, status="approved")

    def reject(self, proposal_id: str) -> None:
        # Log rejection so Animus doesn't re-propose the same thing
        self.db.update(proposal_id, status="rejected")
```

### 4. Feedback Signals

Thumbs up/down in dashboard tags interactions in ChromaDB. Reflection loop filters out negatively-tagged interactions when building LEARNED.md summaries. Pattern of negative feedback on a behavior type triggers a proposal to update PREFERENCES.md.

---

## Arete Tools Integration

These tools live in `Animus/tools/` as shared core logic. Both standalone CLIs (`arete-tools/` org) and Forge workflows call the same underlying functions.

### Tool → Animus Layer Mapping

| Tool | Standalone | Forge Integration | Core Integration | Quorum Integration |
|------|-----------|------------------|-----------------|------------------|
| Verdict | CLI captures decisions | verdict-capture.yaml workflow | Feeds Core episodic memory | — |
| Signal | CLI audits any doc | signal-audit.yaml gate | Audits Animus's own outputs | Quality score → stability |
| Autopsy | CLI diagnoses failures | autopsy-analysis.yaml gate | — | Failure patterns → stability score |
| Calibrate | CLI tracks usage | — | Extends Core identity model | — |
| Provenance | CLI captures lineage | Auto-runs on Forge completions | Core decision record | — |

### Signal as Forge Gate

```yaml
# forge/gates/signal-audit.yaml
name: signal-quality-gate
description: Block low-quality outputs before delivery
trigger: before_output_delivery
agent:
  role: quality_auditor
  module: tools.signal.core.analyzer
  config:
    min_score: 6
    fail_on: reasoning_integrity < 0.5
budget:
  max_tokens: 1500
  max_cost_usd: 0.03
on_fail: block_and_flag   # blocks output, flags for human review
on_pass: deliver
```

### Autopsy as Forge Gate + Quorum Feedback

```yaml
# forge/gates/autopsy-analysis.yaml
name: autopsy-post-run
description: Classify failures and update agent stability in Intent Graph
trigger: on_workflow_completion | on_workflow_failure
agent:
  role: failure_analyst
  module: tools.autopsy.core.classifier
budget:
  max_tokens: 1000
  max_cost_usd: 0.02
outputs:
  - autopsy_report.md
  - quorum_intent_write:          # writes directly to Intent Graph
      intent_type: Constrains
      subject: "{failed_agent_id}.reliability"
      details:
        failure_type: "{classified_failure}"
        failure_step: "{origin_step}"
      stability_delta: -0.1       # reduces agent's stability score on failure
      evidence:
        source: autopsy
        run_id: "{workflow_run_id}"
```

### Verdict as Core Memory Extension

```python
# core/memory/decisions/__init__.py
# Every Forge architectural decision auto-logged to Core episodic memory
# Resurfaces at 30/60/90 days for outcome recording
# Core references decision history when advising on similar decisions

class DecisionMemory:
    def log_forge_decision(self, workflow: str, decision: str, rationale: str):
        self.episodic.store(
            text=f"ARCHITECTURAL DECISION: {decision}\nRationale: {rationale}",
            metadata={
                "type": "decision",
                "source": "forge",
                "workflow": workflow,
                "outcome_due": (datetime.utcnow() + timedelta(days=60)).isoformat(),
                "outcome": None
            }
        )
```

---

## Quorum Architecture (Phase 3)

Quorum is the coordination layer. It is not a message bus, not a supervisor, not a pipeline. It is a **shared perceptual environment** that agents read and write. Coordination emerges from local rules applied to shared state — exactly as in biological stigmergic systems.

**Implementation:** Rust core for performance-critical graph operations (PyO3 bindings to Python). Read-heavy, write-light. SQLite for persistence, concurrent reads, serialized writes.

### IntentNode — The Core Data Structure

```python
@dataclass
class IntentNode:
    agent_id:    str          # Which agent published this (verified credential)
    intent_type: IntentType   # Provides | Requires | Constrains
    subject:     str          # What it's about ("UserModel", "AuthService", "signal-audit")
    details:     dict         # Schema, interface definition, constraints — structured
    stability:   float        # 0.0 (speculative) → 1.0 (committed)
    evidence:    list[Evidence]  # Tests passing, code committed, dependents consuming
    timestamp:   datetime     # When published
    signature:   str          # Cryptographic signature from agent credential
```

### Stability Score — The Pheromone Analog

Stability replaces pheromone concentration. It is the signal agents use to decide whether to align with an intent or treat it as speculative.

```
0.0  → speculative   Agent declared intent, no validation yet
0.3  → acknowledged  At least one other agent has read this intent
0.5  → validated     Another agent has built on or aligned with this intent
0.8  → stable        Multiple consumers, evidence attached (tests, commits)
1.0  → committed     Irreversible — code merged, external dependency formed

Stability increases:
  + another agent consumes/depends on this intent (+0.2)
  + evidence attached: tests passing (+0.1), code committed (+0.2)
  + time with dependents (gradual reinforcement)

Stability decays:
  - no consumers after N hours (unvalidated intents fade)
  - Autopsy failure classification on this agent (-0.1 per failure)
  - conflict detected with higher-stability intent (-0.15)
```

### IntentResolver — Agent Perception

Before every major decision, an agent queries the intent graph:

```python
class IntentResolver:
    def query_before_decision(
        self,
        agent_id: str,
        decision_domain: str,   # "data_model", "api_shape", "dependency", "output_format"
        context: str            # semantic description of current task
    ) -> list[IntentNode]:
        """
        Returns relevant high-stability intents in semantic neighborhood.
        Agent uses this to apply boid rules before deciding.
        """

    def check_separation(self, proposed_intent: IntentNode) -> Optional[IntentNode]:
        """Returns existing intent if duplication would occur (separation rule)."""

    def find_alignment_targets(self, subject: str) -> list[IntentNode]:
        """Returns existing intents to align interfaces with (alignment rule)."""

    def get_consensus(self, domain: str) -> Optional[IntentNode]:
        """Returns highest-stability intent in domain for cohesion (cohesion rule)."""
```

### Boid Rules — Local Coordination Logic

Each agent applies three rules using IntentResolver output, before acting:

```python
class BoidRules:
    def separation(self, resolver: IntentResolver, proposed: IntentNode) -> Decision:
        """
        SEPARATION: Don't duplicate existing work.
        If high-stability intent exists for this subject → don't build competing version.
        Instead: consume existing intent, build on top of it.
        """
        existing = resolver.check_separation(proposed)
        if existing and existing.stability > 0.5:
            return Decision.ALIGN_WITH_EXISTING
        return Decision.PROCEED

    def alignment(self, resolver: IntentResolver, subject: str) -> Optional[dict]:
        """
        ALIGNMENT: Adopt compatible interfaces.
        Find what neighboring agents have converged on → match it.
        Returns the interface/schema to align with, or None if no consensus.
        """
        targets = resolver.find_alignment_targets(subject)
        if targets:
            return max(targets, key=lambda x: x.stability).details
        return None

    def cohesion(self, resolver: IntentResolver, domain: str) -> Optional[IntentNode]:
        """
        COHESION: Move toward shared abstractions.
        Find the emerging consensus in this domain → build toward it.
        """
        return resolver.get_consensus(domain)
```

### Agent Identity — Signed Writes

Every write to the intent graph is signed. No anonymous writes. No impersonation.

```python
class AgentCredential:
    agent_id:   str      # unique identifier, assigned at Forge workflow instantiation
    public_key: str      # used to verify signatures on IntentNodes
    role:       str      # archetype (researcher, writer, reviewer, etc.)
    created_at: datetime
    workflow_id: str     # which Forge workflow this agent belongs to

class IntentGraph:
    def write(self, node: IntentNode, credential: AgentCredential) -> bool:
        """Verifies signature before writing. Rejects unsigned or mismatched writes."""
        if not verify_signature(node, credential):
            raise PermissionError(f"Agent {node.agent_id} signature invalid")
        # Detect anomalous write patterns (agent writing outside its domain)
        if self._is_anomalous(node, credential):
            self._flag_for_review(node, credential)
        return self._write(node)

    def _is_anomalous(self, node: IntentNode, cred: AgentCredential) -> bool:
        """Flags if agent is writing to domains inconsistent with its role/history."""
        # A researcher agent writing execution intents = anomaly
        # An agent writing at 10x its normal frequency = anomaly
        ...
```

### Prompt Injection Defense

Forge workflows that ingest external content (web research, document processing, user input) are vulnerable to indirect prompt injection — malicious instructions hidden in content that agents read.

```python
class InjectionGuard:
    """Runs on all external content before it enters agent context."""

    INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"you are now",
        r"new system prompt",
        r"disregard your",
        r"forget everything",
        # ... extended pattern set
    ]

    def scan(self, content: str, source: str) -> ScanResult:
        """
        Heuristic + Claude API scan for injection patterns.
        Fast heuristic first, Claude API only on suspicious content.
        """
        heuristic_hits = self._pattern_scan(content)
        if not heuristic_hits:
            return ScanResult(safe=True)

        # Escalate to Claude API for confirmation
        verdict = self._llm_verify(content)
        if verdict.is_injection:
            self._log_attempt(content, source, verdict)
            return ScanResult(safe=False, reason=verdict.reason)
        return ScanResult(safe=True)
```

**Where InjectionGuard runs:**
- Forge: on all tool outputs that return external content (web search, document fetch, API responses)
- Agentlint: as a static rule — flags agent configs that ingest unscanned external content
- Context Hygiene: flags injected content that may have persisted into conversation history

### Conflict Resolution

When two agents publish conflicting intents (both claim to provide incompatible versions of the same thing):

```python
class ConflictResolver:
    def resolve(self, node_a: IntentNode, node_b: IntentNode) -> Resolution:
        """
        Resolution order:
        1. Higher stability wins (community signal)
        2. More evidence wins (tests, commits)
        3. Earlier timestamp wins (priority of declaration)
        4. Escalate to human via dashboard if all equal
        """
        if abs(node_a.stability - node_b.stability) > 0.2:
            winner = max([node_a, node_b], key=lambda x: x.stability)
            loser = min([node_a, node_b], key=lambda x: x.stability)
            loser.stability *= 0.5  # penalize, don't delete
            return Resolution(winner=winner, method="stability_precedence")
        # ... further resolution logic
```

---

## Forge Workflow Specification

All Forge workflows are YAML-defined. No hardcoded pipelines. Logic lives in prompts and agent configs, not Python.

### Workflow Schema

```yaml
name: string                    # workflow identifier
description: string             # plain English purpose
version: string                 # semver

agents:
  - role: string                # archetype name
    prompt: path/to/prompt.md   # relative to Forge root
    module: optional.python.module  # for tool integrations

budget:
  max_tokens: integer
  max_cost_usd: float
  warn_at_pct: 80               # warn when 80% of budget spent

gates:
  - after: agent_role           # run gate after this agent
    check: expression           # boolean expression
    on_fail: block | warn | skip

checkpoint:
  enabled: true                 # resume from last checkpoint on failure
  storage: sqlite               # or redis for distributed

output: path/to/output.md       # final output location
```

### Agent Archetypes (built-in)

```
researcher    — information gathering, source evaluation
writer        — content generation, formatting
reviewer      — quality assessment, fact checking
analyst       — data analysis, pattern identification
coordinator   — task decomposition, subtask assignment
auditor       — compliance, quality gate execution
```

### Budget Management

```python
# forge/budget.py
class BudgetManager:
    def __init__(self, max_tokens: int, max_cost_usd: float):
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.spent_tokens = 0
        self.spent_cost = 0.0

    def check(self, estimated_tokens: int) -> bool:
        """Return False if this call would exceed budget."""
        projected_cost = estimate_cost(self.spent_tokens + estimated_tokens)
        if projected_cost > self.max_cost_usd:
            raise BudgetExceeded(
                f"Projected cost ${projected_cost:.4f} exceeds "
                f"budget ${self.max_cost_usd:.4f}"
            )
        return True

    def record(self, tokens_used: int, cost: float) -> None:
        self.spent_tokens += tokens_used
        self.spent_cost += cost
```

---

## Dashboard Specification

FastAPI + HTMX. No npm. No build step. Runs at `localhost:7700`.

### Routes

```
GET  /                    → status overview (Forge health, memory stats, proposals badge)
GET  /chat                → conversation interface
GET  /memory              → browse episodic memory, search, delete
GET  /identity            → view/edit identity files (except CORE_VALUES — read only)
GET  /proposals           → pending self-improvement proposals with approve/reject
GET  /forge               → workflow history, cost tracker, running pipelines
GET  /tools               → Arete Tools status, last run, results
```

### Design Tokens

```css
--background:  #0f0f0f
--surface:     #1a1a1a
--accent:      #00ff88
--text:        #e0e0e0
--muted:       #666666
--danger:      #ff4444
--warning:     #ffaa00
```

### Proposals Page (critical UX)

Each proposal card shows:
- File being modified
- Current content (before)
- Proposed change (after) — diff view
- Animus's reasoning for the change
- Approve button (green) / Reject button (red)
- "Explain more" button → opens detail panel

Rejected proposals: logged with reason, Animus learns not to re-propose. Approved proposals: written immediately, logged to memory.

---

## CLI Interface

```bash
# Setup and onboarding
animus setup               # run full onboarding wizard
animus setup --reset       # reset config only
animus setup --reset-values  # reset CORE_VALUES.md (manual only)

# Conversation
animus chat                # open interactive chat session
animus chat --session X    # resume specific session

# System
animus status              # health check: Ollama, memory, Forge, Quorum
animus dashboard           # open dashboard at localhost:7700
animus update              # pull latest version

# Memory
animus memory search "query"      # search episodic memory
animus memory clear --confirm     # clear all memory (destructive)

# Identity
animus identity show              # print all identity files
animus identity edit PREFERENCES  # open in $EDITOR

# Forge (Phase 2)
animus run <workflow>             # execute a Forge workflow
animus run signal-audit <file>    # run Signal audit via Forge
animus run autopsy <log>          # run Autopsy via Forge
animus run verdict ingest         # run Verdict capture via Forge

# Tools (standalone, work without Forge)
animus tools signal <file>
animus tools autopsy <log>
animus tools verdict review
animus tools verdict digest
```

---

## Config Schema

`~/.config/animus/config.toml` — chmod 600 on write.

```toml
[animus]
version = "0.1.0"
user_name = ""
data_dir = "~/.local/share/animus"
identity_dir = "~/.config/animus/identity"

[llm]
provider = "ollama"          # ollama | anthropic | openai
model = "llama3.2"
ollama_host = "http://localhost:11434"
fallback_provider = "anthropic"
fallback_model = "claude-sonnet-4-20250514"

[memory]
backend = "chromadb"
chromadb_path = "~/.local/share/animus/memory"
max_episodic_results = 5
max_semantic_results = 3

[self_improvement]
reflection_enabled = true
reflection_interval_hours = 24
reflection_min_interactions = 5
auto_write_minor = true      # write minor preference updates without approval
require_approval_for = ["IDENTITY.md", "GOALS.md", "CONTEXT.md"]

[forge]
enabled = false              # true once Forge is connected
forge_host = "http://localhost:8000"
workflows_dir = "~/.config/animus/workflows"

[dashboard]
host = "127.0.0.1"
port = 7700
auto_open = false

[api]
anthropic_api_key = ""       # encrypted at rest
openai_api_key = ""
```

---

## Code Standards

- Type hints everywhere. `from __future__ import annotations` in all files.
- Pydantic models for all data contracts between layers.
- Agents implement base contract (`forge/agents/base.py`). No freelancing.
- YAML configs validated against Pydantic schemas on load. Fail fast.
- Structured logging via `structlog`. No `print()` statements.
- Tests mirror source structure. Integration tests in `tests/integration/`.
- Docstrings on all public functions and classes.
- `ruff` for linting. `mypy` for type checking. Both must pass before commit.

---

## What NOT to Build

- **Chat UI in Forge** — Core owns all user interaction. Forge is headless.
- **File upload in Forge** — Core handles file ingestion, passes to Forge.
- **Conversational memory in Forge** — Core's memory layer is single source of truth.
- **A supervisor agent in Quorum** — The whole point is no supervisor.
- **Hardcoded pipelines in Python** — Everything goes through YAML workflow definitions.
- **npm/node/React in dashboard** — HTMX only. No build step. Ever.
- **Cloud sync by default** — Local-first. Cloud is opt-in, never default.
- **Multi-user features** — Single-user architecture. Tenure handles org-scale.

---

## Build Prompts for Claude Code

Run in order. One prompt per session. Commit after each.

### Prompt 01 — Foundation
```
Initialize the Animus monorepo.

Create root pyproject.toml as a workspace referencing core/, forge/, quorum/ packages.
Create the full directory structure from the spec in CLAUDE.md.
Create __init__.py files for all packages.
Create .gitignore: Python standard + .env + *.toml.bak + .chroma/
Create LICENSE: MIT, 2026, your-org.
Create .github/workflows/ci.yml: ruff + mypy + pytest on push to main.

Do not implement any logic. Structure and config only.
Apply all files. Verify directory tree is correct.
```

### Prompt 02 — Config System
```
Implement the config system in core/src/animus_core/config/.

schema.py: Pydantic BaseSettings model matching the config.toml spec
in CLAUDE.md. Nested models for each [section]. All fields optional
with defaults from defaults.py.

manager.py: ConfigManager class:
  - load() → reads ~/.config/animus/config.toml, returns Config
  - save(config) → writes config.toml, chmod 600 on Linux/macOS
  - exists() → bool
  - get_data_dir() → Path, creates if missing

defaults.py: DEFAULT_CONFIG dict with all values from spec.

tests/test_config.py:
  - load with no file returns defaults
  - save and reload round-trip
  - chmod 600 verified on Linux/macOS
  - nested model access works

Apply all files. Run tests. All must pass.
```

### Prompt 03 — Identity System
```
Implement core/src/animus_core/identity/.

manager.py: IdentityManager class:
  - read(filename) → str, reads from identity_dir
  - write(filename, content) → raises PermissionError for CORE_VALUES.md
  - append(filename, content) → appends to file
  - exists(filename) → bool
  - list() → list of existing identity files

assembler.py: SystemPromptAssembler:
  - build(memory_context: str) → str
  - reads all 6 identity files
  - assembles in order from spec
  - handles missing files gracefully (uses placeholder text)

files/: Jinja2 templates for each identity file.
  Generate from wizard answers. Each template should produce
  a populated markdown file with realistic starter content.

tests/test_identity.py:
  - CORE_VALUES.md write raises PermissionError
  - round-trip read/write for allowed files
  - system prompt assembly includes all sections
  - missing files produce placeholder content

Apply all files. Run tests. All must pass.
```

### Prompt 04 — Memory System
```
Implement core/src/animus_core/memory/.

episodic.py: EpisodicMemory class using ChromaDB:
  - store(text, metadata) → stores interaction
  - query(query_text, n_results, filters) → returns relevant interactions
  - get_recent(hours) → returns interactions from last N hours
  - delete(id) → remove specific interaction
  - clear() → nuclear option, requires confirm=True

semantic.py: SemanticMemory class using ChromaDB:
  - store(text, metadata) → stores factual knowledge
  - query(query_text, n_results) → returns relevant knowledge
  - Collections: separate from episodic to avoid contamination

procedural.py: ProceduralMemory class using SQLite:
  - store(trigger_pattern, steps) → store a learned procedure
  - match(trigger) → find matching procedure
  - record_success(id) / record_failure(id) → track reliability

manager.py: MemoryManager — unified interface to all three types.
  - query_all(text, n_results) → queries all types, merges results
  - format_context(results) → formats for system prompt injection

tests/test_memory.py:
  - store and retrieve episodic interaction
  - semantic query returns relevant results
  - procedural match works on trigger pattern
  - ChromaDB collections don't contaminate each other

Apply all files. Run tests. All must pass.
```

### Prompt 05 — LLM Router + Ollama Interface
```
Implement core/src/animus_core/llm/.

ollama.py: OllamaClient:
  - complete(prompt, system, model) → str response
  - stream(prompt, system, model) → generator of chunks
  - health_check() → bool (GET /api/tags)
  - list_models() → list of installed model names

anthropic.py: AnthropicClient (fallback):
  - complete(prompt, system) → str
  - Uses claude-sonnet-4-20250514

router.py: LLMRouter:
  - Tries local Ollama first (local-first principle)
  - Falls back to Anthropic if Ollama unavailable
  - Logs which provider was used
  - Raises if both unavailable

Ollama installation check:
  - If `ollama` not in PATH, print install instructions
  - Never auto-install system software without user confirmation
  - If installed but no models, run: ollama pull llama3.2

tests/test_llm.py:
  - Mock Ollama responses for unit tests
  - Router falls back correctly when Ollama mock fails
  - Real integration test (marked @pytest.mark.integration) hits live Ollama

Apply all files. Run tests.
```

### Prompt 06 — Onboarding Wizard
```
Implement core/src/animus_core/wizard/setup.py.

Rich terminal wizard with 8 steps. Uses Rich's Prompt, Confirm, Panel.

Steps:
1. Welcome screen — explain what Animus is, what this wizard does
2. Name — ask user's name, store in IDENTITY.md template
3. Role/background — what do you do? (freeform, stored in IDENTITY.md)
4. Current projects — what are you working on? (stored in CONTEXT.md)
5. Goals — short term (3mo) and long term (1yr) (stored in GOALS.md)
6. Preferences — tone (direct/collaborative), format (concise/detailed),
   topics to avoid (stored in PREFERENCES.md)
7. Core values — 3 questions about sovereignty/honesty/loyalty,
   generates CORE_VALUES.md. Show generated content before writing.
   Confirm before writing.
8. LLM setup — detect Ollama, check for models, pull llama3.2 if needed.
   Show Anthropic as fallback option.

After wizard: write all 6 identity files, write config.toml, show summary.

Entry: animus setup → runs wizard if not configured
Re-run: animus setup --reset → re-runs all steps except step 7
Step 7 only: animus setup --reset-values

tests/test_wizard.py:
  - Mock all Rich prompts
  - Verify all 6 files written
  - Verify config.toml written
  - Verify CORE_VALUES.md is locked after wizard

Apply all files. Run tests.
```

### Prompt 07 — Self-Improvement Loop
```
Implement core/src/animus_core/self/.

reflector.py: Reflector class:
  - run() → daily summarization of recent interactions → LEARNED.md
  - Uses prompt from identity/files/reflect.md.jinja2
  - Minimum interactions check before running
  - Writes updated LEARNED.md via IdentityManager

writer.py: IdentityWriter class:
  - detect_preference(message, response) → optional PreferenceSignal
  - write_minor(file, content) → direct write to PREFERENCES.md or LEARNED.md
  - queue_significant(file, change, reason) → routes to ProposalQueue

proposals.py: ProposalQueue class:
  - queue(file, change, reason) → creates pending proposal in SQLite
  - approve(proposal_id) → writes to identity file, marks approved
  - reject(proposal_id) → marks rejected, logs reason
  - list_pending() → returns list of pending proposals
  - get_rejected_patterns() → returns rejection patterns for Animus to learn from

scheduler.py: Scheduler class:
  - schedule_reflection() → sets up daily cron/scheduler based on OS
  - Linux/macOS: crontab entry
  - Windows: Task Scheduler

Reflection prompt template (identity/files/reflect.md.jinja2):
  Produce a prompt that instructs Animus to review recent interactions
  and update LEARNED.md with specific, evidenced observations.
  See spec in CLAUDE.md for full prompt design.

tests/test_self.py:
  - Reflector skips when below min_interactions
  - Reflector produces valid LEARNED.md update
  - Proposals queue, approve, reject cycle works
  - CORE_VALUES.md proposal raises PermissionError at writer level

Apply all files. Run tests.
```

### Prompt 08 — Dashboard
```
Implement core/src/animus_core/dashboard/.

FastAPI app at localhost:7700.
HTMX for dynamic updates. Jinja2 templates.
Dark theme from spec. No npm. No build step.
All CSS inline or CDN. Tailwind CDN for utility classes.

Routes from spec:
  GET / → status overview
  GET /chat → conversation interface with message history
  GET /memory → searchable memory browser
  GET /identity → view all files, edit allowed ones, CORE_VALUES read-only
  GET /proposals → pending proposals with diff view + approve/reject buttons
  GET /forge → Phase 2 placeholder with "Coming in v0.2" status card
  GET /tools → Arete Tools status (placeholder for Phase 2 wiring)

HTMX interactions:
  - Chat: POST /api/chat → streams response back
  - Memory search: GET /api/memory/search?q=... → returns results partial
  - Proposals: POST /api/proposals/{id}/approve or /reject → returns updated card
  - Feedback: POST /api/feedback/{interaction_id}/positive or /negative

Proposals page (critical — see spec):
  Each card: file, before/after diff, reasoning, approve/reject buttons.
  Approval writes immediately. Rejection logged.

tests/test_dashboard.py:
  - All routes return 200
  - Proposal approve/reject cycle works via API
  - Feedback endpoint stores signal in ChromaDB

Apply all files. Run tests.
```

### Prompt 09 — CLI Entry Points
```
Implement core/src/animus_core/cli.py.

Full Typer CLI from spec. All commands from CLAUDE.md CLI section.

Commands:
  setup [--reset] [--reset-values]
  chat [--session TEXT]
  status
  dashboard
  update
  memory search TEXT
  memory clear [--confirm]
  identity show
  identity edit FILENAME
  tools signal FILE
  tools autopsy LOG
  tools verdict [review|digest]

Entry point in pyproject.toml:
  animus = "animus_core.cli:app"

For tools commands: import from tools/ shared core, not standalone packages.
For update: check GitHub releases API, print latest version, pip install if confirmed.

tests/test_cli.py:
  - All commands invoke without error (mocked dependencies)
  - setup --reset-values calls wizard with reset flag
  - tools commands import from correct modules

Apply all files. Run tests.
```

### Prompt 10 — Polish + Package
```
Final polish, packaging, and CI.

pyproject.toml (root):
  - Workspace referencing core/, forge/, quorum/
  - Build system: hatchling
  - Ruff config: line-length 100, select E,W,F,I,N
  - Mypy config: strict, ignore_missing_imports for chromadb

README.md for repo root:
  - One-command install at top
  - Architecture diagram (ASCII from spec)
  - Quickstart: install → setup → chat → dashboard
  - Platform table: Linux ✅ macOS ✅ Windows 🚧
  - Identity files section: explain the 6 files, why CORE_VALUES is locked
  - Self-improvement section: explain reflection loop plainly
  - Philosophy section (sovereignty, persistence, loyalty)
  - Link to Forge as coming in v0.2
  - Status badge: Alpha

.github/workflows/ci.yml:
  - Trigger: push to main, PR to main
  - Jobs: ruff check, mypy check, pytest (all packages)
  - Python: 3.11, 3.12

.github/workflows/release.yml:
  - Trigger: tag push v*
  - Build wheel, publish to PyPI

Run full test suite. All tests must pass.
Run ruff on all files. All checks must pass.
Run mypy on all files. All checks must pass.

Apply all files.
```

---

## Testing Strategy

```
tests/
├── unit/           ← mock everything, test logic in isolation
├── integration/    ← real ChromaDB, real SQLite, mocked LLM
│   @pytest.mark.integration
└── e2e/            ← full stack, requires Ollama running
    @pytest.mark.e2e
```

Run unit only: `pytest tests/unit/`
Run unit + integration: `pytest -m "not e2e"`
Run all: `pytest` (requires Ollama)

---

## Related Projects

| Project | Relationship |
|---------|-------------|
| arete-tools/verdict | Standalone CLI wrapping tools/verdict/core/ |
| arete-tools/signal | Standalone CLI wrapping tools/signal/core/ |
| arete-tools/autopsy | Standalone CLI wrapping tools/autopsy/core/ |
| arete-tools/calibrate | Standalone CLI wrapping tools/calibrate/core/ |
| arete-tools/provenance | Standalone CLI wrapping tools/provenance/core/ |
| your-org/BenchGoblins | Will use Forge workflows for analysis pipelines |
| your-org/DOSSIER | Document intelligence — potential Core integration |
| Gorgon Media Engine | Content pipelines run as Forge workflows |
