"""Settings and configuration management."""

import logging
import re
import secrets
import warnings
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

try:
    from pydantic_settings import YamlConfigSettingsSource
except ImportError:  # pydantic-settings < 2.6
    YamlConfigSettingsSource = None

logger = logging.getLogger(__name__)

# Insecure default values that should not be used in production
_INSECURE_SECRET_KEY = "change-me-in-production"
_INSECURE_DATABASE_URL = "sqlite:///gorgon-state.db"

# Package-root defaults that were used before runtime state moved to platform dirs.
# Kept for backward-compatible relocation in model_post_init.
_PACKAGE_SRC = Path(__file__).parent.parent
_PKG_RUNTIME_DIR_DEFAULTS: dict[str, Path] = {
    "logs_dir": _PACKAGE_SRC / "logs",
    "workflows_dir": _PACKAGE_SRC / "workflows",
    "schedules_dir": _PACKAGE_SRC / "schedules",
    "webhooks_dir": _PACKAGE_SRC / "webhooks",
    "jobs_dir": _PACKAGE_SRC / "jobs",
    "plugins_dir": _PACKAGE_SRC / "plugins" / "custom",
}
# Old base_dir default pointed at the package root / monorepo package directory.
_OLD_BASE_DIR_DEFAULT = Path(__file__).parent.parent.parent.parent

# Minimum requirements for secure configuration
_MIN_SECRET_KEY_LENGTH = 32
# Regex for ${ENV_VAR} placeholders in YAML values
_ENV_VAR_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")

# YAML config search paths (checked in order, first found wins)
_YAML_SEARCH_PATHS = [
    Path("gorgon.yaml"),
    Path("config/gorgon.yaml"),
    Path.home() / ".config" / "gorgon" / "gorgon.yaml",
]


def _find_yaml_config() -> Path | None:
    """Find the first gorgon.yaml in search paths."""
    for path in _YAML_SEARCH_PATHS:
        if path.is_file():
            return path
    return None


