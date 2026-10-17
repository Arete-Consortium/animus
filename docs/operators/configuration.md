# Configuration

> Config files, environment variables, and secrets management for Animus Core.

---

## Overview

Animus Core loads configuration from a **YAML** file with **environment variable overrides**. The config file is auto-created on first run if it doesn't exist.

| Property | Value |
|---|---|
| **File format** | YAML |
| **Default path** | `~/.animus/config.yaml` |
| **Override precedence** | Environment variables > Config file > Defaults |

---

## Config File Structure

The top-level config is `AnimusConfig`, which contains nested dataclass sections:

```yaml
data_dir: ~/.animus
log_level: INFO
log_to_file: true

model:
  provider: ollama
  name: llama3:8b
  ollama_url: http://localhost:11434
  anthropic_api_key: null
  openai_api_key: null
  openai_base_url: null

memory:
  backend: local
  collection_name: animus_memories

api:
  enabled: false
  host: 127.0.0.1
  port: 8420
  api_key: null

voice:
  input_enabled: false
  output_enabled: false
  whisper_model: base
  tts_engine: pyttsx3
  tts_rate: 150

integrations:
  google:
    enabled: false
    client_id: null
    client_secret: null
  todoist:
    enabled: false
    api_key: null
  filesystem:
    enabled: false
    indexed_paths: []
    exclude_patterns:
      - "*.pyc"
      - "__pycache__"
      - ".git"
      - "node_modules"
      - ".venv"
  webhooks:
    enabled: false
    port: 8421
    secret: null

learning:
  enabled: true
  auto_scan_enabled: true
  auto_scan_interval_hours: 24
  min_pattern_occurrences: 3
  min_pattern_confidence: 0.6
  lookback_days: 30
  max_pending_approvals: 50

proactive:
  enabled: true
  background_enabled: false
  background_interval_seconds: 300
  deadline_scan_interval_minutes: 60
  follow_up_scan_interval_minutes: 120

entities:
  enabled: true
  auto_extract: true
  auto_discover: false

citizen_zero:
  enabled: true
  citizen_dir: ""
  shared_dir: ""
  constitutional_corpus_dir: ""
  context_budget_tokens: 2000
  default_failure_mode: interactive

autonomous:
  enabled: false
  observe_policy: auto
  notify_policy: auto
  act_policy: approve
  execute_policy: deny

tools_security:
  allowed_paths:
    - "~"
  blocked_paths:
    - /etc/shadow
    - /etc/passwd
    - /etc/sudoers
    - ~/.ssh/id_*
    - ~/.gnupg
    - ~/.aws/credentials
    - ~/.config/gcloud
  max_file_size_kb: 1000
  write_roots: []
  command_enabled: true
  command_blocklist:
    - rm -rf /
    - rm -rf ~
    - dd if=
    - mkfs
    - ":(){:|:&};:"
    - chmod -R 777 /
    - curl.*|.*sh
    - wget.*|.*sh
  command_timeout_seconds: 30
```

---

## Reference Tables

### Core Settings

| Field | Default | Description |
|---|---|---|
| `data_dir` | `~/.animus` | Data storage directory |
| `log_level` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `log_to_file` | `true` | Write logs to `~/.animus/animus.log` |

### Model Settings (`model`)

| Field | Default | Description |
|---|---|---|
| `provider` | `ollama` | LLM backend: `ollama`, `anthropic`, or `openai` |
| `name` | `llama3:8b` | Model name (provider-specific) |
| `ollama_url` | `http://localhost:11434` | Ollama server URL |
| `anthropic_api_key` | `null` | Anthropic API key |
| `openai_api_key` | `null` | OpenAI API key |
| `openai_base_url` | `null` | OpenAI-compatible endpoint (LM Studio, vLLM, etc.) |

**Provider behavior:**
- `ollama` — Local inference. See [Working with Local Models](local-models.md).
- `anthropic` — Claude models with native `tool_use` support.
- `openai` — GPT models or any OpenAI-compatible endpoint.

**Dual-model routing:** If `provider` is `ollama` and `ANTHROPIC_API_KEY` is set in the environment, Animus automatically swaps: Claude becomes primary, Ollama becomes fallback. This gives you Claude's reasoning with local execution for cheap tasks.

### Memory Settings (`memory`)

| Field | Default | Description |
|---|---|---|
| `backend` | `local` | Storage backend: `local`/`json` or `durable` |
| `collection_name` | `animus_memories` | Legacy collection name retained for migration inventory |

**Backends:**
- `local` / `json` — Simple file-based storage
- `durable` — SQL-backed storage after its deployment setup is complete

