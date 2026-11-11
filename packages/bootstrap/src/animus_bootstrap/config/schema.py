"""Pydantic models for Animus configuration.

Nested section models use plain ``BaseModel`` to avoid pydantic-settings
reading environment variables for fields like ``path`` (which would
collide with ``$PATH``).  Only the top-level :class:`AnimusConfig` extends
``BaseSettings``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnimusSection(BaseModel):
    """Core Animus settings."""

    version: str = "0.1.0"
    first_run: bool = True
    data_dir: str = "~/.local/share/animus"


class ApiSection(BaseModel):
    """API key configuration.

    Keys are resolved in this order (first non-empty wins):
        1. Environment variables (``ANTHROPIC_API_KEY``,
           ``OPENAI_API_KEY``)
        2. Secrets file at
           ``$ANIMUS_SECRETS_FILE`` (default
           ``~/.local/share/animus/secrets.env``) — KEY=VAL lines,
           chmod 400 recommended
        3. The corresponding field in ``config.toml`` (legacy /
           plaintext path, still supported but discouraged)
        4. Empty string default

    The secrets-file layer exists so operators can keep
    ``config.toml`` plaintext-free without committing to systemd
    EnvironmentFile or external secret managers. ``config.toml``
    gets backed up by tools like restic / rsync; the secrets file
    can be excluded from those backup targets independently.
    """

    anthropic_key: str = ""
    openai_key: str = ""

    @staticmethod
    def _load_secrets_env() -> dict[str, str]:
        """Parse KEY=VAL lines from the secrets file, if present.

        Tolerant of missing file, comments, blank lines, and
        single/double-quoted values. Errors during read are
        swallowed — secrets are best-effort, not load-bearing.
        """
        import os
        from pathlib import Path

        path = Path(
            os.environ.get(
                "ANIMUS_SECRETS_FILE",
                os.path.expanduser("~/.local/share/animus/secrets.env"),
            )
        )
        if not path.is_file():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        pairs: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            pairs[key.strip()] = value
        return pairs

    def model_post_init(self, __context: object) -> None:
        """Apply env var > secrets file > config.toml precedence."""
        import os

        secrets = self._load_secrets_env()
        anthropic = os.environ.get("ANTHROPIC_API_KEY") or secrets.get("ANTHROPIC_API_KEY") or ""
        if anthropic:
            self.anthropic_key = anthropic
        openai = os.environ.get("OPENAI_API_KEY") or secrets.get("OPENAI_API_KEY") or ""
        if openai:
            self.openai_key = openai


class ForgeSection(BaseModel):
    """Forge orchestration engine settings."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 8000
    api_key: str = ""


class MemorySection(BaseModel):
    """Memory backend settings."""

    backend: str = "sqlite"
    path: str = "~/.local/share/animus/memory.db"
    max_context_tokens: int = 100_000


class IdentitySection(BaseModel):
    """User identity settings."""

    name: str = ""
    timezone: str = ""
    locale: str = ""
    identity_dir: str = "~/.config/animus/identity"


class OllamaSection(BaseModel):
    """Ollama configuration."""

    enabled: bool = True
    host: str = "localhost"
    port: int = 11434
    model: str = "llama3.2"
    code_model: str = ""
    autoinstall: bool = True


class SelfImprovementSection(BaseModel):
    """Self-improvement loop configuration."""

    reflection_enabled: bool = True
    reflection_interval_hours: int = 24
    reflection_min_interactions: int = 10
    approval_required: bool = True
    proposals_dir: str = "~/.config/animus/proposals"


class ServicesSection(BaseModel):
    """Background services settings."""

    autostart: bool = True
    host: str = "127.0.0.1"
    port: int = 7700
    log_level: str = "info"
    update_check: bool = True
    # Remote-access auth for the dashboard/PWA API surface.
    # auth_required: "auto" enforces a bearer token only when the server is
    # reachable from a non-local client (i.e. bound to a non-localhost host);
    # "always" enforces it everywhere; "never" disables it.
    auth_required: str = "auto"
    # Shared bearer token. Generated on first run when empty; stored in the
    # chmod-600 config file. Used by the PWA over the Tailscale tunnel.
    auth_token: str = ""
    # Optional TLS termination directly in uvicorn. Point these at the files
    # produced by ``tailscale cert <machine>.<tailnet>.ts.net``. When both are
    # set the dashboard serves HTTPS (required for the PWA service worker and
    # Web Push secure context). A loopback reverse proxy is also supported,
    # but it requires ``auth_required = "always"`` so proxy traffic cannot
    # inherit the normal local-client exemption.
    tls_cert: str = ""
    tls_key: str = ""
    # Web Push (VAPID) keys for proactive push notifications to the PWA.
    # Generated on first run when push is first used. The public key is shared
    # with the browser; the private key (PEM) signs push requests.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"


