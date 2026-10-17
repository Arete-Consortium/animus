# Ollama Agent Handoff — Animus

> **Archived deployment handoff. Do not execute it as a current runbook.** This
> February 2026 snapshot predates the Core Chroma retirement and other repository
> changes. Use the current operator documentation and the
> [Chroma retirement plan](chroma-retirement-plan.md) for any legacy memory data.

**Purpose:** Instructions and prompts for a local Ollama agent to deploy, harden, and self-improve the Animus exocortex.
**Last Updated:** 2026-02-20
**Version:** v2.0.0

---

## Phase Tracker

| Phase | Description | Status |
|-------|-------------|--------|
| 1. Validate | Venvs, imports, Ollama, deps | DONE |
| 2. Code Quality | Lint, CodeQL, empty-except, `__all__` | DONE |
| 3. Test Suite | 9,286 tests across 3 packages | DONE |
| 4. Deploy | Systemd services, health checks | DONE |
| 5. Harden | Exception narrowing, type hints, dep audit | DONE |
| 6. Self-Improve | Review loop, test generation, coverage push | DONE |

**Start at Phase 4.** Phases 1-3 were completed on 2026-02-20 by Claude Code.

---

## What You Are

You are an autonomous agent running via Ollama on this machine. Animus is a personal AI exocortex — a monorepo with three independently installable Python packages. Your job is to deploy it as a persistent local service, harden it for production, and then continuously improve code quality.

**You do NOT need to rebuild or restructure anything. The architecture is final.**

---

## Architecture

```
~/projects/animus/                    <- Monorepo root (v2.0.0)
|-- packages/core/                    <- Animus Core v1.0.0
|   |-- animus/                       <- import animus
|   |   |-- cognitive.py              <- LLM interface (Ollama/Anthropic/OpenAI/Mock)
|   |   |-- memory.py                 <- Local JSON or configured durable SQL memory
|   |   |-- proactive.py              <- Nudges, briefings, deadline awareness
|   |   |-- autonomous.py             <- Autonomous executor
|   |   |-- api.py                    <- Optional FastAPI server
|   |   |-- integrations/             <- Google, Todoist, filesystem, webhooks
|   |   |   `-- gorgon.py             <- HTTP client to Forge API
|   |   |-- forge/                    <- Lightweight sequential orchestration
|   |   |-- swarm/                    <- Lightweight parallel DAG orchestration
|   |   |-- protocols/                <- Abstract interfaces
|   |   `-- sync/                     <- Peer discovery + sync
|   |-- tests/                        <- 1,630 pass, 106 skip (optional deps)
|   `-- pyproject.toml
|
|-- packages/forge/                   <- Animus Forge v1.2.0 (was: Gorgon)
|   |-- src/animus_forge/             <- import animus_forge
|   |   |-- api.py                    <- FastAPI server (127.0.0.1:8000)
|   |   |-- cli/                      <- Typer CLI (60+ commands)
|   |   |-- workflow/                 <- YAML workflow executor
|   |   |-- agents/supervisor.py      <- Multi-agent delegation + consensus
|   |   |-- providers/                <- 6 LLM providers
|   |   |-- budget/                   <- Token/cost management (persistent SQLite)
|   |   |-- state/                    <- SQLite WAL + 14 migrations
|   |   |-- skills/                   <- Skill definitions (YAML)
|   |   |-- mcp/                      <- MCP tool execution
|   |   |-- dashboard/                <- Streamlit dashboard
|   |   `-- webhooks/                 <- Webhook delivery + circuit breaker
|   |-- tests/                        <- 6,731 pass
|   |-- skills/                       <- Skill definitions
|   |-- migrations/                   <- 14 SQL migrations
|   |-- workflows/                    <- YAML workflow definitions
|   `-- pyproject.toml
|
|-- packages/quorum/                  <- Animus Quorum v1.1.0 (was: Convergent)
|   |-- python/convergent/            <- import convergent (PyPI: convergentAI)
|   |   |-- intent.py                 <- Intent graph
|   |   |-- triumvirate.py            <- Voting engine
|   |   |-- stigmergy.py              <- Agent coordination signals
|   |   |-- gorgon_bridge.py          <- Integration bridge to Forge
|   |   `-- ...                       <- 36 modules total
|   |-- tests/                        <- 906 pass
|   `-- pyproject.toml
|
|-- .env                              <- Ollama config (gitignored)
|-- .github/workflows/                <- CI: lint + test + security + CodeQL
`-- docs/whitepapers/                 <- Architecture docs
```