Legacy `chroma` values fail closed. Complete the Chroma retirement plan before
changing an existing deployment's backend setting.

### API Server Settings (`api`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Start API server automatically on launch |
| `host` | `127.0.0.1` | Bind address |
| `port` | `8420` | Listen port |
| `api_key` | `null` | Optional bearer token for authentication |

### Voice Settings (`voice`)

| Field | Default | Description |
|---|---|---|
| `input_enabled` | `false` | Enable microphone listening |
| `output_enabled` | `false` | Enable text-to-speech for responses |
| `whisper_model` | `base` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `tts_engine` | `pyttsx3` | TTS backend: `pyttsx3` or `edge-tts` |
| `tts_rate` | `150` | Speech rate (words per minute) |

**Dependencies:** Install with `pip install 'animus[voice]'`

### Integration Settings (`integrations`)

All integrations default to `enabled: false`.

| Section | Key Fields | Description |
|---|---|---|
| `google` | `client_id`, `client_secret` | Google Calendar + Gmail OAuth |
| `todoist` | `api_key` | Todoist task sync |
| `filesystem` | `indexed_paths`, `exclude_patterns` | Local file indexing |
| `webhooks` | `port`, `secret` | Webhook receiver |

### Learning Settings (`learning`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable self-learning system |
| `auto_scan_enabled` | `true` | Auto-detect patterns in background |
| `auto_scan_interval_hours` | `24` | Hours between scans |
| `min_pattern_occurrences` | `3` | Min occurrences to register a pattern |
| `min_pattern_confidence` | `0.6` | Confidence threshold (0.0–1.0) |
| `lookback_days` | `30` | How far back to scan |
| `max_pending_approvals` | `50` | Queue limit for pending learnings |

### Proactive Settings (`proactive`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable proactive intelligence |
| `background_enabled` | `false` | Run background scans |
| `background_interval_seconds` | `300` | Seconds between background scans |
| `deadline_scan_interval_minutes` | `60` | Minutes between deadline checks |
| `follow_up_scan_interval_minutes` | `120` | Minutes between follow-up checks |

### Entity Settings (`entities`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable entity memory |
| `auto_extract` | `true` | Extract entities from conversations |
| `auto_discover` | `false` | Discover new entities via heuristic NER |

### Citizen Zero Settings (`citizen_zero`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable Citizen Zero identity overlay |
| `citizen_dir` | `""` | Path to citizen-zero data (auto-discovered if empty) |
| `shared_dir` | `""` | Path to shared directory (auto-discovered) |
| `constitutional_corpus_dir` | `""` | Path to corpus (auto-discovered) |
| `context_budget_tokens` | `2000` | Max tokens for identity context injection |
| `default_failure_mode` | `interactive` | `strict`, `interactive`, or `degraded` |

**Auto-discovery paths:** `~/projects/notes/citizen-zero`, `~/notes/citizen-zero`, `~/citizen-zero`

### Autonomous Action Settings (`autonomous`)

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Master switch (off by default for safety) |
| `observe_policy` | `auto` | Handle observation-level actions |
| `notify_policy` | `auto` | Handle notification-level actions |
| `act_policy` | `approve` | Handle act-level actions |
| `execute_policy` | `deny` | Handle execute-level actions |

**Policy values:** `auto` (execute without asking), `approve` (queue for approval), `deny` (never execute)

### Tool Security Settings (`tools_security`)

| Field | Default | Description |
|---|---|---|
| `allowed_paths` | `["~"]` | Paths tool file operations are allowed to access |
| `blocked_paths` | `[...]` | Glob patterns for forbidden paths |
| `max_file_size_kb` | `1000` | Max file size for read/write (1 MB) |
| `write_roots` | `[]` | Sandbox directory for writes (empty = no restriction) |
| `command_enabled` | `true` | Allow `run_command` tool |
| `command_blocklist` | `[...]` | Dangerous commands to block |
| `command_timeout_seconds` | `30` | Max command execution time |

---

## Environment Variables

Every config field can be overridden via environment variables. The naming convention is:

- Top-level fields: `ANIMUS_` + uppercase field name
- Nested fields: `ANIMUS_` + section + `_` + field name

