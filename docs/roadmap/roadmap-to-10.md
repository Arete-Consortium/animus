# Animus — Roadmap to 10/10

**Status: CANONICAL (remediation roadmap)** · Created 2026-06-02 · Owner: ARETE (solo)

## What this is

A personal work-queue to close every gap surfaced by the 2026-06 whitepaper
audit, the local adversarial security review, and the cost-enforcement critique
from the cold read. It is **not** a pitch and not a product roadmap. It is the
"what do I do next, in what order, and how do I know each piece is done" doc for
future-me.

Relationship to other docs (see [`../architecture/canonical-principles.md`](../architecture/canonical-principles.md)):
- `whitepapers/ANIMUS_WHITEPAPER_2026-06.md` — the audit that found these gaps.
- `PERSONAL_ROADMAP.md` — *direction* (what Animus is allowed to become).
- This file — *remediation* (closing the gaps to 10/10). When this and
  PERSONAL_ROADMAP disagree on scope, PERSONAL_ROADMAP wins (anti-productization).
- `TODO_NEXT.md` — short-horizon queue; points here for the audit work.

**Pace is yours.** Effort is sized S/M/L, never dated. Sequence is
dependency-driven, not calendar-driven. Account for Toyota OT + sleep recovery;
this is a months-long personal arc, not a sprint.

---

## Definition of 10/10

Eight dimensions. A dimension is 10/10 when its acceptance criteria all hold and
are test- or check-enforced (not just asserted in a doc). Current scores are
honest reads from the whitepaper maturity (68 production / 6 beta / 4 exp / 5 stub).

