# Animus Roadmap

**Project:** Animus — An Intelligent Computing Environment You Own
**Direction updated:** 2026-11-26
**Status:** Consolidation before expansion; implementation evidence must be refreshed independently.

## North Star

Build a personal, local-first intelligent computing environment in which awareness, memory, reasoning, orchestration, governance, and execution are modular and interoperable.

Linux is the current supported public deployment target. Model, framework, operating system, device and hardware independence are architectural objectives. Ambient intelligence, edge AI and distributed computing inform the research direction; they are not claims of completed platform functionality.

See the [README](../../README.md) and [Architecture Overview](../architecture/overview.md).

## Delivery rules

- Consolidate before expanding; reuse before implementing.
- Prefer deterministic mechanisms over unnecessary inference.
- Assign one accountable owner to each capability and avoid overlapping control planes.
- Preserve human authority, explicit authorization, inspectable evidence, and recoverability.
- Validate current functionality before promoting maturity claims.
- Treat phases below as dependency-ordered priorities, not calendar promises.

## Phase A — Consolidation (current priority)

| Workstream | Deliverable | Acceptance evidence |
|---|---|---|
| Runtime reliability | Minimal repeatable Linux deployment; healthy services and local inference | Recorded first-run and restart checks; actionable failure diagnostics |
| End-to-end operation | One useful workflow from request to authorized execution and inspected result | Reproducible run with inputs, outputs, status and evidence |
| Governance boundaries | Explicit ownership of authority, budgets, scope, escalation and completion | Contract review and tests for denial, escalation and unauthorized completion |
| Delegated engineering | Evaluate ForgeHand and standalone Loop Governor integration without duplicating existing Forge capabilities | Demonstrated bounded handoff, evidence return and interruption behavior |
| Operational visibility | Lightweight health and resource reporting using existing infrastructure where possible | Observable service state, failures and resource consumption; measured overhead |
| Memory and recovery | Confirm supported persistence and restart behavior | Restart/recovery tests and documented limitations |
| Documentation truth | Reconcile public claims, package versions, platform support and current evidence | Current CI/release references and verified operator instructions |

**Exit gate:** A repeatable, minimally useful environment on supported hardware; clear authority boundaries; evidence-backed operation and recovery. Do not treat this gate as passed until validated.

## Phase B — Interoperability (after consolidation)

- Inventory existing tools and protocols before creating new infrastructure.
- Define narrow contracts for capability registration, identity, authentication, resource inventory, and workload requests.
- Prototype lightweight event-driven environmental monitoring.
- Evaluate routing across authenticated local and remote nodes, including unavailable-node and insufficient-resource cases.
- Investigate persistent context across interaction devices with explicit access and retention policy.
- Establish extension compatibility and rollback expectations for community modules.

**Exit gate:** Demonstrate at least one bounded cross-node workflow with authenticated capability discovery, explicit authorization, traceable results, and tested failure behavior. Measure overhead and document supported platforms rather than claiming universal compatibility.

## Phase C — Intelligent environments (research direction)

- Explore heterogeneous edge inference and portable deployment across hardware and operating systems.
- Investigate context-aware assistance that does not require continuous inference or pervasive surveillance.
- Evaluate governed adaptation and self-optimization with reversible changes and human authority.
- Explore modular, highly customizable computing environments assembled from independently useful capabilities.

**Research gate:** Each proposed capability must establish a useful problem, reuse analysis, threat model, measurable benefit, resource cost, and acceptance evidence before entering implementation scope.

## Non-goals for the current phase

- Building a new operating system or replacing existing tools without demonstrated need.
- Expanding citizen populations or adding new standalone projects simply to increase capability count.
- Treating distributed execution, automatic discovery, universal portability or ambient assistance as production-ready.
- Unrestricted self-modification or autonomous approval of completion claims.

## Evidence and status reporting

Use current package metadata, CI runs, release evidence, and reproducible operator checks as the source of implementation status. Static test counts and historical checklists are not current verification. Existing accepted ADRs remain authoritative; changes to their decisions require the appropriate review process.

