"""WebSocket endpoint for real-time processing updates.

Provides:
- WS /api/v1/ws — real-time email processing status updates to Dashboard

The ConnectionManager maintains active WebSocket connections and broadcasts
notifications when email processing completes (classification, summarization,
draft reply generation).

Requirements: 6.6
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class WebSocketMessage(BaseModel):
    """Structured message sent over WebSocket to clients."""

    type: str
    payload: Dict[str, Any]
    timestamp: str


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages.

    Maintains a list of connected WebSocket clients and provides methods
    to broadcast messages to all clients or send to individual connections.
    Handles cleanup of disconnected clients automatically during broadcasts.
    """

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The incoming WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket connected. Active connections: %d",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active pool.

        Args:
            websocket: The WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket disconnected. Active connections: %d",
            len(self.active_connections),
        )

    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Send a message to a specific connected client.

        Args:
            websocket: The target WebSocket connection.
            message: The JSON-serializable message to send.
        """
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.warning("Failed to send personal message: %s", exc)
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connected clients.

        Automatically cleans up any clients that have disconnected
        (detected by send failures).

        Args:
            message: The JSON-serializable message to broadcast.
        """
        disconnected: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_processing_update(
        self,
        email_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcast an email processing update to all connected clients.

        This is the primary method used by the agent orchestrator to notify
        the Dashboard of processing state changes.

        Args:
            email_id: The ID of the email being processed.
            event_type: Type of update (e.g., "classification_complete",
                "summarization_complete", "draft_generated", "processing_failed").
            data: Optional additional payload data.
        """
        message = {
            "type": event_type,
            "payload": {
                "email_id": email_id,
                **(data or {}),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.broadcast(message)
        logger.debug(
            "Broadcast %s for email %s to %d clients",
            event_type,
            email_id,
            len(self.active_connections),
        )


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time email processing updates.

    Clients connect to receive live updates about:
    - Email processing status changes
    - New classification results
    - Summarization completions
    - Draft reply generation notifications
    - Processing failures

    The connection stays open until the client disconnects.
    Supports keepalive pings from clients (send {"type": "ping"} to receive
    {"type": "pong"}).
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    # Acknowledge subscription (future: topic-based filtering)
                    await websocket.send_json(
                        {"type": "subscribed", "payload": message.get("payload", {})}
                    )
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "payload": {"message": "Invalid JSON"}}
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
