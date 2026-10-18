# Roadmap — Animus as Research Assistant

**Status:** v0.1.0 — committed 2026-05-24
**Mode:** /specification (decisions locked; do not re-litigate)
**Related:**
  - [[project-animus-agent-platform]] (memory: pure-local autonomous agent commit 2026-05-23)
  - `docs/ROADMAP_quorum_v2.md` (parallel track, currently wk1-2)
  - `packages/forge/src/animus_forge/agent/spec.md` (v0 substrate spec, locked 2026-05-23)
  - `docs/OGMA.md` (source-ingestion persona)

---

## 1. Frame

Animus is being built to ARETE's personal **research assistant** — single-user, pure-local, sovereign. Not consumerized (per `feedback_animus_stays_personal`). Not a generic agent platform — the priority capability set is biased toward reading, retrieval, synthesis, citation, and overnight delegated study, not generic fleet automation. Fleet automation comes free as a side-effect of the substrate.

**Once Animus is operationally a research assistant** (post-RA-1), Claude Code reverts to **advisory only**: architecture review, spec drafting, code review, eval design. Production research execution runs pure-local. Until then, Claude Code retains full execution power for building Animus itself.

---

## 2. Decisions locked 2026-05-24

| ID | Decision | Reason |
|---|---|---|
| D1 | Carve `feat/animus-agent-loop` parallel to Quorum v2 wk2-5 | Qwen3.6 just landed (commit 79e1037) — making it sit idle through 4 more Quorum weeks wastes the enabler. Tracks are non-contentious (different packages). |
| D2 | RD7 from agent v0 spec is **overridden** | Quorum v2 wk5 gate no longer blocks v0 implementation. Quorum learnings can flow into RA-1/RA-2 instead. |
| D3 | v0 spec ships as-is. Research capabilities are an additive layer (RA-1), not a rewrite | The 5 starter tools + skill registry + hooks are domain-neutral substrate. Research-specific tools (web fetch, retrieval, citation) layer on top. |
| D4 | Ogma converges into Animus. The 6 in-flight `feat/lugh-*` branches land via consolidation work (RA-2) | Memory: "Lugh and Ogma work for animus" (user, 2026-05-24). Currently scattered, none on main. |
| D5 | Aurora-arcology pipeline **pattern** ports to Animus; code does not | Aurora is TypeScript/Next.js, EVE Lore domain. The pattern (scrape → ingest → NER → manifest → synthesize → embed) transfers; the code is wrong-language and wrong-domain. |
| D6 | Source-grounded retrieval is mandatory; "answers without sources" is a v0 failure mode | Research assistant ≠ chat bot. Every synthesized answer carries citations to its corpus sources. |

---

## 3. Phases

Each phase has its own `/specification` pass before implementation. This doc names the phases + sequencing; per-phase specs land separately under `packages/forge/src/animus_forge/agent/` or `docs/`.

### RA-0 — Agent loop substrate

**Spec:** `packages/forge/src/animus_forge/agent/spec.md` (already locked, 267 lines, 18 acceptance criteria)
**Branch:** `feat/animus-agent-loop`
**Depends on:** none (RD7 overridden per D2)
**Starts:** immediately
**Ships:** `animus-agent run <task>` CLI, 5 tools (Read/Write/Edit/Bash/Grep), skill registry from `~/.claude/skills/`, hook gates with identity deny + P1-P9 stub, BudgetManager integration, JSON receipts, 18 acceptance tests
**Quality bar:** 95% coverage gate (Forge package floor), all spec acceptance criteria green
**Outcome:** the loop runs, tool execution is gated, audit log captures everything. Generic agent.

### RA-1 — Research capability extension

**Spec:** to be written after RA-0 lands (`docs/spec_research_extension.md`)
**Branch:** `feat/animus-agent-research` (depends on RA-0)
**Starts:** RA-0 merged to main
**Ships, planned scope:**
  - `WebFetch(url, max_bytes, allowlist_only=True)` tool with on-disk cache
  - `Retrieve(query, k, corpus)` tool over the ingest corpus from RA-2
  - `Cite(source_id, span)` and citation-discipline in agent output (every synthesized claim → `[source:line]`)
  - `Synthesize(sources: list[Retrieved], question)` — multi-source consolidation primitive
  - Opt-in `MemoryWrite(finding, tags)` — explicit, not implicit (overrides v0 R24)
  - Research-policy hook example: no auto-publish, no paid-API spend without confirmation
  - Skill registry bias: research skills surfaced (handoff, decision-log, documentation-writer, web-search, web-scrape)
