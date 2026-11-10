"""Tests for the Animus Bootstrap daemon modules.

Covers:
- AnimusInstaller: OS detection, package manager detection, dependency checking,
  dependency installation, service registration, service lifecycle (start/stop/restart).
- AnimusSupervisor: Process start/stop, is_running, supervised restart loop.
- AnimusUpdater: Version fetching (local + PyPI), update comparison, pip upgrade.
- LinuxService: systemd unit generation, install, enable/start, stop, is_running.
- MacOSService: plist generation, install, load/unload agent, is_running.
- WindowsService: All methods raise NotImplementedError.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from animus_bootstrap.daemon.installer import AnimusInstaller
from animus_bootstrap.daemon.platforms.linux import (
    LinuxService,
)
from animus_bootstrap.daemon.platforms.macos import (
    _AGENT_LABEL,
    MacOSService,
)
from animus_bootstrap.daemon.platforms.windows import WindowsService
from animus_bootstrap.daemon.supervisor import AnimusSupervisor
from animus_bootstrap.daemon.updater import _PYPI_PACKAGE, _PYPI_URL, AnimusUpdater

# ======================================================================
# AnimusInstaller
# ======================================================================


class TestAnimusInstallerDetectOS:
    """AnimusInstaller.detect_os maps platform.system() to our canonical names."""

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    def test_linux(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().detect_os() == "linux"

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    def test_macos(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().detect_os() == "macos"

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Windows")
    def test_windows(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().detect_os() == "windows"

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="FreeBSD")
    def test_unknown_defaults_to_linux(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().detect_os() == "linux"


class TestAnimusInstallerDetectPackageManager:
    """AnimusInstaller.detect_package_manager checks binaries in priority order."""

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    def test_apt_found(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda b: "/usr/bin/apt" if b == "apt" else None
        assert AnimusInstaller().detect_package_manager() == "apt"

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    def test_dnf_found_when_apt_absent(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda b: "/usr/bin/dnf" if b == "dnf" else None
        assert AnimusInstaller().detect_package_manager() == "dnf"

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    def test_brew_found(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda b: "/opt/homebrew/bin/brew" if b == "brew" else None
        assert AnimusInstaller().detect_package_manager() == "brew"

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    def test_winget_found(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda b: "C:\\winget.exe" if b == "winget" else None
        assert AnimusInstaller().detect_package_manager() == "winget"

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value=None)
    def test_unknown_when_none_found(self, mock_which: MagicMock) -> None:
        assert AnimusInstaller().detect_package_manager() == "unknown"

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    def test_priority_order_apt_before_dnf(self, mock_which: MagicMock) -> None:
        """When both apt and dnf are present, apt wins (higher priority)."""
        mock_which.side_effect = lambda b: f"/usr/bin/{b}" if b in ("apt", "dnf") else None
        assert AnimusInstaller().detect_package_manager() == "apt"


class _FakeVersionInfo:
    """Mimics sys.version_info for tuple comparison and .major/.minor access."""

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor
        self._tuple = (major, minor)

    def __ge__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return self._tuple >= other
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return self._tuple < other
        return NotImplemented


class TestAnimusInstallerCheckDependencies:
    """AnimusInstaller.check_dependencies checks python version and binary availability."""

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_all_present(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        mock_sys.version_info = _FakeVersionInfo(3, 12)
        mock_which.side_effect = lambda b: f"/usr/bin/{b}"
        result = AnimusInstaller().check_dependencies()
        assert result["python3"] is True
        assert result["pip"] is True
        assert result["ollama"] is True
        assert result["ffmpeg"] is True

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value=None)
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_python_too_old(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        mock_sys.version_info = _FakeVersionInfo(3, 9)
        result = AnimusInstaller().check_dependencies()
        assert result["python3"] is False

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value=None)
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_pip_not_found(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        mock_sys.version_info = _FakeVersionInfo(3, 11)
        result = AnimusInstaller().check_dependencies()
        assert result["pip"] is False

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_pip3_fallback(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        """pip not found, but pip3 is found — pip should be True."""
        mock_sys.version_info = _FakeVersionInfo(3, 11)

        def which_side_effect(b: str) -> str | None:
            if b == "pip":
                return None
            if b == "pip3":
                return "/usr/bin/pip3"
            return None

        mock_which.side_effect = which_side_effect
        result = AnimusInstaller().check_dependencies()
        assert result["pip"] is True

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value=None)
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_optional_deps_missing(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        mock_sys.version_info = _FakeVersionInfo(3, 11)
        result = AnimusInstaller().check_dependencies()
        assert result["ollama"] is False
        assert result["ffmpeg"] is False

    @patch("animus_bootstrap.daemon.installer.shutil.which")
    @patch("animus_bootstrap.daemon.installer.sys")
    def test_exact_min_python_version(self, mock_sys: MagicMock, mock_which: MagicMock) -> None:
        """Python 3.11 exactly meets the minimum requirement."""
        mock_sys.version_info = _FakeVersionInfo(3, 11)
        mock_which.return_value = None
        result = AnimusInstaller().check_dependencies()
        assert result["python3"] is True


class TestAnimusInstallerInstallMissingDeps:
    """AnimusInstaller.install_missing_deps installs only missing required deps."""

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_pip_success(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        deps = {"python3": True, "pip": False, "ollama": False, "ffmpeg": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert "pip" in result
        # Optional deps (ollama, ffmpeg) are NOT installed
        assert "ollama" not in result
        assert "ffmpeg" not in result

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_python3_success(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        deps = {"python3": False, "pip": True}
        result = AnimusInstaller().install_missing_deps(deps)
        assert "python3" in result

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_failure_calledprocesserror(
        self, mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "apt", stderr=b"error msg")
        deps = {"python3": True, "pip": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert result == []

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_failure_calledprocesserror_no_stderr(
        self, mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "apt", stderr=None)
        deps = {"python3": True, "pip": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert result == []

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_timeout(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("apt", 30)
        deps = {"python3": True, "pip": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert result == []

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value=None)
    def test_install_unknown_package_manager(self, mock_which: MagicMock) -> None:
        deps = {"python3": True, "pip": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert result == []

    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_all_deps_already_present(self, mock_which: MagicMock) -> None:
        deps = {"python3": True, "pip": True, "ollama": True, "ffmpeg": True}
        result = AnimusInstaller().install_missing_deps(deps)
        assert result == []

    @patch("animus_bootstrap.daemon.installer.subprocess.run")
    @patch("animus_bootstrap.daemon.installer.shutil.which", return_value="/usr/bin/apt")
    def test_install_multiple_deps(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        """Both python3 and pip missing — both should be installed."""
        mock_run.return_value = MagicMock(returncode=0)
        deps = {"python3": False, "pip": False}
        result = AnimusInstaller().install_missing_deps(deps)
        assert "python3" in result
        assert "pip" in result
        assert mock_run.call_count == 2


class TestAnimusInstallerBuildInstallCommand:
    """AnimusInstaller._build_install_command returns correct commands per package manager."""

    def test_apt_python3(self) -> None:
        cmd = AnimusInstaller._build_install_command("apt", "python3")
        assert cmd == ["sudo", "apt", "install", "-y", "python3.11"]

    def test_apt_pip(self) -> None:
        cmd = AnimusInstaller._build_install_command("apt", "pip")
        assert cmd == ["sudo", "apt", "install", "-y", "python3-pip"]

    def test_dnf_python3(self) -> None:
        cmd = AnimusInstaller._build_install_command("dnf", "python3")
        assert cmd == ["sudo", "dnf", "install", "-y", "python3.11"]

    def test_brew_python3(self) -> None:
        cmd = AnimusInstaller._build_install_command("brew", "python3")
        assert cmd == ["brew", "install", "python@3.11"]

    def test_winget_python3(self) -> None:
        cmd = AnimusInstaller._build_install_command("winget", "python3")
        assert cmd == ["winget", "install", "--accept-package-agreements", "Python.Python.3.11"]

    def test_unknown_pkg_mgr_returns_none(self) -> None:
        cmd = AnimusInstaller._build_install_command("pacman", "python3")
        assert cmd is None

    def test_unknown_dep_name_returns_none(self) -> None:
        cmd = AnimusInstaller._build_install_command("apt", "unknown_dep")
        assert cmd is None


class TestAnimusInstallerRegisterService:
    """AnimusInstaller.register_service delegates to platform-specific service classes."""

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.install_unit", return_value=True)
    @patch(
        "animus_bootstrap.daemon.platforms.linux.LinuxService.generate_systemd_unit",
        return_value="[Unit]\n...",
    )
    def test_linux_success(
        self, mock_gen: MagicMock, mock_install: MagicMock, mock_sys: MagicMock
    ) -> None:
        assert AnimusInstaller().register_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch(
        "animus_bootstrap.daemon.platforms.linux.LinuxService.generate_systemd_unit",
        return_value="",
    )
    def test_linux_empty_unit_returns_false(self, mock_gen: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().register_service() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    @patch("animus_bootstrap.daemon.platforms.macos.MacOSService.install_plist", return_value=True)
    @patch(
        "animus_bootstrap.daemon.platforms.macos.MacOSService.generate_plist",
        return_value="<?xml ...",
    )
    def test_macos_success(
        self, mock_gen: MagicMock, mock_install: MagicMock, mock_sys: MagicMock
    ) -> None:
        assert AnimusInstaller().register_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    @patch(
        "animus_bootstrap.daemon.platforms.macos.MacOSService.generate_plist",
        return_value="",
    )
    def test_macos_empty_plist_returns_false(
        self, mock_gen: MagicMock, mock_sys: MagicMock
    ) -> None:
        assert AnimusInstaller().register_service() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Windows")
    def test_windows_raises_not_implemented(self, mock_sys: MagicMock) -> None:
        # WindowsService.install_service raises NotImplementedError, which is caught
        assert AnimusInstaller().register_service() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    def test_import_error_returns_false(self, mock_sys: MagicMock) -> None:
        with patch.dict("sys.modules", {"animus_bootstrap.daemon.platforms.linux": None}):
            assert AnimusInstaller().register_service() is False


class TestAnimusInstallerServiceLifecycle:
    """AnimusInstaller.is_service_running, start_service, stop_service, restart_service."""

    # --- is_service_running ---

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.is_running", return_value=True)
    def test_is_running_linux_true(self, mock_running: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().is_service_running() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.is_running", return_value=False)
    def test_is_running_linux_false(self, mock_running: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().is_service_running() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    @patch("animus_bootstrap.daemon.platforms.macos.MacOSService.is_running", return_value=True)
    def test_is_running_macos(self, mock_running: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().is_service_running() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Windows")
    def test_is_running_windows_not_implemented(self, mock_sys: MagicMock) -> None:
        # WindowsService.is_running raises NotImplementedError, caught as False
        assert AnimusInstaller().is_service_running() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    def test_is_running_import_error(self, mock_sys: MagicMock) -> None:
        with patch.dict("sys.modules", {"animus_bootstrap.daemon.platforms.linux": None}):
            assert AnimusInstaller().is_service_running() is False

    # --- start_service ---

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch(
        "animus_bootstrap.daemon.platforms.linux.LinuxService.enable_and_start",
        return_value=True,
    )
    def test_start_linux(self, mock_start: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().start_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    @patch("animus_bootstrap.daemon.platforms.macos.MacOSService.load_agent", return_value=True)
    def test_start_macos(self, mock_load: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().start_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Windows")
    def test_start_windows_not_implemented(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().start_service() is False

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    def test_start_import_error(self, mock_sys: MagicMock) -> None:
        with patch.dict("sys.modules", {"animus_bootstrap.daemon.platforms.linux": None}):
            assert AnimusInstaller().start_service() is False

    # --- stop_service ---

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.stop", return_value=True)
    def test_stop_linux(self, mock_stop: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().stop_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Darwin")
    @patch("animus_bootstrap.daemon.platforms.macos.MacOSService.stop", return_value=True)
    def test_stop_macos(self, mock_stop: MagicMock, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().stop_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Windows")
    def test_stop_windows_not_implemented(self, mock_sys: MagicMock) -> None:
        assert AnimusInstaller().stop_service() is False

    # --- restart_service ---

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch(
        "animus_bootstrap.daemon.platforms.linux.LinuxService.enable_and_start",
        return_value=True,
    )
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.stop", return_value=True)
    def test_restart_linux(
        self, mock_stop: MagicMock, mock_start: MagicMock, mock_sys: MagicMock
    ) -> None:
        assert AnimusInstaller().restart_service() is True

    @patch("animus_bootstrap.daemon.installer.platform.system", return_value="Linux")
    @patch(
        "animus_bootstrap.daemon.platforms.linux.LinuxService.enable_and_start",
        return_value=True,
    )
    @patch("animus_bootstrap.daemon.platforms.linux.LinuxService.stop", return_value=False)
    def test_restart_continues_after_stop_fails(
        self, mock_stop: MagicMock, mock_start: MagicMock, mock_sys: MagicMock
    ) -> None:
        """Restart attempts start even if stop returns False."""
        assert AnimusInstaller().restart_service() is True


# ======================================================================
# AnimusSupervisor
# ======================================================================


class TestAnimusSupervisorInit:
    """AnimusSupervisor stores its configuration correctly."""

    def test_defaults(self) -> None:
        sup = AnimusSupervisor("python -m animus")
        assert sup.target == "python -m animus"
        assert sup.max_restarts == 5
        assert sup.restart_delay == 2.0
        assert sup._process is None
        assert sup._restart_count == 0

    def test_custom_values(self) -> None:
        sup = AnimusSupervisor("echo hello", max_restarts=3, restart_delay=0.5)
        assert sup.max_restarts == 3
        assert sup.restart_delay == 0.5


class TestAnimusSupervisorStart:
    """AnimusSupervisor.start creates a Popen subprocess."""

    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_start_creates_process(self, mock_popen: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        sup = AnimusSupervisor("python -m animus")
        sup.start()
        mock_popen.assert_called_once_with(
            ["python", "-m", "animus"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert sup._process is mock_proc

    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_start_already_running_skips(self, mock_popen: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        sup = AnimusSupervisor("python -m animus")
        sup.start()
        sup.start()  # Second call should be a no-op
        assert mock_popen.call_count == 1

    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_start_os_error_propagates(self, mock_popen: MagicMock) -> None:
        mock_popen.side_effect = OSError("No such file")
        sup = AnimusSupervisor("nonexistent_cmd")
        with pytest.raises(OSError, match="No such file"):
            sup.start()


class TestAnimusSupervisorStop:
    """AnimusSupervisor.stop sends SIGTERM, then SIGKILL on timeout."""

    def test_stop_no_process(self) -> None:
        sup = AnimusSupervisor("echo")
        sup.stop()  # Should not raise
        assert sup._process is None

    def test_stop_already_exited(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already exited
        sup._process = mock_proc
        sup.stop()
        assert sup._process is None
        mock_proc.terminate.assert_not_called()

    def test_stop_graceful_termination(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_proc.poll.return_value = None  # Running
        sup._process = mock_proc
        sup.stop()
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()
        assert sup._process is None

    def test_stop_sigterm_timeout_sends_sigkill(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("echo", 10), None]
        sup._process = mock_proc
        sup.stop()
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert sup._process is None

    def test_stop_sigkill_also_times_out(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("echo", 10)
        sup._process = mock_proc
        sup.stop()
        mock_proc.kill.assert_called_once()
        assert sup._process is None

    def test_stop_oserror_handled(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_proc.poll.return_value = None
        mock_proc.terminate.side_effect = OSError("Permission denied")
        sup._process = mock_proc
        sup.stop()
        assert sup._process is None


class TestAnimusSupervisorIsRunning:
    """AnimusSupervisor.is_running checks process poll()."""

    def test_no_process(self) -> None:
        sup = AnimusSupervisor("echo")
        assert sup.is_running() is False

    def test_process_running(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        sup._process = mock_proc
        assert sup.is_running() is True

    def test_process_exited(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        sup._process = mock_proc
        assert sup.is_running() is False


class TestAnimusSupervisorPid:
    """AnimusSupervisor.pid property returns PID when running."""

    def test_pid_when_no_process(self) -> None:
        sup = AnimusSupervisor("echo")
        assert sup.pid is None

    def test_pid_when_running(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_proc.poll.return_value = None
        sup._process = mock_proc
        assert sup.pid == 42

    def test_pid_when_exited(self) -> None:
        sup = AnimusSupervisor("echo")
        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_proc.poll.return_value = 1
        sup._process = mock_proc
        assert sup.pid is None


class TestAnimusSupervisorRunSupervised:
    """AnimusSupervisor.run_supervised manages the restart lifecycle."""

    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_clean_exit_stops_loop(self, mock_popen: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 100
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        sup = AnimusSupervisor("echo hello")
        sup.run_supervised()
        assert mock_popen.call_count == 1

    @patch("animus_bootstrap.daemon.supervisor.time.sleep")
    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_crash_and_restart(self, mock_popen: MagicMock, mock_sleep: MagicMock) -> None:
        """Process crashes once (exit code 1) then exits cleanly (code 0)."""

        def _make_proc(pid: int, exit_code: int) -> MagicMock:
            """Mock process: poll returns None while 'alive', exit_code after wait."""
            proc = MagicMock()
            proc.pid = pid
            waited = {"done": False}

            def _poll() -> int | None:
                return exit_code if waited["done"] else None

            def _wait(**kwargs: object) -> int:
                waited["done"] = True
                return exit_code

            proc.poll.side_effect = _poll
            proc.wait.side_effect = _wait
            return proc

        mock_popen.side_effect = [_make_proc(100, 1), _make_proc(101, 0)]

        sup = AnimusSupervisor("echo", max_restarts=3, restart_delay=0.0)
        sup.run_supervised()
        assert mock_popen.call_count == 2
        assert sup._restart_count == 1

    @patch("animus_bootstrap.daemon.supervisor.time.sleep")
    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_max_restarts_exceeded(self, mock_popen: MagicMock, mock_sleep: MagicMock) -> None:
        """Process crashes repeatedly until max_restarts is exceeded."""

        def _make_crash_proc() -> MagicMock:
            proc = MagicMock()
            proc.pid = 100
            waited = {"done": False}

            def _poll() -> int | None:
                return 1 if waited["done"] else None

            def _wait(**kwargs: object) -> int:
                waited["done"] = True
                return 1

            proc.poll.side_effect = _poll
            proc.wait.side_effect = _wait
            return proc

        mock_popen.side_effect = [_make_crash_proc() for _ in range(3)]

        sup = AnimusSupervisor("echo", max_restarts=2, restart_delay=0.0)
        sup.run_supervised()
        # 1 initial start + 2 restarts = 3 total
        assert mock_popen.call_count == 3
        assert sup._restart_count == 3

    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_keyboard_interrupt_during_wait(self, mock_popen: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 100
        mock_proc.poll.return_value = None
        # First wait() call (in run_supervised) raises KeyboardInterrupt;
        # second wait() call (in stop()) succeeds.
        mock_proc.wait.side_effect = [KeyboardInterrupt(), None]
        mock_popen.return_value = mock_proc

        sup = AnimusSupervisor("echo")
        sup.run_supervised()
        mock_proc.terminate.assert_called_once()

    @patch("animus_bootstrap.daemon.supervisor.time.sleep", side_effect=KeyboardInterrupt())
    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_keyboard_interrupt_during_delay(
        self, mock_popen: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 100
        waited = {"done": False}
        mock_proc.poll.side_effect = lambda: 1 if waited["done"] else None

        def _wait(**kwargs: object) -> int:
            waited["done"] = True
            return 1

        mock_proc.wait.side_effect = _wait
        mock_popen.return_value = mock_proc

        sup = AnimusSupervisor("echo", max_restarts=3, restart_delay=1.0)
        sup.run_supervised()
        assert sup._process is None

    @patch("animus_bootstrap.daemon.supervisor.time.sleep")
    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_oserror_on_start_retries(self, mock_popen: MagicMock, mock_sleep: MagicMock) -> None:
        """OSError during start counts as a restart attempt."""
        mock_proc = MagicMock()
        mock_proc.pid = 100
        waited = {"done": False}
        mock_proc.poll.side_effect = lambda: 0 if waited["done"] else None

        def _wait(**kwargs: object) -> int:
            waited["done"] = True
            return 0

        mock_proc.wait.side_effect = _wait
        mock_popen.side_effect = [OSError("not found"), mock_proc]

        sup = AnimusSupervisor("echo", max_restarts=3, restart_delay=0.0)
        sup.run_supervised()
        assert mock_popen.call_count == 2
        assert sup._restart_count == 1

    @patch("animus_bootstrap.daemon.supervisor.time.sleep")
    @patch("animus_bootstrap.daemon.supervisor.subprocess.Popen")
    def test_oserror_exceeds_max_restarts(
        self, mock_popen: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_popen.side_effect = OSError("not found")
        sup = AnimusSupervisor("echo", max_restarts=2, restart_delay=0.0)
        sup.run_supervised()
        # 1 initial + 2 retries = 3 total attempts
        assert mock_popen.call_count == 3


# ======================================================================
# AnimusUpdater
# ======================================================================


class TestAnimusUpdaterGetCurrentVersion:
    """AnimusUpdater.get_current_version reads from importlib.metadata."""

    @patch("animus_bootstrap.daemon.updater.version", return_value="1.2.3")
    def test_installed_version(self, mock_ver: MagicMock) -> None:
        assert AnimusUpdater().get_current_version() == "1.2.3"
        mock_ver.assert_called_once_with(_PYPI_PACKAGE)

    @patch(
        "animus_bootstrap.daemon.updater.version",
        side_effect=__import__(
            "importlib.metadata", fromlist=["PackageNotFoundError"]
        ).PackageNotFoundError,
    )
    def test_not_installed_returns_0_0_0(self, mock_ver: MagicMock) -> None:
        assert AnimusUpdater().get_current_version() == "0.0.0"


class TestAnimusUpdaterGetLatestVersion:
    """AnimusUpdater.get_latest_version queries PyPI JSON API."""

    @patch("httpx.get")
    def test_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"info": {"version": "2.0.0"}}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        assert AnimusUpdater().get_latest_version() == "2.0.0"
        mock_get.assert_called_once_with(_PYPI_URL, timeout=30)

    @patch("httpx.get")
    def test_http_error(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        )
        mock_get.return_value = mock_resp

        assert AnimusUpdater().get_latest_version() == "0.0.0"

    @patch("httpx.get", side_effect=httpx.RequestError("Connection timeout"))
    def test_request_error(self, mock_get: MagicMock) -> None:
        assert AnimusUpdater().get_latest_version() == "0.0.0"

    @patch("httpx.get")
    def test_malformed_json(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"wrong": "schema"}
        mock_get.return_value = mock_resp

        assert AnimusUpdater().get_latest_version() == "0.0.0"

    @patch("httpx.get")
    def test_json_decode_error(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("not json")
        mock_get.return_value = mock_resp

        assert AnimusUpdater().get_latest_version() == "0.0.0"

    def test_httpx_not_installed(self) -> None:
        with patch.dict("sys.modules", {"httpx": None}):
            updater = AnimusUpdater()
            assert updater.get_latest_version() == "0.0.0"


class TestAnimusUpdaterIsUpdateAvailable:
    """AnimusUpdater.is_update_available compares version strings."""

    @patch.object(AnimusUpdater, "get_latest_version", return_value="2.0.0")
    @patch.object(AnimusUpdater, "get_current_version", return_value="1.0.0")
    def test_update_available(self, mock_curr: MagicMock, mock_latest: MagicMock) -> None:
        assert AnimusUpdater().is_update_available() is True

    @patch.object(AnimusUpdater, "get_latest_version", return_value="1.0.0")
    @patch.object(AnimusUpdater, "get_current_version", return_value="1.0.0")
    def test_already_up_to_date(self, mock_curr: MagicMock, mock_latest: MagicMock) -> None:
        assert AnimusUpdater().is_update_available() is False

    @patch.object(AnimusUpdater, "get_latest_version", return_value="0.9.0")
    @patch.object(AnimusUpdater, "get_current_version", return_value="1.0.0")
    def test_current_newer_than_latest(self, mock_curr: MagicMock, mock_latest: MagicMock) -> None:
        assert AnimusUpdater().is_update_available() is False

    @patch.object(AnimusUpdater, "get_latest_version", return_value="0.0.0")
    @patch.object(AnimusUpdater, "get_current_version", return_value="0.0.0")
    def test_both_zero(self, mock_curr: MagicMock, mock_latest: MagicMock) -> None:
        assert AnimusUpdater().is_update_available() is False

    @patch.object(AnimusUpdater, "get_latest_version", return_value="not_a_version")
    @patch.object(AnimusUpdater, "get_current_version", return_value="1.0.0")
    def test_invalid_version_string(self, mock_curr: MagicMock, mock_latest: MagicMock) -> None:
        assert AnimusUpdater().is_update_available() is False

    def test_packaging_not_installed(self) -> None:
        with patch.dict("sys.modules", {"packaging": None, "packaging.version": None}):
            updater = AnimusUpdater()
            assert updater.is_update_available() is False


class TestAnimusUpdaterApplyUpdate:
    """AnimusUpdater.apply_update runs pip install --upgrade."""

    @patch("animus_bootstrap.daemon.updater.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"Successfully installed animus-bootstrap-2.0.0"
        )
        assert AnimusUpdater().apply_update() is True
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--upgrade", _PYPI_PACKAGE],
            check=True,
            capture_output=True,
            timeout=30,
        )

    @patch("animus_bootstrap.daemon.updater.subprocess.run")
    def test_calledprocesserror(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "pip", stderr=b"could not find package"
        )
        assert AnimusUpdater().apply_update() is False

    @patch("animus_bootstrap.daemon.updater.subprocess.run")
    def test_calledprocesserror_no_stderr(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "pip", stderr=None)
        assert AnimusUpdater().apply_update() is False

    @patch("animus_bootstrap.daemon.updater.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("pip", 30)
        assert AnimusUpdater().apply_update() is False


# ======================================================================
# LinuxService
# ======================================================================


class TestLinuxServiceGenerateUnit:
    """LinuxService.generate_systemd_unit produces valid systemd unit content."""

    def test_contains_required_sections(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "animus_bootstrap.daemon")
        assert "[Unit]" in unit
        assert "[Service]" in unit
        assert "[Install]" in unit

    def test_exec_start_line(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "animus_bootstrap.daemon")
        assert "ExecStart=/usr/bin/python3 -m animus_bootstrap.daemon" in unit

    def test_restart_on_failure(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        assert "Restart=on-failure" in unit

    def test_wanted_by_default_target(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        assert "WantedBy=default.target" in unit

    def test_pythonunbuffered_env(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        assert "PYTHONUNBUFFERED=1" in unit

    def test_description(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        assert "Description=Animus AI Exocortex Daemon" in unit

    def test_network_dependencies(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        assert "After=network-online.target" in unit
        assert "Wants=network-online.target" in unit

    def test_integrity_precheck_can_be_omitted_for_bootstrap_only(self) -> None:
        svc = LinuxService()
        with_integrity = svc.generate_systemd_unit("/usr/bin/python3", "mod")
        bootstrap_only = svc.generate_systemd_unit(
            "/usr/bin/python3", "mod", verify_integrity=False
        )
        assert "ExecStartPre=/usr/bin/python3 -m animus.integrity.cli verify" in with_integrity
        assert "ExecStartPre=" not in bootstrap_only

    def test_pwa_environment_and_runtime_hardening(self) -> None:
        svc = LinuxService()
        unit = svc.generate_systemd_unit(
            "/usr/bin/python3",
            "mod",
            pwa_dir="/opt/animus/pwa dist%stable",
            verify_integrity=False,
        )
        assert 'Environment="ANIMUS_PWA_DIR=/opt/animus/pwa dist%%stable"' in unit
        assert "WorkingDirectory=/" in unit
        assert "NoNewPrivileges=true" in unit
        assert "UMask=0077" in unit
        assert "Environment=PYTHONNOUSERSITE=1" in unit

    @pytest.mark.parametrize("pwa_dir", ["relative/pwa", "../pwa"])
    def test_rejects_relative_pwa_directory(self, pwa_dir: str) -> None:
        svc = LinuxService()
        with pytest.raises(ValueError, match="absolute path"):
            svc.generate_systemd_unit("/usr/bin/python3", "mod", pwa_dir=pwa_dir)

    def test_rejects_newline_in_pwa_directory(self) -> None:
        svc = LinuxService()
        with pytest.raises(ValueError, match="newlines"):
            svc.generate_systemd_unit(
                "/usr/bin/python3", "mod", pwa_dir="/opt/animus/pwa\nEnvironment=BAD=1"
            )


class TestLinuxServiceInstallUnit:
    """LinuxService.install_unit writes the unit file and reloads systemd."""

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_success(self, mock_dir: MagicMock, mock_file: MagicMock, mock_run: MagicMock) -> None:
        mock_dir.mkdir = MagicMock()
        mock_file.write_text = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)

        svc = LinuxService()
        assert svc.install_unit() is True
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.write_text.assert_called_once()
        mock_run.assert_called_once()

    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_write_oserror(self, mock_dir: MagicMock, mock_file: MagicMock) -> None:
        mock_dir.mkdir = MagicMock()
        mock_file.write_text.side_effect = OSError("Permission denied")

        svc = LinuxService()
        assert svc.install_unit() is False

    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_missing_pwa_directory_fails_closed(
        self, mock_dir: MagicMock, mock_file: MagicMock
    ) -> None:
        svc = LinuxService()
        assert svc.install_unit(pwa_dir="/definitely/missing/animus-pwa") is False
        mock_dir.mkdir.assert_not_called()
        mock_file.write_text.assert_not_called()

    @patch("animus_bootstrap.daemon.platforms.linux._integrity_cli_available", return_value=False)
    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_bootstrap_only_install_writes_pwa_path_without_integrity_precheck(
        self,
        mock_dir: MagicMock,
        mock_file: MagicMock,
        mock_run: MagicMock,
        _mock_integrity: MagicMock,
        tmp_path: Path,
    ) -> None:
        pwa_dir = tmp_path / "pwa"
        pwa_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0)

        svc = LinuxService()
        assert svc.install_unit(pwa_dir=str(pwa_dir)) is True

        unit = mock_file.write_text.call_args.args[0]
        assert f'Environment="ANIMUS_PWA_DIR={pwa_dir}"' in unit
        assert "ExecStartPre=" not in unit

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_daemon_reload_failure(
        self, mock_dir: MagicMock, mock_file: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_dir.mkdir = MagicMock()
        mock_file.write_text = MagicMock()
        mock_run.side_effect = subprocess.CalledProcessError(1, "systemctl", stderr=b"error")

        svc = LinuxService()
        assert svc.install_unit() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_daemon_reload_timeout(
        self, mock_dir: MagicMock, mock_file: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_dir.mkdir = MagicMock()
        mock_file.write_text = MagicMock()
        mock_run.side_effect = subprocess.TimeoutExpired("systemctl", 30)

        svc = LinuxService()
        assert svc.install_unit() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_FILE")
    @patch("animus_bootstrap.daemon.platforms.linux._UNIT_DIR")
    def test_daemon_reload_systemctl_not_found(
        self, mock_dir: MagicMock, mock_file: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_dir.mkdir = MagicMock()
        mock_file.write_text = MagicMock()
        mock_run.side_effect = FileNotFoundError("systemctl")

        svc = LinuxService()
        assert svc.install_unit() is False


class TestLinuxServiceEnableAndStart:
    """LinuxService.enable_and_start runs systemctl enable then start."""

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        svc = LinuxService()
        assert svc.enable_and_start() is True
        assert mock_run.call_count == 2

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_enable_fails(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "systemctl", stderr=b"failed")
        svc = LinuxService()
        assert svc.enable_and_start() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_start_timeout(self, mock_run: MagicMock) -> None:
        # enable succeeds, start times out
        mock_run.side_effect = [
            MagicMock(returncode=0),
            subprocess.TimeoutExpired("systemctl", 30),
        ]
        svc = LinuxService()
        assert svc.enable_and_start() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_systemctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("systemctl")
        svc = LinuxService()
        assert svc.enable_and_start() is False


class TestLinuxServiceStop:
    """LinuxService.stop runs systemctl --user stop."""

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        svc = LinuxService()
        assert svc.stop() is True

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "systemctl", stderr=b"error")
        svc = LinuxService()
        assert svc.stop() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("systemctl", 30)
        svc = LinuxService()
        assert svc.stop() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_systemctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("systemctl")
        svc = LinuxService()
        assert svc.stop() is False


class TestLinuxServiceIsRunning:
    """LinuxService.is_running checks systemctl --user is-active."""

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout=b"active\n", returncode=0)
        svc = LinuxService()
        assert svc.is_running() is True

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_inactive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout=b"inactive\n", returncode=3)
        svc = LinuxService()
        assert svc.is_running() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_failed_state(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout=b"failed\n", returncode=3)
        svc = LinuxService()
        assert svc.is_running() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("systemctl", 30)
        svc = LinuxService()
        assert svc.is_running() is False

    @patch("animus_bootstrap.daemon.platforms.linux.subprocess.run")
    def test_systemctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("systemctl")
        svc = LinuxService()
        assert svc.is_running() is False


# ======================================================================
# MacOSService
# ======================================================================


class TestMacOSServiceGeneratePlist:
    """MacOSService.generate_plist produces valid plist XML content."""

    def test_contains_xml_header(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "animus_bootstrap.daemon")
        assert '<?xml version="1.0"' in plist

    def test_contains_label(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "animus_bootstrap.daemon")
        assert f"<string>{_AGENT_LABEL}</string>" in plist

    def test_program_arguments(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "animus_bootstrap.daemon")
        assert "<string>/usr/bin/python3</string>" in plist
        assert "<string>-m</string>" in plist
        assert "<string>animus_bootstrap.daemon</string>" in plist

    def test_run_at_load(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "mod")
        assert "<key>RunAtLoad</key>" in plist
        assert "<true/>" in plist

    def test_keep_alive(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "mod")
        assert "<key>KeepAlive</key>" in plist

    def test_log_paths(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "mod")
        assert "animus.out.log" in plist
        assert "animus.err.log" in plist

    def test_pythonunbuffered(self) -> None:
        svc = MacOSService()
        plist = svc.generate_plist("/usr/bin/python3", "mod")
        assert "<key>PYTHONUNBUFFERED</key>" in plist
        assert "<string>1</string>" in plist


class TestMacOSServiceInstallPlist:
    """MacOSService.install_plist writes the plist file."""

    @patch("animus_bootstrap.daemon.platforms.macos._PLIST_FILE")
    @patch("animus_bootstrap.daemon.platforms.macos._LAUNCH_AGENTS_DIR")
    def test_success(self, mock_agents_dir: MagicMock, mock_plist_file: MagicMock) -> None:
        mock_agents_dir.mkdir = MagicMock()
        mock_plist_file.write_text = MagicMock()
        # Also need to mock the log dir creation
        with patch("animus_bootstrap.daemon.platforms.macos.Path") as mock_path_cls:
            mock_log_dir = MagicMock()
            mock_path_cls.home.return_value.__truediv__ = MagicMock(
                return_value=MagicMock(__truediv__=MagicMock(return_value=mock_log_dir))
            )
            # Actually, the generate_plist also uses Path.home, so let's simplify
            # by just mocking the mkdir calls to not fail
            svc = MacOSService()
            assert svc.install_plist() is True

    @patch("animus_bootstrap.daemon.platforms.macos._PLIST_FILE")
    @patch("animus_bootstrap.daemon.platforms.macos._LAUNCH_AGENTS_DIR")
    def test_oserror(self, mock_agents_dir: MagicMock, mock_plist_file: MagicMock) -> None:
        mock_agents_dir.mkdir.side_effect = OSError("Permission denied")
        svc = MacOSService()
        assert svc.install_plist() is False


class TestMacOSServiceLoadAgent:
    """MacOSService.load_agent runs launchctl load."""

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        svc = MacOSService()
        assert svc.load_agent() is True

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "launchctl", stderr=b"error")
        svc = MacOSService()
        assert svc.load_agent() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("launchctl", 30)
        svc = MacOSService()
        assert svc.load_agent() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_launchctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("launchctl")
        svc = MacOSService()
        assert svc.load_agent() is False


class TestMacOSServiceStop:
    """MacOSService.stop runs launchctl unload."""

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        svc = MacOSService()
        assert svc.stop() is True

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "launchctl", stderr=b"error")
        svc = MacOSService()
        assert svc.stop() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("launchctl", 30)
        svc = MacOSService()
        assert svc.stop() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_launchctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("launchctl")
        svc = MacOSService()
        assert svc.stop() is False


class TestMacOSServiceIsRunning:
    """MacOSService.is_running checks launchctl list output."""

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_running(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        svc = MacOSService()
        assert svc.is_running() is True

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_not_running(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        svc = MacOSService()
        assert svc.is_running() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("launchctl", 30)
        svc = MacOSService()
        assert svc.is_running() is False

    @patch("animus_bootstrap.daemon.platforms.macos.subprocess.run")
    def test_launchctl_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("launchctl")
        svc = MacOSService()
        assert svc.is_running() is False


# ======================================================================
# WindowsService
# ======================================================================


class TestWindowsService:
    """WindowsService — delegates to sc.exe via subprocess."""

    @patch("animus_bootstrap.daemon.platforms.windows.subprocess.run")
    @patch("animus_bootstrap.daemon.platforms.windows._run_sc")
    def test_install_service(self, mock_sc: MagicMock, _mock_run: MagicMock) -> None:
        mock_sc.return_value = MagicMock(returncode=0)
        assert WindowsService().install_service() is True
        mock_sc.assert_called_once()

    @patch("animus_bootstrap.daemon.platforms.windows._run_sc")
    def test_start(self, mock_sc: MagicMock) -> None:
        mock_sc.return_value = MagicMock(returncode=0)
        assert WindowsService().start() is True

    @patch("animus_bootstrap.daemon.platforms.windows._run_sc")
    def test_stop(self, mock_sc: MagicMock) -> None:
        mock_sc.return_value = MagicMock(returncode=0)
        assert WindowsService().stop() is True

    @patch("animus_bootstrap.daemon.platforms.windows.subprocess.run")
    def test_is_running(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="STATE : 4  RUNNING")
        assert WindowsService().is_running() is True

    @patch("animus_bootstrap.daemon.platforms.windows.subprocess.run")
    def test_is_not_running(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="STATE : 1  STOPPED")
        assert WindowsService().is_running() is False

    @patch("animus_bootstrap.daemon.platforms.windows._run_sc")
    @patch("animus_bootstrap.daemon.platforms.windows.subprocess.run")
    def test_uninstall_service(self, mock_run: MagicMock, mock_sc: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="STOPPED")
        mock_sc.return_value = MagicMock(returncode=0)
        assert WindowsService().uninstall_service() is True

    @patch("animus_bootstrap.daemon.platforms.windows._run_sc")
    def test_install_sc_not_found(self, mock_sc: MagicMock) -> None:
        mock_sc.side_effect = FileNotFoundError
        assert WindowsService().install_service() is False