Outstanding earlier roadmap items should be re-evaluated against Phase A rather than automatically discarded or carried forward. In particular, verify schema documentation, version compatibility, recovery behavior, and deployment configuration before declaring them complete.

## Historical baseline

The following material preserves the prior roadmap's reported build state and milestone decisions (June/July 2026, with later edits). It is retained for traceability, not as current acceptance evidence. Historical dates and completion labels are not new commitments or a fresh verification.

## Build Truth (historical baseline)

> ⚠️ **The previous roadmap overstated completion. This version is grounded in filesystem reality.**

| Package | Version | Source Files | Tests | Runtime Status |
|---|---|---|---|---|
| `core` | 2.3.0 | 94 Python | 2,832 | CLI + memory + dashboard operational |
| `forge` | 1.9.0 | 352 Python | 10,431 | Workflow orchestration operational |
| `bootstrap` | 0.8.0 | 136 Python | 1,874 | Daemon + onboarding + dashboard operational |
| `kernel` | 0.1.0 | 189 Python | 107 | Extracted from Forge, durable core wired |
| `quorum` | 1.2.0 (animus-quorum) | 14 Rust + 10 Python | 961 | Rust core + Python bindings, active |
| `types` | 0.1.0 | 4 Python | 67 | Minimal but functional |
| `pwa` | — | 19 TypeScript | 0 | Frontend scaffolded, wiring TBD |
| `contracts` | — | 20 JSON schemas | 0 | Pure JSON, no runtime validation |
| `database` | — | 1 Python + 1 SQL migration | 4 | Migration syntax tests (no DB required) |

**Version alignment**: ⚠️ Documented mismatch. Core 2.3.0, Forge 1.9.0, Bootstrap 0.8.0, others 0.1.0–1.2.0. See `COMPATIBILITY_MATRIX.md` for dependency graph and compatibility ranges. Unified versioning deferred to Phase 2.

**Reported truth baseline:** **25/26 PASS**, 1 FAIL (`version_alignment` — expected and documented). Previously: 21/22 with 1 FAIL. Test infrastructure fixed: root `pyproject.toml` now sets `pythonpath` for all sibling packages.

---

## Historical current-state snapshot

### What Works

- **Core exocortex**: CLI (`python -m animus`), memory tiers over local JSON or
  configured durable SQL, identity, proactive tasks
- **Bootstrap**: Install daemon, onboarding wizard, FastAPI+HTMX dashboard (`localhost:7700`), Ollama health checks
- **Forge**: Multi-agent YAML workflows, 10 archetypes, token budgets, stage persistence and manual restart, SQLite state, adversarial test harness, governance plane
- **Quorum**: Rust intent graph + Python bindings, stigmergy coordination, signal bus, triumvirate voting
- **Kernel**: Extracted 172 files / 55K LOC from Forge, budget/executor/sandbox/resume all present, durable core wired
- **PWA**: TypeScript frontend scaffolded with Vite, login/chat/personas/status views, service worker
- **Types**: Sensitivity, egress, secrets dataclasses (security-focused)
- **Contracts**: 20 canonical JSON schemas (`action`, `event`, `assessment`, `memory`, `trace`, etc.)

### What Is Scaffolding Only

| Structure | Status | Evidence |
|---|---|---|
| `apps/` | ✅ README only | `apps/README.md` explains what belongs here |
| `modules/` | ✅ README only | `modules/README.md` explains boundary vs packages/ |
| `contracts/` (root) | ✅ Removed | Root dir deleted; `packages/contracts/` holds schemas |
| `database/` | ✅ Migration + README | `database/README.md` + `migrations/versions/001_initial_schema.py` |
| `infra/` | ✅ Docker Compose + README | `infra/docker-compose.yml` + `infra/.env.example` |
| `evidence/releases/` | ✅ Bundles generated | `evidence-2026-06-29-075813/` with manifest, tests, schemas, git info |
| `adrs/` | ✅ 5 ADRs | ADR-001 through ADR-005 all committed |

---

## Historical milestones

