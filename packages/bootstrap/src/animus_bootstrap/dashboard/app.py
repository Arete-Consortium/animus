"""Animus Bootstrap dashboard — FastAPI application."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import animus_bootstrap
from animus_bootstrap.config import ConfigManager
from animus_bootstrap.dashboard.auth import auth_required_for, verify_ws_token
from animus_bootstrap.dashboard.csrf import CsrfMiddleware, get_csrf_token
from animus_bootstrap.dashboard.middleware_http import AuthMiddleware
from animus_bootstrap.dashboard.routers import (
    activity,
    automations,
    capture,
    channels_page,
    citizens_page,
    config,
    controls,
    conversations,
    events,
    feedback,
    forge_page,
    home,
    identity_page,
    ledger,
    logs,
    memory,
    personas_page,
    proposals,
    push,
    routing_page,
    self_mod,
    session,
    tasks_page,
    timers_page,
    tools,
    update,
)
from animus_bootstrap.gateway.channels.webchat import WebChatAdapter
from animus_bootstrap.runtime import AnimusRuntime, get_runtime

logger = logging.getLogger(__name__)

_DASHBOARD_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _DASHBOARD_DIR / "static"
_TEMPLATE_DIR = _DASHBOARD_DIR / "templates"


def _resolve_pwa_dir() -> Path:
    """Return the configured PWA build directory or the monorepo default."""
    configured = os.environ.get("ANIMUS_PWA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _DASHBOARD_DIR.parent.parent.parent.parent / "pwa" / "dist"


_PWA_DIR = _resolve_pwa_dir()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start runtime on boot, stop on shutdown."""
    runtime = get_runtime()
    try:
        await runtime.start()
    except Exception:
        logger.warning("Runtime start failed — dashboard running in limited mode")
    app.state.runtime = runtime

    # Wire the approval callback so dashboard can approve LLM-initiated tools
    if runtime.started and getattr(runtime, "tool_executor", None) is not None:
        from animus_bootstrap.dashboard.routers.tools import dashboard_approval_callback

        runtime.tool_executor.set_approval_callback(dashboard_approval_callback)

    # Expose the push subscription store to the push router.
    app.state.push_store = getattr(runtime, "push_store", None)

    # Wire the WebChat adapter to the router so messages get processed
    webchat: WebChatAdapter = app.state.webchat
    await webchat.connect()
    if runtime.started and runtime.router is not None:
        _wire_webchat(webchat, runtime)

    yield

    await webchat.disconnect()
    if runtime.started:
        await runtime.stop()


def _wire_webchat(webchat: WebChatAdapter, runtime: AnimusRuntime) -> None:
    """Connect webchat incoming messages to the router and responses back."""
    from animus_bootstrap.dashboard.routers.conversations import get_message_store
    from animus_bootstrap.gateway.models import GatewayMessage, GatewayResponse

    async def _on_webchat_message(message: GatewayMessage) -> None:
        """Route an incoming webchat message and send the reply back."""
        store = get_message_store()
        # Log user message in the feed
        store.append(
            {
                "channel": message.channel,
                "sender": message.sender_name,
                "text": message.text,
                "timestamp": message.timestamp.isoformat(),
            }
        )

        try:
            response: GatewayResponse = await runtime.router.handle_message(message)
        except Exception:
            logger.exception("Router failed to handle webchat message")
            response = GatewayResponse(text="Sorry, something went wrong.", channel="webchat")

        # Log assistant message in the feed
        store.append(
            {
                "channel": response.channel,
                "sender": "Animus",
                "text": response.text,
                "timestamp": message.timestamp.isoformat(),
            }
        )

        # Send reply back through the WebSocket
        await webchat.send_message(response)

    import asyncio

    runtime.router.register_channel("webchat", webchat)
    asyncio.ensure_future(webchat.on_message(_on_webchat_message))


