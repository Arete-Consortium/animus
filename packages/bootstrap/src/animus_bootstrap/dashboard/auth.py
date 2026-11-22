"""Bearer-token auth helpers for the dashboard/PWA API surface.

The dashboard is dual-natured: it serves HTMX pages to a local browser *and*
a JSON/WebSocket API consumed by the remote PWA (over a Tailscale tunnel).
These helpers implement a single shared bearer token — auto-generated on first
run and stored in the chmod-600 config file — that protects only the PWA
surface while leaving the local HTMX dashboard frictionless.
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from animus_bootstrap.config.manager import ConfigManager
    from animus_bootstrap.config.schema import AnimusConfig

logger = logging.getLogger(__name__)

# Hosts that identify a local client / loopback binding.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def ensure_auth_token(config: AnimusConfig, manager: ConfigManager) -> str:
    """Return the configured auth token, generating + persisting one if empty.

    The token is generated with :func:`secrets.token_urlsafe` and saved via
    :class:`ConfigManager` (which chmod-600s the file). The value is never
    logged; an operator can retrieve it directly from the protected config.

    Args:
        config: The loaded configuration (mutated in place when generating).
        manager: Used to persist a freshly generated token.

    Returns:
        The auth token (never empty).
    """
    token = config.services.auth_token
    if token:
        return token

    token = secrets.token_urlsafe(32)
    config.services.auth_token = token
    manager.save(config)
    logger.info("Generated Animus remote-access token in the protected config file")
    return token


def auth_required_for(config: AnimusConfig) -> bool:
    """Return whether bearer auth should be enforced for this configuration.

    - ``"always"`` → always enforce.
    - ``"never"`` → never enforce.
    - ``"auto"`` (default) → enforce only when bound to a non-local host,
      i.e. the server is reachable from another device.
    """
    mode = config.services.auth_required
    if mode == "always":
        return True
    if mode == "never":
        return False
    return config.services.host not in _LOCAL_HOSTS


def is_local_client(request: Request) -> bool:
    """Return ``True`` if the request originates from the loopback interface."""
    client = request.client
    if client is None:
        return False
    return client.host in _LOCAL_HOSTS


def verify_bearer(authorization: str | None, token: str) -> bool:
    """Constant-time check of an ``Authorization: Bearer <token>`` header."""
    if not authorization or not token:
        return False
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return False
    return secrets.compare_digest(value, token)


def verify_ws_token(provided: str | None, token: str) -> bool:
    """Constant-time check of a token received via WebSocket subprotocol."""
    if not provided or not token:
        return False
    return secrets.compare_digest(provided, token)
