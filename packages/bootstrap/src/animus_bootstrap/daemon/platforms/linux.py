"""Linux systemd user service management."""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 30
_SERVICE_NAME = "animus"
_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
_UNIT_FILE = _UNIT_DIR / f"{_SERVICE_NAME}.service"


def _integrity_cli_available() -> bool:
    """Return whether the selected interpreter can run the Core integrity CLI."""
    try:
        return importlib.util.find_spec("animus.integrity.cli") is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def _systemd_environment(name: str, value: str) -> str:
    """Render one non-secret systemd environment assignment safely."""
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} must not contain newlines")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'Environment="{name}={escaped}"'


class LinuxService:
    """Manages Animus as a systemd user service."""

    def generate_systemd_unit(
        self,
        python_path: str,
        module: str,
        *,
        pwa_dir: str | None = None,
        verify_integrity: bool = True,
    ) -> str:
        """Generate a systemd unit file for the Animus daemon.

        Args:
            python_path: Absolute path to the Python interpreter.
            module: Python module to run (e.g. "animus_bootstrap.daemon").
            pwa_dir: Optional absolute path to the built React PWA.
            verify_integrity: Add the Core integrity pre-start gate when available.

        Returns:
            Unit file content as a string.
        """
        if pwa_dir is not None and not Path(pwa_dir).expanduser().is_absolute():
            raise ValueError("pwa_dir must be an absolute path")

        lines = [
            "[Unit]",
            "Description=Animus AI Exocortex Daemon",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "WorkingDirectory=/",
        ]
        if verify_integrity:
            # C1-8: run the canonical Core integrity CLI in a separate process.
            # A non-zero exit aborts startup; Bootstrap-only installs omit this
            # line because the verifier does not exist in that interpreter.
            lines.append(f"ExecStartPre={python_path} -m animus.integrity.cli verify")
        lines.extend(
            [
                f"ExecStart={python_path} -m {module}",
                "Restart=on-failure",
                "RestartSec=5",
                "NoNewPrivileges=true",
                "UMask=0077",
                "Environment=PYTHONUNBUFFERED=1",
                "Environment=PYTHONNOUSERSITE=1",
            ]
        )
        if pwa_dir is not None:
            lines.append(_systemd_environment("ANIMUS_PWA_DIR", str(Path(pwa_dir).expanduser())))
        lines.extend(["", "[Install]", "WantedBy=default.target", ""])
        unit = "\n".join(lines)
        logger.debug("Generated systemd unit:\n%s", unit)
        return unit

    def install_unit(
        self,
        *,
        pwa_dir: str | None = None,
        verify_integrity: bool | None = None,
    ) -> bool:
        """Write the systemd unit file to the user service directory.

        Creates ~/.config/systemd/user/ if it doesn't exist.

        Returns:
            True if the unit file was written successfully.
        """
        import sys

        python_path = sys.executable
        module = "animus_bootstrap.daemon"
        configured_pwa_dir = pwa_dir or os.environ.get("ANIMUS_PWA_DIR")
        if configured_pwa_dir is not None and not Path(configured_pwa_dir).expanduser().is_dir():
            logger.error("PWA directory does not exist: %s", configured_pwa_dir)
            return False

        should_verify = _integrity_cli_available() if verify_integrity is None else verify_integrity
        if not should_verify:
            logger.warning("Core integrity CLI unavailable; omitting systemd pre-start verifier")
        content = self.generate_systemd_unit(
            python_path,
            module,
            pwa_dir=configured_pwa_dir,
            verify_integrity=should_verify,
        )

        try:
            _UNIT_DIR.mkdir(parents=True, exist_ok=True)
            _UNIT_FILE.write_text(content)
            logger.info("Installed unit file: %s", _UNIT_FILE)
        except OSError as exc:
            logger.error("Failed to write unit file: %s", exc)
            return False

        # Reload systemd to pick up the new unit
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            logger.info("systemd user daemon reloaded")
        except subprocess.CalledProcessError as exc:
            logger.error(
                "daemon-reload failed: %s",
                exc.stderr.decode(errors="replace") if exc.stderr else str(exc),
            )
            return False
        except subprocess.TimeoutExpired:
            logger.error("daemon-reload timed out")
            return False
        except FileNotFoundError:
            logger.error("systemctl not found — is systemd installed?")
            return False

        return True

    def enable_and_start(self) -> bool:
        """Enable and start the Animus systemd user service.

        Returns:
            True if both enable and start succeeded.
        """
        for action in ("enable", "start"):
            try:
                subprocess.run(
                    ["systemctl", "--user", action, f"{_SERVICE_NAME}.service"],
                    check=True,
                    capture_output=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
                logger.info("systemctl --user %s %s: OK", action, _SERVICE_NAME)
            except subprocess.CalledProcessError as exc:
                logger.error(
                    "systemctl --user %s failed: %s",
                    action,
                    exc.stderr.decode(errors="replace") if exc.stderr else str(exc),
                )
                return False
            except subprocess.TimeoutExpired:
                logger.error("systemctl --user %s timed out", action)
                return False
            except FileNotFoundError:
                logger.error("systemctl not found")
                return False

        return True

    def stop(self) -> bool:
        """Stop the Animus systemd user service.

        Returns:
            True if stop succeeded.
        """
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", f"{_SERVICE_NAME}.service"],
                check=True,
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            logger.info("Stopped %s service", _SERVICE_NAME)
            return True
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to stop service: %s",
                exc.stderr.decode(errors="replace") if exc.stderr else str(exc),
            )
            return False
        except subprocess.TimeoutExpired:
            logger.error("systemctl stop timed out")
            return False
        except FileNotFoundError:
            logger.error("systemctl not found")
            return False

    def is_running(self) -> bool:
        """Check if the Animus systemd user service is active.

        Returns:
            True if the service is in "active" state.
        """
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", f"{_SERVICE_NAME}.service"],
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            active = result.stdout.decode().strip() == "active"
            logger.debug("Service %s: %s", _SERVICE_NAME, "active" if active else "inactive")
            return active
        except subprocess.TimeoutExpired:
            logger.error("systemctl is-active timed out")
            return False
        except FileNotFoundError:
            logger.error("systemctl not found")
            return False
