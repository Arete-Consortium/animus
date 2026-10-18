# CLAUDE.md — Animus Monorepo

## Project Overview

Personal AI exocortex with multi-agent orchestration and coordination protocol.

- **Version**: 2.3.0
- **Python**: >=3.10 (Core), >=3.11 (Bootstrap), >=3.12 (Forge)
- **Layout**: Multi-package monorepo — `packages/core`, `packages/forge`, `packages/quorum`, `packages/bootstrap`, `packages/pwa`
- **Tests**: 14,712+ across 5 packages (Core 2109, Forge 9720, Quorum 926, Bootstrap 1841+, Contracts 116)
- **Coverage**: 97% per package
- **License**: MIT

## Non-Negotiables

Read these before every session. No exceptions.

1. **Never bypass budget enforcement.** All LLM calls from Forge must pass through `packages/forge/src/animus_forge/budget/manager.py`. The `BudgetManager` is wired into `WorkflowExecutor` — do not circumvent it with direct provider calls.
2. **Never modify identity files without approval gates.** Bootstrap's `IdentityProposalManager` (20% change threshold) is the only mutation path. Core's `CORE_VALUES.md` is immutable.
3. **Never delete memory or identity files.** Deprecate and archive instead. Memory is append-heavy by design.
4. **Audit log is sacred.** Forge actions emit to structured logs via `packages/forge/src/animus_forge/monitoring/`. This feeds the reflection loop and is the ground truth for spend tracking.
5. **Quorum IntentNodes require signed writes.** Use `convergent.intent` APIs — don't write intent state directly.
6. **No unregistered background threads.** If Forge spawns workers, they must be trackable and cleanly terminable.
7. **Self-improve targets YAML workflows by default.** Python code changes require the full sandbox + approval + rollback pipeline in `packages/forge/src/animus_forge/self_improve/orchestrator.py`. YAML evolution is the safe fast path.
8. **Constitutional principles (P1-P9) constrain all agent behavior.** See `docs/CONSTITUTIONAL_PRINCIPLES.md`. Forge reads these to bound its actions.

## Monorepo Structure

```
animus/
├── packages/
│   ├── core/                    # Animus Core — exocortex, identity, memory, CLI
│   │   ├── animus/              # Python package: import animus
│   │   ├── tests/               # 2109 tests, 97% coverage
│   │   └── pyproject.toml
│   ├── forge/                   # Animus Forge — multi-agent orchestration (was: Gorgon)
│   │   ├── src/animus_forge/    # Python package: import animus_forge
│   │   ├── tests/               # 9720 tests, 97% coverage
│   │   ├── skills/              # Skill definitions (YAML + docs)
│   │   ├── migrations/          # 14 SQL migrations
│   │   ├── workflows/           # YAML workflow definitions
│   │   └── pyproject.toml
│   ├── quorum/                  # Animus Quorum — coordination protocol (was: Convergent)
│   │   ├── python/convergent/   # Python package: import convergent
│   │   ├── src/                 # Rust PyO3 (optional)
│   │   ├── tests/               # 926 tests, 97% coverage
│   │   └── pyproject.toml
│   └── bootstrap/               # Animus Bootstrap — install daemon, wizard, dashboard + gateway + intelligence
│       ├── src/animus_bootstrap/ # Python package: import animus_bootstrap
│       ├── tests/               # 1841 tests, 97% coverage
│       └── pyproject.toml
├── docs/
│   └── whitepapers/             # Architecture whitepapers (all 3 layers)
├── .github/workflows/           # CI: lint + type-check + test-core + test-quorum + test-types + test-contracts + test-forge + test-bootstrap + security
└── pyproject.toml               # Workspace root (dev scripts only)
```

## Independent Installation

Each package can be installed and used separately:

```bash
# Sibling shared-types package — install FIRST so forge/core can resolve
# the ``animus-types`` dep from local source (not PyPI; not published).
pip install -e packages/types/

pip install -e packages/quorum/                # Just coordination protocol
pip install -e packages/types/ -e packages/forge/                # Forge (needs animus-types)
pip install -e packages/types/ -e packages/core/                 # Core (needs animus-types)
pip install -e "packages/bootstrap/[dev]"      # Just bootstrap (daemon + wizard + dashboard)
# Everything — order doesn't matter inside a single pip invocation;
# pip's resolver finds animus-types locally as long as packages/types/
# is one of the -e targets.
pip install -e packages/types/ -e "packages/quorum/[dev]" -e "packages/forge/[dev]" -e "packages/core/[dev]" -e "packages/bootstrap/[dev]"
```

## Testing

