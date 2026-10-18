# Ogma — Reverse-Engineering Synthesis Persona

Ogma reads external work (papers, podcasts, HN, blogs) **and our own projects** and produces implementation-ready synthesis. Companion to Lugh (in [Core](../packages/core/README.md)): where Lugh harvests, Ogma deciphers.

**Named for Ogma** — Celtic god of eloquence who invented Ogham script, the first written Gaelic. Patron of translation and learning. The fit: Ogma turns outside text (and our own code) into Animus-native understanding and rebuild proposals.

---

## Purpose

Four failure modes Ogma exists to prevent:

1. **Harvest fatigue** — Lugh pulls hundreds of items weekly. Without a reader, they pile up unread. Ogma is the reader.
2. **Generic summary-bot output** — public summary services (even LLM-powered ones) produce "this paper proposes a novel approach to…" slop. That's not useful. Ogma grounds every claim against the Animus codebase, so output is actionable, not encyclopedic.
3. **Copy-cat integration** — naive "implement what the paper said" produces dependency bloat and broken composition. Ogma's mandate is **build it better**: understand the mechanism, then design the Animus-native version — sharper contract, better composition, smaller footprint, reproducibility test baked in.
4. **Silent internal drift** — the portfolio accumulates 30+ projects, each with debt the author has stopped seeing. Tactical tools (`/review`, `/refactor`, `/simplify`) work at line level. Ogma works at subsystem level: "how does this module actually work, what's weak, what would we build today if we started fresh?" Same rigor applied inward.

---

## Ethos — Build It Better

From the design conversation (2026-04-18):

> "We want to be able to build the best possible tools, absorb what we can and keep moving forward. Not copy it exactly, but figure out how it works, then build it better."
>
> "It also needs to just be harvesting and rebuilding for our own projects. Improving anything possible to the highest standards and function."

Operational consequences:

- **Same standard outside and inside.** External sources and our own portfolio get the same treatment: understand the mechanism, critique honestly, propose the version that improves on it. No special pleading for our own code.
- **No refusal to propose** — if Animus has no matching abstraction (`animus_gap: NONE`), Ogma still fires. If an internal subsystem is "good enough," Ogma still names the rebuild that would be excellent. Greenfield proposals and principled rebuilds with explicit ROI are the whole point.
- **Critique honestly.** Every external synthesis has a `weaknesses` field naming what's hand-wavy or unreproducible in the source. Every internal audit has the same — no flattery of our own work.
- **Name the improvement.** External: how our version goes beyond the source (tighter contract, Forge/Quorum composition, reproducibility, smaller deps, fail-open I/O, constitutional alignment). Internal: how the rebuild raises standards (cleaner abstractions, consolidated duplication, retired debt, better test surface).

---

## Output Contracts

Two shapes — external and internal. Both saved to `~/projects/notes/ogma/YYYY-MM-DD-<slug>.md` so synthesis is durable and queryable. Missing fields fail the skill.

### External (for `read` and `brief`)

| Field | Purpose |
|-------|---------|
| `concept` | One-paragraph distillation of what the source actually does. No hedging. |
| `novelty` | What's new vs prior art. If reheated, say so. |
| `animus_gap` | `NONE \| PARTIAL \| FULL` + exact file(s):function(s) in Animus that overlap. Verified by Grep/Read — never guessed. |
| `weaknesses` | What's hand-wavy, unreproducible, missing ablations, or load-bearing on bad assumptions. |
| `proposal` | Concrete — module name, abstraction it composes with, sketch of the change. Explicitly names how our version is better. |
| `roi` | Value (what this unlocks), effort (trivial/moderate/substantial), priority (why now vs later). |
| `risks` | Reproducibility, maturity, licensing, perf, scope creep, coupling. |
| `confidence` | 0.0–1.0 + one-line justification. Below 0.6 means another read or a prototype before acting. |
| `sources_cited` | Source URL + prior art + Animus file:line where gap claim was verified. |

### Internal (for `audit` and `sweep`)

