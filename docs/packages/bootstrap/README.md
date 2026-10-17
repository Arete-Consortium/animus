# Animus Bootstrap

**Your personal AI — sovereign, persistent, and self-improving.**

```bash
pip install animus-bootstrap && animus-bootstrap install
```

That single command installs dependencies, runs the onboarding wizard, registers a system service, and opens the dashboard. First-run to working system in under 5 minutes.

<!-- screenshot -->

## Architecture

```
+-----------------------------------------------------+
|  animus-bootstrap install (daemon)                   |
|  One-command bootstrap. Installs deps, registers     |
|  system service, manages config, checks updates.     |
+-----------------------------------------------------+
|  animus-bootstrap setup (onboarding wizard)          |
|  Interactive first-run. API keys, identity,          |
|  Forge connection, device/memory config.             |
+-----------------------------------------------------+
|  animus-bootstrap dashboard (local web UI)           |
|  Status, health, config management, identity         |
|  editor, proposal approval gate. localhost:7700      |
+-----------------------------------------------------+
|  animus-bootstrap reflect (self-improvement loop)    |
|  Daily summarization -> LEARNED.md. Proposes         |
|  identity changes. Waits for your approval.          |
+-----------------------------------------------------+
```

## Quickstart

1. **Install:** `pip install animus-bootstrap`
2. **Run:** `animus-bootstrap install`
3. **Wizard completes:** API keys, identity, memory backend
4. **Dashboard opens:** `http://localhost:7700`
5. **Done.** Animus is running as a system service.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `animus-bootstrap install` | Full install: deps, service, wizard, dashboard |
| `animus-bootstrap setup` | Re-run the onboarding wizard |
| `animus-bootstrap setup --reset-values` | Re-run sovereignty step + regenerate identity files |
| `animus-bootstrap start` | Start the system service |
| `animus-bootstrap stop` | Stop the system service |
| `animus-bootstrap restart` | Restart the system service |
| `animus-bootstrap status` | Show system status (daemon, Ollama, memory, proposals) |
| `animus-bootstrap update` | Check for and apply updates |
| `animus-bootstrap dashboard` | Open dashboard at localhost:7700 |
| `animus-bootstrap reflect` | Trigger a reflection cycle manually |
| `animus-bootstrap config get <key>` | Print a config value |
| `animus-bootstrap config set <key> <value>` | Update a config value |

---

## Configuration

Config lives at `~/.config/animus/config.toml` (chmod 600).

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `animus` | `version` | `0.1.0` | Package version |
| `animus` | `first_run` | `true` | Triggers wizard on install |
| `animus` | `data_dir` | `~/.local/share/animus` | Data storage directory |
| `api` | `anthropic_key` | `""` | Anthropic API key (required) |
| `api` | `openai_key` | `""` | OpenAI API key (optional) |
| `forge` | `enabled` | `false` | Connect to Animus Forge |
| `forge` | `host` | `localhost` | Forge API host |
| `forge` | `port` | `8000` | Forge API port |
| `memory` | `backend` | `sqlite` | Bootstrap backend selector: sqlite / chroma / weaviate; separate from Core backend values |
| `memory` | `path` | `~/.local/share/animus/memory.db` | Memory database path |
| `memory` | `max_context_tokens` | `100000` | Max context window |
| `identity` | `name` | `""` | What Animus calls you |
| `identity` | `timezone` | `""` | Your timezone |
| `services` | `port` | `7700` | Dashboard port |
| `services` | `log_level` | `info` | Logging level |
| `services` | `autostart` | `true` | Start on boot |

---

## Platform Support

| Platform | Status | Service Manager |
|----------|--------|----------------|
| Linux | Supported | systemd (user service) |
| macOS | Supported | launchd |
| Windows | Stub | Planned |

---

## Identity Files

Animus stores your personality and preferences in six markdown files at
`~/.config/animus/identity/`:

| File | Purpose | Who Writes |
|------|---------|------------|
| `CORE_VALUES.md` | Immutable foundation — sovereignty, honesty, loyalty, excellence | You (wizard) |
| `IDENTITY.md` | Who you are — name, role, background | You + Animus |
| `CONTEXT.md` | Current projects, priorities, what's top of mind | You + Animus |
| `PREFERENCES.md` | Tone, format, response style | You + Animus |
| `LEARNED.md` | What Animus has learned about you | Animus (reflection loop) |
| `GOALS.md` | Short and long term goals | You |

### Why CORE_VALUES.md is Locked

`CORE_VALUES.md` is the drift prevention anchor. Animus **cannot** modify this
file — not through the write tool, not through proposals, not through reflection.
It can only be edited manually or via `animus-bootstrap setup --reset-values`.

This ensures Animus's core behavior never silently shifts. If something feels
off, reset your values and everything downstream recalibrates.

---

## Self-Improvement

Animus improves through four mechanisms:

### Reflection Loop
Every 24 hours (configurable), Animus reviews recent interactions, identifies
patterns and preferences, and appends new learnings to `LEARNED.md`.

### Write Tool
During conversation, Animus can update identity files when it observes clear
preferences. Small changes (< 20% of file size) are written directly.

### Proposal System
Changes exceeding 20% of a file go through the approval gate. Each proposal
shows a diff, explains the reasoning, and waits for you to approve or reject
in the dashboard.

### Feedback Signal
Thumbs up/down on interactions in the memory browser feed into the reflection
loop, reinforcing what works and flagging what doesn't.

---

## Philosophy

### Sovereignty
Your data stays on your machine. No telemetry by default. No cloud sync.
Single-user by design. Works fully offline after install.

### Persistence
Bootstrap persists interactions through its configured memory backend. Its
backend contract is separate from Animus Core, where Chroma is retired from the
supported runtime.
Identity files accumulate context over time. Nothing is forgotten
unless you delete it.

### Loyalty
Animus serves your long-term interests, not your momentary preferences.
It will push back when warranted. Core values cannot be overridden.

### Self-Improvement
Animus reflects on interactions, proposes changes to its own behavior,
and waits for your approval. The human stays in the loop.

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **1a — Talk** | Local LLM, identity, memory, dashboard | Complete |
| **1b — Learn** | Reflection loop, proposals, feedback | Complete |
| **2 — Act** | Forge integration (orchestration engine) | Planned |
| **3 — Scale** | Quorum coordination (multi-agent) | Planned |

Forge appears as a status card in the dashboard now. Full integration in Phase 2.

---

## Relationship to Animus Ecosystem

- **Animus Core** — The exocortex engine (identity, memory, CLI)
- **Animus Forge** — Multi-agent orchestration engine (connects at wizard Step 4)
- **Animus Quorum** — Coordination protocol (coming in Phase 3)
- **Animus Bootstrap** — This package. The install/setup/dashboard layer.

---

## Development

```bash
git clone git@github.com:your-org/Animus.git
cd Animus/packages/bootstrap
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/ && ruff format --check src/ tests/
```

1403 tests, 94% coverage, Python 3.11+.

---

## Status

**Alpha** — Not ready for production use. API keys are file-permission protected but the system is under active development.

## License

MIT - 2026, your-org