**Dependency flow:** Quorum (zero deps) -> Forge (depends on Quorum via `convergentai` PyPI) -> Core (connects to Forge via HTTP API)

**Entry points:**
- `animus` -- Interactive CLI (prompt-toolkit)
- `animus-forge --help` -- Orchestration CLI (Typer, 60+ commands)
- `uvicorn animus_forge.api:app` -- Forge REST API

---

## Verified State (2026-02-20)

| Package | Tests | Coverage | Threshold | Status |
|---------|-------|----------|-----------|--------|
| Quorum  | 906   | 97%      | fail_under=97 | ALL PASSING |
| Core    | 1,648 | 96%      | fail_under=95 | ALL PASSING (106 skips = optional deps) |
| Forge   | 6,732 | 88%      | fail_under=85 | ALL PASSING |
| **Total** | **9,286** | | | |

**Infrastructure:**
- Virtual environments: all 3 created and verified (`packages/{core,forge,quorum}/.venv/`)
- Ollama models: `deepseek-coder-v2` (8.9GB), `codellama` (3.8GB), `llama3.1:8b` (4.9GB)
- `.env` created with Ollama defaults (gitignored)
- `~/.animus/{data,logs,memory}` directories exist
- CI: all green on GitHub (lint + test + security + CodeQL)
- CodeQL: 0 open alerts (24 fixed in code, 136 false positives dismissed)
- Lint: `ruff check packages/ && ruff format --check packages/` = clean

**NOT yet done:**
- No `BLOCKERS.md` exists yet (nothing blocked)

**Completed this session:**
- Forge API deployed as systemd service (Phase 4 DONE)
- `scripts/review.py` created (Phase 6.1 DONE)
- Native Anthropic tool_use in cognitive.py (Phase 3 DONE)
- `/workflow` command in chat.py (Phase 4 DONE)
- Exception narrowing in Core (Phase 5.1 DONE)
- Type hints added to Core (Phase 5.2 DONE)
- pip-audit clean, pip 26.0.1 (Phase 5.3 DONE)
- Coverage pushed: Core 96%, Forge 88% (Phase 6.2-6.4 DONE)

**Gotchas:**
- `pytest-timeout` is NOT installed in any venv -- use plain `pytest`
- Forge tests MUST run from `packages/forge/` directory (skills/workflows use relative paths)
- `pip list --outdated` may show false matches for local packages (e.g., `agent-audit` matching an unrelated PyPI package)
- `pandas` 2->3 upgrade is blocked by Streamlit compatibility

---

## Phase 4 -- Deploy as Local Services

### 4.1 -- Create the Forge systemd service

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/animus-forge.service << 'EOF'
[Unit]
Description=Animus Forge -- Orchestration API
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/projects/animus/packages/forge
Environment="PATH=%h/projects/animus/packages/forge/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=%h/projects/animus/.env
ExecStart=%h/projects/animus/packages/forge/.venv/bin/uvicorn animus_forge.api:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable animus-forge
systemctl --user start animus-forge
sleep 3
curl -s http://localhost:8000/health && echo " -- Forge API running"
```

### 4.2 -- Verify Core -> Forge connectivity

```bash
cd ~/projects/animus/packages/core && source .venv/bin/activate
python3 -c "
from animus.integrations.gorgon import GorgonClient
import asyncio
async def check():
    c = GorgonClient('http://localhost:8000')
    h = await c.check_health()
    print(f'Core -> Forge: {h}')
