"""Unit tests for the manual fetch endpoint and WebSocket endpoint.

Tests cover:
- POST /api/v1/emails/fetch triggers Celery task and returns task_id
- POST /api/v1/emails/fetch handles Celery unavailability gracefully
- WebSocket connection lifecycle (connect, ping/pong, disconnect)
- ConnectionManager broadcast and send_personal methods
- ConnectionManager cleanup of disconnected clients

Requirements: 8.4, 6.6
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from src.api.routers.fetch import FetchAcknowledgment, router as fetch_router
from src.api.routers.websocket import ConnectionManager, router as ws_router


# --- Test App ---


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with fetch and websocket routers."""
    app = FastAPI()
    app.include_router(fetch_router)
    app.include_router(ws_router)
    return app


# --- Fetch Endpoint Tests ---


class TestFetchEndpoint:
    """Tests for POST /api/v1/emails/fetch."""

    @patch("src.api.routers.fetch.poll_emails_task", create=True)
    def test_fetch_triggers_celery_task_and_returns_task_id(self, mock_task):
        """POST /emails/fetch should trigger poll_emails_task and return task_id."""
        # Mock the Celery task's .delay() to return an AsyncResult-like object
        mock_result = MagicMock()
        mock_result.id = "abc123-task-id"

        with patch(
            "src.tasks.poll_emails.poll_emails_task"
        ) as mock_poll_task:
            mock_poll_task.delay.return_value = mock_result

            app = _create_test_app()
            client = TestClient(app)
            response = client.post("/api/v1/emails/fetch")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fetch_initiated"
        assert data["task_id"] == "abc123-task-id"
        assert "message" in data

    def test_fetch_returns_error_when_celery_unavailable(self):
        """POST /emails/fetch returns error status when Celery is unavailable."""
        with patch(
            "src.tasks.poll_emails.poll_emails_task"
        ) as mock_poll_task:
            mock_poll_task.delay.side_effect = Exception("Redis connection refused")

            app = _create_test_app()
            client = TestClient(app)
            response = client.post("/api/v1/emails/fetch")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["task_id"] is None
        assert "Redis connection refused" in data["message"]

    def test_fetch_acknowledgment_model(self):
        """FetchAcknowledgment model should serialize correctly."""
        ack = FetchAcknowledgment(
            status="fetch_initiated",
            task_id="task-123",
            message="Fetch initiated",
        )
        assert ack.status == "fetch_initiated"
        assert ack.task_id == "task-123"

        # task_id is optional
        ack_no_task = FetchAcknowledgment(
            status="error",
            message="Something went wrong",
        )
        assert ack_no_task.task_id is None


# --- WebSocket Endpoint Tests ---


class TestWebSocketEndpoint:
    """Tests for WS /api/v1/ws."""

    def test_websocket_connect_and_ping_pong(self):
        """WebSocket should accept connection and respond to ping with pong."""
        app = _create_test_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_text(json.dumps({"type": "ping"}))
            response = websocket.receive_json()
            assert response["type"] == "pong"

    def test_websocket_subscribe_acknowledged(self):
        """WebSocket should acknowledge subscribe messages."""
        app = _create_test_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_text(
                json.dumps({"type": "subscribe", "payload": {"topic": "emails"}})
            )
            response = websocket.receive_json()
            assert response["type"] == "subscribed"
            assert response["payload"]["topic"] == "emails"

    def test_websocket_invalid_json_returns_error(self):
        """WebSocket should return error for invalid JSON messages."""
        app = _create_test_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_text("not valid json {{}")
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "Invalid JSON" in response["payload"]["message"]

    def test_websocket_disconnect_cleans_up(self):
        """WebSocket disconnect should remove connection from manager."""
        from src.api.routers.websocket import manager

        app = _create_test_app()
        client = TestClient(app)

        initial_count = manager.connection_count

        with client.websocket_connect("/api/v1/ws") as websocket:
            # Connection is active
            assert manager.connection_count >= initial_count + 1
            websocket.send_text(json.dumps({"type": "ping"}))
            websocket.receive_json()

        # After disconnect, connection should be removed
        assert manager.connection_count == initial_count


