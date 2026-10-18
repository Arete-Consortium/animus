# Changelog — Animus v2.3 Assistant Stable

**Release Date:** 2026-06-30
**Tag:** `v2.3-assistant-stable`
**Classification:** Assistant-class (pre-Mind architecture)
**Status:** Final stable release on the Core/Forge/Quorum/Bootstrap trajectory

> **Historical release record.** Backend behavior below describes the June 2026
> release and is not current installation or configuration guidance. Current
> Animus Core rejects legacy Chroma selectors and supports local JSON or an
> explicitly configured durable SQL store.

---

## Summary

This release represents the culmination of the pre-public hardening sprint for Animus as an **Assistant-class AI exocortex**. All wiring gaps between the PWA frontend, Contracts runtime validation, and PostgreSQL durable persistence have been closed. The codebase is functional, tested, and ready for public sharing.

This is the **last release on the v2.x trajectory** before work shifts to the separate `animus-mind` repository (v2.1+ Mind-class architecture).

---

## What's Ready vs. Experimental

| Component | Status | Notes |
|---|---|---|
| Core CLI (`animus-core` 2.3.0) | ✅ Stable | Memory, tasks, provider routing, local inference |
| Forge Workflows (`animus-forge` 1.9.0) | ✅ Stable | Multi-agent orchestration, eval calibration, YAML pipelines |
| Quorum Protocol (`convergentAI` 1.2.0) | ✅ Stable | Agent coordination via shared intent graph |
| Bootstrap Dashboard (`animus-bootstrap` 0.8.0) | ✅ Stable | FastAPI + HTMX + Jinja2, serves PWA, REST API |
| PWA Frontend | ✅ Wired | React 19 + Vite + TypeScript, calls `/api/*`, mobile-ready |
| Contracts Validation | ✅ New | 21 JSON schemas (Draft 2020-12) with runtime `jsonschema` + `referencing` |
| PostgreSQL Persistence | ✅ New | `DurableMemoryStore` (SQLAlchemy ORM), Alembic migrations, auto-fallback to Local |
| Local AI Stack | ✅ Stable | Ollama on RX 7900 XTX, 4-model tiered inference |
| Truth Baseline | ✅ Stable | 25/26 checks pass (1 expected version-alignment drift) |
| Secrets Audit | ✅ Clean | No credential exposure in code or history |
| Smoke Tests | ✅ Pass | 17/17 end-to-end checks green |
| 8 Dead Blockchain Packages | 🗑️ Archived | Moved to `packages/_archive/` (validator, prospector, faucet, content, bounty, mev, arbitrage, referral) |

---

## New Features

### PWA ↔ Bootstrap Backend Wiring
- **Static file serving**: Bootstrap mounts PWA `dist/` at `/pwa/` with `html=True`
- **API integration**: PWA calls `/api/conversations/messages` REST endpoint
- **CORS**: Configured permissively (`allow_origins=["*"]`) for dev/mobile access
- **Vite base path**: Set to `/pwa/` so assets reference `/pwa/assets/...`
- **Manifest scope**: Updated `scope`, `start_url`, and `share_target.action` to `/pwa/`
- **Removed hardcoded manifest link**: Vite-plugin-pwa now injects the correct path

### Contracts Runtime Validation
- **New package**: `animus-contracts` (0.1.0)
- **21 JSON schemas** shipped: `action`, `approval_receipt`, `assessment`, `claim`, `common`, `context_envelope`, `decision`, `entity`, `event`, `forecast`, `hypothesis`, `lesson`, `memory_candidate`, `observation`, `outcome`, `pattern`, `signal`, `source`, `action_receipt`, `trace`
- **FastAPI integration**: `ValidatedBody(schema_name)` dependency factory and `validate_contract(schema_name)` decorator
- **Cross-schema `$ref`**: Uses `referencing.Registry` with `referencing.jsonschema.DRAFT202012`
- **Graceful degradation**: Returns 503 if contracts package is not installed

### PostgreSQL Durable Persistence
- **New backend**: `DurableMemoryStore` in `animus-kernel`
- **Auto-selection**: `MemoryLayer(backend="auto")` resolves PostgreSQL → ChromaDB → Local JSON
- **SQLAlchemy ORM**: Supports `store`, `update`, `delete`, `retrieve`, `search`, `list_all`, `get_all_tags`
- **Alembic migrations**: `database/migrations/` reads `ANIMUS_DATABASE_URL` from environment
- **Setup script**: `scripts/setup_postgres.py` tests connectivity, creates DB if missing, runs `alembic upgrade head`
- **URL fix**: Corrected `postgres://` → `postgresql://` scheme for SQLAlchemy compatibility

