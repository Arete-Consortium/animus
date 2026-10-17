"""Tests for the WebChat channel adapter and dashboard integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.dashboard.app import app
from animus_bootstrap.gateway.channels.base import ChannelAdapter
from animus_bootstrap.gateway.channels.webchat import WebChatAdapter
from animus_bootstrap.gateway.models import ChannelHealth, GatewayResponse

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def adapter() -> WebChatAdapter:
    """Return a fresh WebChatAdapter instance."""
    return WebChatAdapter()


@pytest.fixture()
def client() -> TestClient:
    """TestClient wired to the dashboard app."""
    client = TestClient(app)
    client.get("/health")
    token = client.cookies.get("animus_csrf")
    assert token is not None
    client.headers["X-CSRF-Token"] = token
    return client


# ------------------------------------------------------------------
# ChannelAdapter protocol compliance
# ------------------------------------------------------------------


class TestChannelAdapterProtocol:
    """Verify WebChatAdapter satisfies the ChannelAdapter protocol."""

    def test_is_runtime_checkable(self) -> None:
        adapter = WebChatAdapter()
        assert isinstance(adapter, ChannelAdapter)

    def test_has_required_attributes(self) -> None:
        adapter = WebChatAdapter()
        assert hasattr(adapter, "name")
        assert hasattr(adapter, "is_connected")
        assert adapter.name == "webchat"
        assert adapter.is_connected is False


# ------------------------------------------------------------------
# WebChatAdapter — connect / disconnect
# ------------------------------------------------------------------


class TestWebChatConnect:
    """Tests for connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect(self, adapter: WebChatAdapter) -> None:
        assert adapter.is_connected is False
        await adapter.connect()
        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter: WebChatAdapter) -> None:
        await adapter.connect()
        await adapter.disconnect()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_websockets(self, adapter: WebChatAdapter) -> None:
        """Disconnect should attempt to close all WS connections."""
        await adapter.connect()

        mock_ws = AsyncMock()
        adapter._connections.add(mock_ws)
        assert adapter.connection_count == 1

        await adapter.disconnect()
        mock_ws.close.assert_awaited_once()
        assert adapter.connection_count == 0
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_close_error(self, adapter: WebChatAdapter) -> None:
        """Disconnect should not raise even if ws.close() fails."""
        await adapter.connect()

        mock_ws = AsyncMock()
        mock_ws.close.side_effect = RuntimeError("connection already closed")
        adapter._connections.add(mock_ws)

        await adapter.disconnect()  # should not raise
        assert adapter.connection_count == 0


# ------------------------------------------------------------------
# WebChatAdapter — send_message
# ------------------------------------------------------------------


class TestWebChatSendMessage:
    """Tests for broadcasting messages to WebSocket clients."""

    @pytest.mark.asyncio
    async def test_send_message_returns_id(self, adapter: WebChatAdapter) -> None:
        """send_message should return a non-empty message ID."""
        await adapter.connect()
        response = GatewayResponse(text="Hello", channel="webchat")
        msg_id = await adapter.send_message(response)
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    @pytest.mark.asyncio
    async def test_send_message_broadcasts(self, adapter: WebChatAdapter) -> None:
        """send_message sends JSON to all connected clients."""
        await adapter.connect()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        adapter._connections = {ws1, ws2}

        response = GatewayResponse(text="broadcast test", channel="webchat")
        await adapter.send_message(response)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

        # Verify the payload is valid JSON with expected fields
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["text"] == "broadcast test"
        assert payload["channel"] == "webchat"
        assert "id" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_send_message_removes_stale(self, adapter: WebChatAdapter) -> None:
        """send_message should prune clients that error on send."""
        await adapter.connect()

        good_ws = AsyncMock()
        bad_ws = AsyncMock()
        bad_ws.send_text.side_effect = ConnectionError("gone")
        adapter._connections = {good_ws, bad_ws}

        response = GatewayResponse(text="pruning test", channel="webchat")
        await adapter.send_message(response)

        good_ws.send_text.assert_awaited_once()
        assert bad_ws not in adapter._connections
        assert good_ws in adapter._connections

    @pytest.mark.asyncio
    async def test_send_message_no_connections(self, adapter: WebChatAdapter) -> None:
        """send_message with no connections should still return an ID."""
        await adapter.connect()
        response = GatewayResponse(text="nobody home", channel="webchat")
        msg_id = await adapter.send_message(response)
        assert isinstance(msg_id, str)


# ------------------------------------------------------------------
# WebChatAdapter — on_message callback
# ------------------------------------------------------------------


class TestWebChatOnMessage:
    """Tests for registering inbound message callbacks."""

    @pytest.mark.asyncio
    async def test_on_message_registers_callback(self, adapter: WebChatAdapter) -> None:
        callback = AsyncMock()
        await adapter.on_message(callback)
        assert adapter._callback is callback


# ------------------------------------------------------------------
# WebChatAdapter — health_check
# ------------------------------------------------------------------