**Quality bar:** 95% coverage + RA-eval suite scored on `personal-quality` rubric
**Outcome:** the research assistant is **usable**. This is the gate where Claude Code reverts to advisory.

### RA-2 — Source pipeline (Ogma convergence + Aurora pattern port)

**Spec:** to be written before RA-1 ships (`docs/spec_source_pipeline.md`)
**Branch:** `feat/animus-ogma-converge` (independent — can run in parallel with RA-0)
**Starts:** immediately, parallel to RA-0
**Ships:**
  - Consolidation of 6 `feat/lugh-*` branches into main (squash or sequential — TBD in spec)
  - Reframe of Ogma persona for research corpus (currently EVE-economy biased, see commit `b895bc4`)
  - Aurora pattern ported in Python:
    - `scrape` (URL → raw bytes, respecting robots + rate limits)
    - `ingest` (raw → normalized doc with metadata)
    - `ner-extract` (entities for cross-doc linking)
    - `build-manifest` (corpus index)
    - `synthesize-dedupe` (cross-source consolidation)
    - `index-corpus` (writes through the supported Core memory interface;
      semantic/vector retrieval requires a separately selected service)
  - Source-type adapters: PDF (papers), HTML (articles), YouTube/podcast transcripts (already in `feat/lugh-external-sources`), arXiv (already in same branch), HackerNews (same), ARETE's own notes (`~/projects/notes/`)
  - IP discipline borrowed from Aurora: metadata-only ingest into repo, body text in `data/raw/` (gitignored)
**Quality bar:** 95% coverage on new pipeline; corpus is queryable before RA-1 begins
**Outcome:** Animus has a populated, queryable research corpus. The retrieval tool in RA-1 has something to retrieve from.

### RA-3 — Overnight delegate

**Spec:** to be written after RA-1 lands (`docs/spec_overnight_delegate.md`)
**Branch:** `feat/animus-agent-overnight` (depends on RA-0 + RA-1)
**Starts:** RA-1 merged
**Ships:**
  - Task queue (SQLite-backed, persists across restarts)
  - Checkpoint/resume — agent state snapshotted between turns, resumable after crash
  - Summary digest — morning report of overnight work (task → outcome → cost → citations)
  - Quorum v2 wk2 (LivenessWatchdog) hooked in if landed by then — watchdog alerts on stuck overnight tasks
**Quality bar:** 95% coverage; 1-week unattended run, intervention rate measured + recorded in arete-evals
**Outcome:** delegate a research question before bed, wake up to a sourced briefing.

### RA-4 — Always-on (formerly agent v2)

**Spec:** to be written after RA-3 lands
**Branch:** `feat/animus-agent-daemon` (depends on RA-3)
**Starts:** RA-3 merged
**Ships:** file-watcher triggers, cron schedules, MCP-server task ingestion (incoming research questions from other tools), Discord/Slack inbound, persistent daemon under systemd
**Quality bar:** TBD in spec
**Outcome:** continuously-running research collaborator. Watches inputs, drafts findings, queues for review.

---

## 4. Sequencing matrix

```
Time →

Quorum v2:    [wk2] [wk3-4] [wk5: re-eval gate]
                                                       (separate track, separate package)

Research-assistant:
  RA-0:       [============ build ============]
  RA-2:       [============ build ============ → ============= refine =============]
  RA-1:                                          [============ build ============]
  RA-3:                                                                          [====]
  RA-4:                                                                                [====]
                                                  ↑
                                            Claude Code reverts
                                              to advisory-only
```

RA-0 and RA-2 are independent and run in parallel from day one. RA-1 needs both. RA-3 needs RA-1. RA-4 needs RA-3.

Quorum v2 weeks 2-5 run on their own schedule — no contention with the agent track (different packages: `packages/quorum/` vs `packages/forge/src/animus_forge/agent/`). Quorum wk2 (LivenessWatchdog) becomes useful for RA-3; wk3-4 (active-inference IntentResolver) doesn't affect single-agent research work, may become relevant in RA-4 if multiple research agents coordinate.

---

## 5. Branch plan

