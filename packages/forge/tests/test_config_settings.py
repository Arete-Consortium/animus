"""Comprehensive tests for config/settings.py — Settings class and helpers."""

import os
import warnings
from pathlib import Path

import pytest

from animus_forge.config.settings import (
    _INSECURE_DATABASE_URL,
    _INSECURE_SECRET_KEY,
    _MIN_SECRET_KEY_LENGTH,
    Settings,
    get_settings,
)

# =============================================================================
# Helpers
# =============================================================================


_ENV_KEYS_TO_CLEAR = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "NOTION_TOKEN",
    "GITHUB_TOKEN",
    "GMAIL_CREDENTIALS_PATH",
    "SECRET_KEY",
    "DATABASE_URL",
    "PRODUCTION",
    "DEBUG",
    "ALLOW_DEMO_AUTH",
    "REQUIRE_SECURE_CONFIG",
    "API_CREDENTIALS",
    "LOG_FORMAT",
]


def _make_settings(tmp_path, **overrides):
    """Create Settings with temp dirs so model_post_init won't fail.

    All directory fields point inside tmp_path to avoid polluting the real FS.
    Uses _env_file=None to prevent reading the .env file and clears relevant
    env vars so tests get true defaults.
    """
    defaults = dict(
        _env_file=None,
        logs_dir=tmp_path / "logs",
        prompts_dir=tmp_path / "prompts",
        workflows_dir=tmp_path / "workflows",
        schedules_dir=tmp_path / "schedules",
        webhooks_dir=tmp_path / "webhooks",
        jobs_dir=tmp_path / "jobs",
        plugins_dir=tmp_path / "plugins",
    )
    defaults.update(overrides)

    # Remove env vars that would override defaults
    saved = {}
    for key in _ENV_KEYS_TO_CLEAR:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        return Settings(**defaults)
    finally:
        os.environ.update(saved)


# =============================================================================
# Test Default Values
# =============================================================================


