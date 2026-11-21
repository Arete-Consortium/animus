"""Read-only operational connectivity status for the authenticated PWA."""

from __future__ import annotations

import asyncio
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_CACHE_SECONDS = 30.0
_PROBE_TIMEOUT_SECONDS = 1.0
_cached_at = 0.0
_cached_payload: dict[str, object] | None = None
_cache_lock = asyncio.Lock()


async def _probe_relay() -> str:
    """Return a deliberately coarse state after a harmless HTTP request."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        return "not_configured"

    runtime_path = Path(runtime_dir)
    if not runtime_path.is_absolute():
        return "unsafe"

    try:
        runtime_info = runtime_path.lstat()
        socket_path = runtime_path / "forgehand-action-relay.sock"
        socket_info = socket_path.lstat()
    except OSError:
        return "unavailable"

    if (
        stat.S_ISLNK(runtime_info.st_mode)
        or not stat.S_ISDIR(runtime_info.st_mode)
        or runtime_info.st_uid != os.getuid()
        or stat.S_IMODE(runtime_info.st_mode) != 0o700
        or not stat.S_ISSOCK(socket_info.st_mode)
        or socket_info.st_uid != os.getuid()
        or stat.S_IMODE(socket_info.st_mode) != 0o600
    ):
        return "unsafe"

    async def request_preflight() -> bool:
        reader, writer = await asyncio.open_unix_connection(
            path=str(socket_path), limit=4096
        )
        try:
            writer.write(
                b"GET /__forgehand_preflight__ HTTP/1.0\r\n"
                b"Host: localhost\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            status_line = await reader.readline()
            fields = status_line.decode("ascii", errors="replace").split()
            return (
                len(fields) >= 2
                and fields[0].startswith("HTTP/")
                and fields[1].isdigit()
                and 100 <= int(fields[1]) <= 599
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    try:
        responded = await asyncio.wait_for(
            request_preflight(), timeout=_PROBE_TIMEOUT_SECONDS
        )
    except (
        OSError,
        TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
        ValueError,
    ):
        return "unavailable"
    return "responding" if responded else "unavailable"


@router.get("/api/operations/status")
async def operations_status() -> dict[str, object]:
    """Report relay responsiveness without invoking a model or exposing host data."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if _cached_payload is not None and now - _cached_at < _CACHE_SECONDS:
            return _cached_payload

        state = await _probe_relay()
        payload: dict[str, object] = {
            "checked_at": datetime.now(UTC).isoformat(),
            "forgehand_relay": {"status": state},
        }
        _cached_at = time.monotonic()
        _cached_payload = payload
        return payload