asyncio.run(check())
"
```

### 4.3 -- Verify workflows

```bash
cd ~/projects/animus/packages/forge && source .venv/bin/activate
animus-forge list
animus-forge validate workflows/code-review.yaml
```

### 4.4 -- Verify Ollama is the active LLM provider

```bash
cd ~/projects/animus/packages/core && source .venv/bin/activate
python3 -c "
from animus.cognitive import CognitiveLayer, ModelConfig
layer = CognitiveLayer(primary_config=ModelConfig.ollama('llama3.1:8b'))
import asyncio
result = asyncio.run(layer.think('What is 2+2? Reply with just the number.'))
print(f'Ollama response: {result}')
"
```

### 4.5 -- Enable lingering (survive logout)

```bash
# Allows user services to run even when not logged in
loginctl enable-linger arete
```

### 4.6 -- Deployment verification checklist

Run all of these. Every line must succeed:

```bash
systemctl --user is-active animus-forge            # "active"
curl -sf http://localhost:8000/health               # 200 OK
journalctl --user -u animus-forge --no-pager -n 5   # No errors in logs
```

---

## Phase 5 -- Production Hardening

### 5.1 -- Narrow exception types

> **PROMPT (use deepseek-coder-v2):**
> ```
> You are hardening Python code for production. Find `except Exception` blocks
> and narrow them to specific exception types. Read the try block to determine
> what exceptions can actually be raised.
>
> Common mappings:
> - File I/O: OSError, FileNotFoundError, PermissionError
> - JSON: json.JSONDecodeError
> - HTTP: httpx.HTTPError, requests.RequestException
> - Database: sqlite3.Error, sqlite3.OperationalError
> - Type conversion: ValueError, TypeError, KeyError
> - Import: ImportError, ModuleNotFoundError
>
> Do NOT narrow exceptions in test files -- those are intentionally broad.
> Do NOT change `except Exception` in top-level error handlers (API routes, CLI commands).
> ```

### 5.2 -- Add missing type hints

> **PROMPT (use deepseek-coder-v2):**
> ```
> Add type hints to all public functions (not starting with _) that are missing them.
> Use Python 3.10+ syntax: list[str] not List[str], str | None not Optional[str].
>
> Rules:
> - If a class has a method named `list`, `set`, or `dict`, add
>   `from __future__ import annotations` at the top of the file
> - Return types are required
> - Use `Any` sparingly -- prefer specific types
> - For callbacks, use `Callable[[arg_types], return_type]`
> ```

### 5.3 -- Dependency audit

```bash
cd ~/projects/animus/packages/core && source .venv/bin/activate
pip list --outdated --format=columns

cd ~/projects/animus/packages/forge && source .venv/bin/activate
pip list --outdated --format=columns
```

**Update ONE at a time. Test after each.**
```bash
pip install --upgrade <package>
pytest tests/ -x -q
```

**Do NOT update:**
- `pandas` -- major version (2->3) blocked by Streamlit
- `bcrypt` -- major version (4->5) needs testing
- Any package that requires Python version changes

### 5.4 -- Security scan

```bash
cd ~/projects/animus/packages/core && source .venv/bin/activate
pip-audit --skip-editable

cd ~/projects/animus/packages/forge && source .venv/bin/activate
pip-audit --skip-editable
```

---

## Phase 6 -- Self-Improvement Loop

Once deployed and healthy, cycle through improvements. **One change at a time. Test after each.**

### 6.1 -- Create the review script

Save this as `~/projects/animus/scripts/review.py`:

```python
#!/usr/bin/env python3
"""Review a single file using local Ollama model."""
import json
import os
import sys
import urllib.request