```bash
# Individual packages
cd packages/core && pytest tests/ -v
cd packages/forge && pytest tests/ -v  # MUST run from forge dir (skills/workflows use relative paths)
cd packages/quorum && PYTHONPATH=python pytest tests/ -v
cd packages/bootstrap && pytest tests/ -v

# From root (core + quorum work from root, forge needs working-directory)
pytest packages/core/tests/ -v
PYTHONPATH=packages/quorum/python pytest packages/quorum/tests/ -v
pytest packages/bootstrap/tests/ -v
```

## Linting

```bash
ruff check packages/ && ruff format --check packages/
```

Each package has its own ruff config in its pyproject.toml.

## Pre-commit Hooks

Install once after cloning:

```bash
pip install pre-commit
pre-commit install
```

Run manually across all files:

```bash
pre-commit run --all-files
```

## Type Checking (Mypy Ratchet)

Type checking is blocking in CI. Baseline counts are stored in `scripts/.mypy-baseline.json`.

```bash
# Check current counts against baseline
python scripts/mypy-ratchet.py core kernel forge bootstrap

# Re-baseline after intentional fixes
python scripts/mypy-ratchet.py --init
```

## Package Identity

| Package | PyPI Name | Import | Dependencies |
|---------|-----------|--------|--------------|
| Core | animus-core | `import animus` | ollama, pyyaml, pydantic, rich, prompt-toolkit, cryptography, animus-types |
| Forge | animus-forge | `import animus_forge` | openai, anthropic, convergentai, typer, rich |
| Quorum | convergentAI | `import convergent` | zero production deps |
| Bootstrap | animus-bootstrap | `import animus_bootstrap` | typer, rich, httpx, pydantic |

## Cross-Package Dependencies

- **Quorum** has zero deps — pure library
- **Forge** depends on Quorum (`convergentai ^1.1.0`)
- **Core** optionally depends on Forge for orchestration features
- **Bootstrap** is standalone — connects to Forge via HTTP (optional)

## Layer Overview

**Core** (`packages/core/animus/`) — User-facing exocortex. Identity, memory, tools, CLI (40+ commands), voice, integrations (Google, Todoist, filesystem, webhooks). Lightweight embedded workflow engine (forge/swarm submodules).

**Forge** (`packages/forge/src/animus_forge/`) — Production orchestration engine. Workflow executor with mixins (AI, MCP, queue, graph), provider abstraction (6 providers), persistent budget management, streaming execution logs, eval framework, MCP tool execution, consensus voting, API + CLI + TUI + dashboard.

**Quorum** (`packages/quorum/python/convergent/`) — Coordination protocol library. Intent graph, constraints, contracts, economics, versioned graph, triumvirate voting, stigmergy, flocking, signal bus, phi-weighted scoring, GorgonBridge integration, health dashboard, cycle detection, event log. Optional Rust PyO3 for performance.

**Bootstrap** (`packages/bootstrap/src/animus_bootstrap/`) — Install daemon, onboarding wizard, local dashboard, message gateway, intelligence layer, and persona system. Phase 1: one-command install, Rich-based setup wizard (8 steps), HTMX dashboard at localhost:7700, systemd/launchd service management, auto-updater. Phase 2: message gateway with 8 channel adapters (Telegram, Discord, Slack, Matrix, WhatsApp, Signal, Email, WebChat), cross-channel sessions, cognitive backends (Anthropic/Ollama/Forge), middleware (auth/ratelimit/logging). Phase 3: intelligence layer with memory integration (SQLite FTS5 plus Bootstrap-specific optional stubs, separate from Core), tool executor (8 built-in tools + MCP bridge + permission system), proactive engine (scheduler, quiet hours, 3 built-in checks), automation pipeline (triggers/conditions/actions with SQLite persistence), IntelligentRouter (memory-enriched + tool loop), intelligence dashboard (/tools, /automations, /activity). Phase 4: persona & voice layer with PersonaEngine (registry + channel routing), VoiceConfig (6 presets + time shifts), KnowledgeDomainRouter (9 domains), ContextAdapter (time/channel/mood), SQLite persona persistence, persona dashboard (/personas, /routing). Runtime wiring (AnimusRuntime orchestrator, lifespan, health endpoint). Native Anthropic tool_use (CognitiveResponse, ToolCall, multi-turn cognitive loop). Phase 5: self-improvement loop with self-heal proactive check (auto-detects tool failures/slow/errors every 6h), ImprovementSandbox (safe YAML config + identity changes with backup/rollback), impact measurement (baseline/post metrics, -100 to +100 score), 37 built-in tools, 6 proactive checks.

