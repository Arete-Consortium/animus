"""Tests for the PWA quick-capture and conversation-history endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.dashboard.app import app
from animus_bootstrap.gateway.models import create_message


@pytest.fixture()
def restore_state() -> Iterator[None]:
    """Restore app.state.runtime around tests that set it."""
    had_runtime = hasattr(app.state, "runtime")
    original = getattr(app.state, "runtime", None)
    try:
        yield
    finally:
        if had_runtime:
            app.state.runtime = original
        elif hasattr(app.state, "runtime"):
            delattr(app.state, "runtime")


@pytest.fixture()
def client() -> TestClient:
    client = TestClient(app)
    client.get("/health")
    token = client.cookies.get("animus_csrf")
    assert token is not None
    client.headers["X-CSRF-Token"] = token
    return client


# ------------------------------------------------------------------
# Quick capture
# ------------------------------------------------------------------


class TestCapture:
    def test_capture_stores_note(self, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        store_mock = AsyncMock(return_value="Stored episodic memory: hi")
        monkeypatch.setattr(
            "animus_bootstrap.dashboard.routers.capture._store_memory",
            store_mock,
        )
        resp = client.post("/api/capture", json={"text": "remember the milk"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        store_mock.assert_awaited_once()

    def test_capture_rejects_empty(self, client: TestClient) -> None:
        resp = client.post("/api/capture", json={"text": "   "})
        assert resp.status_code == 400


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------


class TestHistory:
    def test_history_empty_without_runtime(self, client: TestClient, restore_state: None) -> None:
        app.state.runtime = None
        resp = client.get("/api/conversations/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_maps_messages(self, client: TestClient, restore_state: None) -> None:
        user_msg = create_message("webchat", "user1", "Alice", "hello")
        assistant_msg = create_message("webchat", "animus", "Animus", "hi back")
        assistant_msg.role = "assistant"

        session_manager = MagicMock()
        # Newest-first as get_recent_messages returns.
        session_manager.get_recent_messages = AsyncMock(return_value=[assistant_msg, user_msg])
        runtime = MagicMock()
        runtime.session_manager = session_manager
        app.state.runtime = runtime

        resp = client.get("/api/conversations/history?limit=10")
        assert resp.status_code == 200
        items = resp.json()
        # Reversed to chronological order for display.
        assert items[0]["text"] == "hello"
        assert items[0]["sender"] == "Alice"
        assert items[1]["text"] == "hi back"
        assert items[1]["sender"] == "animus"
        assert items[1]["role"] == "assistant"
