"""Tests for the read-only Forgehand relay status endpoint."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from animus_bootstrap.dashboard.routers import operations_status


@pytest.mark.asyncio()
async def test_probe_reports_responding_when_local_http_listener_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid HTTP response on a protected socket is reported as responding."""
    received: list[bytes] = []
    runtime_dir = "/tmp/animus-relay-runtime"
    socket_path = f"{runtime_dir}/forgehand-action-relay.sock"

    async def fake_open_unix_connection(
        *, path: str, limit: int
    ) -> tuple[asyncio.StreamReader, object]:
        assert path == socket_path
        assert limit == 4096

        class Reader:
            async def readline(self) -> bytes:
                return b"HTTP/1.0 404 Not Found\r\n"

        class Writer:
            def write(self, data: bytes) -> None:
                received.append(data)

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                return None

            async def wait_closed(self) -> None:
                return None

        return Reader(), Writer()

    original_lstat = Path.lstat

    def fake_lstat(path: Path) -> object:
        path_string = str(path)
        if path_string == runtime_dir:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=os.getuid())
        if path_string == socket_path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid())
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(asyncio, "open_unix_connection", fake_open_unix_connection)
    monkeypatch.setenv("XDG_RUNTIME_DIR", runtime_dir)

    assert await operations_status._probe_relay() == "responding"

    assert received and received[0].startswith(
        b"GET /__forgehand_preflight__ HTTP/1.0\r\n"
    )


@pytest.mark.asyncio()
async def test_probe_rejects_unprotected_runtime_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A runtime directory with broader permissions is never probed."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(mode=0o755)
    (runtime_dir / "forgehand-action-relay.sock").touch(mode=0o600)
    os.chmod(runtime_dir, 0o755)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    assert await operations_status._probe_relay() == "unsafe"


@pytest.mark.asyncio()
async def test_probe_reports_unconfigured_when_runtime_directory_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    assert await operations_status._probe_relay() == "not_configured"


@pytest.mark.asyncio()
async def test_api_response_contains_only_coarse_relay_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def responding() -> str:
        return "responding"

    monkeypatch.setattr(operations_status, "_probe_relay", responding)
    monkeypatch.setattr(operations_status, "_cached_at", 0.0)
    monkeypatch.setattr(operations_status, "_cached_payload", None)

    payload = await operations_status.operations_status()

    assert set(payload) == {"checked_at", "forgehand_relay"}
    assert payload["forgehand_relay"] == {"status": "responding"}
    assert "runtime" not in str(payload)