def review_file(filepath: str) -> str:
    with open(filepath) as f:
        code = f.read()

    data = json.dumps({
        "model": os.getenv("OLLAMA_MODEL", "deepseek-coder-v2"),
        "prompt": f"""Senior Python engineer code review.
Project: Animus -- personal AI exocortex.
Three layers: Core (identity/memory), Forge (orchestration), Quorum (coordination).

Review this file. For each issue found, provide:
1. Line number
2. Issue category (correctness/security/performance/typing/style)
3. Current code
4. Suggested fix
5. Why it matters

Focus on: correctness bugs, error handling gaps, missing type hints, performance issues.
Skip: style preferences, docstring formatting, import ordering.

File: {filepath}

```python
{code}
```""",
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["response"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python review.py <filepath>")
        sys.exit(1)
    print(review_file(sys.argv[1]))
```

Then run:
```bash
chmod +x ~/projects/animus/scripts/review.py
python3 ~/projects/animus/scripts/review.py packages/core/animus/cognitive.py
```

### 6.2 -- Priority review queue

Review these files first (highest impact, most complex logic):

```bash
# Core -- brain
python3 scripts/review.py packages/core/animus/cognitive.py
python3 scripts/review.py packages/core/animus/memory.py
python3 scripts/review.py packages/core/animus/proactive.py
python3 scripts/review.py packages/core/animus/autonomous.py

# Forge -- orchestration
python3 scripts/review.py packages/forge/src/animus_forge/workflow/executor_core.py
python3 scripts/review.py packages/forge/src/animus_forge/agents/supervisor.py
python3 scripts/review.py packages/forge/src/animus_forge/api.py
python3 scripts/review.py packages/forge/src/animus_forge/budget/persistent.py

# Quorum -- coordination
python3 scripts/review.py packages/quorum/python/convergent/intent.py
python3 scripts/review.py packages/quorum/python/convergent/triumvirate.py
```

### 6.3 -- Test generation

> **PROMPT (use deepseek-coder-v2):**
> ```
> Write pytest tests for this module. Requirements:
> - Test all public functions
> - Include happy path, edge cases, and error cases
> - Mock external dependencies (LLM calls, HTTP, filesystem)
> - Use pytest fixtures for setup/teardown
> - Use parametrize for similar test cases
> - No pytest-asyncio -- use asyncio.run() wrapper for async tests
> - Target 95%+ coverage for the module
>
> Project conventions:
> - Mocks use unittest.mock (patch, MagicMock)
> - Test files go in the package's tests/ directory
> - Name: test_<module_name>.py
> ```

### 6.4 -- Coverage push targets

Modules with the most room for improvement:

```bash
# Find modules under 90% coverage
cd ~/projects/animus/packages/forge && source .venv/bin/activate
pytest tests/ --cov=animus_forge --cov-report=term-missing -q 2>&1 | grep -E "^\S.*\s[0-9]{1,2}%"

cd ~/projects/animus/packages/core && source .venv/bin/activate
pytest tests/ --cov=animus --cov-report=term-missing -q 2>&1 | grep -E "^\S.*\s[0-9]{1,2}%"
```

### 6.5 -- Commit protocol

After EVERY improvement:

```bash
cd ~/projects/animus

# 1. Lint
ruff check packages/ --fix
ruff format packages/

# 2. Test the affected package
cd packages/<affected_package>
source .venv/bin/activate
pytest tests/ -x -q

# 3. Commit (specific files only, never `git add .`)
cd ~/projects/animus
git add <changed files>
git commit -m "improve(<package>): <what and why>"

# Do NOT push -- human reviews before push
```

### 6.6 -- Improvement cycle order

Repeat this loop:

1. Pick the next file from the priority queue (6.2)
2. Run `review.py` on it
3. Apply fixes (one at a time)
4. Lint
5. Test the affected package
6. Commit
7. Move to next file

When the priority queue is exhausted:
- Run coverage push (6.4) to find low-coverage modules
- Write tests for them (6.3)
- Commit each test file individually

---

## Ollama Prompts Library

### General reasoning (use llama3.1:8b)
```
You are an AI systems architect working on Animus, a personal AI exocortex.
The system has three layers:
- Core: Identity, memory (local JSON or configured durable SQL), proactive engine, CLI
- Forge: Multi-agent orchestration, workflow execution, budget management
- Quorum: Coordination protocol, intent graphs, voting, stigmergy

9,260 tests across 3 packages. All passing. Deployed locally.

Answer the following question about the system: <question>
```

### Code review (use deepseek-coder-v2)
```
Senior Python engineer review. Project: Animus AI exocortex (3 packages, 9267 tests, v2.0.0).
Review this code for: correctness, error handling, typing, performance, security.
List specific issues with line numbers and fixes. No style opinions.

<code>
```

### Test writing (use deepseek-coder-v2)
```
Write pytest unit tests for this Python module from the Animus project.
Requirements: mock all external calls, test edge cases, use fixtures.
No pytest-asyncio (use asyncio.run() wrapper). Target 95% coverage.

Module path: <path>
<code>
```

### Bug investigation (use deepseek-coder-v2)
```
A test is failing in the Animus project. Analyze the error and suggest a fix.
Show the exact code change needed. Do not change test expectations unless the
test itself is wrong.

Test file: <path>
Error output:
<error>
```

### Docstring generation (use llama3.1:8b)
```
Add Google-style docstrings to all public functions in this module.
Include: one-line summary, Args with types, Returns, Raises.
Do not modify any code logic.

<code>
```

### Exception narrowing (use deepseek-coder-v2)
```
Narrow broad exception handlers in this Python file.
Replace `except Exception` with specific types based on what the try block does.
Do NOT change exceptions in: test files, top-level API routes, CLI commands.
Show each change as: file:line, before, after, reason.

<code>
```

---

## What NOT to Do

- **Do NOT delete any files or directories**
- **Do NOT bulk-upgrade dependencies** -- one at a time, test after each
- **Do NOT restructure the monorepo** -- the package layout is final
- **Do NOT push to GitHub** -- stage commits locally, human pushes
- **Do NOT modify .env with real API keys** -- managed by human
- **Do NOT run `pip freeze > requirements.txt`** -- packages use pyproject.toml
- **Do NOT install new packages** without checking pyproject.toml first
- **Do NOT change public API signatures** -- existing code depends on them
- **Do NOT use `git add .` or `git add -A`** -- add specific files only

---

## Blockers -- When to Stop

Stop and write a report when you hit:

- **Credentials needed** -- API keys, SSH auth, cloud services
- **Test failures after 3 attempts** -- log it, move on
- **Architecture questions** -- "should this be in Core or Forge?" -> ask human
- **Breaking changes** -- anything that would change public API or CLI
- **Systemd issues** -- if the service won't start after 3 restarts

**Report format:**
```
BLOCKER: [type]
Package: core | forge | quorum
File: [path]
Problem: [exact error]
Tried: [what you attempted]
Need: [what the human should do]
```

Write blocker reports to `~/projects/animus/BLOCKERS.md` (append, don't overwrite).

---

## Quick Reference

```bash
# Services
systemctl --user start animus-forge     # Start Forge API
systemctl --user stop animus-forge      # Stop Forge API
systemctl --user status animus-forge    # Check status
systemctl --user restart animus-forge   # Restart after changes
journalctl --user -u animus-forge -f    # Tail logs

# CLI
cd ~/projects/animus/packages/core && source .venv/bin/activate && animus
cd ~/projects/animus/packages/forge && source .venv/bin/activate && animus-forge --help

# Tests
cd ~/projects/animus/packages/quorum && source .venv/bin/activate && pytest tests/ -q
cd ~/projects/animus/packages/core && source .venv/bin/activate && pytest tests/ -q
cd ~/projects/animus/packages/forge && source .venv/bin/activate && pytest tests/ -q

# Lint
cd ~/projects/animus && ruff check packages/ && ruff format --check packages/

# Ollama
ollama list                             # List models
ollama ps                               # Running models
curl -s http://localhost:11434/api/tags  # API check

# Review a file
python3 ~/projects/animus/scripts/review.py <filepath>
```

---

## Success Criteria

**Phase 4 (Deploy) -- done when:**
- [x] All 3 packages import cleanly
- [x] Ollama responds to prompts
- [x] 9,260 tests pass (906 + 1,630 + 6,731)
- [x] Lint clean
- [x] 0 CodeQL alerts
- [x] Forge API runs as systemd service (`curl localhost:8000/health`)
- [x] Core can reach Forge via HTTP
- [x] Service survives logout (`loginctl enable-linger`)

**Phase 5 (Harden) -- done when:**
- [ ] No broad `except Exception` without justification (outside API routes/CLI)
- [ ] All public functions have type hints
- [ ] `pip-audit --skip-editable` clean on all packages
- [ ] Dependencies at latest compatible versions

**Phase 6 (Self-Improve) -- done when:**
- [ ] All 10 priority files reviewed
- [ ] Coverage: Core >= 96%, Forge >= 88%, Quorum >= 98%
- [ ] `scripts/review.py` exists and works
- [ ] At least 5 improvement commits made