class TestWebChatHealthCheck:
    """Tests for the health check method."""

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, adapter: WebChatAdapter) -> None:
        health = await adapter.health_check()
        assert isinstance(health, ChannelHealth)
        assert health.channel == "webchat"
        assert health.connected is False

    @pytest.mark.asyncio
    async def test_health_check_connected(self, adapter: WebChatAdapter) -> None:
        await adapter.connect()
        health = await adapter.health_check()
        assert health.connected is True


# ------------------------------------------------------------------
# WebChatAdapter — connection_count property
# ------------------------------------------------------------------


class TestWebChatConnectionCount:
    """Tests for the connection_count property."""

    def test_zero_initially(self, adapter: WebChatAdapter) -> None:
        assert adapter.connection_count == 0

    def test_tracks_connections(self, adapter: WebChatAdapter) -> None:
        adapter._connections.add(MagicMock())
        adapter._connections.add(MagicMock())
        assert adapter.connection_count == 2


# ------------------------------------------------------------------
# WebChatAdapter — handle_websocket
# ------------------------------------------------------------------


class TestWebChatHandleWebsocket:
    """Tests for the WebSocket handler method."""

    @pytest.mark.asyncio
    async def test_handle_websocket_json(self, adapter: WebChatAdapter) -> None:
        """Valid JSON message should be parsed and forwarded to callback."""
        callback = AsyncMock()
        await adapter.on_message(callback)

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"text": "hello", "sender_id": "u1", "sender_name": "Alice"}),
                ConnectionError("closed"),  # triggers exit from receive loop
            ]
        )

        # The second call raises, which triggers WebSocketDisconnect handling
        # We need to simulate the disconnect properly
        from fastapi import WebSocketDisconnect

        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"text": "hello", "sender_id": "u1", "sender_name": "Alice"}),
                WebSocketDisconnect(),
            ]
        )

        await adapter.handle_websocket(mock_ws)

        mock_ws.accept.assert_awaited_once()
        callback.assert_awaited_once()
        msg = callback.call_args[0][0]
        assert msg.text == "hello"
        assert msg.sender_id == "u1"
        assert msg.sender_name == "Alice"
        assert msg.channel == "webchat"

    @pytest.mark.asyncio
    async def test_handle_websocket_plain_text(self, adapter: WebChatAdapter) -> None:
        """Non-JSON text should be treated as the message body."""
        callback = AsyncMock()
        await adapter.on_message(callback)

        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=["just plain text", WebSocketDisconnect()])

        await adapter.handle_websocket(mock_ws)

        callback.assert_awaited_once()
        msg = callback.call_args[0][0]
        assert msg.text == "just plain text"

    @pytest.mark.asyncio
    async def test_handle_websocket_tracks_connections(self, adapter: WebChatAdapter) -> None:
        """The WS should be in _connections during the session and removed after."""
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[WebSocketDisconnect()])

        await adapter.handle_websocket(mock_ws)
        # After disconnect, the connection should be removed
        assert mock_ws not in adapter._connections

    @pytest.mark.asyncio
    async def test_handle_websocket_no_callback(self, adapter: WebChatAdapter) -> None:
        """Messages should be received even with no callback registered."""
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[json.dumps({"text": "ignored"}), WebSocketDisconnect()]
        )

        await adapter.handle_websocket(mock_ws)  # should not raise


# ------------------------------------------------------------------
# Dashboard — Conversations page
# ------------------------------------------------------------------