| # | Dimension | Now | 10/10 acceptance criteria |
|---|---|---|---|
| D1 | **Cost discipline** (keystone) | **8** (was claimed 10; [review](../reviews/animus-10-10-review-2026-06-03.md) corrected) | Raw-token `allocate()` reservation is atomic + thread-safe ✅ (A2). **Gaps:** ET ceiling is *not* enforced at the admission gate (`can_allocate` ignores the ET axis — a single opus/output-heavy step can overshoot 100x); `estimate_cost` "single source" is a dead method — the live spend path uses a *second*, stale 2024 table in `metrics/cost_tracker.py`. → corrections C1, C8, C12. |
| D2 | **Memory** | 7 | Tiered HOT/WARM/COLD with real promotion; incremental BM25; no full second in-RAM copy; LLM-summarized consolidation; sync conflict-surfacing. |
| D3 | **Security & at-rest** | **6** (was claimed 9; review corrected) | Content-DLP + integrity *mechanisms* are sound, but **wired incompletely:** Bedrock/Vertex have NO egress gate; Azure streaming bypasses it; `scannable_text()` misses tool defs/results/args; the deployed integrity baseline is STALE (daemon refuses boot now); forge-side enforcement call-sites are untracked. Per-install salt ✅ (A7). → corrections C2–C5, ops re-baseline. Encryption at rest (A5) still outstanding. |
| D4 | **Eval integrity** | **8** (was claimed 10; review corrected) | Judge-failure handling ✅ (B1), RLIMIT sandbox bounding ✅ (B4), calibration stats ✅ (B2) all genuinely hold. **Gaps:** `CodeExecutionMetric` scores *crashing* code 1.0 when `expected` is None (returncode never checked); regex precedence no-ops a configured pattern; equivalence uses CI half-width not bounds. → corrections C6, C9, C10. |
| D5 | **Orchestration** | **7** (was claimed 8; review corrected) | Budget reservation ✅ (A2); auto-promotion staging/approval separation is sound ✅ (B5). **Gap:** `eval_experiment_runner` reads a nonexistent `avg_score` on the real `SuiteResult` (field is `total_score`) — the measured signal is silently dropped; the B3 test passed only via MagicMock. Dry-run not stamped on the structured record. → corrections C7, C11. |
| D6 | **Coordination (Quorum)** | 7 | Pluggable `StabilityScorer` protocol ✅ (B7, prereq for active inference). Remaining: flood-resistant scorer impl, EventLog wiring enforced at the bridge, content-addressed transition log for replay/bisect. |
| D7 | **Autonomy-readiness** | 5 | Durability/rebuild dry-run + `animus export --all`; encryption at rest; a measured one-week overnight-delegate run. Earn the right to run unattended. |
| D8 | **Doc coherence** | 8 | CANON kept current (status flips in the same PR as the feature); zero present-tense claims without code; no contradicting roadmaps. (Mostly closed in PR #80.) |

10/10 overall = all eight at criteria, **and** the cost keystone (D1) enforced,
because every other claim rests on it.

---

## Phase C0 — 10/10 corrections (HIGHEST PRIORITY)

The 2026-06-03 adversarial [review](../reviews/animus-10-10-review-2026-06-03.md)
found that Sessions 1-6 declared several dimensions 10/10 prematurely: real
cores with bypassable edges, masked by tests that mocked or centered the buggy
path. These must close before any 10/10 claim. **Each must land with a test
that actually exercises the failing path (not a mock of it).**

**Must-fix (the 10/10 claim is false until these close):** — ALL CLOSED, PR #89
- [x] **C-ops** Regenerated the deployed integrity baseline from a clean tree
      (`python -m animus.integrity.cli regenerate`; `verify` passes). Baseline
      lives at `~/.config/animus` (runtime artifact); the committed surface is
      the expanded tracked-module tuple (C5) + its pinning test. Re-baseline is
      an operator step after every enforcement-surface change.
- [x] **C2** Added `_check_request_egress` + `ANIMUS_OFFLINE` init gate to the
      Bedrock and Vertex providers. Bedrock async/stream-async wrap the sync
      paths, so gating `complete`/`complete_stream`/`initialize` covers all
      four; Vertex has native async, so all four entrypoints gate directly.
      Tests in `test_provider_egress_gates.py` exercise the real
      `_check_request_egress` (secret-payload + CONFIDENTIAL block, clean PUBLIC
      pass) and the offline init gate.
- [x] **C3** Added the egress check to Azure `complete_stream` /
      `complete_stream_async`; tests drive a secret through both streaming
      entrypoints and assert `EgressDeniedError` before any client call.
- [x] **C4** Extended `scannable_text()` to recursively collect tool
      definitions, `tool_result` content, and `tool_use` input args; 3 new
      blocking tests (`TestScannableTextToolBlocks`).
- [x] **C5** Added the forge-side enforcement modules (`network.egress`,
      `providers.base`, `providers.router`) to `_TRACKED_MODULES_OPTIONAL`;
      `test_forge_enforcement_modules_tracked_when_installed` pins them.
- [x] **C6** `CodeExecutionMetric._execute_python` now returns `(output, ok)`;
      `score()` returns 0.0 on non-zero exit / TIMEOUT. New
      `test_crashing_code_scores_zero_when_expected_none` (raise / `sys.exit(7)`
      / exit-1 / exit-0 → 0.0, clean print → 1.0).
- [x] **C7** `eval_experiment_runner` reads `total_score` (not the nonexistent
      `avg_score`); test rebuilt on a real `SuiteResult(passed=8, …,
      total_score=0.873)` asserting the score reaches the report string.

**Should-fix:** — C8–C13 CLOSED, PR #90 (C13's external pre-exec integrity self-check deferred — see below)
- [x] **C8** `allocate`/`can_allocate`/`_can_allocate_unlocked` take an optional
      `effective` ET estimate (defaults to neutral `tokens`); ET ceiling is now
      checked at admission against `_total_effective + _pending_effective + est`,
      with a `_pending_effective` reservation mirror released in `release()`.
      5 admission tests (reject-on-estimate, pending-reservation block, neutral
      default, tighten-after-expensive-usage, off-switch).
- [x] **C9** `self._pattern or (str(expected) if expected else None)` on both
      regex metrics — a configured pattern with falsy `expected` is now honored
      instead of dropping to the always-pass no-op; the two pinning tests rewritten
      to assert the corrected behavior.
- [x] **C10** Added bounds-based `equivalent` (TOST-style: whole CI inside
      ±MEANINGFUL_EFFECT); `underpowered` = `not significant and not equivalent`.
      `power_note` derives the "within ±x" envelope from the actual bounds. New
      test: off-center CI [-0.005, 0.085] (half-width 0.045 < 0.05) is correctly
      underpowered, not "equivalent".
- [x] **C11** `is_dry_run` added to the `IterationRecord` dataclass, stamped at
      all 3 construction sites + the audit JSONL entry; tests assert it reaches
      both record and JSONL for dry-run and real-runner cases.
- [x] **C12** Corrected `estimate_cost`'s false "single source of truth"
      docstring (it's a coarse tier approximation; `CostTracker.calculate_cost`
      is the authoritative per-model $ source) and refreshed the stale 2024
      `CostTracker.PRICING` to current Claude 4.x / GPT-4.1 ids. Test pins that
      `claude-opus-4-8` / `claude-sonnet-4-6` / `gpt-4.1-mini` resolve.
- [x] **C13** (partial) Added `google_api_key` (`AIza…`) to the canonical
      credential patterns; fixed the `compute_stability` falsy-scorer drop
      (`scorer if scorer is not None else DEFAULT`). The "duplicated stability
      formula" was investigated — only the shared `0.3` base constant, no real
      duplication. **Deferred:** the external pre-exec integrity self-check
      (in-process self-hash is defeatable) is a larger design item, not bundled
      here.

**What genuinely held up** (survived adversarial probing — the credibility
floor): raw-token reservation atomicity; the unified credential-pattern source +
the 4 wired providers failing closed; the integrity *mechanism* (real boot gate,
tracks the cross-package primitive); judge-failure handling end-to-end; RLIMIT
sandbox bounding; calibration statistics; auto-promotion staging/approval
separation; B7 byte-identical protocol extraction.

---

## Phase C1 — close the enforcement loop END-TO-END (HIGH PRIORITY)

A 2026-06-03 post-C0 fan-out review (40 agents, 5 dimensions, every finding
adversarially verified) + a local-qwen self-audit found the **meta-gap C0
didn't address**: C0 made the enforcement *primitives* correct, but the live
request path drops the data they depend on, so two of them are **inert in
production**. The primitives are right; the wiring isn't. (29 findings confirmed,
6 false-positives filtered.)