### Config Forward-Compatibility
- Added `model_config = SettingsConfigDict(extra="ignore")` to `AnimusConfig`
- Fixes `extra_forbidden` pydantic error when config contains user-defined sections like `[providers]`

### Improved Error Messages
- Specific `httpx.HTTPStatusError` handling in conversations router:
  - **401**: Clear auth-failure message with fix instructions (API key missing)
  - **429**: Rate-limit detection with retry guidance
  - **Generic**: Fallback exception logging instead of silent "Sorry, something went wrong"

### Security Hardening
- Disabled OpenAPI docs exposure in production: `docs_url=None, redoc_url=None`
- Cleaned credential placeholder from `alembic.ini`
- Pinned GitHub Actions to SHA commits
- Added `.env` and credential patterns to `.gitignore`
- Added `.mypy_cache/`, `*.db`, and `gorgon-*.db` patterns to `.gitignore`

---

## Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| `extra_forbidden` on startup | Pydantic rejected unknown TOML sections | `extra="ignore"` in `AnimusConfig` |
| Contracts install failed | `force-include` couldn't find `*.schema.json` | Replaced with `artifacts = ["*.schema.json"]` |
| `referencing` API drift | `Resource.from_contents(..., default_specification=...)` deprecated | Used `Resource(contents=..., specification=DRAFT202012)` |
| PostgreSQL dialect error | URL used `postgres://` instead of `postgresql://` | Fixed in `scripts/setup_postgres.py` |
| Alembic `KeyError: 'url'` | `sqlalchemy.url` commented out in `alembic.ini` | Added `_get_url()` reading `ANIMUS_DATABASE_URL` |
| PWA files not found | `_PWA_DIR` had one extra `.parent` | Corrected path resolution |
| Runtime router generic failure | Missing API key → 401 → catch-all handler | Added specific HTTPStatusError handling |
| Stale app DI leak in tests | `importlib.reload("api.main")` created new app object | Documented pattern: import `app` fresh per test |

---

## Testing

- **Unit tests**: Bootstrap 2019 passed, Core 2798 passed
- **Truth baseline**: 25/26 PASS (1 version_alignment FAIL — expected drift between package versions)
- **End-to-end smoke tests**: 17/17 PASS
  - PWA build
  - Bootstrap server start
  - Static file serving
  - API health check
  - Conversation creation
  - Message sending
  - Contracts validation
  - PostgreSQL connectivity
  - Alembic migrations
  - Memory store CRUD
  - Auth middleware
  - CORS preflight
  - Forge workflow execution
  - Core CLI invocation
  - Local AI inference
  - Truth baseline run

---

## Documentation

- **README.md**: Updated with Linux-only scope, quick start (npm build + bootstrap serve), PostgreSQL setup, architecture diagram, "What's Ready vs Experimental" table
- **CHANGELOG**: This file
- **Migration guide**: `docs/migration/v2.3-to-mind.md` (describes port to Mind-class architecture)

---

## Known Limitations (Non-Goals for v2.3)

The following are **out of scope** for this Assistant-class release and are addressed in the Mind-class architecture (`animus-mind`):

- **No continuous event stream** — Query-response only; no autonomous sensors
- **No world model** — No unified world state engine or knowledge graph
- **No bitemporal state** — Cannot audit "what was true when?"
- **No policy decision point** — Auth is bearer token only; no capability grants
- **No adversarial test harness** — Tests confirm happy path; invariants aren't attacked
- **No evidence bundles** — Releases pass tests but don't generate machine-readable proof
- **No kill switches** — No independent emergency controls
- **No material dissent preservation** — Single-answer synthesis; contradictions not retained
- **No agent contracts** — Forge workflows lack runtime budget/schema enforcement
- **SQLite canonical** — PostgreSQL is optional; JSON files are fallback canonical store

---

## Migration Notice

**This codebase is frozen as the v2.3 Assistant Stable.** Active development continues in the `animus-mind` repository, which implements the v2.1 Mind-class architecture (8 technical planes, 22 canonical schemas, PostgreSQL durable authority, event ledger, adversarial harness, evidence bundles).

See `docs/migration/v2.3-to-mind.md` for the porting guide.

---

## Full Commit Range

`e102e54` — Pre-public hardening sprint (PWA, Contracts, PostgreSQL, error handling, CORS, config fixes)

For the complete history, see `git log --oneline` from this tag.