class GatewaySection(BaseModel):
    """Gateway core settings."""

    enabled: bool = True
    default_backend: str = "anthropic"
    system_prompt: str = ""
    max_response_tokens: int = 4096
    # Gateway middleware (all default to open/off → unchanged behaviour).
    # allowlist entries are "channel:sender_id"; empty list = open mode.
    allowlist: list[str] = Field(default_factory=list)
    # Per-sender token bucket; 0 disables rate limiting.
    rate_limit_max_tokens: int = 0
    rate_limit_refill_rate: float = 1.0
    # Persist an inbound/outbound audit log to SQLite when True.
    message_log: bool = False


class WebchatChannelConfig(BaseModel):
    """Built-in webchat channel configuration."""

    enabled: bool = True


class TelegramChannelConfig(BaseModel):
    """Telegram channel configuration."""

    enabled: bool = False
    bot_token: str = ""


class DiscordChannelConfig(BaseModel):
    """Discord channel configuration."""

    enabled: bool = False
    bot_token: str = ""
    allowed_guilds: list[str] = Field(default_factory=list)


class SlackChannelConfig(BaseModel):
    """Slack channel configuration."""

    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""


class MatrixChannelConfig(BaseModel):
    """Matrix channel configuration."""

    enabled: bool = False
    homeserver: str = ""
    access_token: str = ""
    room_ids: list[str] = Field(default_factory=list)


class SignalChannelConfig(BaseModel):
    """Signal channel configuration."""

    enabled: bool = False
    phone_number: str = ""


class WhatsappChannelConfig(BaseModel):
    """WhatsApp channel configuration."""

    enabled: bool = False
    phone_number: str = ""


class EmailChannelConfig(BaseModel):
    """Email channel configuration."""

    enabled: bool = False
    imap_host: str = ""
    smtp_host: str = ""
    username: str = ""
    password: str = ""
    poll_interval: int = 60


class ChannelsSection(BaseModel):
    """Channel adapter configurations."""

    webchat: WebchatChannelConfig = Field(default_factory=WebchatChannelConfig)
    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)
    discord: DiscordChannelConfig = Field(default_factory=DiscordChannelConfig)
    slack: SlackChannelConfig = Field(default_factory=SlackChannelConfig)
    matrix: MatrixChannelConfig = Field(default_factory=MatrixChannelConfig)
    signal: SignalChannelConfig = Field(default_factory=SignalChannelConfig)
    whatsapp: WhatsappChannelConfig = Field(default_factory=WhatsappChannelConfig)
    email: EmailChannelConfig = Field(default_factory=EmailChannelConfig)


class MCPConfig(BaseModel):
    """MCP server configuration."""

    config_path: str = "~/.config/animus/mcp.json"
    auto_discover: bool = True


class IntelligenceSection(BaseModel):
    """Intelligence layer settings."""

    enabled: bool = True
    memory_backend: str = "sqlite"  # "sqlite" | "chromadb" | "animus"
    memory_db_path: str = "~/.local/share/animus/intelligence.db"
    tool_approval_default: str = "auto"  # "auto" | "approve" | "deny"
    max_tool_calls_per_turn: int = 5
    tool_timeout_seconds: int = 30
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class ProactiveCheckConfig(BaseModel):
    """Configuration for a single proactive check."""

    enabled: bool = True
    schedule: str = ""
    channels: list[str] = Field(default_factory=list)


class ProactiveSection(BaseModel):
    """Proactive engine settings."""

    enabled: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    timezone: str = "UTC"
    checks: dict[str, ProactiveCheckConfig] = Field(default_factory=dict)


