"""
Animus Configuration Management

Loads configuration from YAML file with environment variable overrides.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def default_data_dir() -> Path:
    """Return the default data directory."""
    return Path.home() / ".animus"


@dataclass
class ModelConfig:
    """Configuration for the cognitive model.

    OLLAMA-FIRST DEFAULT:
      - Ollama is the primary provider. No API keys required.
      - Cloud providers are OPT-IN via ANIMUS_CLOUD_PROVIDER env var.

    Supported providers:
      - "ollama"    — local models via Ollama (default, zero cost)
      - "anthropic" — Claude models via Anthropic API (opt-in)
      - "openai"    — OpenAI models, or any OpenAI-compatible endpoint
                      (LM Studio, vLLM, Together, Groq, etc.) via openai_base_url
    """

    provider: str = "ollama"
    name: str = "llama3:8b"
    ollama_url: str = "http://localhost:11434"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None  # For OpenAI-compatible endpoints

    def __post_init__(self):
        # Allow environment overrides
        self.provider = os.environ.get("ANIMUS_MODEL_PROVIDER", self.provider)
        self.name = os.environ.get("ANIMUS_MODEL_NAME", self.name)
        self.ollama_url = os.environ.get("ANIMUS_OLLAMA_URL", self.ollama_url)
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", self.anthropic_api_key)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", self.openai_api_key)
        self.openai_base_url = os.environ.get("OPENAI_BASE_URL", self.openai_base_url)


@dataclass
class MemoryConfig:
    """Configuration for the memory system."""

    backend: str = "local"  # "local"/"json" or "durable"
    collection_name: str = "animus_memories"

    def __post_init__(self):
        self.backend = os.environ.get("ANIMUS_MEMORY_BACKEND", self.backend)


@dataclass
class ObjectStoreConfig:
    """Configuration for the durable object store (PostgreSQL backend).

    When ``database_url`` is set, the :class:`DurableObjectStore` is available
    for bitemporal object persistence with ledger and outbox.
    """

    backend: str = "sqlite"  # "sqlite" or "postgres"
    database_url: str | None = None

    def __post_init__(self):
        self.backend = os.environ.get("ANIMUS_OBJECT_STORE_BACKEND", self.backend)
        self.database_url = os.environ.get("ANIMUS_DATABASE_URL", self.database_url)


@dataclass
class APIConfig:
    """Configuration for the HTTP API server."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8420
    api_key: str | None = None

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_API_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        self.host = os.environ.get("ANIMUS_API_HOST", self.host)
        if env_port := os.environ.get("ANIMUS_API_PORT"):
            self.port = int(env_port)
        self.api_key = os.environ.get("ANIMUS_API_KEY", self.api_key)


@dataclass
class VoiceConfig:
    """Configuration for voice input/output."""

    input_enabled: bool = False
    output_enabled: bool = False
    whisper_model: str = "base"  # tiny, base, small, medium, large
    tts_engine: str = "pyttsx3"  # pyttsx3 or edge-tts
    tts_rate: int = 150

    def __post_init__(self):
        if env_input := os.environ.get("ANIMUS_VOICE_INPUT"):
            self.input_enabled = env_input.lower() in ("true", "1", "yes")
        if env_output := os.environ.get("ANIMUS_VOICE_OUTPUT"):
            self.output_enabled = env_output.lower() in ("true", "1", "yes")
        self.whisper_model = os.environ.get("ANIMUS_WHISPER_MODEL", self.whisper_model)
        self.tts_engine = os.environ.get("ANIMUS_TTS_ENGINE", self.tts_engine)
        if env_rate := os.environ.get("ANIMUS_TTS_RATE"):
            self.tts_rate = int(env_rate)


@dataclass
class GoogleIntegrationConfig:
    """Configuration for Google integrations (Calendar, Gmail)."""

    enabled: bool = False
    client_id: str | None = None
    client_secret: str | None = None

    def __post_init__(self):
        if env_enabled := os.environ.get("GOOGLE_INTEGRATION_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", self.client_id)
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", self.client_secret)


