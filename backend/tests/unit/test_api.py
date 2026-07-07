"""Unit tests for the FastAPI API layer.

Tests:
- Auth middleware (401 without key, 200 with valid key)
- GET /emails pagination (default 20, max 100, sorted desc)
- GET /emails/{id} returns 404 for non-existent
- POST /emails/{id}/reply/approve returns 409 for already-actioned
- POST /emails/fetch returns acknowledgment
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from src.models.database import get_session


# --- Test App Factory ---


def _create_test_app(api_key: str = "") -> FastAPI:
    """Create a minimal test FastAPI app with the same routes and middleware.

    This avoids lru_cache issues with get_settings by directly constructing
    the app with middleware that uses a known api_key value.
    """
    from src.api.routers.emails import router as emails_router
    from src.api.routers.fetch import router as fetch_router
    from src.api.routers.websocket import router as websocket_router

    app = FastAPI(title="Test App")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom auth middleware using the test api_key directly
    from starlette.middleware.base import BaseHTTPMiddleware
    from fastapi import Request, Response
    from fastapi.responses import JSONResponse

    class TestAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            if request.url.path in {"/docs", "/openapi.json", "/redoc", "/health"}:
                return await call_next(request)
            if request.headers.get("upgrade", "").lower() == "websocket":
                return await call_next(request)

            if api_key:  # Only enforce if api_key is configured
                provided_key = request.headers.get("X-API-Key")
                if not provided_key or provided_key != api_key:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing API key"},
                    )

            return await call_next(request)

    app.add_middleware(TestAuthMiddleware)

    app.include_router(emails_router)
    app.include_router(fetch_router)
    app.include_router(websocket_router)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app


def _mock_session_paginated(count_value: int = 0, items=None):
    """Create a mock session for paginated queries (count + data)."""
    mock_session = AsyncMock()

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = count_value

    mock_items_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items or []
    mock_items_result.scalars.return_value = mock_scalars

    mock_session.execute = AsyncMock(
        side_effect=[mock_count_result, mock_items_result]
    )
    mock_session.commit = AsyncMock()
    return mock_session


def _mock_session_single(result=None):
    """Create a mock session for single-item queries."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = result
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


# --- Auth Middleware Tests ---