**The keystone cluster — enforcement built but not fed (all self-verified):** — CLOSED, PR #92
- [x] **C1-1** ET enforcement is a no-op on the live path. `executor_core.py:265`
      calls `record_usage(step.id, step_result.tokens_used)` and `StepResult`
      (executor_results.py:33) carries only `tokens_used: int` — no model, no I/O
      split. `effective_tokens()` takes the `m × tokens` branch with m=1.0, so
      ET == raw on the only production path; the "5× real cost reads OK" §8.4
      scenario is still reachable. **Fix:** thread `CompletionResponse`'s
      `model`/`input_tokens`/`output_tokens` (already populated, base.py:177)
      through `StepResult` into `record_usage(model=…, input_tokens=…,
      output_tokens=…)` and pass `effective=` to `allocate`/`can_allocate`.
- [x] **C1-2** Workflow AI requests never set `sensitivity` — `executor_ai.py:264`
      builds `CompletionRequest(...)` with no `sensitivity`, so every
      executor-issued request is PUBLIC and the egress *tier* gate is inert from
      the workflow path. **Fix:** plumb step/workflow sensitivity into the request.
- [x] **C1-3** `TierRouter` rebuild (router.py:130-142) drops `sensitivity`,
      `tools`, `tool_choice` — silent PUBLIC downgrade + broken agentic tool-use
      when routing to an Ollama model. **Fix:** copy all fields (or use
      `dataclasses.replace`).
- [x] **C1-4** `LlamaCppProvider` has NO egress gate (no `_check_request_egress`,
      no `ANIMUS_OFFLINE`) yet `base_url` can be any remote host — a C2-class miss.
      **Fix:** add the same gate the other cloud providers got in C2/C3.

**Security residue (review + qwen agree):**
- [x] **C1-5** The 5 concrete cloud-provider modules (anthropic/openai/azure/
      bedrock/vertex `_provider.py`) are NOT in the integrity tracked-set — only
      `providers.base`/`router` are (C5 residual). Tampering a provider's own
      `_check_request_egress` passes boot detection. **Fix:** add them to
      `_TRACKED_MODULES_OPTIONAL`.
- [x] **C1-6** Credential DLP is all prefix-anchored (`sk-ant-`, `AKIA`, `AIza`…)
      so prefixless/high-entropy secrets pass the content scan — content-DLP is
      defense-in-depth behind the tier tag, but the gap is real. **Fix:** add a
      shannon-entropy heuristic for long tokens; document residual limits.
- [x] **C1-7** Egress enforcement is per-provider convention, not structurally
      enforced — every new/edited provider is additive risk. **Fix:** funnel all
      providers through one `Provider.complete` wrapper that calls the gate, OR a
      registry-level check at `manager.py:239-259`.
- [x] **C1-8** External (non-in-process) integrity check — the deferred half of
      C13; the self-hash + `ANIMUS_INTEGRITY_OVERRIDE=1` are both bypassable by an
      adversary with env/process control. Larger design item.

**Correctness / quality (lower severity, real):**
- [x] **C1-9** `evolution_loop.py:296` compares a 0-100 percent against a 0.80
      fraction (budget-pause threshold unit mismatch).
- [x] **C1-10** `PersistentBudgetManager.add_usage` (persistence.py:201-228) is a
      non-atomic read-modify-write — concurrent spend updates are lost.
- [x] **C1-11** `StreamChunk.to_dict()` (base.py:217-230) references non-existent
      attributes → `AttributeError` if ever called.
- [x] **C1-12** `cost_audit.py:170-177` empty-history path uses naive `datetime`
      → `TypeError` against tz-aware `UsageRecord` timestamps. Persisted budget
      timestamps are also naive local (persistence.py:105,170,224,250).
- [x] **C1-13** `BudgetManager._restore_from_db` (manager.py:225) catches all
      exceptions and silently retries raw-only — masks real schema/backend bugs.