class TestSettingsDefaults:
    """Verify default values for every Settings field."""

    def test_default_openai_key(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.openai_api_key == ""

    def test_default_github_token(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.github_token is None

    def test_default_notion_token(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.notion_token is None

    def test_default_gmail_credentials_path(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.gmail_credentials_path is None

    def test_default_anthropic_api_key(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.anthropic_api_key is None

    def test_default_claude_cli_path(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.claude_cli_path == "claude"

    def test_default_claude_mode(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.claude_mode == "api"

    def test_default_app_name(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.app_name == "Gorgon"

    def test_default_debug(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.debug is False

    def test_default_production(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.production is False

    def test_default_require_secure_config(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.require_secure_config is False

    def test_default_log_level(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.log_level == "INFO"

    def test_default_log_format(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.log_format == "text"

    def test_default_sanitize_logs(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.sanitize_logs is True

    def test_default_database_url(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.database_url == _INSECURE_DATABASE_URL

    def test_default_secret_key(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.secret_key == _INSECURE_SECRET_KEY

    def test_default_access_token_expire_minutes(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.access_token_expire_minutes == 60

    def test_default_api_credentials(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.api_credentials is None

    def test_default_allow_demo_auth(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.allow_demo_auth is False

    def test_default_shell_timeout(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.shell_timeout_seconds == 300

    def test_default_shell_max_output(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.shell_max_output_bytes == 10 * 1024 * 1024

    def test_default_shell_allowed_commands(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.shell_allowed_commands is None

    def test_default_rate_limits(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.ratelimit_openai_rpm == 60
        assert s.ratelimit_openai_tpm == 90000
        assert s.ratelimit_anthropic_rpm == 60
        assert s.ratelimit_github_rpm == 30
        assert s.ratelimit_notion_rpm == 30
        assert s.ratelimit_gmail_rpm == 30

    def test_default_bulkhead_limits(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.bulkhead_openai_concurrent == 10
        assert s.bulkhead_anthropic_concurrent == 10
        assert s.bulkhead_github_concurrent == 5
        assert s.bulkhead_notion_concurrent == 3
        assert s.bulkhead_gmail_concurrent == 5
        assert s.bulkhead_default_timeout == 30.0

    def test_default_request_size_limits(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.request_max_body_size == 10 * 1024 * 1024
        assert s.request_max_json_size == 1 * 1024 * 1024
        assert s.request_max_form_size == 50 * 1024 * 1024

    def test_default_brute_force_limits(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.brute_force_max_attempts_per_minute == 60
        assert s.brute_force_max_attempts_per_hour == 300
        assert s.brute_force_max_auth_attempts_per_minute == 5
        assert s.brute_force_max_auth_attempts_per_hour == 20
        assert s.brute_force_initial_block_seconds == 60.0
        assert s.brute_force_max_block_seconds == 3600.0

    def test_default_tracing(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.tracing_enabled is True
        assert s.tracing_service_name == "gorgon-api"
        assert s.tracing_sample_rate == 1.0


# =============================================================================
# Test Security Properties
# =============================================================================


class TestSecurityProperties:
    """Tests for has_secure_secret_key, has_secure_database, is_production_safe."""

    def test_insecure_default_key(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.has_secure_secret_key is False

    def test_short_key_is_insecure(self, tmp_path):
        s = _make_settings(tmp_path, secret_key="short")
        assert s.has_secure_secret_key is False

    def test_key_at_exactly_min_length(self, tmp_path):
        key = "a" * _MIN_SECRET_KEY_LENGTH
        s = _make_settings(tmp_path, secret_key=key)
        assert s.has_secure_secret_key is True

    def test_long_non_default_key_is_secure(self, tmp_path):
        key = "x" * 64
        s = _make_settings(tmp_path, secret_key=key)
        assert s.has_secure_secret_key is True

    def test_default_database_is_insecure(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.has_secure_database is False

    def test_custom_database_is_secure(self, tmp_path):
        s = _make_settings(tmp_path, database_url="postgresql://user:pass@host/db")
        assert s.has_secure_database is True

    def test_is_production_safe_both_secure(self, tmp_path):
        s = _make_settings(
            tmp_path,
            secret_key="x" * 64,
            database_url="postgresql://user:pass@host/db",
        )
        assert s.is_production_safe is True

    def test_is_production_safe_insecure_key(self, tmp_path):
        s = _make_settings(
            tmp_path,
            database_url="postgresql://user:pass@host/db",
        )
        assert s.is_production_safe is False

    def test_is_production_safe_insecure_db(self, tmp_path):
        s = _make_settings(tmp_path, secret_key="x" * 64)
        assert s.is_production_safe is False


# =============================================================================
# Test generate_secret_key
# =============================================================================


class TestGenerateSecretKey:
    """Tests for the static generate_secret_key method."""

    def test_returns_string(self):
        key = Settings.generate_secret_key()
        assert isinstance(key, str)

    def test_key_is_long_enough(self):
        key = Settings.generate_secret_key()
        assert len(key) >= _MIN_SECRET_KEY_LENGTH

    def test_keys_are_unique(self):
        keys = {Settings.generate_secret_key() for _ in range(10)}
        assert len(keys) == 10


# =============================================================================
# Test Credentials
# =============================================================================


class TestCredentials:
    """Tests for get_credentials_map and verify_credentials."""

    def test_no_credentials_returns_empty_map(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.get_credentials_map() == {}

    def test_single_credential_pair(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="alice:abc123")
        creds = s.get_credentials_map()
        assert creds == {"alice": "abc123"}

    def test_multiple_credential_pairs(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="alice:abc,bob:def")
        creds = s.get_credentials_map()
        assert creds == {"alice": "abc", "bob": "def"}

    def test_whitespace_trimmed(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="  alice : abc , bob : def  ")
        creds = s.get_credentials_map()
        assert creds == {"alice": "abc", "bob": "def"}

    def test_entry_without_colon_skipped(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="alice:abc,malformed,bob:def")
        creds = s.get_credentials_map()
        assert creds == {"alice": "abc", "bob": "def"}

    def test_colon_in_password_hash(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="alice:abc:extra")
        creds = s.get_credentials_map()
        # split(":", 1) means password_hash = "abc:extra"
        assert creds == {"alice": "abc:extra"}

    def test_verify_sha256_credentials(self, tmp_path):
        from hashlib import sha256

        password = "my-password"
        pw_hash = sha256(password.encode()).hexdigest()
        s = _make_settings(tmp_path, api_credentials=f"alice:{pw_hash}")
        assert s.verify_credentials("alice", password) is True

    def test_verify_sha256_wrong_password(self, tmp_path):
        from hashlib import sha256

        pw_hash = sha256(b"correct-password").hexdigest()
        s = _make_settings(tmp_path, api_credentials=f"alice:{pw_hash}")
        assert s.verify_credentials("alice", "wrong-password") is False

    def test_verify_bcrypt_credentials(self, tmp_path):
        import bcrypt

        password = "my-password"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        s = _make_settings(tmp_path, api_credentials=f"alice:{hashed}")
        assert s.verify_credentials("alice", password) is True

    def test_verify_bcrypt_wrong_password(self, tmp_path):
        import bcrypt

        hashed = bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode()
        s = _make_settings(tmp_path, api_credentials=f"alice:{hashed}")
        assert s.verify_credentials("alice", "wrong") is False

    def test_verify_unknown_user(self, tmp_path):
        s = _make_settings(tmp_path, api_credentials="alice:hash")
        assert s.verify_credentials("unknown", "whatever") is False

    def test_verify_demo_auth_enabled(self, tmp_path):
        s = _make_settings(tmp_path, allow_demo_auth=True)
        assert s.verify_credentials("anyone", "demo") is True

    def test_verify_demo_auth_wrong_password(self, tmp_path):
        s = _make_settings(tmp_path, allow_demo_auth=True)
        assert s.verify_credentials("anyone", "not-demo") is False

    def test_verify_demo_auth_disabled(self, tmp_path):
        s = _make_settings(tmp_path, allow_demo_auth=False)
        assert s.verify_credentials("anyone", "demo") is False

    def test_verify_configured_user_takes_precedence_over_demo(self, tmp_path):
        from hashlib import sha256

        pw_hash = sha256(b"realpass").hexdigest()
        s = _make_settings(
            tmp_path,
            api_credentials=f"alice:{pw_hash}",
            allow_demo_auth=True,
        )
        # "demo" should NOT work for alice because she has configured creds
        assert s.verify_credentials("alice", "demo") is False
        assert s.verify_credentials("alice", "realpass") is True


# =============================================================================
# Test model_post_init — Directory Creation
# =============================================================================


class TestModelPostInit:
    """Tests for model_post_init directory creation."""

    def test_creates_logs_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.logs_dir.exists()

    def test_creates_prompts_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.prompts_dir.exists()

    def test_creates_workflows_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.workflows_dir.exists()

    def test_creates_schedules_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.schedules_dir.exists()

    def test_creates_webhooks_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.webhooks_dir.exists()

    def test_creates_jobs_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.jobs_dir.exists()

    def test_creates_plugins_dir(self, tmp_path):
        s = _make_settings(tmp_path)
        assert s.plugins_dir.exists()

    def test_creates_nested_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        _make_settings(tmp_path, logs_dir=deep)
        assert deep.exists()


# =============================================================================
# Test Production Validation
# =============================================================================


class TestProductionValidation:
    """Tests for _validate_production_config."""

    def test_production_mode_rejects_insecure_key(self, tmp_path):
        with pytest.raises(ValueError, match="Insecure configuration"):
            _make_settings(tmp_path, production=True)

    def test_production_mode_rejects_short_key(self, tmp_path):
        with pytest.raises(ValueError, match="too short"):
            _make_settings(
                tmp_path,
                production=True,
                secret_key="short",
                database_url="postgresql://user:pass@host/db",
            )

    def test_production_mode_rejects_insecure_database(self, tmp_path):
        with pytest.raises(ValueError, match="DATABASE_URL"):
            _make_settings(
                tmp_path,
                production=True,
                secret_key="x" * 64,
            )

    def test_production_mode_rejects_debug(self, tmp_path):
        with pytest.raises(ValueError, match="DEBUG"):
            _make_settings(
                tmp_path,
                production=True,
                debug=True,
                secret_key="x" * 64,
                database_url="postgresql://user:pass@host/db",
            )

    def test_production_mode_rejects_demo_auth(self, tmp_path):
        with pytest.raises(ValueError, match="Demo authentication"):
            _make_settings(
                tmp_path,
                production=True,
                allow_demo_auth=True,
                secret_key="x" * 64,
                database_url="postgresql://user:pass@host/db",
            )

    def test_production_mode_accepts_secure_config(self, tmp_path):
        s = _make_settings(
            tmp_path,
            production=True,
            secret_key="x" * 64,
            database_url="postgresql://user:pass@host/db",
        )
        assert s.production is True

    def test_require_secure_config_enforces(self, tmp_path):
        with pytest.raises(ValueError, match="secure config"):
            _make_settings(tmp_path, require_secure_config=True)

    def test_dev_mode_warns_insecure_key(self, tmp_path):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _make_settings(tmp_path)
            security_warnings = [x for x in w if "Security" in str(x.message)]
            assert len(security_warnings) >= 1

    def test_dev_mode_warns_insecure_database(self, tmp_path):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _make_settings(tmp_path)
            db_warnings = [x for x in w if "DATABASE_URL" in str(x.message)]
            assert len(db_warnings) >= 1

    def test_secure_dev_mode_no_warnings(self, tmp_path):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _make_settings(
                tmp_path,
                secret_key="x" * 64,
                database_url="postgresql://user:pass@host/db",
            )
            security_warnings = [x for x in w if "Security" in str(x.message)]
            assert len(security_warnings) == 0

    def test_production_error_message_lists_all_issues(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            _make_settings(
                tmp_path,
                production=True,
                debug=True,
                allow_demo_auth=True,
            )
        msg = str(exc_info.value)
        assert "SECRET_KEY" in msg
        assert "DATABASE_URL" in msg
        assert "DEBUG" in msg
        assert "Demo authentication" in msg


# =============================================================================
# Test get_settings Cache
# =============================================================================


class TestGetSettings:
    """Tests for the cached get_settings function."""

    def test_returns_settings_instance(self):
        get_settings.cache_clear()
        s = get_settings()
        assert isinstance(s, Settings)

    def test_returns_same_instance(self):
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_creates_new_instance(self):
        get_settings.cache_clear()
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        assert s1 is not s2


# =============================================================================
# Test Custom Field Values
# =============================================================================


class TestCustomFieldValues:
    """Test creating Settings with custom values."""

    def test_custom_openai_key(self, tmp_path):
        s = _make_settings(tmp_path, openai_api_key="sk-test")
        assert s.openai_api_key == "sk-test"

    def test_custom_debug(self, tmp_path):
        s = _make_settings(tmp_path, debug=True)
        assert s.debug is True

    def test_custom_log_level(self, tmp_path):
        s = _make_settings(tmp_path, log_level="DEBUG")
        assert s.log_level == "DEBUG"

    def test_custom_shell_timeout(self, tmp_path):
        s = _make_settings(tmp_path, shell_timeout_seconds=600)
        assert s.shell_timeout_seconds == 600

    def test_custom_rate_limit(self, tmp_path):
        s = _make_settings(tmp_path, ratelimit_openai_rpm=120)
        assert s.ratelimit_openai_rpm == 120

    def test_custom_tracing_sample_rate(self, tmp_path):
        s = _make_settings(tmp_path, tracing_sample_rate=0.5)
        assert s.tracing_sample_rate == 0.5

    def test_extra_fields_ignored(self, tmp_path):
        """Extra fields in env should be ignored (extra='ignore')."""
        s = _make_settings(tmp_path, unknown_field="value")
        assert not hasattr(s, "unknown_field")


# =============================================================================
# Test Path Fields
# =============================================================================


class TestPathFields:
    """Tests for path-related fields."""

    def test_base_dir_is_path(self, tmp_path):
        s = _make_settings(tmp_path)
        assert isinstance(s.base_dir, Path)

    def test_logs_dir_is_path(self, tmp_path):
        s = _make_settings(tmp_path)
        assert isinstance(s.logs_dir, Path)

    def test_custom_paths(self, tmp_path):
        custom_logs = tmp_path / "custom_logs"
        s = _make_settings(tmp_path, logs_dir=custom_logs)
        assert s.logs_dir == custom_logs
        assert custom_logs.exists()