| Field | Purpose |
|-------|---------|
| `concept` | What this subsystem actually does. If muddled, name the muddle. |
| `what_works` | Load-bearing strengths the rebuild must preserve. |
| `weaknesses` | Architectural debt, duplicated logic, stale abstractions, test gaps, coupling violations, perf cliffs. file:line specific. |
| `cross_portfolio_overlap` | Another Arete project solve the same problem differently? Consolidation candidate, or divergence intentional? |
| `rebuild_proposal` | If starting today, what's the version-2? Contracts, abstractions, file layout, test surface. Strategic, not incremental. |
| `incremental_path` | If full rebuild isn't justified, the minimum intervention that captures most of the value. If it's fine as-is, say so. |
| `roi` | Capability / debt / perf / velocity gains. Effort estimate. Priority. |
| `risks` | Breaking consumers, data migration, contract drift, context loss, opportunity cost. |
| `confidence` | 0.0–1.0 + justification. |
| `sources_cited` | File:line references + related Arete projects + external work that informed the proposal. |

Shared fields (`concept`, `weaknesses`, `roi`, `risks`, `confidence`, `sources_cited`) are identical in spirit across modes.

---

## Surfaces

Three delivery modes, staggered by scope.

### v1 — Claude Code skill (`/ogma`)

Manual, in-session. Five verbs:

- `/ogma read <id>` — deep synthesis of one external item (paper / HN / podcast / URL)
- `/ogma brief [--since 7d] [--min-score 0.5]` — batch briefing across lugh cache
- `/ogma gap "<concept>"` — reverse query ("does Animus already do X?")
- `/ogma audit <target>` — internal subsystem audit ("how would we rebuild this to highest standards?")
- `/ogma sweep [--portfolio] [--min-age 60d]` — portfolio-wide audit sweep, ranked by rebuild ROI

**Spec:** `~/.claude/skills/ogma/SKILL.md`
**Persistence:** markdown at `~/projects/notes/ogma/YYYY-MM-DD-<slug>.md`
**Grounding (external):** Grep/Read on Animus repo + WebFetch on source.
**Grounding (internal):** Grep/Read on target project + git log for activity + pytest --collect-only for test surface.

**Status: v1 spec shipping now.**

### v2 — Forge workflow

Cron-triggered batch. YAML workflow in `packages/forge/workflows/ogma-weekly.yaml`.
Fires weekly after Lugh harvests, reads top-N scored items, produces one composite
briefing, posts to Discord, and stores the briefing through the supported Core
memory interface.

**Depends on:**
- v1 output contract stabilized
- Supported Core memory write path from `lugh.sources` (planned)
- Forge budget manager (existing)
- Forge provider routing (existing)

**Open questions:**
- Which provider tier? Opus for deep reads, Sonnet/Haiku for brief summaries, Ollama for keyword gating?
- How does the workflow handle source-unreachable items? Skip, retry, or escalate to human?

### v3 — Animus MCP tool