class PersonaVoiceConfig(BaseModel):
    """Voice configuration for a persona profile."""

    tone: str = "balanced"
    max_response_length: str = "medium"
    emoji_policy: str = "minimal"
    language: str = "en"
    custom_instructions: str = ""


class PersonaProfileConfig(BaseModel):
    """A persona profile in config."""

    name: str = ""
    description: str = ""
    system_prompt: str = ""
    tone: str = "balanced"
    knowledge_domains: list[str] = Field(default_factory=list)
    excluded_topics: list[str] = Field(default_factory=list)
    channel_bindings: dict[str, bool] = Field(default_factory=dict)


class PersonasSection(BaseModel):
    """Persona system settings."""

    enabled: bool = True
    default_name: str = "Animus"
    default_tone: str = "balanced"
    default_max_response_length: str = "medium"
    default_emoji_policy: str = "minimal"
    default_system_prompt: str = "You are Animus, a personal AI assistant."
    profiles: dict[str, PersonaProfileConfig] = Field(default_factory=dict)


class AnimusConfig(BaseSettings):
    """Top-level Animus configuration model.

    Maps to the TOML structure:
        [animus] / [api] / [forge] / [memory] / [identity] / [services]
        [gateway] / [channels] / [intelligence] / [proactive] / [personas]

    All fields are optional with sensible defaults. Config file lives at
    ``~/.config/animus/config.toml``.

    Extra fields (e.g. user-defined sections like ``[providers]``) are
    ignored so that forward-compatible config files do not crash startup.
    """

    model_config = SettingsConfigDict(extra="ignore")

    animus: AnimusSection = Field(default_factory=AnimusSection)
    api: ApiSection = Field(default_factory=ApiSection)
    forge: ForgeSection = Field(default_factory=ForgeSection)
    memory: MemorySection = Field(default_factory=MemorySection)
    identity: IdentitySection = Field(default_factory=IdentitySection)
    services: ServicesSection = Field(default_factory=ServicesSection)
    gateway: GatewaySection = Field(default_factory=GatewaySection)
    channels: ChannelsSection = Field(default_factory=ChannelsSection)
    intelligence: IntelligenceSection = Field(default_factory=IntelligenceSection)
    proactive: ProactiveSection = Field(default_factory=ProactiveSection)
    personas: PersonasSection = Field(default_factory=PersonasSection)
    ollama: OllamaSection = Field(default_factory=OllamaSection)
    self_improvement: SelfImprovementSection = Field(default_factory=SelfImprovementSection)

    def get_data_path(self) -> Path:
        """Return the resolved data directory path."""
        return Path(self.animus.data_dir).expanduser()

    def get_memory_path(self) -> Path:
        """Return the resolved memory database path."""
        return Path(self.memory.path).expanduser()

    def validate_secrets(self) -> list[str]:
        """Check that secrets required by enabled features are present.

        Returns a list of warning messages for missing secrets.
        Designed for fail-fast startup — call this before runtime.start().
        """
        warnings: list[str] = []

        backend = self.gateway.default_backend

        if backend == "anthropic" and not self.api.anthropic_key:
            warnings.append(
                "Gateway backend is 'anthropic' but ANTHROPIC_API_KEY "
                "is not set (env var or config file). "
                "Will fall back to Ollama."
            )

        if backend == "forge" and self.forge.enabled and not self.forge.api_key:
            warnings.append(
                "Forge is enabled as gateway backend but forge.api_key is not configured."
            )

        # Channel tokens — only warn for enabled channels
        channel_checks = [
            (self.channels.telegram, "bot_token", "Telegram"),
            (self.channels.discord, "bot_token", "Discord"),
            (self.channels.slack, "bot_token", "Slack"),
            (self.channels.matrix, "access_token", "Matrix"),
        ]
        for channel_cfg, secret_field, name in channel_checks:
            if channel_cfg.enabled and not getattr(channel_cfg, secret_field, ""):
                warnings.append(f"{name} channel is enabled but {secret_field} is empty.")

        if self.channels.email.enabled:
            if not self.channels.email.username or not self.channels.email.password:
                warnings.append("Email channel is enabled but username/password not set.")

        return warnings
