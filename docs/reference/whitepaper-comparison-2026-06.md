# Current Code vs the 2026-06 Whitepaper — Gap Closure (refreshed 2026-06-03, post-C0)

Re-running the canonical whitepaper's own gap list
([`../whitepapers/ANIMUS_WHITEPAPER_2026-06.md`](../whitepapers/ANIMUS_WHITEPAPER_2026-06.md))
against the code after Sessions 1-6 **and the full Phase C0 backlog**
(PR #89 must-fix C2–C7, PR #90 should-fix C8–C13), cross-checked against the
2026-06-03 adversarial [review](../reviews/animus-10-10-review-2026-06-03.md).
Status is honest: ✅ closed, ◐ partial (closed in mechanism, gap remains), ✗ open.

## §6 Design Refinements (the P0-P3 backlog)

| # | Whitepaper refinement | Status | Notes |
|---|---|---|---|
| 1 | `allowed_tiers` default-deny | ✅ | Reframed (PR #80): egress surface already pins `{PUBLIC}`; the local-read default is the correct contract. Review confirmed. |
| 2 | Wire content taxonomy (F1-F8) | ✅ | PR #80. |
| 3 | Real code-exec sandbox | ✅ | RLIMIT bounding (B4) + **C6**: `CodeExecutionMetric` now scores non-zero exit / TIMEOUT 0.0 (crashing code no longer scores 1.0). |
| 4 | Unify the two egress copies | ✅ | `animus_types.egress` canonical; review confirmed no drift. |
| 5 | `allocate()` real reservation | ✅ | Raw-token reservation atomic + thread-safe (A2) **+ C8**: optional `effective` ET estimate + `_pending_effective` reservation, ET ceiling now checked at admission. |
| 6 | Effective-Tokens enforced | ✅ | Post-hoc via `status==EXCEEDED` (A1) **+ C8** admission gate — an opus/output-heavy step is now refused before it runs, not only caught next step. |
| 7 | Judge-failure visibility | ✅ | B1; review confirmed end-to-end (raise → ERROR → `provider_error`). |
| 8 | Expand integrity baseline | ✅ | Self-hash + cross-package primitive (A6) **+ C5**: forge enforcement modules (`network.egress`, `providers.base`, `providers.router`) now tracked; baseline regenerated. *(Operators re-baseline on deploy — `animus.integrity.cli regenerate`.)* |
| 9 | EventLog wiring enforced | ✗ | Not started (D6 tail). |
| 10 | `StabilityScorer` protocol | ✅ | B7; review confirmed byte-identical default + injectable seam **+ C13** falsy-scorer-drop fix. |
| 11 | Indexed retrieval for the supported local store | ✗ | Phase E (E1). |
| 12 | Bound local-store RAM and full-file rewrite costs | ✗ | Phase E (E2). |
| 13 | Quality-gate YAML parsing | ✗ | Phase E (E5). |
| 14 | Per-install encryption salt | ✅ | A7; review confirmed (no legacy data, zero-cost). |
| 15 | Gorgon rename + gitignore db | ✅ | `gorgon.yaml` removed **+ C12**: stale 2024 `CostTracker.PRICING` refreshed to Claude 4.x / GPT-4.1; false "single source" docstring corrected. |

**§6 score: 11 closed, 0 partial, 4 open** (of 15) — open: #9 EventLog,
#11 supported-local retrieval indexing, #12 supported-local scaling, and #13
quality-gate YAML (all Phase D/E). Up from 0 at whitepaper time; the entire
P0–P3 enforcement backlog is now closed.

## §7 Future Work

| Item | Status | Notes |
|---|---|---|
| Judge calibration / meta-eval | ✅ | B2; review confirmed statistics sound. |
| Auto-promotion eval loop | ◐ | Logic + staging/approval correct (B5) **+ C7**: experiment runner now reads the real `total_score` (no longer drops the signal) **+ C11**: dry-run iterations stamped on the record + audit JSONL. Still zero production callers — the loop is correct but not yet wired into a live workflow. |
| Active-inference IntentResolver | ✗ (seam ✅) | B7 laid the injectable scorer seam; the flood-resistant impl is unbuilt. |
| RA-1/2 research layer · overnight delegate (RA-3) | ✗ | Phase C — not started. |
| Encryption at rest + signed memory | ✗ | A5 — operator-gated (gocryptfs PR #67 unmerged). |
| Durability / `export --all` + rebuild | ✗ | A8 — Session 4 was skipped; **this is the biggest still-open "earn unattended operation" gap.** |
| Tiered memory · replay/bisect · secret manager · Pareto optimizer | ✗ | Phase D/E. |

## §8 Open Questions / Risks

| Risk | Movement | Notes |
|---|---|---|
| 8.1 Where do safety boundaries hold? | ◐ | Content-aware egress (A4) now wired on **all** cloud providers incl. Bedrock/Vertex + Azure streaming, and scans tool defs / tool_result / tool_use args (C2-C4); forge enforcement modules integrity-tracked (C5). **Remaining:** encryption at rest (A5) untouched, and the integrity self-hash is in-process (defeatable) — external pre-exec check deferred (C13). The boundary is *materially tighter; two known edges remain.* |
| 8.2 Single-maintainer sustainability | ✅ (mitigated) | CANON.md + claim reconciliation + this review give the coherence machinery the whitepaper called for. |
| 8.3 Are the evals valid? | ✅ | Judge calibration (B2) + judge-failure visibility (B1) turn "assumed" into "measured." |
| 8.4 Cost at scale | ✅ | Raw reservation enforced (A2); ET enforced at both admission (C8) and post-hoc; pricing clarified to one authoritative source — `CostTracker.calculate_cost` (per-model $), with `estimate_cost` relabelled a coarse approximation (C12). |

## Bottom line vs the whitepaper

The whitepaper's honest self-audit (68 production / 6 beta / 4 exp / 5 stub)
described a system with real cores and a long, named gap list. **Sessions 1-6
materially closed that list** — judge integrity, calibration, the scorer seam,
the per-install salt, the unified egress/credential source, raw-token cost
reservation, and the kaizen-loop scaffolding are genuinely in place and
adversarially verified.

The 2026-06-03 review then showed Sessions 1-6 had **over-claimed "10/10" on
D1/D3/D4/D5** — the enforcement edges (ET admission gate, Bedrock/Vertex egress,
Azure streaming, tool-block DLP, the integrity tracked-set, sandbox
crash-scoring, the auto-promotion runner) were bypassable or broken, several
masked by tests that mocked the failing path.

**Phase C0 has now closed all 13 of those corrections** ([PR #89](../roadmap/roadmap-to-10.md)
must-fix C2-C7, PR #90 should-fix C8-C13), each with a test that exercises the
real failing path. The honest delta from the whitepaper today: **the entire
catalogued P0-P3 enforcement backlog is closed and adversarially verified; the
egress/DLP/cost/integrity boundaries that were "leaky" are now tight on the
paths the review probed.** Two security edges remain by explicit decision —
encryption at rest (A5) and an external (non-in-process) integrity check (the
deferred half of C13) — and the bigger unattended-readiness gap is still
durability: `export --all` + tested cold-rebuild (A8) is untouched. So:
**materially higher maturity, enforcement-complete, but not yet fully
unattended-ready until A5/A8 land.**