**E2E coverage gaps (the review's e2e dimension):**
- [x] **C1-14** No e2e proving a sensitive payload is *blocked at egress during a
      real workflow run* (only unit-level egress tests exist). With C1-1/C1-2
      fixed, add it — it's the test that would have caught this whole cluster.
- [x] **C1-15** Budget-EXCEEDED halting a *real* workflow is never tested (only
      the dry-run estimate gate); checkpoint/resume e2e doesn't cover
      resume-after-real-crash with partial AI work.

**Auto-promotion / kaizen loop:** correct but **zero production callers** — the
`EvolutionLoop` + `auto_promote_on_improvement` are exported, never invoked by a
live workflow. Either wire them or mark explicitly experimental.

---

## Phase 0 — DONE (PR #80)

Closed already; recorded so future-me doesn't redo it.

- P0 refinements: content-taxonomy wired (#2), code-exec interim isolation via
  `sys.executable -I` (#3, real sandbox still pending → B4), egress unified into
  `animus_types` (#5), tier default-deny reframed + `recall_for_egress` contract
  (#1), ET **opt-in ceiling** mechanism shipped (#4 — the *flip* is A1).
- Test-warning cleanup (root-fixed dead `yaml_file` config + Security filters).
- Claim reconciliation + `../architecture/canonical-principles.md` + canonical whitepaper + clickable PDF.
- → Advances D8 to ~8; lays the mechanism for D1.

---

## Phase A — The keystone + trustworthy substrate

Do this first. A1 makes the central thesis true; the rest is what you must have
before it is sane to run Animus unattended.

| ID | Item | Source | Current → Target | Acceptance | Effort |
|---|---|---|---|---|---|
| **A1 ✅** | **Make Effective-Tokens the enforced budget unit ("the flip")** — DONE Session 1, option (b) | §6 #6, §8.4, cold-read keystone | ET reporting-only → **ET enforced** | Chose (b): raw `total_budget` kept, ET ceiling auto-derived; status takes worse-of-raw/ET; executor halts on EXCEEDED; migration 020 persists ET across restart. Non-breaking (raw-only records neutral) so 0 workflow YAMLs changed. Done-criteria test green; full forge suite 10,210 passed | L |
| **A2 ✅** | `BudgetManager.allocate()` real reservation — DONE Session 2 | §6 #5, appendix | check-only → reserves | Lock + pending state; `allocate()` atomically check-and-reserves; parallel handler reserves once/sub-step + releases in finally; threaded test proves no collective overspend | M |
| **A3 ✅** | Single pricing source — DONE Session 2 | appendix (orchestration) | two tables → one | `estimate_cost` derives from `DEFAULT_MODEL_MULTIPLIERS` × base $9/1M; config overrides flow into cost; reproduces old opus/sonnet numbers | S |
| **A4 ✅** | Content-aware egress — DONE Session 3 | §8.1, Qwen #1, residual gap | tier-trust only → tier + content scan | Canonical credential scanner in `animus_types.secrets` (reused by core redaction — no drift); `is_egress_allowed(content=...)` denies credential-bearing payloads; 4 providers wired via `assert_egress_allowed`; secret mis-tagged PUBLIC is blocked | M |
| **A5 ✅** | Encryption at rest — DONE Session 4 | §7 significant, §8.1, ARCHITECTURE claim | plaintext ext4 → encrypted | gocryptfs vault (PR #67) finished + memory store inside it; documented recovery; CANON/ARCHITECTURE flip from PLANNED→done | M |
| **A6 ✅** | Expand integrity baseline — DONE Session 3 | §6 #8, Qwen #3 | 4 files → all critical-path + self | Self-hashes the checker + guardrails; adds cross-package modules via importlib (`animus_types.egress`/`secrets` required, forge openrouter/pi_wrap optional) — closes the gap where core's egress was a re-export shim; tamper of any trips verify. **Operator must re-baseline** (`python -m animus.integrity.cli regenerate`) after this lands | M |
| **A7 ✅** | Per-install encryption salt — DONE Session 2 | §6 #14 | hardcoded `gorgon-` salt → random per-install | `get_install_salt` helper; random 16B persisted 0600 to `~/.config/animus`; wired at BOTH sites (field_encryption + settings/manager); env overrides kept. Verified no legacy-encrypted data exists, so zero migration cost | S |
| **A8 ✅** | Durability: rebuild dry-run + `animus export --all` — DONE Session 4 | §7 significant | none → portable archive + tested rebuild | `export --all` produces documented-schema archive; timed cold rebuild restores state; loss-of-machine is survivable | M |

Exit: D1 → 9, D3 → 9, D7 substrate in place. **This is the phase that matters most.**

---

## Phase B — Eval integrity + close the Kaizen loop

The self-improvement loop is only trustworthy if the evals it depends on are.

| ID | Item | Source | Acceptance | Effort |
|---|---|---|---|---|
| **B1 ✅** | Judge-failure visibility — DONE Session 5 | §6 #7, §8.3 | judge raises `JudgeError` (no provider / call fails / unparseable) instead of 0.5; evaluator turns it into an ERROR result; classifier buckets `provider_error` | S |
| **B2 ✅** | Judge calibration / meta-eval harness — DONE Session 6 | §7 significant, §8.3 | `calibrate_judge` scores a judge vs a human golden set (MAE/agreement/correlation; a raising judge counts as error, not silent agreement); `judge_drift` tracks per-model drift | M |
| **B3 ✅** | Evolution loop: real experiment runner — DONE Session 6 | appendix (forge) | `eval_experiment_runner` factory (real measured runner); injection mechanism proven; dry-run now flagged loudly (`is_dry_run` + warning + status) so it's never mistaken for evidence | M |
| **B4 ✅** | Real code-exec sandbox — DONE Session 5 | §6 #3 (beyond interim) | `-I -S` + scrubbed env + isolated cwd + kernel RLIMITs (CPU/memory/file-size via preexec_fn); infinite loop → TIMEOUT, memory bomb bounded — not just `-I` | M |
| **B5 ✅** | Auto-promotion eval loop — DONE Session 6 | §7 transformative | `auto_promote_on_improvement`: a significant `eval compare` win stages a human-gated WorkflowEvolution pending patch pinning the version; rejects not-significant / regression / underpowered; never auto-applies | M |
| **B6 ✅** | `compare` power/sample-size advisor — DONE Session 5 | §7 incremental | `underpowered`/`power_note` on ComparisonReport: a non-significant result with CI wider than ±0.05 is flagged underpowered (vs tight-CI equivalence); surfaced in the `compare` CLI | S |
| **B7 ✅** | StabilityScorer protocol extraction — DONE Session 6 | §6 #10 | `StabilityScorer` Protocol + `DefaultStabilityScorer` (current logic unchanged); `compute_stability(scorer=None)` delegates; default behavior identical, custom scorer injectable — the seam for active inference | M |

Exit: D4 → 9-10, D5 → 9, Kaizen loop genuinely autonomous-within-gates.

---

## Phase C — Make it the daily tool

The point of the whole system. Validates the autonomy claims under real load.

| ID | Item | Source | Acceptance | Effort |
|---|---|---|---|---|
| **C1** | RA-1/RA-2 research capability layer | §7 transformative, RA roadmap | WebFetch(allowlist) + Retrieve + Cite + Synthesize; source-grounded output contract ("answer without sources" = fail) | L |
| **C2** | RA-3 overnight delegate | §7 significant, §8 | Persistent SQLite task queue + turn-level checkpoint/resume + morning digest (task→outcome→cost→citations); measured 1-week unattended intervention rate | L |

Exit: D7 → 10 (the delegate is the proof the substrate works). Claude Code reverts to advisory.

---

## Phase D — Differentiators (build last, on a proven substrate)

High-impact, but each depends on earlier work. Building these on an unproven base
makes demos you can't trust.

| ID | Item | Source | Dep | Effort |
|---|---|---|---|---|
| **D1i** | HOT/WARM/COLD tiered memory + lossless compaction | §7 transformative, §6, ANIMUS_MEMORY_GAPS | A8 durability | L |
| **D2i** | Active-inference IntentResolver | §7 significant, Quorum v2 | B7 scorer protocol, B2 calibration | L |
| **D3i** | Replay/bisect over content-addressed event log | §7 transformative | EventLog rework | M |
| **D4i** | EventLog wiring enforced at GorgonBridge | §6 #9 | — | S |
| **D5i** | LivenessWatchdog + coupling MI dashboard | §7 incremental, Quorum v2 | EventLog | M |

Exit: D2 → 10, D6 → 10.

---

## Phase E — Scale, hygiene, residual hardening (continuous)

Slot in opportunistically; none blocks the above. Includes the Qwen net-new items.

| ID | Item | Source | Effort |
|---|---|---|---|
| E1 | Indexed retrieval for the supported local store (preserve filter semantics) | §6 #11 | M |
| E2 | Bound local-store full-corpus RAM and rewrite costs; measure durable routing | §6 #12 | L |
| E3 | LLM-summarized consolidation (not first-tag concat) | appendix (memory) | M |
| E4 | Sync: conflict-surfacing (not silent last-write-wins) | appendix (memory) | M |
| E5 | Quality-gate YAML parsing reconcile (or remove the README example) | §6 #13 | M |
| E6 | Finish Gorgon→Forge rename; gitignore committed `*.db` | §6 #15 | S |
| E7 | Unified secret manager (age/pass backend, `secrets://`) | §7 significant, SECURITY_LAYER spec | L |
| E8 | Cost/quality Pareto optimizer over run history | §7 incremental | M |
| E9 | systemd unit files versioned in repo + integrity-checked | §8.1, Qwen #7 | S |
| E10 | PI-envelope cross-model testing (Qwen/Llama, not just Sonnet) | §8.1, Qwen #P1 | M |
| E11 | **Self-improve / red-team loop abuse hardening** | **Qwen #4 (net-new)** | M |
| E12 | **Local-model supply-chain: pin + checksum model blobs** | **Qwen #5 (net-new)** | M |
| E13 | **TOCTOU on tier labels: immutable tier at read / re-check at use** | **Qwen #6 (net-new)** | M |
| E14 | Ollama upgrade so the uncensored 35B Qwen3.6-A3B red-team model loads | this session | S |
| E15 | **Migration-number collision guard** — a test/CI check that fails when two `migrations/*.sql` share a leading number | **Session 1 (the `012` collision that broke the first full run)** | S |
| **E16** | **Citizen Integration Contract** — map constitutional rights (P01/P02/P05/P07) to concrete code components; close G1–G7 gaps or honestly mark NOT YET IMPLEMENTED; make citizenhood inspectable in architecture docs | **Architecture reconciliation review 2026-07-16** | M |

---

## Completeness matrix (every audit issue → roadmap ID)

So nothing silently drops.

- §6 refinements: #1✅(P0) #2✅ #3✅interim/B4 #4✅mech/A1 #5→A2 #6→A1 #7→B1 #8→A6 #9→D4i #10→B7 #11→E1 #12→E2 #13→E5 #14→A7 #15→E6
- §7 future work: RA→C1/C2 · auto-promotion→B5 · tiered memory→D1i · replay/bisect→D3i · active-inference→D2i · overnight delegate→C2 · encryption+signing→A5 · durability/export→A8 · judge-calibration→B2 · secret manager→E7 · liveness/coupling→D5i · pareto→E8 · power-advisor→B6
- §8 risks: 8.1→A4/A5/A6/E9/E10 · 8.2→D8/CANON(✅) · 8.3→B1/B2 · 8.4→A1/A2/A3
- Qwen net-new: #4→E11 · #5→E12 · #6→E13 ; reinforced: egress-content→A4, encryption→A5, integrity→A6
- Appendix limitations not above: consolidation→E3 · sync→E4 · pricing→A3 · evolution-dry-run→B3 · impact-score-quality→(fold into B5/D5i)

## Session plan — demo/structure → fully operational, ASAP, on-spec-or-better

**The goal of this arc:** take every feature that is currently *claimed but not
actually working* (reporting-only cost, opt-in security gates, dry-run loops,
plaintext-at-rest) to **fully operational, meeting or exceeding the whitepaper's
stated contract.** Not new capabilities — the existing system, made real.

**Definition of OPERATIONAL (the milestone, end of Session 6):** no feature in
the system is reporting-only, opt-in-by-accident, stubbed, or
trust-the-caller. Every claimed guarantee is enforced and has a test that
proves it. After this, Animus can be *relied on*, not just demoed.

**On-spec-or-better rule:** each "done when" criterion is at least the
whitepaper's contract; where cheap, it exceeds it (e.g. egress goes from
tier-trust to *content-aware*, which is stronger than the spec). Never ship a
criterion weaker than the documented contract.

**Critical path:** Session 1 (cost keystone) is the highest-leverage block — do
it first, alone. Sessions 1–6 reach OPERATIONAL. Session 7 is residual security
hardening (incl. the local security-review items) and can run in parallel with
later work — it does not gate "operational."

Each session: one coherent cluster, a definition of done that is **a passing
test or check**, and a clean PR. Pace is yours; a "session" is a focused block,
not a fixed number of hours. Don't start the next until the prior exits green.
Sessions can merge if a block runs short; split if it runs long.

### Session 1 — The keystone: enforce cost (roadmap A1) ✅ DONE
**Why first:** every other claim rests on cost being a hard constraint; today it
isn't. Breaking change, so it gets its own session.
- [x] **Decision gate:** chose **(b)** — keep raw `total_budget`, auto-derive the
      ET ceiling. Non-breaking.
- [x] Route the executor's `_check_budget_exceeded` + `record_usage` through the
      ET-aware `status` (worse-of-raw/ET governs; `effective_ceiling` derives
      from `total_budget`; `enforce_effective_tokens=False` is the escape hatch).
- [x] `_restore_from_db()` rebuilds `_total_effective` via migration 020 (persists
      per-record ET), with a raw-only fallback for un-migrated DBs.
- [x] Workflow YAMLs: **0 changed** — every production `record_usage` is raw-only,
      so ET == raw there (neutral). Migrated the 5 budget tests that encoded the
      old opt-in behavior + 3 migration-fixture lists.
- [x] **Done:** parallel opus run trips `EXCEEDED` at 30% raw (test green);
      executor halts on it; **full forge suite 10,210 passed, 0 failed**. D1 → 9.

### Session 2 — Finish the cost cluster + a quick security win (A2, A3, A7) ✅ DONE
- [x] **A2** `BudgetManager.allocate()` reserves under a lock; parallel handler
      reserves once/sub-step + releases in finally; threaded test proves 20
      concurrent 200-tok reservations grant exactly 10 against a 2000 budget.
- [x] **A3** `estimate_cost` derives from the one tier-multiplier table × base
      $9/1M (config overrides flow through); old opus/sonnet numbers preserved.
- [x] **A7** `get_install_salt` (random 16B, persisted 0600 to `~/.config/animus`)
      wired at both salt sites; env overrides kept. Confirmed **no** legacy-
      encrypted data exists (credentials/api_keys/mcp/settings all 0 rows), so
      zero migration cost.
- [x] **Done:** A2 reservation + threaded tests, A3 single-source tests, A7 salt
      tests all green; affected coverage tests migrated (removed-method gate).
      Prior full run 10,221 passed / 3 failed-now-fixed; CI confirms. **D1 → 10.**

### Session 3 — Egress + integrity (A4, A6) ✅ DONE
- [x] **A4** content-aware egress: canonical credential scanner in
      `animus_types.secrets` (core redaction now reuses it — drift removed);
      `is_egress_allowed(content=...)` denies credential-bearing payloads; the 4
      cloud providers gate via a shared `assert_egress_allowed`. Closes the
      §8.1 residual + Qwen #1/#2/#3.
- [x] **A6** integrity baseline self-hashes the checker + guardrails AND tracks
      cross-package modules via importlib (`animus_types.egress`/`secrets`
      required; forge `openrouter`/`pi_wrap` optional) — the core `network/egress.py`
      was a re-export shim, so the real logic was previously untracked.
- [x] **Done:** mis-tag egress test blocks; module-drift + tamper trip verify;
      verify_hardening 24/24; core security slice 92 passed; types 31; forge DLP
      78. **D3 → 9.** ⚠️ Operator re-baseline required: `python -m
      animus.integrity.cli regenerate`.

### Session 4 — At-rest + durability (A5, A8)
- [x] **A5** finish the gocryptfs vault (PR #67) with the memory store inside it;
      documented recovery; flip ARCHITECTURE/CANON from PLANNED → done.
- [x] **A8** `animus export --all` (documented schema) + a timed cold-rebuild
      that restores state.
- **Done when:** store is encrypted at rest; a from-scratch rebuild passes.
  D3 → 10, D7 substrate in place.

### Session 5 — Eval integrity fixes (B1, B4, B6) ✅ DONE
- [x] **B1** judge raises `JudgeError` (no provider / call fails / unparseable)
      → ERROR result → classified `provider_error`, never a silent 0.5.
- [x] **B4** code-exec sandbox: `-I -S` + scrubbed env + isolated cwd + kernel
      RLIMITs (CPU/memory/file-size). Infinite loop → TIMEOUT; memory bomb bounded.
- [x] **B6** `compare` advisor: `underpowered`/`power_note` distinguish a wide-CI
      underpowered "not significant" from tight-CI equivalence; shown in the CLI.
- [x] **Done:** broken-judge test surfaces an error + routes provider_error;
      sandbox bounds a runaway; small-suite compare flags underpower. eval 236,
      compare 22, sandbox/routing green; whole-tree ruff clean. **D4 → 9.**

> Note: Session 4 (A5 encryption-at-rest + A8 durability) was skipped to here;
> do it before the autonomy/daily-tool phases (it gates D7 + D3=10).

### Session 6 — Close the Kaizen loop (B2, B3, B5, B7) ✅ DONE
- [x] **B2** `calibrate_judge` (MAE/agreement/correlation vs a golden set; a
      raising judge = error, not silent agreement) + `judge_drift`.
- [x] **B3** `eval_experiment_runner` real runner + injection proven; dry-run
      flagged (`is_dry_run` + loud warning + status) so it's never mistaken for
      evidence. *(CLI/daemon exposure of the loop: follow-up — the seam + status
      field are in place.)*
- [x] **B5** `auto_promote_on_improvement`: significant win → human-gated pending
      patch; rejects not-significant / regression / underpowered; never applies.
- [x] **B7** `StabilityScorer` Protocol + `DefaultStabilityScorer`;
      `compute_stability(scorer=None)` delegates; default unchanged (131 quorum
      tests green), custom scorer injectable.
- [x] **Done:** B2/B3/B5/B7 tests green; quorum 966; whole-tree ruff clean.
      **D4 → 10, D5 → 8, D6 → 7.**

### Session 7 — Security residual hardening (Qwen review + §8.1 leftovers)
Does NOT gate "operational" — run it parallel to Phase C/D or right after S6.
The 2026-06 local security review's 3 net-new items + the remaining §8.1 gaps.
- [x] **E13 (Qwen #6) TOCTOU on tier labels** — `is_egress_allowed()` re-checks
      payload content at use time; PUBLIC tag + credential payload = blocked.
      Tests: `test_content_recheck_blocks_secrets_even_when_public`.
- [x] **E11 (Qwen #4) self-improve / red-team loop abuse** — `SafetyChecker`
      screens analyzer suggestions for probe-shaped content before plan creation.
      `is_probe_shaped()` matches jailbreak, DAN mode, encoding evasion, and
      repetition-flooding patterns. End-to-end test proves `_apply_changes` is
      never called when a probe is detected.
- [ ] **E12 (Qwen #5) local-model supply-chain** — pin + checksum the Ollama
      model blobs Animus trusts; refuse to run a red-team/eval model whose digest
      changed unexpectedly. Closes the "backdoored open-weight model" vector.
- [x] **E9 systemd unit integrity** — `_TRACKED_REPO_PATHS` hashes 10 repo-root
      systemd/deploy configs; `_repo_root()` discovers git root from package root.
      Tampered unit files trip `IntegrityMismatchError` at boot.
- [ ] **E10 PI-envelope cross-model testing** — the prompt-injection footer is
      only tested against Sonnet; add Qwen/Llama cases (the local-first models
      that are the *actual* primary consumers).
- **Done when:** supply-chain digest test trips on a changed blob; probe-can't-
  escalate test passes; unit-tamper trips boot refusal; PI envelope holds on
  Qwen/Llama. D3 → 10 (fully hardened).
- **Done 2026-07-16:** E9 + E11 + E13 closed. 3/5 Session 7 security items
  complete; E10 + E12 deferred to follow-up.
- [ ] **E14** Ollama upgrade so the uncensored 35B Qwen3.6-A3B loads — then
      re-run the adversarial review with the *aggressive* model for a stronger pass.

**After Session 6 = OPERATIONAL.** The existing system is fully working,
on-spec-or-better, every claim enforced and tested. Session 7 hardens the
security tail. Only *then* do Phases C (daily-tool: RA layer, overnight delegate)
and D (differentiators: tiered memory, active inference, replay) begin — the
*build* arc, re-planned into sessions on the now-trustworthy substrate.

### Phase E sessions — scale, hygiene, guards (non-security; continuous)

Phase E is *opportunistic*: none of these gate OPERATIONAL, and any can be
slotted in when its area is already open. Security-tail E-items (E9–E14) live in
Session 7. The rest cluster into three optional sessions below. Same rule: a
"done when" that is a passing test, and a clean PR.

#### Session 8 — Memory scaling & correctness (E1–E4)
Lifts the memory layer off its scaling ceilings and removes silent data loss.
Best done when the memory store is otherwise quiet (no concurrent migrations).
- [ ] **E1** Add measured indexed retrieval to the supported local store without
      changing filter or ordering semantics. *Done when:* large-corpus queries avoid
      a full scan and the existing store contract tests return identical results.
- [ ] **E2** Bound `LocalMemoryStore` full-corpus RAM and full-file rewrite costs,
      or route measured large-corpus deployments to the durable store.
      *Done when:* a large-corpus test meets an explicit memory/write budget and
      all supported store contract tests still pass. (L — the heaviest Phase E item.)
- [ ] **E3** `consolidate()` summarizes via the cognitive layer instead of
      first-tag 150-char concat. *Done when:* a consolidated memory is a real
      summary (LLM in test = mock returning a marker), originals untouched
      (append-only preserved).
- [ ] **E4** Cross-device sync surfaces conflicts instead of silent
      last-write-wins. *Done when:* two divergent edits to the same record
      produce a recorded conflict (not a dropped loser) in a sync test.
- **Exit:** D2 (memory) scaling ceilings removed; no silent loss. D2 → 10.

#### Session 9 — Hygiene & dev-tooling guards (E5, E6, E8, E15)
Cheap correctness + the poka-yoke that would have caught Session 1's own bug.
- [ ] **E15** Migration-number collision guard (NEW, from Session 1). A test
      globs `migrations/*.sql`, parses the leading integer, and asserts the set
      is unique. *Done when:* the test fails on a duplicate number and passes on
      the current tree. ~20 lines; do this **first** in the session — it is the
      poka-yoke for the exact failure that broke Session 1's first full run.
- [ ] **E5** Reconcile the quickstart `gates:` YAML: either parse it in the
      production `WorkflowConfig` loader (reuse Core's safe gate parser) or
      remove the example from the README. *Done when:* docs and the loader agree
      (a test asserts a `gates:` workflow either enforces or is rejected, not
      silently ignored).
- [ ] **E6** Finish the Gorgon→Forge rename (`branch_prefix` default, residual
      identifiers) and gitignore the committed runtime `*.db` files. *Done when:*
      `grep -ri gorgon src/` is clean of live identifiers; no `*.db` tracked.
- [ ] **E8** Cost/quality Pareto optimizer over the eval run store: recommend
      the cheapest (model, prompt_version) holding a target quality band.
      *Done when:* given seeded run history, it returns the Pareto-optimal config
      in a test. (Builds on the now-enforced Effective-Tokens from Session 1.)
- **Exit:** D5/D8 hygiene closed; the migration guard prevents a repeat of the
  Session 1 collision.

#### Session 10 (optional, large) — Unified secret manager (E7)
- [ ] **E7** Build the `SECURITY_LAYER.md` secret manager (age/pass backend,
      `animus secrets` CLI, `secrets://` URI resolution) to replace ad-hoc
      credential handling. Large and cross-cutting with security; sequence it
      near Session 7 or whenever credential handling next causes friction.
      *Done when:* a `secrets://` reference resolves at load; no plaintext
      secret in config; round-trip test green. Flip the SECURITY_LAYER spec
      `ASPIRATIONAL-SPEC → CANONICAL` in `../architecture/canonical-principles.md` when it lands.

## Working rule

When an item lands, in the **same PR**: flip its status in `../architecture/canonical-principles.md`, tick it
here, and remove it from `TODO_NEXT.md`. That is how this stays a live map and
not roadmap #5.
