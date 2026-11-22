"""WebChat channel adapter — WebSocket-based browser chat."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from animus_bootstrap.gateway.channels.base import MessageCallback
from animus_bootstrap.gateway.models import (
    ChannelHealth,
    GatewayResponse,
    create_message,
)

logger = logging.getLogger(__name__)


class WebChatAdapter:
    """WebSocket-based channel adapter for the browser dashboard chat.

    This adapter manages a set of active WebSocket connections and bridges
    them to the gateway message bus via :class:`GatewayMessage` /
    :class:`GatewayResponse`.  It does **not** require any external API
    keys — it works purely over the local dashboard.
    """

    name: str = "webchat"

    def __init__(self) -> None:
        self.is_connected: bool = False
        self._callback: MessageCallback | None = None
        self._connections: set[WebSocket] = set()

    # ------------------------------------------------------------------
    # ChannelAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Mark the adapter as ready to accept WebSocket connections."""
        self.is_connected = True
        logger.info("WebChat adapter connected")

    async def disconnect(self) -> None:
        """Close all active WebSocket connections and mark as disconnected."""
        for ws in list(self._connections):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        self._connections.clear()
        self.is_connected = False
        logger.info("WebChat adapter disconnected")

    async def send_message(self, response: GatewayResponse) -> str:
        """Broadcast a response to all connected WebSocket clients.

        Returns:
            A generated message ID string.
        """
        message_id = str(uuid.uuid4())
        payload = json.dumps(
            {
                "id": message_id,
                "channel": response.channel,
                "text": response.text,
                "timestamp": datetime.now(UTC).isoformat(),
                "sender": "animus",
                "metadata": response.metadata,
            }
        )

        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                disconnected.append(ws)

        # Clean up stale connections
        for ws in disconnected:
            self._connections.discard(ws)

        return message_id

    async def on_message(self, callback: MessageCallback) -> None:
        """Register the callback invoked when a user sends a chat message."""
        self._callback = callback

    async def health_check(self) -> ChannelHealth:
        """Return current health status including active connection count."""
        return ChannelHealth(
            channel="webchat",
            connected=self.is_connected,
        )

    # ------------------------------------------------------------------
    # WebSocket handler (called by the dashboard router)
    # ------------------------------------------------------------------

    async def handle_websocket(
        self, websocket: WebSocket, *, subprotocol: str | None = None
    ) -> None:
        """Accept and manage a single WebSocket connection lifecycle.

        This method is called from the dashboard's ``/ws/chat`` endpoint.
        It loops receiving text frames, converts them to
        :class:`GatewayMessage`, and forwards to the registered callback.
        """
        await websocket.accept(subprotocol=subprotocol)
        self._connections.add(websocket)
        logger.debug("WebChat: new connection (total=%d)", len(self._connections))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    # Treat plain text as the message body
                    data = {"text": raw}

                text = data.get("text", "")
                sender_id = data.get("sender_id", "webchat-user")
                sender_name = data.get("sender_name", "User")

                msg = create_message(
                    channel="webchat",
                    sender_id=sender_id,
                    sender_name=sender_name,
                    text=text,
                )

                if self._callback is not None:
                    await self._callback(msg)

        except WebSocketDisconnect:
            logger.debug("WebChat: connection closed normally")
        finally:
            self._connections.discard(websocket)
            logger.debug("WebChat: removed connection (total=%d)", len(self._connections))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        """Return the number of active WebSocket connections."""
        return len(self._connections)