| Branch | Purpose | Depends on | Status |
|---|---|---|---|
| `feat/animus-agent-loop` | RA-0 implementation | — | new |
| `feat/animus-ogma-converge` | RA-2 — Ogma branches consolidation + Aurora pattern port | — | new (will subsume `feat/lugh-*` branches) |
| `feat/animus-agent-research` | RA-1 — research capability layer | RA-0 merged | new |
| `feat/animus-agent-overnight` | RA-3 — overnight delegate | RA-1 merged | new |
| `feat/animus-agent-daemon` | RA-4 — always-on | RA-3 merged | new |

In-flight `feat/lugh-*` branches to be subsumed by `feat/animus-ogma-converge`:
- `feat/lugh-daily-digest` (2026-04-20)
- `feat/lugh-external-sources` (2026-04-18)
- `refactor/harvest-to-lugh` (2026-04-17)
- `restore/lugh-to-main` (2026-04-18)
- `docs/ogma-persona` (2026-04-18)
- Note: memory `reference_podcast_intel_pipeline` says `feat/ogma-v0-youtube-source` was "DONE+uncommitted" — need to inventory uncommitted work before consolidating

---

## 6. Out of scope

- **Consumerization** — no public-facing version, no multi-tenant (per `feedback_animus_stays_personal`)
- **Reusing aurora-arcology codebase wholesale** — only the pipeline pattern transfers (per D5)
- **EVE-specific Ogma capabilities** — those evolve in aurora-arcology or a separate fork
- **Claude Code SDK wrappers as implementation path** — per `project_animus_agent_platform` decision
- **Academic paper output** — per `feedback_engineer_not_researcher` (engineering artifacts only)
- **Anthropic API in the agent loop** — pure-local execution; cloud LLM only via Claude Code advisory channel
- **Reimplementing animus-core's memory** — RA-1 `MemoryWrite` uses the existing Core memory layer
- **Reimplementing animus-forge's Provider abstraction** — agent uses LlamaCppProvider (landed today) or OllamaProvider

---

## 7. Open questions to resolve before per-phase specs

### Before RA-1 spec
- Retrieval store: use supported Core local/durable storage for persistence;
  if RA-1 requires semantic/vector retrieval, select and threat-model a separate
  retrieval service in its own specification rather than coupling it to Core.
- Citation format: machine-readable JSON sidecar, or inline `[source:N]` markers in answers, or both? (recommendation: both — markers in prose, sidecar in receipt)
- Web fetch allowlist: per-task explicit list, or persistent allowlist file, or default-deny with run-time prompt? (recommendation: persistent allowlist + per-task override)

### Before RA-2 spec
- 6 `feat/lugh-*` branches — squash into one PR vs land sequentially?
- Memory says `feat/ogma-v0-youtube-source` has "DONE+uncommitted" work — what's in the worktree?
- Ogma persona reframe: in-place edit of `docs/OGMA.md`, or new `docs/OGMA_research.md` and deprecate old?
- Where does the corpus live on disk? (recommendation: `~/.local/share/animus/corpus/{raw,extracted,index}/`)

### Before RA-3 spec
- Queue storage: new SQLite DB, or extend Forge's existing audit DB?
- Crash-resume contract: turn-level snapshot, or full agent state pickle?
- Digest delivery: file, Discord webhook (already used by fleet-monitor), email, or all three?

### Before RA-4 spec
- MCP-server ingestion: does the agent become an MCP server, or does it host an MCP client that polls?
- Always-on resource ceiling: hard memory cap, or rely on systemd `MemoryMax`?

---

## 8. Re-evaluation gates

| Gate | When | What to re-evaluate |
|---|---|---|
| G1 | RA-0 ships | Was the parallel-track call correct? Did Quorum v2 wk2-5 suffer from attention split? |
| G2 | RA-1 ships | Claude Code transitions to advisory. Confirm the research-assistant frame is the right priority (vs fleet-agent or generic-agent) based on actual usage |
| G3 | RA-2 ships | Corpus quality check. Is retrieval producing useful answers? If no, ingest pipeline needs revision before RA-3 |
| G4 | RA-3 ships | One-week unattended run intervention rate. If > 1 intervention/day, RA-4 (always-on) is premature |
| G5 | RA-4 ships | Stop. Don't pre-commit a v5. Evaluate against actual use for at least one quarter before extending. |

---

End of roadmap.