Exposes Ogma output as an MCP tool so any client (CC, another agent, the user's personal chatbot) can query accumulated synthesis:

- `ogma_query "<concept>"` — returns prior Ogma reads matching concept, ranked by confidence × recency
- `ogma_gap "<concept>"` — runs v1 gap flow
- `ogma_read <id>` — runs v1 read flow

Served from the existing Animus MCP server (`packages/core/animus/mcp_server.py`), following the same registration pattern as Lugh's `HARVEST_TOOL` + `WATCHLIST_*_TOOL`s.

---

## Architecture — How It Stays Grounded

```
┌─────────────┐     ┌────────────┐     ┌──────────────────────────┐
│ Lugh cache  │────▶│ /ogma read │────▶│ Per-item synthesis .md   │
│ (SQLite)    │     │            │     │ notes/ogma/2026-*.md     │
└─────────────┘     └────┬───────┘     └──────────────────────────┘
                         │
                         ▼
                    ┌──────────────┐
                    │ Animus repo  │ ◀── Grep / Read for
                    │ grounding    │     animus_gap verification
                    └──────────────┘
```

Key constraint: **no Animus file path appears in output unless it was actually read during synthesis.** This is the rule that separates Ogma from a summary bot.

The markdown archive at `~/projects/notes/ogma/` is Ogma's long-term memory in
v1. In v2 its metadata and content can be ingested through the supported Core
memory interface. Semantic retrieval requires a separately selected and managed
retrieval service; it is not supplied by the retired Core Chroma adapter.

---

## Relationship to Animus Subsystems

| Subsystem | Interaction |
|-----------|-------------|
| **Lugh** (`packages/core/animus/lugh/`) | Upstream — provides `SourceItem`s + relevance scores Ogma reads from |
| **Forge self-improve** (`packages/forge/src/animus_forge/self_improve/`) | **Primary downstream** — Ogma proposals feed the improvement pipeline as strategic input (see below) |
| **Forge** (`packages/forge/`) | v2 — runs `/ogma brief` and `/ogma sweep` as budget-managed workflows |
| **Quorum** (`packages/quorum/`) | Out of scope for v1. v3 could route high-stakes proposals (>0.7 confidence, substantial effort) through triumvirate voting before acting |
| **Core memory** (`packages/core/animus/memory.py`) | v2 — Ogma writes synthesis as episodic memories; v3 queries them via MCP |
| **Constitutional Principles** (P1–P9) | Proposals evaluated against principles; violations → escalate or reject |

## Self-Improvement Integration — The Flywheel

Animus already has a self-improvement loop:

- `packages/forge/src/animus_forge/self_improve/analyzer.py` produces `ImprovementSuggestion`s from heuristics (docstring gaps, bare excepts, TODOs).
- `orchestrator.py` coordinates approval → safety → sandbox → rollback → PR.
- `packages/forge/forge/better.md` defines what "better" means and constrains scope (YAML-only, 3000-token iterations as of 2026-04-18).

**What's missing:** strategic direction. The heuristic analyzer picks low-hanging fruit it can pattern-match. It doesn't know that a module is architecturally weak, that a subsystem duplicates another project's work, or that a just-published paper reveals a better way to do memory compression.

Ogma is that strategic layer. The integration is staged:

### Phase 1 — Today (v1)

Ogma writes markdown proposals to `~/projects/notes/ogma/`. You read them, decide what's worth doing, manually invoke Forge or open PRs. **No automatic execution** — you stay in the loop. This is deliberate for v1 because Ogma's proposals will occasionally be wrong, and "wrong + automatic + substantial effort" is bad.

### Phase 2 — `self_improve.sources.ogma`

Add a new module `packages/forge/src/animus_forge/self_improve/sources/ogma.py` that reads the Ogma notes directory and converts proposals to `ImprovementSuggestion` records (same shape the analyzer produces). These flow through the existing `orchestrator.py` — reusing **every existing gate** (approval, safety checker, sandbox, rollback, PR manager). Ogma is a new *source* of suggestions, not a new pipeline.

Practical effect: instead of the self-improve loop only proposing "add a docstring
to `_parse_date()`," it can propose "add a learned-memory overlay behind the
supported retrieval interface, per Ogma audit 2026-04-22-memory.md."

### Phase 3 — Outcome feedback loop

After Forge executes an Ogma-sourced suggestion, emit a structured outcome event (sandbox result, test delta, `better.md` measurement delta). Ogma — on its next run — reads the outcome alongside the original proposal and audits *itself*: did the rebuild actually improve things? Which proposals compound? Which classes of proposal systematically fail?

Over time, this closes the loop: Lugh harvests → Ogma synthesizes → Forge executes → Ogma measures. Each cycle, the exocortex is measurably better, and Ogma's own calibration improves because it sees its own outcomes.

### The scope constraint itself is audit-worthy

`better.md` today says "YAML only, 3000 tokens per iteration." That was the right call when the self-improve loop was unproven. It may no longer be the right call. **One of Ogma's early internal audits should target `better.md` itself** — is the YAML-only constraint still warranted, or are we leaving the highest-leverage improvements on the table? Meta, but not accidentally so: if the self-improvement loop can't critique its own scope, it's not actually self-improving.

---

## Non-Goals

- **Not a code generator.** Proposals are specs, not patches. Forge is for code changes; Ogma is for deciding what's worth changing.
- **Not a peer reviewer.** Synthesis is opinionated by design — Ogma is not neutral. It serves the Animus project's goals.
- **Not a literature search tool.** Lugh harvests breadth; Ogma goes deep on what Lugh surfaced.
- **Not a hype-trend tracker.** Relevance scoring lives in Lugh; Ogma processes what scores well, not what trends.
- **Not a line-level refactor helper.** Use `/refactor` or `/simplify` for code-level changes. Ogma operates at subsystem / architectural scope.
- **Not a PR reviewer.** Use `/review` or `/code-reviewer`. Ogma is strategic ("is this the right subsystem?"), not tactical ("is this the right diff?").

---

## Roadmap

| Version | Surface | Status | Depends on |
|---------|---------|--------|------------|
| v1.0 | `/ogma` skill — read/brief/gap/audit/sweep | **Shipping now** | Lugh sources (PR #24) |
| v1.1 | Markdown archive indexed by animus_sync | Planned | v1.0 merged |
| v2.0 | Forge weekly briefing workflow | Planned | Supported Core memory write path for Lugh |
| v2.1 | Discord embed of weekly Ogma brief | Planned | v2.0 |
| **v2.5** | **`self_improve.sources.ogma` — Ogma proposals feed orchestrator as `ImprovementSuggestion`s** | **Planned** | v2.0 + scope review of `better.md` |
| v3.0 | MCP tool surface | Planned | v2.0 |
| v3.1 | Outcome feedback — Ogma reads Forge results, self-audits proposal quality | Planned | v2.5 |
| v3.2 | Quorum-gated proposals for high-effort changes | Speculative | v3.0 + Quorum IntentNode wiring |

---

## First Real Test

The design call-out — Google AI memory compression work (likely [Titans: Learning to Memorize at Test Time](https://arxiv.org/abs/2501.00663), Behrouz et al. 2024). Directly relevant because Animus **is** a memory system. A good v1 output would:

- Distill the learned-memory-at-test-time mechanism
- Gap-check against the supported `packages/core/animus/memory/` interface
  (local or durable storage, no learned compression) — `animus_gap: NONE`
- Weaknesses: reproducibility unclear, perf at scale unvalidated, interaction with existing retrieval not specified
- Proposal: learned-memory overlay in `packages/core/animus/learning/`, composed with existing retrieval, optional per-query compression
- ROI: moderate effort, high value — could differentiate Animus's memory tier
- Confidence: 0.6 (promising but early)

That's the shape. Summary bots can't produce it; Ogma's grounding rules make it possible.

---

## v0 Implementation Plan — Code (added 2026-05-11)

Everything above is the *vision* (v1 skill / v2 Forge workflow / v3 MCP). This section is the *buildable v0* — grounded in a recon of what already exists. The driving use case: a podcast-transcript harvest that's been run by hand (yt-dlp → clean → analyze, 15 episodes, 2026-05-11) and should be code. That harvest is, in this architecture, **a missing Lugh source + the missing Ogma `read` flow**.

### What already exists (recon 2026-05-11)

- **Lugh is fully built.** `packages/core/animus/lugh/sources/`:
  - `base.py` — `Source` Protocol (`source_id: str`; `fetch(self, limit) -> Iterable[SourceItem]`) + `SourceItem` dataclass (`source_id, item_id, title, url, published, summary, author, tags, raw_text, metadata`; `.fingerprint` = SHA-256 of `(source_id, item_id)` for dedup) + `SourceCache`.
  - `registry.py` — JSON-driven registry at `~/.animus/lugh_sources.json`; `load_registry()` materializes entries → Source instances; entries shaped like `{"kind": "arxiv", "category": "cs.LG"}`, `{"kind": "hn", "query_id": "front_page"}`, `{"kind": "podcast", "show_id": "all-in", "feed_url": "...", "fetch_transcripts": false}`.
  - Existing sources: `arxiv.py` (category RSS), `hn.py` (Algolia API), `podcasts.py` (RSS + optional iTunes transcript fetch srt/vtt/json→plaintext), `rss.py` (feed helpers).
  - `relevance.py` — `KeywordScorer(default_keywords).score(item) -> float` (0.0–1.0); wired into `SourceCache.put_many(scorer=...)`.
  - `watchlist.py` — periodic-scan scheduler (7-day default), `run_watchlist_scan()` async, exposed as the `animus_watchlist_scan` MCP tool. **This is the recurring-harvest mechanism — Ogma doesn't need its own scheduler.**
- **Ogma has zero code.** Only `~/.claude/skills/ogma/SKILL.md` (the v1 skill spec) and `~/projects/notes/ogma/` (4 example outputs from a 2026-04-19 hand-run + a `digests/` subdir).
- **LLM calls in core**: `packages/core/animus/cognitive.py` — `CognitiveLayer(ModelConfig.ollama()/.anthropic()/.openai()).generate(prompt, system)`. Note the HybridBackend lesson (ADL-20260511-001 #2): 401/403 must fail loud, not fall back to Ollama's tool-ignoring stub.
- **Conventions** (`packages/core/pyproject.toml`): ruff
  `["E","F","I","N","W","UP"]`, line-length 100, `target-version py310`;
  pytest in `tests/`; 97% coverage target; base dependencies include `ollama`,
  `pyyaml`, `pydantic`, `rich`, and `prompt-toolkit` — **no `chromadb`, `typer`,
  or `yt-dlp`**. Shell out to the system `yt-dlp` (`~/.local/bin/yt-dlp`) via
  `subprocess`; don't add the library dependency.
- **MCP tools** (`packages/core/animus/mcp_server.py`): FastMCP `@mcp.tool()` decorators for simple ones; explicit `Tool` dataclasses (`name/description/parameters/handler/category`) in `lugh/watchlist_tools.py` for the richer ones. v0 builds **no MCP tool** — that's v3.

### v0 deliverables (two phases)

**Phase 1 — the harvest half (Lugh `YouTubeSource`)** — *this is the immediate win; self-contained; build + test first.*

`packages/core/animus/lugh/sources/youtube.py`:
- `class YouTubeSource` implementing the `Source` Protocol. Construction: `YouTubeSource(channel: str, show_name: str, *, fetch_captions: bool = True, raw_dir: Path | None = None)`. `source_id = f"youtube:{channel}"`.
- `fetch(limit)` — shell out to `yt-dlp --flat-playlist --playlist-end N --print "%(id)s ::: %(title)s" "https://www.youtube.com/{channel}/videos"` to list recent videos; for each new video (not already in cache), optionally `yt-dlp --skip-download --write-auto-subs --sub-lang en --sub-format vtt -o ...` then **clean the VTT** (the dedupe/strip logic we already proved: drop `WEBVTT`/`Kind:`/`Language:`/timestamp/`align:` lines, strip inline `<...>` tags, dedupe consecutive identical lines) → `SourceItem(raw_text=cleaned_transcript, summary=<first ~500 chars>, metadata={"video_id":..., "channel":..., "show_name":..., "has_captions":...})`.
- Raw VTT → a gitignored dir (default `~/.animus/lugh_raw/youtube/`), never committed (IP discipline — same posture as Aurora Arcology's "Aurora does not redistribute creator transcripts"). The `SourceItem` carries the cleaned text; the raw VTT is a local cache only.
- Graceful degradation: `yt-dlp` missing → log + return empty (fail-open, like the other sources); a video with no captions → emit the `SourceItem` with `has_captions=False` and `raw_text=""` (title/description only); throttle with a small sleep between caption pulls.
- A `default_youtube_sources()` returning the Core feed list (the seeds — `@AIDailyBrief` daily; `@LatentSpacePod`, `@NoPriorsPodcast`, `@a16z` weekly; `@allin`, `@PeterDiamandis`, `@DwarkeshPatel`, `@CognitiveRevolutionPodcast`, `@LennysPodcast` as Watch-tier). See `~/projects/notes/ideas/podcast-harvest-2026-q2.md` §"Tracked sources" for the full list + handles (verified 2026-05-11).

`packages/core/animus/lugh/sources/registry.py` — add a `youtube` kind: `{"kind": "youtube", "channel": "@AIDailyBrief", "show_name": "The AI Daily Brief", "fetch_captions": true}`; `load_registry()` instantiates `YouTubeSource` for each; seed `default_youtube_sources()` on first run (parallel to how arxiv/hn seed but podcasts don't — YouTube can seed since the channel handles are stable). Also a `lugh sources add-youtube <channel>` CLI command, mirroring `add-podcast`.

`tests/test_lugh_youtube_source.py` — mock `subprocess.run` for both the list call and the caption pull; assert: VTT cleaning produces deduped prose; `SourceItem`s have correct `source_id`/`fingerprint`/`metadata`; missing-yt-dlp → empty; no-captions video → `has_captions=False` item; the registry round-trips a `youtube` entry. Plus a unit test for the VTT cleaner as a pure function (extract it as `clean_vtt(text: str) -> str`).

**Phase 2 — the synthesis half (Ogma `read`)** — *bigger, LLM-heavy; clean-room this.*

`packages/core/animus/ogma/` (new sub-package, mirrors `lugh/`; import `from animus.ogma import ...`):
- `models.py` — `OgmaOutput` dataclass with the external-contract fields (`concept, novelty, animus_gap, weaknesses, proposal, roi, risks, confidence, sources_cited`) + an internal variant (`what_works, cross_portfolio_overlap, rebuild_proposal, incremental_path` ...). `to_markdown(self) -> str` rendering the SKILL.md output format; `write(self, dir: Path = ~/projects/notes/ogma) -> Path` with the `YYYY-MM-DD-<slug>.md` naming.
- `grounding.py` — `verify_animus_gap(concept) -> GapResult` (grep/read the animus repo; the rule: no animus file path in output unless it was actually read), `git_activity(target)`, `test_surface(target)` (`pytest --collect-only`).
- `read.py` — `read(item: SourceItem | str, *, model: str = ...) -> OgmaOutput`: assemble the source text + grounding context → `CognitiveLayer.generate(prompt, system=<the Ogma persona prompt from SKILL.md>)` → parse the response into `OgmaOutput` → `.write()`. **Tiered relevance gate before the expensive read**: if the `SourceItem`'s `KeywordScorer` score < threshold, skip (or downgrade to a one-line note); Tier-1 keywords (model release, MCP, pricing, AI-security, FDE/AI-enablement hiring) get flagged for immediate surfacing in the output.
- `brief.py` — `brief(since="7d", min_score=0.5) -> Path`: batch over the lugh cache, one composite briefing.
- `cli.py` — `ogma read <id>`, `ogma brief`, `ogma gap "<concept>"`; wire into `packages/core/animus/__main__.py`'s REPL as `/ogma ...` so the existing skill actually executes instead of just describing.
- `gap.py`, `audit.py`, `sweep.py` — stubs in v0 (the SKILL.md verbs); fill in v0.x.
- `tests/test_ogma_*.py` — `OgmaOutput.to_markdown()` round-trips the contract; `grounding.verify_animus_gap` doesn't emit unread paths; `read()` with a mocked `CognitiveLayer` produces a well-formed `OgmaOutput` and writes the file; the relevance gate skips low-score items.

**Wiring it together (the recurring harvest):** add the `youtube` entries to `~/.animus/lugh_sources.json`; the existing `watchlist.py` scheduler picks them up on its scan interval (daily for AIDB — may need a per-source interval override, currently 7-day global; add `"interval_days"` to the registry entry if so); harvested `SourceItem`s land in `SourceCache` with relevance scores; Ogma `brief` (run on a cron, or invoked via the skill) reads the high-scoring new items → composite briefing → `~/projects/notes/ogma/digests/YYYY-MM-DD.md`; Tier-1 items get surfaced immediately (push notification via the bootstrap proactive engine, or top-of-next-session). The full external-feeds list (curator blogs, lab blogs, MCP changelog, governance) in the harvest MD §"Tracked sources" maps onto Lugh's existing `rss.py` source — those are easier than YouTube and can be added the same way.

### Out of scope for v0

- The MCP tool surface (v3). The Forge weekly-workflow version (v2 — though `brief` on a cron approximates it). The `audit`/`sweep` internal-subsystem flows (v0.x — `read`/`brief`/`gap` first). Outcome feedback (v3.1). Quorum-gated proposals (v3.2). Per the spec's own staging, automatic execution of Ogma proposals stays out — Ogma writes proposals, the operator decides.

### Status

Branch `feat/ogma-v0-youtube-source` off `main`. `animus.service` stopped (mandatory during commit work — the proactive engine self-commits otherwise; see `~/.claude/projects/-home-arete-projects/memory/project_animus_dev_gotchas.md`). Phase 1 (`YouTubeSource` + registry + tests) is the immediate build. Phase 2 (the `ogma/` package) is a clean follow-up — the patterns to mirror are `lugh/sources/base.py` (the contract) and `~/.claude/skills/ogma/SKILL.md` (the output format + persona prompt).
