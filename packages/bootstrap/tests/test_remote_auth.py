"""Tests for remote-access bearer auth (helpers, HTTP middleware, WS auth)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.config.schema import AnimusConfig
from animus_bootstrap.dashboard import auth
from animus_bootstrap.dashboard.app import app
from animus_bootstrap.dashboard.middleware_http import _is_public

# ------------------------------------------------------------------
# Helpers / fixtures
# ------------------------------------------------------------------


def _config(*, host: str = "127.0.0.1", required: str = "auto", token: str = "") -> AnimusConfig:
    cfg = AnimusConfig()
    cfg.services.host = host
    cfg.services.auth_required = required
    cfg.services.auth_token = token
    return cfg


@pytest.fixture()
def restore_config() -> Iterator[None]:
    """Save and restore the shared app.state.config around a test."""
    original = app.state.config
    try:
        yield
    finally:
        app.state.config = original


# ------------------------------------------------------------------
# auth helpers
# ------------------------------------------------------------------


class TestAuthHelpers:
    def test_ensure_auth_token_generates_and_saves(self) -> None:
        cfg = _config()
        manager = MagicMock()
        token = auth.ensure_auth_token(cfg, manager)
        assert token
        assert cfg.services.auth_token == token
        manager.save.assert_called_once_with(cfg)

    def test_ensure_auth_token_idempotent(self) -> None:
        cfg = _config(token="existing-token")
        manager = MagicMock()
        token = auth.ensure_auth_token(cfg, manager)
        assert token == "existing-token"
        manager.save.assert_not_called()

    def test_ensure_auth_token_does_not_log_secret(self, caplog: pytest.LogCaptureFixture) -> None:
        cfg = _config()
        manager = MagicMock()
        token = auth.ensure_auth_token(cfg, manager)
        assert token not in caplog.text

    @pytest.mark.parametrize(
        ("host", "required", "expected"),
        [
            ("127.0.0.1", "auto", False),
            ("localhost", "auto", False),
            ("::1", "auto", False),
            ("0.0.0.0", "auto", True),
            ("100.64.0.1", "auto", True),
            ("127.0.0.1", "always", True),
            ("0.0.0.0", "never", False),
        ],
    )
    def test_auth_required_for(self, host: str, required: str, expected: bool) -> None:
        assert auth.auth_required_for(_config(host=host, required=required)) is expected

    def test_verify_bearer(self) -> None:
        assert auth.verify_bearer("Bearer secret", "secret") is True
        assert auth.verify_bearer("bearer secret", "secret") is True
        assert auth.verify_bearer("Bearer wrong", "secret") is False
        assert auth.verify_bearer("secret", "secret") is False  # missing scheme
        assert auth.verify_bearer(None, "secret") is False
        assert auth.verify_bearer("Bearer secret", "") is False

    def test_verify_ws_token(self) -> None:
        assert auth.verify_ws_token("secret", "secret") is True
        assert auth.verify_ws_token("wrong", "secret") is False
        assert auth.verify_ws_token(None, "secret") is False
        assert auth.verify_ws_token("secret", "") is False

    def test_is_local_client(self) -> None:
        local = MagicMock()
        local.client.host = "127.0.0.1"
        assert auth.is_local_client(local) is True

        remote = MagicMock()
        remote.client.host = "100.64.0.1"
        assert auth.is_local_client(remote) is False

        noclient = MagicMock()
        noclient.client = None
        assert auth.is_local_client(noclient) is False


# ------------------------------------------------------------------
# HTTP middleware
# ------------------------------------------------------------------


class TestHttpAuthMiddleware:
    def test_auth_disabled_allows_api(self, restore_config: None) -> None:
        app.state.config = _config(host="127.0.0.1", required="auto")  # auth off
        client = TestClient(app)  # non-local client, but auth disabled
        assert client.get("/api/health").status_code == 200

    def test_remote_api_without_token_rejected(self, restore_config: None) -> None:
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)  # client host = "testclient" (non-local)
        resp = client.get("/api/health")
        assert resp.status_code == 401

    def test_remote_api_with_token_allowed(self, restore_config: None) -> None:
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)
        resp = client.get("/api/health", headers={"Authorization": "Bearer t0ken"})
        assert resp.status_code == 200

    def test_local_client_bypasses_auth_in_auto_mode(self, restore_config: None) -> None:
        app.state.config = _config(host="0.0.0.0", required="auto", token="t0ken")
        client = TestClient(app, client=("127.0.0.1", 12345))
        assert client.get("/api/health").status_code == 200

    def test_always_mode_rejects_local_client_without_token(self, restore_config: None) -> None:
        app.state.config = _config(host="127.0.0.1", required="always", token="t0ken")
        client = TestClient(app, client=("127.0.0.1", 12345))
        assert client.get("/api/health").status_code == 401

    def test_always_mode_accepts_local_client_with_token(self, restore_config: None) -> None:
        app.state.config = _config(host="127.0.0.1", required="always", token="t0ken")
        client = TestClient(app, client=("127.0.0.1", 12345))
        response = client.get("/api/health", headers={"Authorization": "Bearer t0ken"})
        assert response.status_code == 200

    def test_htmx_page_blocked_for_remote_without_token(self, restore_config: None) -> None:
        # C92: the HTMX dashboard (bare paths) must NOT be reachable by a remote
        # client without the token — the old model allowed it, exposing the
        # config/memory/self-mod pages to the whole tailnet.
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)  # non-local, no token
        assert client.get("/").status_code == 401

    def test_htmx_page_reachable_locally_and_with_token(self, restore_config: None) -> None:
        app.state.config = _config(host="0.0.0.0", required="auto", token="t0ken")
        local = TestClient(app, client=("127.0.0.1", 12345))
        assert local.get("/").status_code == 200
        remote = TestClient(app)
        assert remote.get("/", headers={"Authorization": "Bearer t0ken"}).status_code == 200

    def test_bare_sensitive_route_requires_token_for_remote(self, restore_config: None) -> None:
        # C92 critical #1: dangerous BARE-path routes (no /api prefix) were
        # unauthenticated for remote clients. They must now require the token.
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        remote = TestClient(app)  # non-local, no token
        for path in ("/memory/export", "/config", "/tools", "/self-mod"):
            assert remote.get(path).status_code == 401, f"{path} reachable without token"

    def test_public_paths_reachable_without_token(self, restore_config: None) -> None:
        # The minimal allowlist — bare liveness probe stays public so monitors
        # work; everything sensitive is gated above.
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        remote = TestClient(app)  # non-local, no token
        assert remote.get("/health").status_code == 200

    @pytest.mark.parametrize("path", ["/pwa", "/pwa/", "/pwa/assets/app.js", "/static"])
    def test_public_shell_paths_do_not_require_token(self, restore_config: None, path: str) -> None:
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        response = TestClient(app).get(path)
        assert response.status_code != 401

    @pytest.mark.parametrize("path", ["/pwa-private", "/static-admin", "/api/health"])
    def test_public_prefixes_do_not_overmatch(self, path: str) -> None:
        assert _is_public(path) is False

    def test_configured_pwa_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from animus_bootstrap.dashboard.app import _resolve_pwa_dir

        pwa_dir = tmp_path / "dist"
        monkeypatch.setenv("ANIMUS_PWA_DIR", str(pwa_dir))
        assert _resolve_pwa_dir() == pwa_dir.resolve()


# ------------------------------------------------------------------
# WebSocket auth
# ------------------------------------------------------------------


class TestWebSocketAuth:
    def test_ws_rejected_without_token(self, restore_config: None) -> None:
        from starlette.websockets import WebSocketDisconnect

        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/chat"):
                pass

    def test_ws_accepted_with_token(self, restore_config: None) -> None:
        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)
        with client.websocket_connect(
            "/ws/chat", subprotocols=["animus-chat", "animus-auth.t0ken"]
        ) as ws:
            ws.close()

    def test_ws_query_token_is_not_accepted(self, restore_config: None) -> None:
        from starlette.websockets import WebSocketDisconnect

        app.state.config = _config(host="0.0.0.0", required="always", token="t0ken")
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/chat?token=t0ken"):
                pass

    def test_ws_open_when_auth_disabled(self, restore_config: None) -> None:
        app.state.config = _config(host="127.0.0.1", required="auto")  # auth off
        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as ws:
            ws.close()

    def test_ws_always_mode_rejects_loopback_without_token(self, restore_config: None) -> None:
        from starlette.websockets import WebSocketDisconnect

        app.state.config = _config(host="127.0.0.1", required="always", token="t0ken")
        client = TestClient(app, client=("127.0.0.1", 12345))
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/chat"):
                pass

    def test_ws_always_mode_accepts_loopback_with_token(self, restore_config: None) -> None:
        app.state.config = _config(host="127.0.0.1", required="always", token="t0ken")
        client = TestClient(app, client=("127.0.0.1", 12345))
        with client.websocket_connect(
            "/ws/chat", subprotocols=["animus-chat", "animus-auth.t0ken"]
        ) as ws:
            ws.close()


# ------------------------------------------------------------------
# Config round-trip
# ------------------------------------------------------------------


class TestMemoryExportRedaction:
    """C92 critical #2: /memory/export must never serialize secrets."""

    def test_redact_secrets_masks_keys_and_tokens(self) -> None:
        from animus_bootstrap.dashboard.routers.memory import _redact_secrets

        dumped = {
            "api": {"anthropic_key": "sk-secret", "openai_key": "sk-other"},
            "forge": {"api_key": "forge-secret"},
            "services": {
                "auth_token": "the-token",
                "tls_key": "/k.pem",
                "vapid_private_key": "PEMDATA",
                "vapid_public_key": "PUBLIC-OK",  # shared with browser — keep
                "max_response_tokens": 4096,  # int budget — keep
                "host": "0.0.0.0",
            },
        }
        out = _redact_secrets(dumped)
        assert out["api"]["anthropic_key"] == "***redacted***"
        assert out["api"]["openai_key"] == "***redacted***"
        assert out["forge"]["api_key"] == "***redacted***"
        assert out["services"]["auth_token"] == "***redacted***"
        assert out["services"]["tls_key"] == "***redacted***"
        assert out["services"]["vapid_private_key"] == "***redacted***"
        # Non-secrets preserved.
        assert out["services"]["vapid_public_key"] == "PUBLIC-OK"
        assert out["services"]["max_response_tokens"] == 4096
        assert out["services"]["host"] == "0.0.0.0"
        # No secret value survives anywhere in the structure.
        import json

        blob = json.dumps(out)
        for secret in ("sk-secret", "sk-other", "forge-secret", "the-token", "PEMDATA"):
            assert secret not in blob


class TestServicesConfigRoundTrip:
    def test_new_service_fields_round_trip(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from animus_bootstrap.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        cfg = AnimusConfig()
        cfg.services.host = "0.0.0.0"
        cfg.services.auth_required = "always"
        cfg.services.auth_token = "round-trip-token"
        cfg.services.tls_cert = "/tmp/cert.pem"
        cfg.services.tls_key = "/tmp/key.pem"
        manager.save(cfg)

        loaded = manager.load()
        assert loaded.services.host == "0.0.0.0"
        assert loaded.services.auth_required == "always"
        assert loaded.services.auth_token == "round-trip-token"
        assert loaded.services.tls_cert == "/tmp/cert.pem"
        assert loaded.services.tls_key == "/tmp/key.pem"

    def test_partial_services_section_merges_defaults(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from animus_bootstrap.config.manager import ConfigManager

        path = tmp_path / "config.toml"
        path.write_text('[services]\nhost = "0.0.0.0"\n')
        manager = ConfigManager(config_dir=tmp_path)
        loaded = manager.load()
        assert loaded.services.host == "0.0.0.0"
        # Untouched fields fall back to defaults.
        assert loaded.services.port == 7700
        assert loaded.services.auth_required == "auto"
