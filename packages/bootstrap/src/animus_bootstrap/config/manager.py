"""Configuration manager for reading/writing Animus config files."""

from __future__ import annotations

import logging
import os
import platform
import stat
import tomllib
from collections.abc import Mapping
from pathlib import Path

import tomli_w

from animus_bootstrap.config.defaults import DEFAULT_CONFIG
from animus_bootstrap.config.schema import AnimusConfig

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path("~/.config/animus").expanduser()
_CONFIG_FILE = "config.toml"


class ConfigManager:
    """Manages reading, writing, and locating the Animus config file.

    The config lives at ``~/.config/animus/config.toml``.  If the file does
    not exist, :meth:`load` returns an :class:`AnimusConfig` populated
    entirely from defaults.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or _CONFIG_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> AnimusConfig:
        """Load configuration from disk, falling back to defaults.

        Returns:
            Fully populated :class:`AnimusConfig` instance.
        """
        path = self.get_config_path()
        if not path.is_file():
            logger.debug("Config file not found at %s, using defaults", path)
            return AnimusConfig()

        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            logger.warning("Failed to read config at %s: %s — using defaults", path, exc)
            return AnimusConfig()

        merged = _deep_merge(DEFAULT_CONFIG, raw)
        return AnimusConfig.model_validate(merged)

    def save(self, config: AnimusConfig) -> None:
        """Persist configuration to disk as TOML.

        On Linux and macOS the file is ``chmod 600`` to protect API keys.

        Args:
            config: The configuration to write.
        """
        path = self.get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        data = config.model_dump()
        with open(path, "wb") as fh:
            tomli_w.dump(data, fh)

        if platform.system() in ("Linux", "Darwin"):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

        logger.debug("Config saved to %s", path)

    def exists(self) -> bool:
        """Return ``True`` if the config file exists on disk."""
        return self.get_config_path().is_file()

    def get_config_path(self) -> Path:
        """Return the full path to the config TOML file."""
        return self._config_dir / _CONFIG_FILE

    def get_data_dir(self) -> Path:
        """Return the data directory, creating it if it does not exist.

        The path is read from the current config (or defaults if no
        config file is present).
        """
        config = self.load()
        data_dir = config.get_data_path()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _deep_merge(base: Mapping[str, object], override: Mapping[str, object]) -> dict[str, object]:
    """Recursively merge *override* into a copy of *base*.

    Keys in *override* take precedence.  Nested dicts are merged rather
    than replaced so that partial TOML sections work correctly.
    """
    merged: dict[str, object] = {}
    for key in {*base, *override}:
        base_val = base.get(key)
        over_val = override.get(key)
        if isinstance(base_val, dict) and isinstance(over_val, dict):
            merged[key] = _deep_merge(base_val, over_val)  # type: ignore[arg-type]
        elif key in override:
            merged[key] = over_val
        else:
            merged[key] = base_val
    return merged
