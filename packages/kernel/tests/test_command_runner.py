"""Tests for the general-purpose command runner."""

from __future__ import annotations

import asyncio
import shlex
import sys

import pytest

from animus_kernel.builder.command_runner import (
    CommandResult,
    _truncate_bytes,
    _validate_command,
    _validate_cwd,
    arun,
    run,
)
from animus_kernel.tools.safety import SecurityError


class TestValidateCommand:
    def test_empty_command_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            _validate_command("")

    def test_whitespace_only_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            _validate_command("   ")

    @pytest.mark.parametrize("seq", [";", "|", "&&"])
    def test_blocked_sequences(self, seq):
        with pytest.raises(SecurityError, match="forbidden shell sequence"):
            _validate_command(f"echo hi {seq} echo bye")

    def test_dangerous_mkfs_blocked(self):
        with pytest.raises(SecurityError, match="Dangerous command blocked"):
            _validate_command("mkfs.ext4 /dev/sda1")

    def test_dangerous_dd_blocked(self):
        with pytest.raises(SecurityError, match="Dangerous command blocked"):
            _validate_command("dd if=/dev/zero of=/dev/sda")

    def test_dangerous_rm_root_blocked(self):
        with pytest.raises(SecurityError, match="Dangerous command blocked"):
            _validate_command("rm -rf /")

    def test_valid_command_returns_tokens(self):
        tokens = _validate_command("echo hello world")
        assert tokens == ["echo", "hello", "world"]

    def test_file_not_found_propagates(self, tmp_path):
        # FileNotFoundError is raised by Popen when binary missing
        with pytest.raises(SecurityError, match="Command not found"):
            run("/nonexistent_binary_12345", cwd=str(tmp_path))


class TestValidateCwd:
    def test_missing_directory_raises(self):
        with pytest.raises(SecurityError, match="does not exist"):
            _validate_cwd("/does/not/exist")

    def test_file_not_directory_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(SecurityError, match="not a directory"):
            _validate_cwd(str(f))

    def test_valid_returns_resolved_path(self, tmp_path):
        path = _validate_cwd(str(tmp_path))
        assert path == tmp_path.resolve()


class TestTruncateBytes:
    def test_no_truncation(self):
        data = b"hello"
        assert _truncate_bytes(data, 10) == (b"hello", False)

    def test_truncation(self):
        data = b"hello world"
        assert _truncate_bytes(data, 5) == (b"hello", True)


class TestRun:
    def test_echo_command(self, tmp_path):
        result = run("echo hello", cwd=str(tmp_path))
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.stderr == ""
        assert result.timeout is False
        assert result.duration_ms >= 0

    def test_stderr_capture(self, tmp_path):
        result = run("python3 -c \"import sys; sys.stderr.write('err\\n')\"", cwd=str(tmp_path))
        assert result.exit_code == 0
        assert "err" in result.stderr

    def test_timeout(self, tmp_path):
        result = run("sleep 5", cwd=str(tmp_path), timeout=0.1)
        assert result.timeout is True
        assert result.exit_code != 0 or result.timeout

    def test_nonexistent_command(self, tmp_path):
        with pytest.raises(SecurityError, match="Command not found"):
            run("__not_a_real_command__", cwd=str(tmp_path))

    def test_truncation(self, tmp_path):
        # Produce output larger than 10 MB default limit
        result = run("python3 -c \"print('x' * (11 * 1024 * 1024))\"", cwd=str(tmp_path))
        assert result.truncated is True

    def test_env_passed(self, tmp_path):
        result = run(
            f"{shlex.quote(sys.executable)} -c \"import os; print(os.environ.get('TEST_VAR'))\"",
            cwd=str(tmp_path),
            env={"TEST_VAR": "42"},
        )
        assert "42" in result.stdout


class TestArun:
    def test_echo_async(self, tmp_path):
        result = asyncio.run(arun("echo async", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert "async" in result.stdout

    def test_timeout_async(self, tmp_path):
        result = asyncio.run(arun("sleep 5", cwd=str(tmp_path), timeout=0.1))
        assert result.timeout is True

    def test_stderr_async(self, tmp_path):
        result = asyncio.run(
            arun("python3 -c \"import sys; sys.stderr.write('err\\n')\"", cwd=str(tmp_path))
        )
        assert "err" in result.stderr


class TestCommandResult:
    def test_result_is_frozen(self):
        result = CommandResult(
            exit_code=0, stdout="", stderr="", duration_ms=1.0, timeout=False, truncated=False
        )
        with pytest.raises(Exception):
            result.exit_code = 1