### Phase 0: Foundation — MOSTLY COMPLETE

- [x] Dead packages archived to `packages/_archive/` (8 packages)
- [x] ADR-001 through ADR-005 recorded in `adrs/`
- [x] 20 canonical JSON schemas extracted to `packages/contracts/`
- [x] **Truth baseline fixed** — `check_test_count` now FAILs on non-zero exit codes; `python3` fallback added
- [x] **Version alignment check implemented** — reads all 8 package versions, reports mismatches (still 7 unique versions)
- [x] **Schema importability** — 20 schemas auto-generated as Pydantic v2 models in `packages/types/`
- [x] **Root architecture dirs** — populated with READMEs or removed (root `contracts/` deleted)

**Blockers**: Phase 1 can start. Remaining Phase 0 gap: unify package versions (not urgent).

### Phase 1: Schema Integration (Q3 2026)

- [x] Port 20 JSON schemas into importable Python types in `packages/types/` (via `scripts/compile_schemas.py`)
- [x] Add `pyproject.toml` to `packages/contracts/` (now a real package)
- [x] Build schema validation layer (JSON Schema → Pydantic or dataclass) — `scripts/validate_schemas.py` checks all 25 schemas for meta-schema validity, unique $id, dangling $refs, and Pydantic model importability + minimal payload round-trip. Verified green.
- [x] Add JSON Schema CI gate — `.github/workflows/ci.yml` has `schema-validate` job running on PR/push to main.
- [ ] Document schema usage patterns in `docs/reference/`
- [x] Align `packages/quorum/` name (`convergentAI` → `animus-quorum`) — completed 2026-07-23

### Phase 2: Durable Core (Q3–Q4 2026) — COMPLETE

- [x] Implement object registry in `database/` (PostgreSQL default, SQLite projection)
- [x] Implement event ledger with bitemporal projections
- [x] Wire `packages/kernel/` into durable core model (`DurableMemoryStore` in `memory/stores/durable.py`)
- [x] Add traceability linter (`scripts/traceability_linter.py`)
- [x] Populate `database/` with migration tooling
- [x] Populate `infra/` with Docker Compose or systemd deployment manifests

### Phase 3: Evidence & Governance (Q4 2026) — COMPLETE

- [x] Build `scripts/assemble_evidence_bundle.py`
- [x] Create release evidence bundles in `evidence/releases/` (evidence-2026-06-29-075813)
- [x] Integrate adversarial test harness (`packages/forge/src/animus_forge/evaluation/adversarial.py`)
- [x] Implement policy decision point + governance plane (`packages/forge/src/animus_forge/governance/`)
- [x] Add ADR-002 through ADR-005 for decisions made to date

### Phase 4: Public/Private Split (Q1 2027) — COMPLETE (Documentation + Decision)

- [x] Initialize private repo for owner-specific data — spec ready, migration guide written
- [x] Move synthetic fixtures to public repo — `memory_eval_corpus.json` already synthetic and public-safe
- [x] Document boundary and migration path — `docs/operators/public-private-split.md` + `migration-guide.md`
- [x] Make repo public OR deploy docs to Netlify/Cloudflare Pages — ADR-006 recommends public; Cloudflare Pages workflow provided as fallback

### Phase 5: Mind Action Pack Integration (Q1–Q2 2027)

- [ ] Port `.claude/agents/`, `.claude/skills/`, `.claude/rules/` from artifacts into versioned packages
- [ ] Validate against current operating model (v2.1 planes)
- [ ] Document agent runtime expectations in `docs/operators/`

---

## Historical blockers and deployment notes

Earlier documentation reported CI billing restrictions, private-repository Pages limitations, kernel coverage concerns, and local database configuration requirements. These are historical observations, not asserted current blockers. Recheck each against current CI, repository visibility, package coverage and deployment configuration as relevant.

## See Also

- [Architecture Overview](../architecture/overview.md)
- [Package Architecture](../architecture/packages.md)
- [Decisions](../architecture/decisions/README.md)
- [Getting Started](../getting-started/quickstart.md)
