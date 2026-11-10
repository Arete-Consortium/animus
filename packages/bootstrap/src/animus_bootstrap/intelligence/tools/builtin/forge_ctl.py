"""Forge management tools — start, stop, status, and invoke the Forge orchestration engine."""

from __future__ import annotations

import asyncio
import json
import logging

from animus_bootstrap.intelligence.tools.executor import ToolDefinition

logger = logging.getLogger(__name__)

_DEFAULT_FORGE_HOST = "127.0.0.1"
_DEFAULT_FORGE_PORT = 8000
_DEFAULT_TIMEOUT = 10.0


async def _forge_status(host: str = _DEFAULT_FORGE_HOST, port: int = _DEFAULT_FORGE_PORT) -> str:
    """Check if the Forge API is reachable and return its health status."""
    try:
        import httpx
    except ImportError:
        return "httpx not installed — cannot reach Forge API"

    url = f"http://{host}:{port}/health"
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return f"Forge is running: {json.dumps(data, indent=2)}"
            return f"Forge responded with HTTP {resp.status_code}: {resp.text[:500]}"
    except httpx.ConnectError:
        return f"Forge is not reachable at {url}"
    except httpx.HTTPError as exc:
        return f"Error checking Forge status: {exc}"


async def _forge_start(host: str = _DEFAULT_FORGE_HOST, port: int = _DEFAULT_FORGE_PORT) -> str:
    """Start the Forge orchestration engine via systemd or direct uvicorn."""
    # Try systemd first
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "is-active",
            "animus-forge",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        status = stdout.decode().strip()
        if status == "active":
            return "Forge is already running (systemd service active)"
    except (FileNotFoundError, TimeoutError):
        pass  # systemd not available, try direct start

    # Try systemd start
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "start",
            "animus-forge",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode == 0:
            logger.info("Forge started via systemd")
            return "Forge started via systemd service"
        logger.warning("systemd start failed: %s", stderr.decode().strip())
    except (FileNotFoundError, TimeoutError):
        logger.debug("systemd start unavailable, trying uvicorn fallback")

    # Fallback: direct uvicorn launch
    try:
        proc = await asyncio.create_subprocess_exec(
            "uvicorn",
            "animus_forge.api:app",
            "--host",
            host,
            "--port",
            str(port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Don't wait for completion — it's a long-running server
        await asyncio.sleep(2)
        if proc.returncode is None:
            logger.info("Forge started via uvicorn (PID %d)", proc.pid)
            return f"Forge started via uvicorn (PID {proc.pid}) on {host}:{port}"
        _, stderr = await proc.communicate()
        return f"Forge failed to start: {stderr.decode().strip()}"
    except FileNotFoundError:
        return "Neither systemctl nor uvicorn found — cannot start Forge"
    except OSError as exc:
        return f"Error starting Forge: {exc}"


async def _forge_stop() -> str:
    """Stop the Forge orchestration engine."""
    # Try systemd first
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "stop",
            "animus-forge",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode == 0:
            logger.info("Forge stopped via systemd")
            return "Forge stopped via systemd service"
        logger.warning("systemd stop failed: %s", stderr.decode().strip())
    except (FileNotFoundError, TimeoutError):
        logger.debug("systemd stop unavailable, trying pkill fallback")

    # Fallback: kill the uvicorn process
    try:
        proc = await asyncio.create_subprocess_exec(
            "pkill",
            "-f",
            "uvicorn animus_forge",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            return "Forge process killed"
        return "No Forge process found to stop"
    except OSError as exc:
        return f"Error stopping Forge: {exc}"


async def _forge_invoke(
    endpoint: str,
    method: str = "GET",
    body: str = "",
    host: str = _DEFAULT_FORGE_HOST,
    port: int = _DEFAULT_FORGE_PORT,
) -> str:
    """Invoke an arbitrary Forge API endpoint."""
    try:
        import httpx
    except ImportError:
        return "httpx not installed — cannot reach Forge API"

    url = f"http://{host}:{port}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                resp = await client.get(url)
            elif method.upper() == "POST":
                payload = json.loads(body) if body else {}
                resp = await client.post(url, json=payload)
            elif method.upper() == "PUT":
                payload = json.loads(body) if body else {}
                resp = await client.put(url, json=payload)
            elif method.upper() == "DELETE":
                resp = await client.delete(url)
            else:
                return f"Unsupported HTTP method: {method}"

        # Truncate large responses
        text = resp.text[:2000]
        return f"HTTP {resp.status_code}:\n{text}"
    except json.JSONDecodeError:
        return f"Invalid JSON body: {body[:200]}"
    except httpx.ConnectError:
        return f"Forge is not reachable at {url}"
    except httpx.HTTPError as exc:
        return f"Forge invoke error: {exc}"


def get_forge_tools() -> list[ToolDefinition]:
    """Return Forge management tool definitions. All require approval."""
    return [
        ToolDefinition(
            name="forge_status",
            description="Check if the Forge orchestration engine is running and healthy.",
            parameters={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Forge API host.",
                        "default": _DEFAULT_FORGE_HOST,
                    },
                    "port": {
                        "type": "integer",
                        "description": "Forge API port.",
                        "default": _DEFAULT_FORGE_PORT,
                    },
                },
            },
            handler=_forge_status,
            category="forge",
            permission="auto",
        ),
        ToolDefinition(
            name="forge_start",
            description=(
                "Start the Forge orchestration engine. "
                "Tries systemd first, falls back to direct uvicorn launch. Requires approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Host to bind Forge on.",
                        "default": _DEFAULT_FORGE_HOST,
                    },
                    "port": {
                        "type": "integer",
                        "description": "Port to bind Forge on.",
                        "default": _DEFAULT_FORGE_PORT,
                    },
                },
            },
            handler=_forge_start,
            category="forge",
            permission="approve",
        ),
        ToolDefinition(
            name="forge_stop",
            description="Stop the Forge orchestration engine. Requires approval.",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=_forge_stop,
            category="forge",
            permission="approve",
        ),
        ToolDefinition(
            name="forge_invoke",
            description=(
                "Invoke an arbitrary Forge API endpoint. "
                "Returns the HTTP status code and response body."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "API path (e.g. '/api/v1/workflows').",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method: GET, POST, PUT, DELETE.",
                        "default": "GET",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON body for POST/PUT requests.",
                        "default": "",
                    },
                    "host": {
                        "type": "string",
                        "description": "Forge API host.",
                        "default": _DEFAULT_FORGE_HOST,
                    },
                    "port": {
                        "type": "integer",
                        "description": "Forge API port.",
                        "default": _DEFAULT_FORGE_PORT,
                    },
                },
                "required": ["endpoint"],
            },
            handler=_forge_invoke,
            category="forge",
            permission="approve",
        ),
    ]
