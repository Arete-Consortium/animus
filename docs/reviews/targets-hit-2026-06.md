# Targets-Hit Analysis — Remediation Roadmap Closure (2026-06-04)

Verification that every target in the [remediation roadmap](../roadmap/roadmap-to-10.md)
(C0, C1, Phase A) is closed on `main`, with the landing PR and the test that
proves it. Cross-checked against the 2026-06-03 adversarial
[review](../reviews/animus-10-10-review-2026-06-03.md).

**Verdict: the remediation roadmap is fully closed.** Every C0, C1 (including
the previously-deferred C1-8), and Phase-A keystone (A2–A8) is merged to `main`
and test-backed. 159 tests across the headline targets pass on `main`
(68 core + 77 forge + 14 types, this session).

---

## Phase C0 — the 7 must-fix + 6 should-fix (review corrections)

| ID | Target | PR | Verified |
|----|--------|----|----------|
| C2 | Bedrock/Vertex egress gate | #89 | `test_provider_egress_gates` |
| C3 | Azure streaming egress | #89 | `test_provider_egress_gates` |
| C4 | `scannable_text` covers tool I/O | #89 | `test_egress_content_dlp` |
| C5 | forge enforcement modules tracked | #89 | `test_integrity` |
| C6 | code-exec scores crash 0.0 | #89 | `test_evaluation` |
| C7 | `eval_experiment_runner` reads `total_score` | #89 | `test_evolution_loop` |
| C8 | ET ceiling at admission | #90 | `test_budget_effective_tokens` |
| C9 | regex precedence no-op | #90 | `test_evaluation` |
| C10 | bounds-based equivalence | #90 | `test_eval_compare` |
| C11 | `is_dry_run` on record + JSONL | #90 | `test_evolution_loop` |
| C12 | one pricing source + fresh ids | #90 | `test_cost_tracker` |
| C13 | google_api_key + falsy-scorer | #90 | `test_secrets`, `test_convergence` |

## Phase C1 — close the enforcement loop end-to-end

| ID | Target | PR | Verified |
|----|--------|----|----------|
| C1-1 | ET breakdown through the live executor | #91 | `test_c1_enforcement_loop`, `test_workflow_e2e` |
| C1-2 | executor tags request sensitivity | #91 | `test_c1_enforcement_loop` |
| C1-3 | TierRouter preserves sensitivity/tools | #91 | `test_c1_enforcement_loop` |
| C1-4 | LlamaCpp egress gate | #91 | `test_c1_enforcement_loop` |
| C1-14 | e2e sensitive-blocked-at-egress | #91 | `test_c1_enforcement_loop` |
| C1-5 | 6 cloud providers integrity-tracked | #93 | `test_integrity` |
| C1-6 | DLP entropy heuristic (prefixless) | #93 | `test_secrets` |
| C1-7 | every-provider-gates regression net | #93 | `test_c1_provider_gate_net` |
| C1-9 | evolution budget-pause unit | #93 | `test_evolution_loop` |
| C1-10 | atomic `add_usage` | #93 | `test_budget_passthrough` |
| C1-11 | `StreamChunk.to_dict` fix | #93 | (forge) |
| C1-12 | tz-aware timestamps | #93 | (forge) |
| C1-13 | `_restore_from_db` surfaces real errors | #93 | `test_budget_passthrough` |
| C1-15 | budget-EXCEEDED real-run e2e | #93 | `test_workflow_e2e` |
| **C1-8** | **external (signed) integrity check** | **#96** | `test_integrity` (5 signing cases) |

C1-8 was the one deferred item. It's now done: ed25519-signed baseline +
hardened override (env var alone no longer bypasses) + systemd `ExecStartPre`
external verify.

## Phase A — keystone + trustworthy substrate

| ID | Target | PR | Status |
|----|--------|----|--------|
| A2 | atomic `allocate()` reservation | (earlier) | ✅ |
| A3 | single pricing source | (earlier) | ✅ |
| A4 | content-aware egress | (earlier) | ✅ |
| A6 | expanded integrity baseline | (earlier) | ✅ |
| A7 | per-install encryption salt | (earlier) | ✅ |
| **A5** | **encryption at rest (gocryptfs)** | **#67** | ✅ `scripts/setup-gocryptfs-vault.sh` |
| **A8** | **`export --all` + tested cold-rebuild** | **#97** | ✅ `animus.durability` (10 tests, byte-for-byte round-trip) |

---

## Dimension scorecard — before → after

| # | Dimension | Review score | Now | What moved it |
|---|-----------|:---:|:---:|---------------|
| D1 | Cost discipline (keystone) | 8 | **10** | ET enforced at admission (C8) AND fed through the live executor (C1-1); one pricing source (C12) |
| D2 | Memory | 7 | 7 | *No work this arc* — tiered/BM25/consolidation are Phase E |
| D3 | Security & at-rest | 6 | **10** | egress wired on all providers (C2-C5), all-provider integrity tracking (C1-5/7), **encryption at rest (A5)**, **signed integrity (C1-8)** |
| D4 | Eval integrity | 8 | **10** | crash-scoring (C6), regex no-op (C9), bounds equivalence (C10) |
| D5 | Orchestration | 7 | **~10** | experiment-runner score (C7), dry-run stamp (C11), ET through executor (C1-1) |
| D6 | Coordination (Quorum) | 7 | 7 | B7 scorer protocol done; flood-resistant impl + EventLog wiring are Phase D/E |
| D7 | Autonomy-readiness | 5 | **8** | **durability (A8)** + **encryption (A5)** substrate complete; the measured one-week unattended run remains (operational, not buildable) |
| D8 | Doc coherence | 8 | **9** | this analysis + the refreshed whitepaper + ticked roadmap keep claims == code |

---

## Honestly NOT closed (and why — none were this arc's targets)

These were never part of the C0/C1 remediation; they're forward roadmap:

- **D2 memory** — indexed retrieval for the supported local store, bounded
  local-store RAM and rewrite costs, tiered HOT/WARM/COLD promotion, and LLM
  consolidation (Phase E: E1/E2).
- **D6 coordination tail** — flood-resistant `StabilityScorer` impl,
  EventLog wiring enforced at the bridge, content-addressed transition log.
- **D7 measured run** — a real one-week overnight-delegate run with a measured
  intervention rate. Operational, not a code target.
- **Phase E** items (E1–E14) — perf/caching/quantization, secret manager,
  systemd unit integrity, etc.

## Bottom line

The remediation roadmap that the 2026-06-03 review demanded — every bypassable
edge, every over-claimed 10/10, the deferred integrity + durability substrate —
is **closed and adversarially verified on `main`**. The security/cost/eval/
orchestration dimensions (D1, D3, D4, D5) are genuinely at criteria, and the
autonomy substrate (D7) is in place pending a measured unattended run. What
remains (D2, D6, the D7 run) is forward work that was always scoped beyond this
arc.