## Key Files

### Core
- `packages/core/animus/__main__.py` — CLI entry point (prompt-toolkit)
- `packages/core/animus/cognitive.py` — LLM interface (Ollama/Anthropic/OpenAI/Mock)
- `packages/core/animus/memory/` — Episodic/semantic/procedural memory through
  supported local JSON or configured durable SQL; the Chroma adapter is retained
  only for isolated migration verification
- `packages/core/animus/forge/engine.py` — Lightweight sequential orchestration
- `packages/core/animus/swarm/engine.py` — Lightweight parallel orchestration

### Forge
- `packages/forge/src/animus_forge/api.py` — HTTP API app
- `packages/forge/src/animus_forge/cli/main.py` — Typer CLI
- `packages/forge/src/animus_forge/workflow/executor_core.py` — Workflow executor
- `packages/forge/src/animus_forge/agents/supervisor.py` — SupervisorAgent

### Quorum
- `packages/quorum/python/convergent/intent.py` — Core Intent model
- `packages/quorum/python/convergent/triumvirate.py` — Voting engine
- `packages/quorum/python/convergent/gorgon_bridge.py` — Integration bridge

## Architecture Docs

| File | Purpose |
|------|---------|
| `docs/CONSTITUTIONAL_PRINCIPLES.md` | P1-P9 principles that constrain all agent behavior |
| `docs/CONSCIOUSNESS_QUORUM_BRIDGE.md` | Reflection loop -> Quorum intent graph integration |
| `docs/WORKFLOW_EVOLUTION_CONSTRAINTS.md` | YAML-only fast path + evolution notes pattern |
| `docs/ARCHITECTURE.md` | System architecture overview |
| `docs/SAFETY.md` | Security layer design |

## Common Commands

```bash
# Test individual packages
cd packages/core && pytest tests/ -v
cd packages/forge && pytest tests/ -v  # MUST run from forge dir (relative paths)
cd packages/quorum && PYTHONPATH=python pytest tests/ -v
cd packages/bootstrap && pytest tests/ -v

# Lint + format (always run BOTH)
ruff check packages/ && ruff format --check packages/

# Install everything for development (drift-proof: discovers ALL packages/*,
# installs them editable in one invocation so local-only deps like animus-types
# always resolve from source). Use this for any venv rebuild.
bash scripts/setup-venv.sh            # full rebuild
bash scripts/setup-venv.sh --dry-run  # list discovered packages, install nothing

# Manual equivalent (must include packages/types/ — it is NOT on PyPI):
pip install -e "packages/types/[dev]" -e "packages/quorum/[dev]" -e "packages/forge/[dev]" -e "packages/core/[dev]" -e "packages/bootstrap/[dev]"
```

## Coding Standards

- Type hints on all functions
- Dataclasses in Core, Pydantic in Forge, dataclasses in Quorum
- Ruff for linting/formatting (per-package configs in pyproject.toml)
- pytest for testing (97% coverage target per package)
- `lru_cache` pollution: use `get_settings.cache_clear()` in both setup AND teardown
- `sys.executable` for subprocess calls (never bare `python`)
- Forge `Provider.complete()` takes `CompletionRequest`, not raw messages
- Forge supervisor method is `process_message()`, not `process()`

## Anti-Patterns

- Do NOT bypass `BudgetManager` with direct provider calls
- Do NOT use bare `python` in subprocess — use `sys.executable`
- Do NOT modify `CORE_VALUES.md` — it is immutable
- Do NOT write intent state directly — use `convergent.intent` APIs
- Do NOT reset fields in `__post_init__` that are set before method entry

## Dependencies

### Core
ollama, pyyaml, pydantic, rich, prompt-toolkit, cryptography, animus-types

### Forge
openai, anthropic, convergentai, typer, rich, pydantic

### Quorum
Zero production dependencies (pure library)

### Bootstrap
typer, rich, httpx, pydantic

## Git Conventions

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Run `pytest` + `ruff check` before pushing
- CI: lint + test-core + test-quorum + test-forge + test-bootstrap + security

## Domain Context

Animus is a personal AI exocortex — a system for augmenting human cognition with persistent memory, multi-agent orchestration, and self-improvement capabilities. Key concepts:

- **Exocortex**: External cognitive system (memory + reasoning + tools)
- **Forge**: Multi-agent orchestration with budget-managed LLM calls
- **Quorum**: Coordination protocol for agent consensus (intent graph, triumvirate voting)
- **Bootstrap**: One-command install with daemon, dashboard, and message gateway
- **Constitutional Principles**: P1-P9 behavioral constraints on all agents