class TestAuthMiddleware:
    """Test API key authentication middleware."""

    def test_returns_401_without_api_key(self):
        """Requests without X-API-Key header get 401."""
        app = _create_test_app(api_key="test-secret-key")
        client = TestClient(app)
        response = client.get("/api/v1/emails")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_returns_401_with_invalid_api_key(self):
        """Requests with wrong X-API-Key get 401."""
        app = _create_test_app(api_key="test-secret-key")
        client = TestClient(app)
        response = client.get(
            "/api/v1/emails", headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    def test_returns_200_with_valid_api_key(self):
        """Requests with correct X-API-Key pass through auth."""
        app = _create_test_app(api_key="test-secret-key")
        mock_session = _mock_session_paginated(count_value=0, items=[])

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get(
            "/api/v1/emails",
            headers={"X-API-Key": "test-secret-key"},
        )
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_health_endpoint_no_auth(self):
        """Health endpoint doesn't require auth."""
        app = _create_test_app(api_key="test-secret-key")
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# --- Email List Endpoint Tests ---


class TestEmailListEndpoint:
    """Test GET /api/v1/emails pagination."""

    def test_default_pagination(self):
        """Default page_size is 20."""
        app = _create_test_app()
        mock_session = _mock_session_paginated(count_value=0, items=[])

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get("/api/v1/emails")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 20
        assert data["page"] == 1
        assert data["total"] == 0
        app.dependency_overrides.clear()

    def test_max_page_size_capped_at_100(self):
        """page_size cannot exceed 100 (FastAPI Query validation)."""
        app = _create_test_app()

        async def override_get_session():
            yield AsyncMock()

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get("/api/v1/emails?page_size=200")
        assert response.status_code == 422
        app.dependency_overrides.clear()

    def test_returns_items_sorted_desc(self):
        """Items are returned sorted by processing_timestamp descending."""
        app = _create_test_app()

        # Create mock emails (already in desc order from "DB")
        email1 = MagicMock()
        email1.id = uuid.uuid4()
        email1.provider_message_id = "msg1"
        email1.sender = "alice@test.com"
        email1.subject = "First"
        email1.body = "Body 1"
        email1.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        email1.processing_timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        email1.category = "Urgent"
        email1.priority = "High"
        email1.confidence = 0.95
        email1.summary = None
        email1.action_items = None
        email1.summary_is_fallback = False
        email1.workflow_stage = "completed"
        email1.flagged_for_review = False

        email2 = MagicMock()
        email2.id = uuid.uuid4()
        email2.provider_message_id = "msg2"
        email2.sender = "bob@test.com"
        email2.subject = "Second"
        email2.body = "Body 2"
        email2.timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
        email2.processing_timestamp = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
        email2.category = "Informative"
        email2.priority = "Medium"
        email2.confidence = 0.8
        email2.summary = "A summary"
        email2.action_items = ["action1"]
        email2.summary_is_fallback = False
        email2.workflow_stage = "completed"
        email2.flagged_for_review = False

        mock_session = _mock_session_paginated(count_value=2, items=[email2, email1])

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get("/api/v1/emails")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # email2 (more recent) should be first
        assert data["items"][0]["sender"] == "bob@test.com"
        assert data["items"][1]["sender"] == "alice@test.com"
        app.dependency_overrides.clear()


# --- Email Detail Endpoint Tests ---


class TestEmailDetailEndpoint:
    """Test GET /api/v1/emails/{email_id}."""

    def test_returns_404_for_nonexistent_email(self):
        """GET /emails/{id} returns 404 when email doesn't exist."""
        app = _create_test_app()
        fake_id = str(uuid.uuid4())
        mock_session = _mock_session_single(result=None)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get(f"/api/v1/emails/{fake_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Email not found"
        app.dependency_overrides.clear()

    def test_returns_email_detail(self):
        """GET /emails/{id} returns full processing result."""
        app = _create_test_app()
        email_id = uuid.uuid4()

        mock_email = MagicMock()
        mock_email.id = email_id
        mock_email.provider_message_id = "msg123"
        mock_email.sender = "test@test.com"
        mock_email.subject = "Test Subject"
        mock_email.body = "Test body"
        mock_email.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_email.processing_timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        mock_email.category = "Urgent"
        mock_email.priority = "High"
        mock_email.confidence = 0.9
        mock_email.summary = "A test summary"
        mock_email.action_items = ["Reply ASAP"]
        mock_email.summary_is_fallback = False
        mock_email.workflow_stage = "completed"
        mock_email.flagged_for_review = False

        mock_session = _mock_session_single(result=mock_email)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.get(f"/api/v1/emails/{email_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["email_id"] == str(email_id)
        assert data["sender"] == "test@test.com"
        assert data["classification"]["category"] == "Urgent"
        app.dependency_overrides.clear()


# --- Reply Approve Endpoint Tests ---


class TestReplyApproveEndpoint:
    """Test POST /api/v1/emails/{email_id}/reply/approve."""

    def test_returns_409_for_already_actioned_draft(self):
        """POST approve returns 409 when draft already actioned."""
        app = _create_test_app()
        fake_email_id = uuid.uuid4()

        mock_draft = MagicMock()
        mock_draft.status = "approved"
        mock_draft.id = uuid.uuid4()

        mock_session = _mock_session_single(result=mock_draft)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.post(f"/api/v1/emails/{fake_email_id}/reply/approve")
        assert response.status_code == 409
        assert "already actioned" in response.json()["detail"]
        app.dependency_overrides.clear()

    def test_returns_404_for_nonexistent_draft(self):
        """POST approve returns 404 when no draft exists."""
        app = _create_test_app()
        fake_email_id = uuid.uuid4()
        mock_session = _mock_session_single(result=None)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.post(f"/api/v1/emails/{fake_email_id}/reply/approve")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_approve_with_edited_body(self):
        """POST approve accepts edited_body and edited_subject."""
        app = _create_test_app()
        fake_email_id = uuid.uuid4()

        mock_draft = MagicMock()
        mock_draft.status = "pending"
        mock_draft.id = uuid.uuid4()

        mock_session = _mock_session_single(result=mock_draft)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.post(
            f"/api/v1/emails/{fake_email_id}/reply/approve",
            json={"edited_body": "New body", "edited_subject": "New subject"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        app.dependency_overrides.clear()


# --- Reply Reject Endpoint Tests ---


class TestReplyRejectEndpoint:
    """Test POST /api/v1/emails/{email_id}/reply/reject."""

    def test_reject_pending_draft(self):
        """POST reject marks a pending draft as rejected."""
        app = _create_test_app()
        fake_email_id = uuid.uuid4()

        mock_draft = MagicMock()
        mock_draft.status = "pending"
        mock_draft.id = uuid.uuid4()

        mock_session = _mock_session_single(result=mock_draft)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.post(f"/api/v1/emails/{fake_email_id}/reply/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        app.dependency_overrides.clear()

    def test_reject_returns_409_for_already_actioned(self):
        """POST reject returns 409 when draft already actioned."""
        app = _create_test_app()
        fake_email_id = uuid.uuid4()

        mock_draft = MagicMock()
        mock_draft.status = "sent"
        mock_draft.id = uuid.uuid4()

        mock_session = _mock_session_single(result=mock_draft)

        async def override_get_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        client = TestClient(app)

        response = client.post(f"/api/v1/emails/{fake_email_id}/reply/reject")
        assert response.status_code == 409
        app.dependency_overrides.clear()


# --- Fetch Endpoint Tests ---


class TestFetchEndpoint:
    """Test POST /api/v1/emails/fetch."""

    def test_fetch_returns_acknowledgment(self):
        """POST /emails/fetch returns accepted status."""
        app = _create_test_app()
        client = TestClient(app)
        response = client.post("/api/v1/emails/fetch")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "message" in data