class TestConversationsPage:
    """Tests for the /conversations routes."""

    def test_conversations_page_returns_200(self, client: TestClient) -> None:
        """GET /conversations returns 200."""
        resp = client.get("/conversations")
        assert resp.status_code == 200

    def test_conversations_page_contains_title(self, client: TestClient) -> None:
        """GET /conversations contains the page title."""
        resp = client.get("/conversations")
        assert "Conversations" in resp.text

    def test_conversations_messages_returns_json(self, client: TestClient) -> None:
        """GET /conversations/messages returns a JSON array."""
        resp = client.get("/conversations/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_conversations_messages_with_data(self, client: TestClient) -> None:
        """GET /conversations/messages returns stored messages."""
        test_msgs = [
            {"id": "1", "channel": "webchat", "sender": "User", "text": "hi", "timestamp": "now"},
        ]
        with patch(
            "animus_bootstrap.dashboard.routers.conversations.get_message_store",
            return_value=test_msgs,
        ):
            resp = client.get("/conversations/messages")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["text"] == "hi"

    def test_conversations_messages_limit(self, client: TestClient) -> None:
        """GET /conversations/messages respects the limit parameter."""
        test_msgs = [
            {
                "id": str(i),
                "channel": "webchat",
                "sender": "User",
                "text": f"msg{i}",
                "timestamp": "t",
            }
            for i in range(10)
        ]
        with patch(
            "animus_bootstrap.dashboard.routers.conversations.get_message_store",
            return_value=test_msgs,
        ):
            resp = client.get("/conversations/messages?limit=3")
        data = resp.json()
        assert len(data) == 3

    def test_conversations_page_shows_messages(self, client: TestClient) -> None:
        """GET /conversations renders messages in the template."""
        test_msgs = [
            {
                "id": "1",
                "channel": "webchat",
                "sender": "Alice",
                "text": "hello world",
                "timestamp": "t",
            },
        ]
        with patch(
            "animus_bootstrap.dashboard.routers.conversations.get_message_store",
            return_value=test_msgs,
        ):
            resp = client.get("/conversations")
        assert "hello world" in resp.text
        assert "Alice" in resp.text


# ------------------------------------------------------------------
# Dashboard — Channels page
# ------------------------------------------------------------------


class TestChannelsPage:
    """Tests for the /channels routes."""

    def test_channels_page_returns_200(self, client: TestClient) -> None:
        """GET /channels returns 200."""
        resp = client.get("/channels")
        assert resp.status_code == 200

    def test_channels_page_contains_title(self, client: TestClient) -> None:
        """GET /channels contains the page title."""
        resp = client.get("/channels")
        assert "Channels" in resp.text

    def test_channels_page_shows_webchat(self, client: TestClient) -> None:
        """GET /channels displays the WebChat channel card."""
        resp = client.get("/channels")
        assert "WebChat" in resp.text

    def test_channels_page_shows_all_channels(self, client: TestClient) -> None:
        """GET /channels displays all known channel types."""
        resp = client.get("/channels")
        body = resp.text
        for name in ("WebChat", "Telegram", "Discord", "Slack", "Matrix"):
            assert name in body, f"Expected {name} in channels page"

    def test_toggle_channel(self, client: TestClient) -> None:
        """POST /channels/{name}/toggle toggles enabled state and redirects."""
        test_channels = [
            {
                "name": "test-ch",
                "display_name": "Test",
                "color": "#fff",
                "icon": "T",
                "enabled": False,
                "description": "test",
            },
        ]
        with patch(
            "animus_bootstrap.dashboard.routers.channels_page.get_channel_registry",
            return_value=test_channels,
        ):
            resp = client.post("/channels/test-ch/toggle", follow_redirects=False)

        assert resp.status_code == 303
        assert "/channels" in resp.headers["location"]
        # The channel should now be enabled
        assert test_channels[0]["enabled"] is True

    def test_toggle_channel_disable(self, client: TestClient) -> None:
        """POST /channels/{name}/toggle can disable an enabled channel."""
        test_channels = [
            {
                "name": "test-ch",
                "display_name": "Test",
                "color": "#fff",
                "icon": "T",
                "enabled": True,
                "description": "test",
            },
        ]
        with patch(
            "animus_bootstrap.dashboard.routers.channels_page.get_channel_registry",
            return_value=test_channels,
        ):
            resp = client.post("/channels/test-ch/toggle", follow_redirects=False)

        assert resp.status_code == 303
        assert test_channels[0]["enabled"] is False

    def test_toggle_unknown_channel(self, client: TestClient) -> None:
        """POST /channels/{name}/toggle with unknown name still redirects."""
        test_channels: list[dict[str, str | bool]] = []
        with patch(
            "animus_bootstrap.dashboard.routers.channels_page.get_channel_registry",
            return_value=test_channels,
        ):
            resp = client.post("/channels/nonexistent/toggle", follow_redirects=False)
        assert resp.status_code == 303


# ------------------------------------------------------------------
# Dashboard — WebSocket endpoint
# ------------------------------------------------------------------


class TestWebSocketEndpoint:
    """Tests for the /ws/chat WebSocket endpoint."""

    def test_websocket_endpoint_exists(self) -> None:
        """The /ws/chat route should be registered on the app."""
        ws_routes = [r.path for r in app.routes if hasattr(r, "path") and "ws" in r.path]
        assert "/ws/chat" in ws_routes


# ------------------------------------------------------------------
# Dashboard — sidebar navigation
# ------------------------------------------------------------------


class TestSidebarNav:
    """Verify new sidebar items are present in rendered pages."""

    def test_sidebar_has_conversations_link(self, client: TestClient) -> None:
        """The sidebar should contain a link to /conversations."""
        # Use the conversations page itself — no external deps to mock
        resp = client.get("/conversations")
        assert 'href="/conversations"' in resp.text

    def test_sidebar_has_channels_link(self, client: TestClient) -> None:
        """The sidebar should contain a link to /channels."""
        resp = client.get("/channels")
        assert 'href="/channels"' in resp.text


# ------------------------------------------------------------------
# App state — webchat adapter
# ------------------------------------------------------------------


class TestAppState:
    """Verify the shared WebChatAdapter on app.state."""

    def test_webchat_on_app_state(self) -> None:
        assert hasattr(app.state, "webchat")
        assert isinstance(app.state.webchat, WebChatAdapter)
