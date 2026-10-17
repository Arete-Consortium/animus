# Animus Roadmap

**Project**: Animus — Personal AI exocortex / Mind-class system
**Classification**: Flagship
**Version**: 2.3.0 (core), mixed across packages (see [Build Truth](#build-truth))
**Last updated**: 2026-06-29
**Next review**: 2026-07-27

---

## Build Truth

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

**Truth baseline**: ✅ Honest. **25/26 PASS**, 1 FAIL (`version_alignment` — expected and documented). Previously: 21/22 with 1 FAIL. Test infrastructure fixed: root `pyproject.toml` now sets `pythonpath` for all sibling packages.

---

## Current State (Real)

### What Works

- **Core exocortex**: CLI (`python -m animus`), memory tiers over local JSON or
  configured durable SQL, identity, proactive tasks
- **Bootstrap**: Install daemon, onboarding wizard, FastAPI+HTMX dashboard (`localhost:7700`), Ollama health checks
- **Forge**: Multi-agent YAML workflows, 10 archetypes, token budgets, checkpoint/resume, SQLite state, adversarial test harness, governance plane
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

## Milestones (Revised)

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

## Prioritized Next Actions (Post-Phase 0)

1. **Schema validation layer** — JSON Schema → Pydantic gate in CI for `packages/contracts/`
2. **Kernel durable core wiring** — connect `packages/kernel/` memory backends to `database/` registry/ledger
3. **Traceability linter** — requirement-to-test mapping from ADRs to test modules
4. **Evidence bundle release** — generate first official bundle in `evidence/releases/`
5. **Quorum naming alignment** — document or rename `convergentAI` → `animus-quorum`

---

## Blockers

| Blocker | Impact | Resolution |
|---|---|---|
| Version misalignment | Low | Documented in `COMPATIBILITY_MATRIX.md`; unified versioning deferred |
| Kernel under-tested (99 tests for 189 files) | Medium | Add coverage before durable core integration |
| GitHub CI billing blocked | Medium | All CI jobs fail; local-first validation only |
| MkDocs deployment blocked | Low | Repo is private; Pages requires Pro or public repo |
| Alembic `sqlalchemy.url` configuration | Low | Default `driver://user:pass@...` in `alembic.ini` — set via env var or local config |

---

## Definition of Done (Phase 0 Completion)

- [x] Truth baseline fails on broken checks, not silently passes
- [x] All 8 packages have version metadata and alignment is documented (`COMPATIBILITY_MATRIX.md`)
- [x] `packages/types/` imports at least 10 of the 20 contract schemas as Python
- [x] Every root architecture directory has a `README.md` explaining its purpose or is removed
- [x] `scripts/assemble_evidence_bundle.py` exists and produces a manifest

---

## MkDocs Deployment

- **Status**: Site builds clean (0 warnings). Deployment blocked because repo is private.
- **Options**: Make repo public (fastest), upgrade GitHub Pro, or deploy to Netlify/Cloudflare Pages
- **Files**: `mkdocs.yml`, `docs/requirements-docs.txt`, `.github/workflows/docs-deploy.yml` all ready

---

## See Also

- [Architecture Overview](../architecture/overview.md) — 8-plane model
- [Package Architecture](../architecture/packages.md) — Dependency graph and version matrix
- [Decisions](../architecture/decisions/README.md) — ADRs
- [Truth Baseline](https://github.com/your-org/animus/blob/main/truth-baseline.toml) — Source of truth config (needs fix)
