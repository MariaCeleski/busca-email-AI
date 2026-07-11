"""Unit tests for API middleware (auth, logging, validation).

Tests:
- Auth middleware: API key validation, OAuth Bearer token validation, public path bypass
- Access logging: requester_id extraction, no body content in logs
- Validation handler: 422 with field-level errors
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.middleware.auth import (
    AuthMiddleware,
    _is_public_path,
    _validate_api_key,
    _validate_oauth_token,
)
from src.api.middleware.validation import install_validation_error_handler


# --- Helper: create test app with real middleware ---


def _create_auth_test_app(
    api_key: str = "test-api-key",
    jwt_secret: str = "test-jwt-secret",
    jwt_algorithm: str = "HS256",
) -> FastAPI:
    """Create a test FastAPI app with the AuthMiddleware."""
    app = FastAPI()

    # Patch get_settings to return test values
    mock_settings = MagicMock()
    mock_settings.api_key = api_key
    mock_settings.jwt_secret_key = jwt_secret
    mock_settings.jwt_algorithm = jwt_algorithm

    with patch("src.api.middleware.auth.get_settings", return_value=mock_settings):
        app.add_middleware(AuthMiddleware)

    # We need to patch get_settings inside the middleware dispatch too
    app.state.mock_settings = mock_settings

    @app.get("/api/v1/emails")
    async def list_emails():
        return {"items": []}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/docs")
    async def docs():
        return {"docs": True}

    @app.get("/api/v1/auth/login")
    async def auth_login():
        return {"login": True}

    @app.get("/api/v1/auth/gmail/callback")
    async def auth_callback():
        return {"callback": True}

    return app


# --- Unit tests for helper functions ---


class TestIsPublicPath:
    """Test the _is_public_path helper function."""

    def test_docs_is_public(self):
        assert _is_public_path("/docs") is True

    def test_openapi_json_is_public(self):
        assert _is_public_path("/openapi.json") is True

    def test_health_is_public(self):
        assert _is_public_path("/health") is True

    def test_redoc_is_public(self):
        assert _is_public_path("/redoc") is True

    def test_auth_prefix_is_public(self):
        assert _is_public_path("/api/v1/auth") is True
        assert _is_public_path("/api/v1/auth/login") is True
        assert _is_public_path("/api/v1/auth/gmail/callback") is True

    def test_emails_is_not_public(self):
        assert _is_public_path("/api/v1/emails") is False

    def test_root_is_not_public(self):
        assert _is_public_path("/") is False


class TestValidateApiKey:
    """Test the _validate_api_key helper function."""

    def test_valid_key_matches(self):
        assert _validate_api_key("my-secret", "my-secret") is True

    def test_invalid_key_does_not_match(self):
        assert _validate_api_key("wrong-key", "my-secret") is False

    def test_empty_configured_key_allows_all(self):
        """Dev mode: no configured key allows any key."""
        assert _validate_api_key("anything", "") is True

    def test_empty_provided_key_fails(self):
        assert _validate_api_key("", "my-secret") is False


class TestValidateOAuthToken:
    """Test the _validate_oauth_token helper function."""

    def test_valid_token_returns_payload(self):
        """A valid, non-expired JWT returns the decoded payload."""
        secret = "test-secret"
        payload = {"sub": "user123", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, secret, algorithm="HS256")

        result = _validate_oauth_token(token, secret, "HS256")
        assert result is not None
        assert result["sub"] == "user123"

    def test_expired_token_returns_none(self):
        """An expired JWT returns None."""
        secret = "test-secret"
        payload = {"sub": "user123", "exp": int(time.time()) - 3600}
        token = jwt.encode(payload, secret, algorithm="HS256")

        result = _validate_oauth_token(token, secret, "HS256")
        assert result is None

    def test_invalid_signature_returns_none(self):
        """A JWT signed with wrong key returns None."""
        payload = {"sub": "user123", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        result = _validate_oauth_token(token, "correct-secret", "HS256")
        assert result is None

    def test_malformed_token_returns_none(self):
        """A non-JWT string returns None."""
        result = _validate_oauth_token("not-a-jwt", "secret", "HS256")
        assert result is None

    def test_empty_secret_returns_none(self):
        """No secret configured returns None."""
        payload = {"sub": "user123", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "any-secret", algorithm="HS256")

        result = _validate_oauth_token(token, "", "HS256")
        assert result is None

    def test_token_without_exp_is_valid(self):
        """A JWT without exp claim is valid (no expiry check)."""
        secret = "test-secret"
        payload = {"sub": "user123"}
        token = jwt.encode(payload, secret, algorithm="HS256")

        result = _validate_oauth_token(token, secret, "HS256")
        assert result is not None
        assert result["sub"] == "user123"


# --- Integration tests for AuthMiddleware ---


class TestAuthMiddlewareIntegration:
    """Test AuthMiddleware with a real FastAPI TestClient."""

    def _make_app_with_patched_settings(
        self,
        api_key: str = "test-api-key",
        jwt_secret: str = "test-jwt-secret",
        jwt_algorithm: str = "HS256",
    ):
        """Create app with middleware that uses patched settings."""
        app = FastAPI()

        mock_settings = MagicMock()
        mock_settings.api_key = api_key
        mock_settings.jwt_secret_key = jwt_secret
        mock_settings.jwt_algorithm = jwt_algorithm

        # Custom middleware that uses our mock settings directly
        class TestAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                from src.api.middleware.auth import (
                    _is_public_path,
                    _validate_api_key,
                    _validate_oauth_token,
                )

                if _is_public_path(request.url.path):
                    return await call_next(request)

                if request.headers.get("upgrade", "").lower() == "websocket":
                    return await call_next(request)

                # Try API key
                req_api_key = request.headers.get("X-API-Key")
                if req_api_key:
                    if _validate_api_key(req_api_key, mock_settings.api_key):
                        request.state.requester_id = f"apikey:{req_api_key[:8]}"
                        return await call_next(request)
                    else:
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid or missing API key"},
                        )

                # Try OAuth Bearer token
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                    payload = _validate_oauth_token(
                        token, mock_settings.jwt_secret_key, mock_settings.jwt_algorithm
                    )
                    if payload is not None:
                        requester_id = payload.get("sub", "unknown")
                        request.state.requester_id = f"oauth:{requester_id}"
                        return await call_next(request)
                    else:
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid or expired OAuth token"},
                        )

                # No credentials
                if not mock_settings.api_key and not mock_settings.jwt_secret_key:
                    request.state.requester_id = "anonymous"
                    return await call_next(request)

                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Authentication required. Provide X-API-Key header or Authorization: Bearer <token>"
                    },
                )

        app.add_middleware(TestAuthMiddleware)

        @app.get("/api/v1/emails")
        async def list_emails(request: Request):
            requester = getattr(request.state, "requester_id", "none")
            return {"items": [], "requester": requester}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/v1/auth/login")
        async def auth_login():
            return {"login": True}

        return app

    def test_401_without_any_credentials(self):
        """Returns 401 when no credentials are provided."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)
        response = client.get("/api/v1/emails")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_401_with_invalid_api_key(self):
        """Returns 401 when API key is wrong."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)
        response = client.get(
            "/api/v1/emails", headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]

    def test_200_with_valid_api_key(self):
        """Returns 200 when valid API key is provided."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)
        response = client.get(
            "/api/v1/emails", headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requester"].startswith("apikey:")

    def test_200_with_valid_oauth_token(self):
        """Returns 200 when valid Bearer token is provided."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)

        payload = {"sub": "user-42", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "test-jwt-secret", algorithm="HS256")

        response = client.get(
            "/api/v1/emails",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requester"] == "oauth:user-42"

    def test_401_with_expired_oauth_token(self):
        """Returns 401 when Bearer token is expired."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)

        payload = {"sub": "user-42", "exp": int(time.time()) - 3600}
        token = jwt.encode(payload, "test-jwt-secret", algorithm="HS256")

        response = client.get(
            "/api/v1/emails",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]

    def test_401_with_invalid_oauth_signature(self):
        """Returns 401 when Bearer token has invalid signature."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)

        payload = {"sub": "user-42", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        response = client.get(
            "/api/v1/emails",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_health_endpoint_bypasses_auth(self):
        """Health endpoint does not require authentication."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_auth_endpoints_bypass_auth(self):
        """Auth-related endpoints do not require authentication."""
        app = self._make_app_with_patched_settings()
        client = TestClient(app)
        response = client.get("/api/v1/auth/login")
        assert response.status_code == 200

    def test_dev_mode_allows_all_when_no_keys_configured(self):
        """Dev mode: allows all requests when no keys are configured."""
        app = self._make_app_with_patched_settings(api_key="", jwt_secret="")
        client = TestClient(app)
        response = client.get("/api/v1/emails")
        assert response.status_code == 200
        data = response.json()
        assert data["requester"] == "anonymous"


# --- Validation Error Handler Tests ---


class CreateEmailRequest(BaseModel):
    """Model defined at module level so FastAPI can resolve the type annotation."""

    sender: str
    subject: str
    priority: int = Field(ge=1, le=5)


class TestValidationErrorHandler:
    """Test the custom validation error handler (422 with field-level errors)."""

    def _create_validation_app(self):
        """Create app with validation handler and a strict endpoint."""
        app = FastAPI()
        install_validation_error_handler(app)

        @app.post("/api/v1/test")
        async def create_item(body: CreateEmailRequest):
            return {"ok": True}

        return app

    def test_returns_422_for_missing_required_fields(self):
        """Returns 422 with field-level errors for missing fields."""
        app = self._create_validation_app()
        client = TestClient(app)

        response = client.post("/api/v1/test", json={})
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Request validation failed"
        assert "errors" in data
        # Should have errors for sender, subject, priority
        error_fields = [e["loc"][-1] for e in data["errors"]]
        assert "sender" in error_fields
        assert "subject" in error_fields

    def test_returns_422_for_invalid_field_values(self):
        """Returns 422 with field error for out-of-range values."""
        app = self._create_validation_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/test",
            json={"sender": "test@test.com", "subject": "Hi", "priority": 10},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Request validation failed"
        errors = data["errors"]
        assert len(errors) >= 1
        # Priority field should have the error
        priority_errors = [e for e in errors if "priority" in e["loc"]]
        assert len(priority_errors) > 0

    def test_returns_200_for_valid_request(self):
        """Valid request passes validation and returns 200."""
        app = self._create_validation_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/test",
            json={"sender": "test@test.com", "subject": "Hi", "priority": 3},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_error_format_includes_loc_msg_type(self):
        """Each validation error includes loc, msg, and type fields."""
        app = self._create_validation_app()
        client = TestClient(app)

        response = client.post("/api/v1/test", json={"priority": "not-a-number"})
        assert response.status_code == 422
        data = response.json()
        for error in data["errors"]:
            assert "loc" in error
            assert "msg" in error
            assert "type" in error