# --- ConnectionManager Tests ---


class TestConnectionManager:
    """Tests for the ConnectionManager class."""

    def test_init_empty(self):
        """ConnectionManager starts with no active connections."""
        mgr = ConnectionManager()
        assert mgr.connection_count == 0
        assert mgr.active_connections == []

    @pytest.mark.asyncio
    async def test_connect_accepts_and_adds(self):
        """connect() should accept the websocket and add it to active list."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        await mgr.connect(mock_ws)

        mock_ws.accept.assert_awaited_once()
        assert mock_ws in mgr.active_connections
        assert mgr.connection_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """disconnect() should remove the websocket from active list."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        mgr.active_connections.append(mock_ws)

        mgr.disconnect(mock_ws)

        assert mock_ws not in mgr.active_connections
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_handles_already_removed(self):
        """disconnect() should not raise if websocket is already gone."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        # Should not raise
        mgr.disconnect(mock_ws)
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        """broadcast() should send message to all active connections."""
        mgr = ConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        mgr.active_connections = [ws1, ws2]

        message = {"type": "test", "data": "hello"}
        await mgr.broadcast(message)

        ws1.send_json.assert_awaited_once_with(message)
        ws2.send_json.assert_awaited_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected_clients(self):
        """broadcast() should clean up clients that fail to receive messages."""
        mgr = ConnectionManager()
        ws_good = AsyncMock(spec=WebSocket)
        ws_bad = AsyncMock(spec=WebSocket)
        ws_bad.send_json.side_effect = Exception("Connection closed")
        mgr.active_connections = [ws_good, ws_bad]

        await mgr.broadcast({"type": "test"})

        # Good connection stays
        assert ws_good in mgr.active_connections
        # Bad connection removed
        assert ws_bad not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_send_personal_to_specific_client(self):
        """send_personal() should send only to the targeted websocket."""
        mgr = ConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        mgr.active_connections = [ws1, ws2]

        message = {"type": "personal", "data": "for you"}
        await mgr.send_personal(ws1, message)

        ws1.send_json.assert_awaited_once_with(message)
        ws2.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_personal_removes_on_failure(self):
        """send_personal() should remove websocket if send fails."""
        mgr = ConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.send_json.side_effect = Exception("Connection lost")
        mgr.active_connections = [ws]

        await mgr.send_personal(ws, {"type": "test"})

        assert ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_processing_update(self):
        """broadcast_processing_update() should format and broadcast correctly."""
        mgr = ConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        mgr.active_connections = [ws]

        await mgr.broadcast_processing_update(
            email_id="email-123",
            event_type="classification_complete",
            data={"category": "Urgent", "priority": "High"},
        )

        ws.send_json.assert_awaited_once()
        sent_message = ws.send_json.call_args[0][0]
        assert sent_message["type"] == "classification_complete"
        assert sent_message["payload"]["email_id"] == "email-123"
        assert sent_message["payload"]["category"] == "Urgent"
        assert sent_message["payload"]["priority"] == "High"
        assert "timestamp" in sent_message

    @pytest.mark.asyncio
    async def test_broadcast_processing_update_without_data(self):
        """broadcast_processing_update() works with no extra data."""
        mgr = ConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        mgr.active_connections = [ws]

        await mgr.broadcast_processing_update(
            email_id="email-456",
            event_type="processing_failed",
        )

        sent_message = ws.send_json.call_args[0][0]
        assert sent_message["type"] == "processing_failed"
        assert sent_message["payload"]["email_id"] == "email-456"

    @pytest.mark.asyncio
    async def test_connection_count_property(self):
        """connection_count should reflect current active connections."""
        mgr = ConnectionManager()
        assert mgr.connection_count == 0

        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        mgr.active_connections = [ws1, ws2]
        assert mgr.connection_count == 2

        mgr.disconnect(ws1)
        assert mgr.connection_count == 1
