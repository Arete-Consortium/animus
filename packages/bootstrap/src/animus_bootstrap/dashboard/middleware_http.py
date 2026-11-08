"""Default-deny bearer-auth middleware for the dashboard.

A remote (non-local) client must present a valid bearer token for EVERY
route except a small public allowlist (static assets + the bare liveness
probe). Local clients (loopback) are exempt, keeping the on-box HTMX
dashboard frictionless.

This is default-DENY by client locality, NOT an allowlist of "/api" paths.
The earlier design gated only the ``/api`` prefix, which left the most
dangerous endpoints — all served on BARE paths (``/tools/execute``,
``/config``, ``/memory/export``, ``/self-mod``, ``/update/apply``,
``/proposals/*``) — completely unauthenticated for any remote client once
the box was bound for remote access. Locality, not URL shape, is the trust
boundary, so the token is required across the whole surface.

The active configuration is read from ``request.app.state.config`` at
dispatch time so a token generated during ``serve()`` is picked up without
rebuilding the middleware stack.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from animus_bootstrap.config.schema import AnimusConfig
from animus_bootstrap.dashboard.auth import (
    auth_required_for,
    is_local_client,
    verify_bearer,
)

# The ONLY routes a not-yet-authenticated remote client may reach: static
# assets, the PWA shell, and the bare, non-sensitive liveness probe. Anything
# carrying data, secrets, or a mutation requires the token. Keep this list
# minimal — every addition widens the unauthenticated remote surface.
_PUBLIC_PREFIXES: tuple[str, ...] = ("/static/", "/pwa/")
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/pwa", "/pwa/"})


def _is_public(path: str) -> bool:
    """Return ``True`` only for the minimal unauthenticated remote allowlist."""
    return path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """Require a bearer token from non-local clients for all non-public routes."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[object]],
    ) -> object:
        config: AnimusConfig | None = getattr(request.app.state, "config", None)
        if (
            config is not None
            and auth_required_for(config)
            and not is_local_client(request)
            and not _is_public(request.url.path)
        ):
            header = request.headers.get("Authorization")
            if not verify_bearer(header, config.services.auth_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid bearer token."},
                )
        return await call_next(request)  # type: ignore[return-value]
