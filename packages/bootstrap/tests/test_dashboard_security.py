"""Security hardening tests for the Animus Bootstrap dashboard.

These tests verify the Phase-0 security fixes declared in ADL-20260723-001:
1. No CDN dependencies in templates
2. No secrets rendered in HTML DOM
3. CSRF blocks cross-origin and missing-token POSTs
4. XSS mitigated via Jinja2 autoescaping (no raw HTMLResponse)
5. CORS tightened to localhost only
6. Dashboard loads offline (static JS/CSS served locally)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.config.schema import AnimusConfig
from animus_bootstrap.dashboard.app import app

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    """TestClient for the dashboard app."""
    return TestClient(app)


# ------------------------------------------------------------------
# 1. No CDN dependencies in templates
# ------------------------------------------------------------------


class TestNoCdnDependencies:
    """Verify all external CDN refs have been removed from templates."""

    CDN_PATTERNS = ("cdnjs", "unpkg", "jsdelivr", "tailwindcss.com", "https://cdn.")

    def _template_files(self) -> list[Path]:
        tmpl_dir = (
            Path(__file__).parent.parent / "src" / "animus_bootstrap" / "dashboard" / "templates"
        )
        return list(tmpl_dir.rglob("*.html"))

    def test_no_cdn_urls_in_templates(self) -> None:
        """Every template must be free of known CDN hostnames."""
        failures: list[str] = []
        for path in self._template_files():
            text = path.read_text()
            for pat in self.CDN_PATTERNS:
                if pat in text:
                    failures.append(f"{path.name}: found '{pat}'")
        assert not failures, "CDN references detected:\n" + "\n".join(failures)

    def test_local_tailwind_script(self) -> None:
        """Tailwind must be loaded from /static/js/tailwindcss-cdn.js."""
        base = (
            Path(__file__).parent.parent
            / "src"
            / "animus_bootstrap"
            / "dashboard"
            / "templates"
            / "base.html"
        )
        text = base.read_text()
        assert 'src="/static/js/tailwindcss-cdn.js"' in text, "base.html must load local Tailwind"

    def test_local_htmx_script(self) -> None:
        """HTMX must be loaded from /static/js/htmx.min.js."""
        base = (
            Path(__file__).parent.parent
            / "src"
            / "animus_bootstrap"
            / "dashboard"
            / "templates"
            / "base.html"
        )
        text = base.read_text()
        assert 'src="/static/js/htmx.min.js"' in text, "base.html must load local HTMX"

    def test_local_htmx_sse(self) -> None:
        """HTMX SSE extension must be loaded from /static/js/htmx-sse.js."""
        logs = (
            Path(__file__).parent.parent
            / "src"
            / "animus_bootstrap"
            / "dashboard"
            / "templates"
            / "logs.html"
        )
        text = logs.read_text()
        assert 'src="/static/js/htmx-sse.js"' in text, "logs.html must load local SSE ext"


# ------------------------------------------------------------------
# 2. No secrets rendered in HTML DOM
# ------------------------------------------------------------------


class TestNoSecretsInDom:
    """Verify API keys are never emitted in the rendered page."""

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_config_page_masks_anthropic_key(
        self, mock_cm_cls: MagicMock, client: TestClient
    ) -> None:
        """The full Anthropic key must not appear in the response body."""
        cfg = AnimusConfig()
        cfg.api.anthropic_key = "sk-ant-test-secret-key-12345678"
        mgr = MagicMock()
        mgr.load.return_value = cfg
        mock_cm_cls.return_value = mgr

        resp = client.get("/config")
        assert resp.status_code == 200
        assert cfg.api.anthropic_key not in resp.text

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_config_page_masks_openai_key(self, mock_cm_cls: MagicMock, client: TestClient) -> None:
        """The full OpenAI key must not appear in the response body."""
        cfg = AnimusConfig()
        cfg.api.openai_key = "sk-openai-test-secret-98765432"
        mgr = MagicMock()
        mgr.load.return_value = cfg
        mock_cm_cls.return_value = mgr

        resp = client.get("/config")
        assert resp.status_code == 200
        assert cfg.api.openai_key not in resp.text

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_config_page_masks_forge_key(self, mock_cm_cls: MagicMock, client: TestClient) -> None:
        """The full Forge API key must not appear in the response body."""
        cfg = AnimusConfig()
        cfg.forge.api_key = "forge-secret-key-abcdef"
        mgr = MagicMock()
        mgr.load.return_value = cfg
        mock_cm_cls.return_value = mgr

        resp = client.get("/config")
        assert resp.status_code == 200
        assert cfg.forge.api_key not in resp.text


# ------------------------------------------------------------------
# 3. CSRF protection
# ------------------------------------------------------------------


class TestCsrfProtection:
    """Verify the custom CsrfMiddleware rejects unsafe requests."""

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_post_without_csrf_token_rejected(
        self, mock_cm_cls: MagicMock, client: TestClient
    ) -> None:
        """A POST without the X-CSRF-Token header must be rejected."""
        mgr = MagicMock()
        mgr.load.return_value = AnimusConfig()
        mock_cm_cls.return_value = mgr

        resp = client.post("/config", data={"identity_name": "Hacker"})
        assert resp.status_code == 403
        assert "CSRF" in resp.text

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_post_with_valid_csrf_token_accepted(
        self, mock_cm_cls: MagicMock, client: TestClient
    ) -> None:
        """A POST with the correct X-CSRF-Token header must succeed."""
        mgr = MagicMock()
        mgr.load.return_value = AnimusConfig()
        mock_cm_cls.return_value = mgr

        # First GET to obtain the CSRF cookie
        get_resp = client.get("/config")
        assert get_resp.status_code == 200
        cookie = client.cookies.get("animus_csrf")
        assert cookie is not None, "CSRF cookie should be set after GET"

        resp = client.post(
            "/config",
            data={"identity_name": "Legit"},
            headers={"X-CSRF-Token": cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    @patch("animus_bootstrap.dashboard.routers.config.ConfigManager")
    def test_post_with_wrong_csrf_token_rejected(
        self, mock_cm_cls: MagicMock, client: TestClient
    ) -> None:
        """A POST with an incorrect X-CSRF-Token header must be rejected."""
        mgr = MagicMock()
        mgr.load.return_value = AnimusConfig()
        mock_cm_cls.return_value = mgr

        resp = client.post(
            "/config",
            data={"identity_name": "Hacker"},
            headers={"X-CSRF-Token": "invalid-token"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.text

    def test_same_origin_json_api_post_does_not_require_csrf(self, client: TestClient) -> None:
        """PWA JSON calls rely on same-origin checks, not an unreadable HttpOnly token."""
        resp = client.post(
            "/api/conversations/messages",
            json={"text": "csrf-json-probe"},
        )
        assert resp.status_code == 200

    def test_cross_origin_json_api_post_rejected(self, client: TestClient) -> None:
        """The JSON exemption must never admit a cross-origin mutation."""
        resp = client.post(
            "/api/conversations/messages",
            json={"text": "csrf-cross-origin-probe"},
            headers={"Origin": "https://evil.example"},
        )
        assert resp.status_code == 403
        assert "Origin" in resp.text


# ------------------------------------------------------------------
# 4. XSS mitigated — no raw HTMLResponse with user data
# ------------------------------------------------------------------


class TestXssMitigation:
    """Verify routers use TemplateResponse (Jinja2 autoescaping) instead of raw HTMLResponse."""

    def test_no_htmlresponse_in_routers(self) -> None:
        """No router file should contain HTMLResponse(...) with interpolated strings."""
        routers_dir = (
            Path(__file__).parent.parent / "src" / "animus_bootstrap" / "dashboard" / "routers"
        )
        failures: list[str] = []
        for path in routers_dir.glob("*.py"):
            text = path.read_text()
            if "HTMLResponse(" in text:
                failures.append(f"{path.name}: still uses HTMLResponse")
        assert not failures, "HTMLResponse found in:\n" + "\n".join(failures)

    @patch("animus_bootstrap.dashboard.routers.feedback._get_feedback_store")
    def test_feedback_escaped(self, mock_get_store: MagicMock, client: TestClient) -> None:
        """Feedback response must not contain unescaped user input."""
        store = MagicMock()
        mock_get_store.return_value = store

        # Prime the CSRF cookie via a GET
        client.get("/feedback")
        cookie = client.cookies.get("animus_csrf")
        assert cookie is not None

        resp = client.post(
            "/api/feedback",
            data={
                "message_text": "<script>alert(1)</script>",
                "response_text": "ok",
                "rating": "1",
                "comment": "",
                "channel": "webchat",
            },
            headers={"X-CSRF-Token": cookie},
        )
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text or "alert(1)" not in resp.text


# ------------------------------------------------------------------
# 5. CORS tightened to localhost
# ------------------------------------------------------------------


class TestCorsTight:
    """Verify CORS middleware only allows localhost origin."""

    def test_cors_allows_localhost(self, client: TestClient) -> None:
        """Requests from localhost:7700 should be allowed."""
        resp = client.get("/", headers={"Origin": "http://localhost:7700"})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:7700"

    def test_cors_blocks_external_origin(self, client: TestClient) -> None:
        """Requests from evil.com should not receive CORS headers."""
        resp = client.get("/", headers={"Origin": "https://evil.com"})
        # FastAPI returns 200 but omits ACAO header for disallowed origins
        assert "access-control-allow-origin" not in resp.headers


# ------------------------------------------------------------------
# 6. Dashboard loads offline
# ------------------------------------------------------------------


class TestOfflineLoading:
    """Verify critical static assets are served locally."""

    def test_tailwind_js_served(self, client: TestClient) -> None:
        """GET /static/js/tailwindcss-cdn.js must return 200."""
        resp = client.get("/static/js/tailwindcss-cdn.js")
        assert resp.status_code == 200
        assert "tailwind" in resp.text.lower() or len(resp.content) > 100_000

    def test_htmx_js_served(self, client: TestClient) -> None:
        """GET /static/js/htmx.min.js must return 200."""
        resp = client.get("/static/js/htmx.min.js")
        assert resp.status_code == 200
        assert "htmx" in resp.text.lower()

    def test_htmx_sse_js_served(self, client: TestClient) -> None:
        """GET /static/js/htmx-sse.js must return 200."""
        resp = client.get("/static/js/htmx-sse.js")
        assert resp.status_code == 200
        assert "sse" in resp.text.lower()