| Variable | Overrides |
|---|---|
| `ANIMUS_DATA_DIR` | `data_dir` |
| `ANIMUS_LOG_LEVEL` | `log_level` |
| `ANIMUS_LOG_TO_FILE` | `log_to_file` |
| `ANIMUS_MODEL_PROVIDER` | `model.provider` |
| `ANIMUS_MODEL_NAME` | `model.name` |
| `ANIMUS_OLLAMA_URL` | `model.ollama_url` |
| `ANTHROPIC_API_KEY` | `model.anthropic_api_key` |
| `OPENAI_API_KEY` | `model.openai_api_key` |
| `OPENAI_BASE_URL` | `model.openai_base_url` |
| `ANIMUS_MEMORY_BACKEND` | `memory.backend` |
| `ANIMUS_API_ENABLED` | `api.enabled` |
| `ANIMUS_API_HOST` | `api.host` |
| `ANIMUS_API_PORT` | `api.port` |
| `ANIMUS_API_KEY` | `api.api_key` |
| `ANIMUS_VOICE_INPUT` | `voice.input_enabled` |
| `ANIMUS_VOICE_OUTPUT` | `voice.output_enabled` |
| `ANIMUS_WHISPER_MODEL` | `voice.whisper_model` |
| `ANIMUS_TTS_ENGINE` | `voice.tts_engine` |
| `ANIMUS_TTS_RATE` | `voice.tts_rate` |
| `ANIMUS_LEARNING_ENABLED` | `learning.enabled` |
| `ANIMUS_LEARNING_AUTO_SCAN` | `learning.auto_scan_enabled` |
| `ANIMUS_PROACTIVE_ENABLED` | `proactive.enabled` |
| `ANIMUS_PROACTIVE_BACKGROUND` | `proactive.background_enabled` |
| `ANIMUS_ENTITIES_ENABLED` | `entities.enabled` |
| `ANIMUS_ENTITIES_AUTO_EXTRACT` | `entities.auto_extract` |
| `ANIMUS_ENTITIES_AUTO_DISCOVER` | `entities.auto_discover` |
| `ANIMUS_CITIZEN_ZERO_ENABLED` | `citizen_zero.enabled` |
| `ANIMUS_CZ_CONSTITUTIONAL_DIR` | `citizen_zero.constitutional_corpus_dir` |
| `ANIMUS_CZ_CONTEXT_BUDGET` | `citizen_zero.context_budget_tokens` |
| `ANIMUS_CZ_FAILURE_MODE` | `citizen_zero.default_failure_mode` |
| `ANIMUS_AUTONOMOUS_ENABLED` | `autonomous.enabled` |
| `ANIMUS_AUTONOMOUS_OBSERVE_POLICY` | `autonomous.observe_policy` |
| `ANIMUS_AUTONOMOUS_NOTIFY_POLICY` | `autonomous.notify_policy` |
| `ANIMUS_AUTONOMOUS_ACT_POLICY` | `autonomous.act_policy` |
| `ANIMUS_AUTONOMOUS_EXECUTE_POLICY` | `autonomous.execute_policy` |
| `GOOGLE_INTEGRATION_ENABLED` | `integrations.google.enabled` |
| `GOOGLE_CLIENT_ID` | `integrations.google.client_id` |
| `GOOGLE_CLIENT_SECRET` | `integrations.google.client_secret` |
| `TODOIST_ENABLED` | `integrations.todoist.enabled` |
| `TODOIST_API_KEY` | `integrations.todoist.api_key` |
| `FILESYSTEM_INTEGRATION_ENABLED` | `integrations.filesystem.enabled` |
| `WEBHOOK_ENABLED` | `integrations.webhooks.enabled` |
| `WEBHOOK_PORT` | `integrations.webhooks.port` |
| `WEBHOOK_SECRET` | `integrations.webhooks.secret` |

---

## Secrets Management

**Never store API keys in the config file in shared environments.**

Recommended approach:

1. **Environment variables** (preferred for local development)
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   export OPENAI_API_KEY="sk-..."
   ```

2. **Secrets file** (optional, loaded by some integrations)
   ```bash
   # ~/.animus/secrets.env
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   ```

3. **Config file** (acceptable for non-sensitive values only)
   ```yaml
   model:
     provider: ollama  # no key needed
   ```

**Pre-commit check:** Run `grep -rn 'sk-\|ghp_\|sk-ant-' --include='*.md' .` before committing docs to ensure no keys are leaked.

---

## Editing Config

### Via REPL

Config changes take effect on next startup. Edit `~/.animus/config.yaml` directly:

```bash
# Edit the file
nano ~/.animus/config.yaml

# Restart Animus
animus
```

### Via Environment

For one-off changes without editing files:

```bash
ANIMUS_MODEL_PROVIDER=anthropic ANIMUS_MODEL_NAME=claude-sonnet-4 animus
```

---

## See Also

- [Working with Local Models](local-models.md) — Ollama-specific configuration
- [CLI Commands Reference](../reference/cli-commands.md) — Commands that read config values
- [Troubleshooting](troubleshooting.md) — Common config issues