@dataclass
class TodoistConfig:
    """Configuration for Todoist integration."""

    enabled: bool = False
    api_key: str | None = None

    def __post_init__(self):
        if env_enabled := os.environ.get("TODOIST_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        self.api_key = os.environ.get("TODOIST_API_KEY", self.api_key)


@dataclass
class FilesystemConfig:
    """Configuration for filesystem integration."""

    enabled: bool = False
    indexed_paths: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["*.pyc", "__pycache__", ".git", "node_modules", ".venv"]
    )

    def __post_init__(self):
        if env_enabled := os.environ.get("FILESYSTEM_INTEGRATION_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")


@dataclass
class WebhookConfig:
    """Configuration for webhook receiver."""

    enabled: bool = False
    port: int = 8421
    secret: str | None = None

    def __post_init__(self):
        if env_enabled := os.environ.get("WEBHOOK_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_port := os.environ.get("WEBHOOK_PORT"):
            self.port = int(env_port)
        self.secret = os.environ.get("WEBHOOK_SECRET", self.secret)


@dataclass
class IntegrationConfig:
    """Configuration for all external integrations."""

    google: GoogleIntegrationConfig = field(default_factory=GoogleIntegrationConfig)
    todoist: TodoistConfig = field(default_factory=TodoistConfig)
    filesystem: FilesystemConfig = field(default_factory=FilesystemConfig)
    webhooks: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass
class ToolsSecurityConfig:
    """Security configuration for tool execution."""

    # File system access restrictions
    allowed_paths: list[str] = field(default_factory=lambda: [str(Path.home())])
    blocked_paths: list[str] = field(
        default_factory=lambda: [
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers",
            "~/.ssh/id_*",
            "~/.gnupg",
            "~/.aws/credentials",
            "~/.config/gcloud",
        ]
    )
    max_file_size_kb: int = 1000  # 1MB default

    # Write sandbox: when set, write_file/edit_file only work within these dirs.
    # Empty list = no restriction (writes allowed anywhere in allowed_paths).
    write_roots: list[str] = field(default_factory=list)

    # Command execution restrictions
    command_enabled: bool = True
    command_blocklist: list[str] = field(
        default_factory=lambda: [
            "rm -rf /",
            "rm -rf ~",
            "dd if=",
            "mkfs",
            ":(){:|:&};:",  # Fork bomb
            "chmod -R 777 /",
            "curl.*|.*sh",
            "wget.*|.*sh",
        ]
    )
    command_timeout_seconds: int = 30


@dataclass
class LearningConfig:
    """Configuration for the self-learning system."""

    enabled: bool = True
    auto_scan_enabled: bool = True
    auto_scan_interval_hours: int = 24
    min_pattern_occurrences: int = 3
    min_pattern_confidence: float = 0.6
    lookback_days: int = 30
    max_pending_approvals: int = 50

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_LEARNING_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_auto_scan := os.environ.get("ANIMUS_LEARNING_AUTO_SCAN"):
            self.auto_scan_enabled = env_auto_scan.lower() in ("true", "1", "yes")


@dataclass
class ProactiveConfig:
    """Configuration for the proactive intelligence system."""

    enabled: bool = True
    background_enabled: bool = False
    background_interval_seconds: int = 300
    deadline_scan_interval_minutes: int = 60
    follow_up_scan_interval_minutes: int = 120

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_PROACTIVE_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_bg := os.environ.get("ANIMUS_PROACTIVE_BACKGROUND"):
            self.background_enabled = env_bg.lower() in ("true", "1", "yes")


@dataclass
class EntityConfig:
    """Configuration for the entity/relationship memory system."""

    enabled: bool = True
    auto_extract: bool = True  # Auto-extract entities from conversations
    auto_discover: bool = False  # Auto-discover new entities via heuristic NER

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_ENTITIES_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_extract := os.environ.get("ANIMUS_ENTITIES_AUTO_EXTRACT"):
            self.auto_extract = env_extract.lower() in ("true", "1", "yes")
        if env_discover := os.environ.get("ANIMUS_ENTITIES_AUTO_DISCOVER"):
            self.auto_discover = env_discover.lower() in ("true", "1", "yes")


@dataclass
class CitizenZeroConfig:
    """Configuration for Citizen Zero overlay."""

    enabled: bool = True
    citizen_dir: str = ""  # auto-discovered if empty
    shared_dir: str = ""  # auto-discovered if empty
    constitutional_corpus_dir: str = ""  # auto-discovered if empty
    context_budget_tokens: int = 2000
    default_failure_mode: str = "interactive"  # "strict" | "interactive" | "degraded"

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_CITIZEN_ZERO_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")

        if not self.citizen_dir:
            for candidate in [
                Path.home() / "projects" / "notes" / "citizen-zero",
                Path.home() / "notes" / "citizen-zero",
                Path.home() / "citizen-zero",
            ]:
                if candidate.exists():
                    self.citizen_dir = str(candidate / "v0.1-animus")
                    self.shared_dir = str(candidate / "shared")
                    self.constitutional_corpus_dir = str(candidate / "corpus")
                    break

        if env_corpus := os.environ.get("ANIMUS_CZ_CONSTITUTIONAL_DIR"):
            self.constitutional_corpus_dir = env_corpus

        if env_budget := os.environ.get("ANIMUS_CZ_CONTEXT_BUDGET"):
            try:
                self.context_budget_tokens = int(env_budget)
            except ValueError:
                pass

        if env_mode := os.environ.get("ANIMUS_CZ_FAILURE_MODE"):
            if env_mode in ("strict", "interactive", "degraded"):
                self.default_failure_mode = env_mode


@dataclass
class CitizensConfig:
    """Configuration for the Mind Foundation citizens (Architect, etc.)."""

    enabled: bool = True
    codebase_path: str = ""
    conversation_log_dir: str = ""
    evidence_dir: str = ""
    forge_host: str = "localhost"
    forge_port: int = 7700
    auto_store_proposals: bool = True  # Store proposals in memory automatically
    session_steward_enabled: bool = False  # Retrospective session telemetry auditor

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_CITIZENS_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_path := os.environ.get("ANIMUS_CITIZENS_CODEBASE_PATH"):
            self.codebase_path = env_path
        if env_logs := os.environ.get("ANIMUS_CITIZENS_CONVERSATION_LOG_DIR"):
            self.conversation_log_dir = env_logs
        if env_evidence := os.environ.get("ANIMUS_CITIZENS_EVIDENCE_DIR"):
            self.evidence_dir = env_evidence
        if env_host := os.environ.get("ANIMUS_CITIZENS_FORGE_HOST"):
            self.forge_host = env_host
        if env_port := os.environ.get("ANIMUS_CITIZENS_FORGE_PORT"):
            try:
                self.forge_port = int(env_port)
            except ValueError:
                pass
        if env_steward := os.environ.get("ANIMUS_SESSION_STEWARD_ENABLED"):
            self.session_steward_enabled = env_steward.lower() in ("true", "1", "yes")


@dataclass
class SessionConfig:
    """Configuration for session lifecycle management."""

    session_timer_minutes: int = 30
    wrapup_threshold: float = 0.96
    auto_restart: bool = True

    def __post_init__(self):
        if env_timer := os.environ.get("ANIMUS_SESSION_TIMER_MINUTES"):
            try:
                self.session_timer_minutes = int(env_timer)
            except ValueError:
                pass
        if env_threshold := os.environ.get("ANIMUS_WRAPUP_THRESHOLD"):
            try:
                self.wrapup_threshold = float(env_threshold)
            except ValueError:
                pass
        if env_restart := os.environ.get("ANIMUS_SESSION_AUTO_RESTART"):
            self.auto_restart = env_restart.lower() in ("true", "1", "yes")


@dataclass
class AutonomousConfig:
    """Configuration for the autonomous action system.

    Controls whether Animus can take independent actions and at what
    risk levels. Policies map action levels to handling strategies:
      - "auto"    — execute without asking
      - "approve" — queue for user approval
      - "deny"    — never execute autonomously

    Default is conservative: only observe/notify are auto, act requires
    approval, execute is denied.
    """

    enabled: bool = False  # Master switch — off by default
    observe_policy: str = "auto"
    notify_policy: str = "auto"
    act_policy: str = "approve"
    execute_policy: str = "deny"

    def __post_init__(self):
        if env_enabled := os.environ.get("ANIMUS_AUTONOMOUS_ENABLED"):
            self.enabled = env_enabled.lower() in ("true", "1", "yes")
        if env_obs := os.environ.get("ANIMUS_AUTONOMOUS_OBSERVE_POLICY"):
            self.observe_policy = env_obs
        if env_not := os.environ.get("ANIMUS_AUTONOMOUS_NOTIFY_POLICY"):
            self.notify_policy = env_not
        if env_act := os.environ.get("ANIMUS_AUTONOMOUS_ACT_POLICY"):
            self.act_policy = env_act
        if env_exec := os.environ.get("ANIMUS_AUTONOMOUS_EXECUTE_POLICY"):
            self.execute_policy = env_exec


@dataclass
class AnimusConfig:
    """Main configuration for Animus."""

    data_dir: Path = field(default_factory=default_data_dir)
    log_level: str = "INFO"
    log_to_file: bool = True
    model: ModelConfig = field(default_factory=ModelConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    object_store: ObjectStoreConfig = field(default_factory=ObjectStoreConfig)
    api: APIConfig = field(default_factory=APIConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    integrations: IntegrationConfig = field(default_factory=IntegrationConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    tools_security: ToolsSecurityConfig = field(default_factory=ToolsSecurityConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    entities: EntityConfig = field(default_factory=EntityConfig)
    autonomous: AutonomousConfig = field(default_factory=AutonomousConfig)
    citizen_zero: CitizenZeroConfig = field(default_factory=CitizenZeroConfig)
    citizens: CitizensConfig = field(default_factory=CitizensConfig)
    session: SessionConfig = field(default_factory=SessionConfig)

    def __post_init__(self):
        # Convert string to Path if needed
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)

        # Expand user path
        self.data_dir = self.data_dir.expanduser()

        # Environment overrides
        if env_data_dir := os.environ.get("ANIMUS_DATA_DIR"):
            self.data_dir = Path(env_data_dir).expanduser()
        self.log_level = os.environ.get("ANIMUS_LOG_LEVEL", self.log_level)

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.yaml"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "animus.log"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def history_file(self) -> Path:
        return self.data_dir / "history"

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        """Convert config to dictionary for serialization."""
        return {
            "data_dir": str(self.data_dir),
            "log_level": self.log_level,
            "log_to_file": self.log_to_file,
            "model": {
                "provider": self.model.provider,
                "name": self.model.name,
                "ollama_url": self.model.ollama_url,
                "openai_base_url": self.model.openai_base_url,
            },
            "memory": {
                "backend": self.memory.backend,
                "collection_name": self.memory.collection_name,
            },
            "api": {
                "enabled": self.api.enabled,
                "host": self.api.host,
                "port": self.api.port,
            },
            "voice": {
                "input_enabled": self.voice.input_enabled,
                "output_enabled": self.voice.output_enabled,
                "whisper_model": self.voice.whisper_model,
                "tts_engine": self.voice.tts_engine,
                "tts_rate": self.voice.tts_rate,
            },
            "integrations": {
                "google": {
                    "enabled": self.integrations.google.enabled,
                },
                "todoist": {
                    "enabled": self.integrations.todoist.enabled,
                },
                "filesystem": {
                    "enabled": self.integrations.filesystem.enabled,
                    "indexed_paths": self.integrations.filesystem.indexed_paths,
                    "exclude_patterns": self.integrations.filesystem.exclude_patterns,
                },
                "webhooks": {
                    "enabled": self.integrations.webhooks.enabled,
                    "port": self.integrations.webhooks.port,
                },
            },
            "learning": {
                "enabled": self.learning.enabled,
                "auto_scan_enabled": self.learning.auto_scan_enabled,
                "auto_scan_interval_hours": self.learning.auto_scan_interval_hours,
                "min_pattern_occurrences": self.learning.min_pattern_occurrences,
                "min_pattern_confidence": self.learning.min_pattern_confidence,
                "lookback_days": self.learning.lookback_days,
            },
            "proactive": {
                "enabled": self.proactive.enabled,
                "background_enabled": self.proactive.background_enabled,
                "background_interval_seconds": self.proactive.background_interval_seconds,
            },
            "entities": {
                "enabled": self.entities.enabled,
                "auto_extract": self.entities.auto_extract,
                "auto_discover": self.entities.auto_discover,
            },
            "autonomous": {
                "enabled": self.autonomous.enabled,
                "observe_policy": self.autonomous.observe_policy,
                "notify_policy": self.autonomous.notify_policy,
                "act_policy": self.autonomous.act_policy,
                "execute_policy": self.autonomous.execute_policy,
            },
            "citizen_zero": {
                "enabled": self.citizen_zero.enabled,
                "citizen_dir": self.citizen_zero.citizen_dir,
                "shared_dir": self.citizen_zero.shared_dir,
                "constitutional_corpus_dir": self.citizen_zero.constitutional_corpus_dir,
                "context_budget_tokens": self.citizen_zero.context_budget_tokens,
                "default_failure_mode": self.citizen_zero.default_failure_mode,
            },
            "citizens": {
                "enabled": self.citizens.enabled,
                "codebase_path": self.citizens.codebase_path,
                "conversation_log_dir": self.citizens.conversation_log_dir,
                "evidence_dir": self.citizens.evidence_dir,
                "forge_host": self.citizens.forge_host,
                "forge_port": self.citizens.forge_port,
                "auto_store_proposals": self.citizens.auto_store_proposals,
            },
            "session": {
                "session_timer_minutes": self.session.session_timer_minutes,
                "wrapup_threshold": self.session.wrapup_threshold,
                "auto_restart": self.session.auto_restart,
            },
        }

    def save(self) -> None:
        """Save configuration to YAML file."""
        self.ensure_dirs()
        with open(self.config_file, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AnimusConfig":
        """
        Load configuration from file.

        Precedence (highest to lowest):
        1. Environment variables
        2. Config file values
        3. Default values
        """
        config = cls()

        # Determine config file path
        if config_path is None:
            config_path = config.config_file

        # Load from file if exists
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

            # Apply file values (env vars applied in __post_init__)
            if "data_dir" in data:
                config.data_dir = Path(data["data_dir"]).expanduser()
            if "log_level" in data:
                config.log_level = data["log_level"]
            if "log_to_file" in data:
                config.log_to_file = data["log_to_file"]

            if model_data := data.get("model"):
                if "provider" in model_data:
                    config.model.provider = model_data["provider"]
                if "name" in model_data:
                    config.model.name = model_data["name"]
                if "ollama_url" in model_data:
                    config.model.ollama_url = model_data["ollama_url"]
                if "openai_base_url" in model_data:
                    config.model.openai_base_url = model_data["openai_base_url"]

            memory_data = data.get("memory")
            if isinstance(memory_data, dict):
                if "backend" in memory_data:
                    config.memory.backend = memory_data["backend"]
                if "collection_name" in memory_data:
                    config.memory.collection_name = memory_data["collection_name"]
            if not isinstance(memory_data, dict) or "backend" not in memory_data:
                # Config files created before the Core runtime retirement could
                # omit this field and inherit the former Chroma default. Keep
                # that legacy selection so startup fails closed instead of
                # silently opening an empty local store after an upgrade.
                config.memory.backend = "chroma"

            # Nested dataclass __post_init__ runs before file values are loaded.
            # Reapply the documented highest-precedence environment override.
            if memory_backend := os.environ.get("ANIMUS_MEMORY_BACKEND"):
                config.memory.backend = memory_backend

            if api_data := data.get("api"):
                if "enabled" in api_data:
                    config.api.enabled = api_data["enabled"]
                if "host" in api_data:
                    config.api.host = api_data["host"]
                if "port" in api_data:
                    config.api.port = api_data["port"]
                if "api_key" in api_data:
                    config.api.api_key = api_data["api_key"]

            if voice_data := data.get("voice"):
                if "input_enabled" in voice_data:
                    config.voice.input_enabled = voice_data["input_enabled"]
                if "output_enabled" in voice_data:
                    config.voice.output_enabled = voice_data["output_enabled"]
                if "whisper_model" in voice_data:
                    config.voice.whisper_model = voice_data["whisper_model"]
                if "tts_engine" in voice_data:
                    config.voice.tts_engine = voice_data["tts_engine"]
                if "tts_rate" in voice_data:
                    config.voice.tts_rate = voice_data["tts_rate"]

            if integrations_data := data.get("integrations"):
                if google_data := integrations_data.get("google"):
                    if "enabled" in google_data:
                        config.integrations.google.enabled = google_data["enabled"]
                    if "client_id" in google_data:
                        config.integrations.google.client_id = google_data["client_id"]
                    if "client_secret" in google_data:
                        config.integrations.google.client_secret = google_data["client_secret"]
                if todoist_data := integrations_data.get("todoist"):
                    if "enabled" in todoist_data:
                        config.integrations.todoist.enabled = todoist_data["enabled"]
                    if "api_key" in todoist_data:
                        config.integrations.todoist.api_key = todoist_data["api_key"]
                if fs_data := integrations_data.get("filesystem"):
                    if "enabled" in fs_data:
                        config.integrations.filesystem.enabled = fs_data["enabled"]
                    if "indexed_paths" in fs_data:
                        config.integrations.filesystem.indexed_paths = fs_data["indexed_paths"]
                    if "exclude_patterns" in fs_data:
                        config.integrations.filesystem.exclude_patterns = fs_data[
                            "exclude_patterns"
                        ]
                if webhook_data := integrations_data.get("webhooks"):
                    if "enabled" in webhook_data:
                        config.integrations.webhooks.enabled = webhook_data["enabled"]
                    if "port" in webhook_data:
                        config.integrations.webhooks.port = webhook_data["port"]
                    if "secret" in webhook_data:
                        config.integrations.webhooks.secret = webhook_data["secret"]
            if learning_data := data.get("learning"):
                if "enabled" in learning_data:
                    config.learning.enabled = learning_data["enabled"]
                if "auto_scan_enabled" in learning_data:
                    config.learning.auto_scan_enabled = learning_data["auto_scan_enabled"]
                if "auto_scan_interval_hours" in learning_data:
                    config.learning.auto_scan_interval_hours = learning_data[
                        "auto_scan_interval_hours"
                    ]
                if "min_pattern_occurrences" in learning_data:
                    config.learning.min_pattern_occurrences = learning_data[
                        "min_pattern_occurrences"
                    ]
                if "min_pattern_confidence" in learning_data:
                    config.learning.min_pattern_confidence = learning_data["min_pattern_confidence"]
                if "lookback_days" in learning_data:
                    config.learning.lookback_days = learning_data["lookback_days"]

            if proactive_data := data.get("proactive"):
                if "enabled" in proactive_data:
                    config.proactive.enabled = proactive_data["enabled"]
                if "background_enabled" in proactive_data:
                    config.proactive.background_enabled = proactive_data["background_enabled"]
                if "background_interval_seconds" in proactive_data:
                    config.proactive.background_interval_seconds = proactive_data[
                        "background_interval_seconds"
                    ]

            if entity_data := data.get("entities"):
                if "enabled" in entity_data:
                    config.entities.enabled = entity_data["enabled"]
                if "auto_extract" in entity_data:
                    config.entities.auto_extract = entity_data["auto_extract"]
                if "auto_discover" in entity_data:
                    config.entities.auto_discover = entity_data["auto_discover"]

            if autonomous_data := data.get("autonomous"):
                if "enabled" in autonomous_data:
                    config.autonomous.enabled = autonomous_data["enabled"]
                if "observe_policy" in autonomous_data:
                    config.autonomous.observe_policy = autonomous_data["observe_policy"]
                if "notify_policy" in autonomous_data:
                    config.autonomous.notify_policy = autonomous_data["notify_policy"]
                if "act_policy" in autonomous_data:
                    config.autonomous.act_policy = autonomous_data["act_policy"]
                if "execute_policy" in autonomous_data:
                    config.autonomous.execute_policy = autonomous_data["execute_policy"]

            if citizen_zero_data := data.get("citizen_zero"):
                if "enabled" in citizen_zero_data:
                    config.citizen_zero.enabled = citizen_zero_data["enabled"]
                if "citizen_dir" in citizen_zero_data:
                    config.citizen_zero.citizen_dir = citizen_zero_data["citizen_dir"]
                if "shared_dir" in citizen_zero_data:
                    config.citizen_zero.shared_dir = citizen_zero_data["shared_dir"]
                if "constitutional_corpus_dir" in citizen_zero_data:
                    config.citizen_zero.constitutional_corpus_dir = citizen_zero_data[
                        "constitutional_corpus_dir"
                    ]
                if "context_budget_tokens" in citizen_zero_data:
                    config.citizen_zero.context_budget_tokens = citizen_zero_data[
                        "context_budget_tokens"
                    ]
                if "default_failure_mode" in citizen_zero_data:
                    config.citizen_zero.default_failure_mode = citizen_zero_data[
                        "default_failure_mode"
                    ]

            if citizens_data := data.get("citizens"):
                if "enabled" in citizens_data:
                    config.citizens.enabled = citizens_data["enabled"]
                if "codebase_path" in citizens_data:
                    config.citizens.codebase_path = citizens_data["codebase_path"]
                if "conversation_log_dir" in citizens_data:
                    config.citizens.conversation_log_dir = citizens_data["conversation_log_dir"]
                if "evidence_dir" in citizens_data:
                    config.citizens.evidence_dir = citizens_data["evidence_dir"]
                if "forge_host" in citizens_data:
                    config.citizens.forge_host = citizens_data["forge_host"]
                if "forge_port" in citizens_data:
                    config.citizens.forge_port = citizens_data["forge_port"]
                if "auto_store_proposals" in citizens_data:
                    config.citizens.auto_store_proposals = citizens_data["auto_store_proposals"]

            if session_data := data.get("session"):
                if "session_timer_minutes" in session_data:
                    config.session.session_timer_minutes = session_data["session_timer_minutes"]
                if "wrapup_threshold" in session_data:
                    config.session.wrapup_threshold = session_data["wrapup_threshold"]
                if "auto_restart" in session_data:
                    config.session.auto_restart = session_data["auto_restart"]

            # Re-apply environment overrides
            config.__post_init__()
            config.model.__post_init__()
            config.memory.__post_init__()
            config.api.__post_init__()
            config.voice.__post_init__()
            config.integrations.google.__post_init__()
            config.integrations.todoist.__post_init__()
            config.integrations.filesystem.__post_init__()
            config.integrations.webhooks.__post_init__()
            config.learning.__post_init__()
            config.proactive.__post_init__()
            config.entities.__post_init__()
            config.autonomous.__post_init__()
            config.citizen_zero.__post_init__()
            config.citizens.__post_init__()
            config.session.__post_init__()

        return config


def get_config() -> AnimusConfig:
    """Get the global configuration, loading from default location."""
    return AnimusConfig.load()
