"""CSRF protection for the Animus dashboard.

Generates a per-session token stored in a secure cookie and validates it
on every state-changing POST request.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_CSRF_COOKIE_NAME = "animus_csrf"
_CSRF_HEADER_NAME = "x-csrf-token"


def generate_csrf_token() -> str:
    """Generate a new random CSRF token."""
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    """Retrieve or create a CSRF token for the current session."""
    token: str | None = request.cookies.get(_CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token


class CsrfMiddleware(BaseHTTPMiddleware):
    """Validate CSRF token on state-changing requests and ensure cookie is set."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[object]],
    ) -> object:
        # Ensure a CSRF cookie exists for every request
        cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
        if not cookie_token:
            cookie_token = generate_csrf_token()

        # Only validate POST/PUT/DELETE/PATCH
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Skip validation for public/health endpoints
            path = request.url.path
            if path in ("/health", "/api/health") or path.startswith("/static"):
                response = await call_next(request)
                set_csrf_cookie(response, cookie_token)
                return response  # type: ignore[return-value]

            # Validate Origin header for same-origin policy.  Use the request
            # scheme so direct TLS/Tailscale HTTPS is not rejected as HTTP.
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if origin:
                expected_origin = f"{request.url.scheme}://{host}"
                if origin.rstrip("/") != expected_origin.rstrip("/"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Invalid Origin header."},
                    )

            # The PWA uses same-origin JSON requests and bearer auth rather
            # than ambient cookie authentication.  A cross-site form cannot
            # send application/json, and cross-origin fetches are rejected by
            # the Origin check above (as well as CORS).  Keep CSRF tokens
            # mandatory for HTMX/form and other non-JSON mutations.
            media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
            if path.startswith("/api/") and media_type == "application/json":
                response = await call_next(request)
                set_csrf_cookie(response, cookie_token)
                return response  # type: ignore[return-value]

            # Validate CSRF token (header only — reading form body consumes the stream
            # and breaks downstream FastAPI form parsers).
            submitted = request.headers.get(_CSRF_HEADER_NAME)
            if not submitted or not secrets.compare_digest(cookie_token, submitted):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Missing or invalid CSRF token."},
                )

        response = await call_next(request)
        set_csrf_cookie(response, cookie_token)
        return response  # type: ignore[return-value]


def set_csrf_cookie(response: object, token: str) -> None:
    """Attach the CSRF token as a secure cookie to the response."""
    from fastapi.responses import Response

    if isinstance(response, Response):
        response.set_cookie(
            _CSRF_COOKIE_NAME,
            token,
            httponly=True,
            samesite="strict",
            secure=False,  # Localhost only; reverse proxy handles HTTPS
            path="/",
        )