class Settings(BaseSettings):
    """Application settings.

    Priority chain: init kwargs > env vars > .env file > gorgon.yaml > defaults
    """

    # NOTE: the YAML source is wired manually in settings_customise_sources
    # via _find_yaml_config(), so yaml_file / yaml_file_encoding are NOT set
    # here. Declaring them in model_config without a default YamlConfigSettings
    # source makes pydantic-settings emit an "unused config key" UserWarning.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Class-level cache for the resolved YAML path (not a pydantic field)
    _yaml_path: ClassVar[Path | None] = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customise settings source priority.

        Priority: init kwargs > env vars > .env file > gorgon.yaml > file secrets > defaults
        """
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]

        if YamlConfigSettingsSource is not None:
            yaml_path = _find_yaml_config()
            cls._yaml_path = yaml_path
            if yaml_path:
                sources.append(
                    YamlConfigSettingsSource(
                        settings_cls,
                        yaml_file=yaml_path,
                        yaml_file_encoding="utf-8",
                    )
                )

        sources.append(file_secret_settings)
        return tuple(sources)

    @model_validator(mode="before")
    @classmethod
    def _resolve_env_var_placeholders(cls, data: dict) -> dict:
        """Strip unresolved ${VAR} placeholders so they become None.

        YAML files may contain ${ENV_VAR} syntax for secrets. When the env var
        is not set, the raw placeholder string would pollute the field value.
        This validator converts those to None so the field default applies.
        """
        if not isinstance(data, dict):
            return data
        for key, value in data.items():
            if isinstance(value, str) and _ENV_VAR_PLACEHOLDER_RE.match(value):
                data[key] = None
        return data

    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openrouter_api_key: str | None = Field(
        None, description="OpenRouter API key (open-weights gateway, PUBLIC-only egress)"
    )
    github_token: str | None = Field(None, description="GitHub personal access token")
    notion_token: str | None = Field(None, description="Notion integration token")
    gmail_credentials_path: str | None = Field(None, description="Path to Gmail OAuth credentials")

    # Claude/Anthropic Settings
    anthropic_api_key: str | None = Field(None, description="Anthropic API key for Claude")
    claude_cli_path: str = Field("claude", description="Path to Claude CLI executable")
    claude_mode: str = Field("api", description="Claude invocation mode: 'api' or 'cli'")

    # Application Settings
    app_name: str = Field("Gorgon", description="Application name")
    debug: bool = Field(False, description="Debug mode")
    production: bool = Field(
        False,
        description="Production mode - enables strict security validation",
    )
    require_secure_config: bool = Field(
        False,
        description="Require secure SECRET_KEY and DATABASE_URL even in dev mode",
    )
    log_level: str = Field("INFO", description="Logging level")
    log_format: str = Field("text", description="Log format: 'text' or 'json'")
    sanitize_logs: bool = Field(True, description="Sanitize sensitive data from logs")

    # Paths
    # Runtime state defaults to ~/.animus so wheel installs don't write into
    # site-packages.  Fields still accept env overrides (e.g. LOGS_DIR).
    base_dir: Path = Field(default_factory=lambda: Path.home() / ".animus")
    logs_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["logs_dir"])
    prompts_dir: Path = Field(default_factory=lambda: _PACKAGE_SRC / "prompts")
    workflows_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["workflows_dir"])
    schedules_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["schedules_dir"])
    webhooks_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["webhooks_dir"])
    jobs_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["jobs_dir"])
    plugins_dir: Path = Field(default_factory=lambda: _PKG_RUNTIME_DIR_DEFAULTS["plugins_dir"])
    skills_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent.parent / "skills",
        description="Directory containing skill definitions (schema.yaml + SKILL.md)",
    )

    # Database
    database_url: str = Field(
        default=_INSECURE_DATABASE_URL,
        description="Database URL (sqlite:///path.db or postgresql://user:pass@host/db)",
    )

    # Auth
    secret_key: str = Field(
        default=_INSECURE_SECRET_KEY, description="Secret key for token generation"
    )
    access_token_expire_minutes: int = Field(60, description="Access token expiration in minutes")
    # API credentials (comma-separated user:password_hash pairs)
    # Generate hash with: python -c "from hashlib import sha256; print(sha256(b'your_password').hexdigest())"
    api_credentials: str | None = Field(
        None,
        description="API credentials as 'user1:hash1,user2:hash2'. Hash passwords with SHA-256.",
    )
    allow_demo_auth: bool = Field(
        False,
        description="Allow demo authentication (user: any, password: 'demo'). Set ALLOW_DEMO_AUTH=true to enable.",
    )

    # Shell execution limits
    shell_timeout_seconds: int = Field(
        300,
        description="Maximum execution time for shell commands in seconds (default: 5 minutes)",
    )
    shell_max_output_bytes: int = Field(
        10 * 1024 * 1024,
        description="Maximum output size for shell commands in bytes (default: 10MB)",
    )
    shell_allowed_commands: str | None = Field(
        None,
        description="Comma-separated list of allowed shell commands (empty = all allowed)",
    )

    # Rate Limiting (API clients)
    ratelimit_openai_rpm: int = Field(60, description="OpenAI requests per minute")
    ratelimit_openai_tpm: int = Field(90000, description="OpenAI tokens per minute")
    ratelimit_anthropic_rpm: int = Field(60, description="Anthropic requests per minute")
    ratelimit_github_rpm: int = Field(30, description="GitHub requests per minute")
    ratelimit_notion_rpm: int = Field(30, description="Notion requests per minute")
    ratelimit_gmail_rpm: int = Field(30, description="Gmail requests per minute")

    # Bulkhead/Concurrency Limits (API clients)
    bulkhead_openai_concurrent: int = Field(10, description="OpenAI max concurrent requests")
    bulkhead_anthropic_concurrent: int = Field(10, description="Anthropic max concurrent requests")
    bulkhead_github_concurrent: int = Field(5, description="GitHub max concurrent requests")
    bulkhead_notion_concurrent: int = Field(3, description="Notion max concurrent requests")
    bulkhead_gmail_concurrent: int = Field(5, description="Gmail max concurrent requests")
    bulkhead_default_timeout: float = Field(30.0, description="Default bulkhead timeout in seconds")

    # Request Size Limits (API)
    request_max_body_size: int = Field(
        10 * 1024 * 1024,
        description="Maximum request body size in bytes (default: 10MB)",
    )
    request_max_json_size: int = Field(
        1 * 1024 * 1024, description="Maximum JSON body size in bytes (default: 1MB)"
    )
    request_max_form_size: int = Field(
        50 * 1024 * 1024, description="Maximum form body size in bytes (default: 50MB)"
    )

    # Brute Force Protection
    brute_force_max_attempts_per_minute: int = Field(
        60, description="Max requests per minute from a single IP"
    )
    brute_force_max_attempts_per_hour: int = Field(
        300, description="Max requests per hour from a single IP"
    )
    brute_force_max_auth_attempts_per_minute: int = Field(
        5, description="Max auth attempts per minute from a single IP"
    )
    brute_force_max_auth_attempts_per_hour: int = Field(
        20, description="Max auth attempts per hour from a single IP"
    )
    brute_force_initial_block_seconds: float = Field(
        60.0, description="Initial block duration in seconds"
    )
    brute_force_max_block_seconds: float = Field(
        3600.0, description="Maximum block duration in seconds (default: 1 hour)"
    )

    # Distributed Tracing
    tracing_enabled: bool = Field(True, description="Enable distributed tracing")
    tracing_service_name: str = Field("gorgon-api", description="Service name for tracing")
    tracing_sample_rate: float = Field(
        1.0, description="Trace sampling rate (0.0-1.0, default: trace all)"
    )

    # Azure OpenAI
    azure_openai_api_key: str | None = Field(None, description="Azure OpenAI API key")
    azure_openai_endpoint: str | None = Field(None, description="Azure OpenAI endpoint URL")
    azure_openai_deployment: str | None = Field(None, description="Azure OpenAI deployment name")

    # Google Cloud / Vertex AI
    google_application_credentials: str | None = Field(
        None, description="Path to Google Cloud service account JSON"
    )
    google_cloud_project: str | None = Field(None, description="Google Cloud project ID")
    google_cloud_location: str | None = Field(
        None, description="Google Cloud region (e.g. us-central1)"
    )

    # Redis
    redis_url: str | None = Field(None, description="Redis connection URL")

    # Telegram
    telegram_bot_token: str | None = Field(None, description="Telegram bot token")
    telegram_allowed_users: str | None = Field(
        None, description="Comma-separated Telegram user IDs"
    )
    telegram_admin_users: str | None = Field(
        None, description="Comma-separated Telegram admin user IDs"
    )

    # Discord
    discord_bot_token: str | None = Field(None, description="Discord bot token")
    discord_allowed_users: str | None = Field(None, description="Comma-separated Discord user IDs")
    discord_admin_users: str | None = Field(
        None, description="Comma-separated Discord admin user IDs"
    )
    discord_allowed_guilds: str | None = Field(
        None, description="Comma-separated Discord guild IDs"
    )

    # Security / Encryption
    settings_encryption_key: str | None = Field(
        None, description="Fernet key for settings encryption"
    )
    jwt_secret: str | None = Field(None, description="JWT secret for settings encryption fallback")

    @property
    def has_secure_secret_key(self) -> bool:
        """Check if secret key meets security requirements.

        Requirements:
        - Not the insecure default value
        - At least 32 characters long
        """
        if self.secret_key == _INSECURE_SECRET_KEY:
            return False
        if len(self.secret_key) < _MIN_SECRET_KEY_LENGTH:
            return False
        return True

    @property
    def has_secure_database(self) -> bool:
        """Check if database URL has been changed from insecure default."""
        return self.database_url != _INSECURE_DATABASE_URL

    @property
    def is_production_safe(self) -> bool:
        """Check if configuration is safe for production use."""
        return self.has_secure_secret_key and self.has_secure_database

    @staticmethod
    def generate_secret_key() -> str:
        """Generate a cryptographically secure secret key."""
        return secrets.token_urlsafe(48)  # 64 characters, 384 bits of entropy

    def get_credentials_map(self) -> dict[str, str]:
        """Parse API credentials into a username -> password_hash map."""
        if not self.api_credentials:
            return {}

        credentials = {}
        for pair in self.api_credentials.split(","):
            pair = pair.strip()
            if ":" in pair:
                username, password_hash = pair.split(":", 1)
                credentials[username.strip()] = password_hash.strip()
        return credentials

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verify username and password against configured credentials.

        Supports bcrypt hashes (preferred) and legacy SHA-256 hashes.

        Args:
            username: The username to verify
            password: The plaintext password to verify

        Returns:
            True if credentials are valid, False otherwise
        """
        # Check configured credentials first
        credentials = self.get_credentials_map()
        if username in credentials:
            stored = credentials[username]
            # bcrypt hashes start with $2b$ or $2a$
            if stored.startswith(("$2b$", "$2a$")):
                import bcrypt

                return bcrypt.checkpw(password.encode(), stored.encode())
            else:
                # Legacy SHA-256 (deprecated — migrate to bcrypt)
                from hashlib import sha256

                logger.warning(
                    "Legacy SHA-256 credentials detected for user %s — migrate to bcrypt",
                    username,
                )
                password_hash = sha256(password.encode()).hexdigest()
                return secrets.compare_digest(stored, password_hash)

        # Fall back to demo auth if allowed
        if self.allow_demo_auth and password == "demo":
            return True

        return False

    def model_post_init(self, __context) -> None:
        """Ensure directories exist and validate production config."""
        # Relocate any runtime directory still using the old package-relative
        # default to the user data directory.  This prevents wheel installs from
        # writing state into site-packages when callers only override base_dir or
        # rely on defaults.
        if self.base_dir.resolve() == _OLD_BASE_DIR_DEFAULT.resolve():
            self.base_dir = Path.home() / ".animus"

        for field_name, old_default in _PKG_RUNTIME_DIR_DEFAULTS.items():
            current = getattr(self, field_name)
            try:
                if current.resolve() == old_default.resolve():
                    subdir = old_default.relative_to(_PACKAGE_SRC)
                    setattr(self, field_name, self.base_dir / subdir)
            except OSError:
                # If the path cannot be resolved (e.g. broken symlink), leave it.
                pass

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_dir.mkdir(parents=True, exist_ok=True)
        self.webhooks_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Production mode validation
        self._validate_production_config()

    def _validate_production_config(self) -> None:
        """Validate configuration for production safety."""
        issues = []

        if not self.has_secure_secret_key:
            if self.secret_key == _INSECURE_SECRET_KEY:
                msg = (
                    "SECRET_KEY is using insecure default value. "
                    f"Set SECRET_KEY environment variable to a secure random string "
                    f"(minimum {_MIN_SECRET_KEY_LENGTH} characters). "
                    f'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
            else:
                msg = (
                    f"SECRET_KEY is too short ({len(self.secret_key)} chars). "
                    f"Minimum length is {_MIN_SECRET_KEY_LENGTH} characters. "
                    f'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
            issues.append(msg)

        if not self.has_secure_database:
            msg = (
                "DATABASE_URL is using default SQLite path. "
                "Set DATABASE_URL environment variable for production "
                "(e.g., postgresql://user:pass@host/db or sqlite:///absolute/path.db)."
            )
            issues.append(msg)

        if self.debug and self.production:
            msg = "DEBUG mode is enabled in production. Set DEBUG=false."
            issues.append(msg)

        if self.allow_demo_auth and self.production:
            msg = (
                "Demo authentication is enabled in production. "
                "Set ALLOW_DEMO_AUTH=false and configure API_CREDENTIALS."
            )
            issues.append(msg)

        # Determine if we should enforce or warn
        enforce_security = self.production or self.require_secure_config

        if issues:
            if enforce_security:
                # In production or when require_secure_config is set, raise error
                mode = "production" if self.production else "secure config"
                raise ValueError(
                    f"Insecure configuration not allowed ({mode} mode enabled):\n"
                    + "\n".join(f"  - {issue}" for issue in issues)
                )
            else:
                # In dev mode, warn loudly
                for issue in issues:
                    warnings.warn(f"Security: {issue}", stacklevel=3)
                    logger.warning("SECURITY WARNING: %s", issue)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Alias for CLI and other consumers that expect get_config()
get_config = get_settings