app = FastAPI(
    title="Animus Dashboard",
    version=animus_bootstrap.__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Load config once for middleware/WS auth. Stored on app.state so serve()
# can refresh it after generating the remote-access token. With the default
# localhost binding, auth is a no-op (see auth_required_for).
app.state.config = ConfigManager().load()

# CORS — tightened to localhost only for security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7700"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

# CSRF protection for state-changing requests
app.add_middleware(CsrfMiddleware)

# Bearer-token auth for the PWA API surface (no-op for local HTMX dashboard).
app.add_middleware(AuthMiddleware)

# Static files — dashboard assets
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# PWA static files — built React app mounted at /pwa
if _PWA_DIR.is_dir():
    app.mount("/pwa", StaticFiles(directory=str(_PWA_DIR), html=True), name="pwa")
else:
    logger.warning("PWA build directory not found at %s — skipping mount", _PWA_DIR)

# Jinja2 templates (shared across routers via app.state)
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
templates.env.globals["version"] = animus_bootstrap.__version__


def _csrf_context(request: Request) -> dict[str, str]:
    """Inject CSRF token into every template context."""
    return {"csrf_token": get_csrf_token(request)}


templates.env.globals["csrf_token"] = _csrf_context
app.state.templates = templates

# Shared WebChat adapter instance
_webchat = WebChatAdapter()
app.state.webchat = _webchat

# Include routers
app.include_router(home.router)
app.include_router(conversations.router)
app.include_router(channels_page.router)
app.include_router(config.router)
app.include_router(memory.router)
app.include_router(logs.router)
app.include_router(update.router)
app.include_router(tools.router)
app.include_router(automations.router)
app.include_router(activity.router)
app.include_router(events.router)
app.include_router(citizens_page.router)
app.include_router(personas_page.router)
app.include_router(routing_page.router)
app.include_router(self_mod.router)
app.include_router(forge_page.router)
app.include_router(tasks_page.router)
app.include_router(timers_page.router)
app.include_router(feedback.router)
app.include_router(identity_page.router)
app.include_router(proposals.router)
app.include_router(session.router)
app.include_router(capture.router)
app.include_router(push.router)
app.include_router(controls.router)
app.include_router(ledger.router)


def _health_payload(request: Request) -> dict[str, object]:
    """Build the health status dict for the runtime and its components."""
    runtime: AnimusRuntime | None = getattr(request.app.state, "runtime", None)
    return {
        "status": "ok" if runtime and runtime.started else "degraded",
        "version": animus_bootstrap.__version__,
        "components": {
            "memory": runtime.memory_manager is not None if runtime else False,
            "tools": runtime.tool_executor is not None if runtime else False,
            "proactive": runtime.proactive_engine is not None if runtime else False,
            "automations": runtime.automation_engine is not None if runtime else False,
        },
    }


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Return JSON health status (unauthenticated, for local probes/daemon)."""
    return JSONResponse(_health_payload(request))


@app.get("/api/health")
async def api_health(request: Request) -> JSONResponse:
    """Health for the PWA — same payload, behind the bearer-auth surface.

    The PWA also uses this endpoint to validate a token at login time.
    """
    return JSONResponse(_health_payload(request))


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket endpoint for the browser-based WebChat channel.

    When remote auth is active, a valid ``animus-auth.<token>`` offered
    subprotocol is required from non-local clients. The token is not put in
    the URL, where server and proxy access logs may capture it.
    """
    config = getattr(websocket.app.state, "config", None)
    offered_protocols = websocket.scope.get("subprotocols", [])
    auth_prefix = "animus-auth."
    provided_token = next(
        (
            protocol[len(auth_prefix) :]
            for protocol in offered_protocols
            if protocol.startswith(auth_prefix)
        ),
        None,
    )
    if config is not None and auth_required_for(config):
        client = websocket.client
        is_local = client is not None and client.host in ("127.0.0.1", "localhost", "::1")
        if not is_local or config.services.auth_required == "always":
            if not verify_ws_token(provided_token, config.services.auth_token):
                await websocket.close(code=1008)
                return
    subprotocol = "animus-chat" if "animus-chat" in offered_protocols else None
    await app.state.webchat.handle_websocket(websocket, subprotocol=subprotocol)


def serve() -> None:
    """Launch the dashboard server."""
    from animus_bootstrap.dashboard.auth import ensure_auth_token

    manager = ConfigManager()
    cfg = manager.load()

    # Generate + persist a remote-access token when auth will be enforced, so
    # the operator can copy it to the phone. Refresh app.state so the running
    # app's middleware/WS auth see the token.
    if auth_required_for(cfg):
        ensure_auth_token(cfg, manager)
    app.state.config = cfg

    # Optional direct TLS termination (e.g. a `tailscale cert` keypair). Both
    # files must be present; otherwise serve plain HTTP.
    tls: dict[str, str] = {}
    if cfg.services.tls_cert and cfg.services.tls_key:
        tls = {
            "ssl_certfile": cfg.services.tls_cert,
            "ssl_keyfile": cfg.services.tls_key,
        }

    uvicorn.run(
        "animus_bootstrap.dashboard.app:app",
        host=cfg.services.host,
        port=cfg.services.port,
        log_level=cfg.services.log_level,
        reload=False,
        **tls,
    )


if __name__ == "__main__":
    serve()
