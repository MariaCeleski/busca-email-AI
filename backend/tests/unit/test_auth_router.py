"""Unit tests for the auth router endpoints.

Tests:
- GET /api/v1/auth/{provider}/connect — OAuth flow initiation
- GET /api/v1/auth/{provider}/callback — OAuth code exchange
- POST /api/v1/auth/{provider}/disconnect — Account disconnection and data deletion

Validates: Requirements 9.1, 9.2, 9.3, 10.5, 10.6, 10.7
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routers.auth import (
    _MAX_DELETION_RETRIES,
    _delete_user_data_with_retry,
    router,
)


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the auth router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Tests for GET /api/v1/auth/{provider}/connect ---


class TestConnectEndpoint:
    """Tests for the OAuth connect endpoint."""

    @pytest.mark.asyncio
    async def test_connect_gmail_returns_authorization_url(self, client):
        """Should return an authorization URL for gmail."""
        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_instance = MockOAuthManager.return_value
            mock_instance.initiate_flow.return_value = (
                "https://accounts.google.com/o/oauth2/v2/auth?client_id=test"
            )

            response = await client.get("/api/v1/auth/gmail/connect")

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "gmail"
        assert "authorization_url" in data
        assert data["authorization_url"].startswith("https://accounts.google.com")
        mock_instance.initiate_flow.assert_called_once_with("gmail")

    @pytest.mark.asyncio
    async def test_connect_microsoft_returns_authorization_url(self, client):
        """Should return an authorization URL for microsoft."""
        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_instance = MockOAuthManager.return_value
            mock_instance.initiate_flow.return_value = (
                "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test"
            )

            response = await client.get("/api/v1/auth/microsoft/connect")

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "microsoft"
        assert "authorization_url" in data

    @pytest.mark.asyncio
    async def test_connect_unsupported_provider_returns_400(self, client):
        """Should return 400 for unsupported provider."""
        response = await client.get("/api/v1/auth/yahoo/connect")
        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_connect_initiate_flow_value_error(self, client):
        """Should return 400 if OAuthManager raises ValueError."""
        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_instance = MockOAuthManager.return_value
            mock_instance.initiate_flow.side_effect = ValueError("Bad config")

            response = await client.get("/api/v1/auth/gmail/connect")

        assert response.status_code == 400
        assert "Bad config" in response.json()["detail"]


# --- Tests for GET /api/v1/auth/{provider}/callback ---


class TestCallbackEndpoint:
    """Tests for the OAuth callback endpoint."""

    @pytest.mark.asyncio
    async def test_callback_with_error_param_redirects(self, client):
        """Should redirect to dashboard with error when consent is denied (Req 9.3)."""
        response = await client.get(
            "/api/v1/auth/gmail/callback?error=access_denied",
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert "auth/error" in location
        assert "consent_denied" in location

    @pytest.mark.asyncio
    async def test_callback_without_code_returns_400(self, client):
        """Should return 400 if no code is provided."""
        response = await client.get("/api/v1/auth/gmail/callback")
        assert response.status_code == 400
        assert "Authorization code is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_callback_unsupported_provider_returns_400(self, client):
        """Should return 400 for unsupported provider."""
        response = await client.get(
            "/api/v1/auth/yahoo/callback?code=test_code"
        )
        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_callback_success_redirects_to_dashboard(self, client):
        """Should redirect to dashboard on successful code exchange."""
        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_instance = MockOAuthManager.return_value
            mock_instance.handle_callback = AsyncMock(
                return_value=MagicMock(
                    access_token="access_123",
                    refresh_token="refresh_123",
                    expires_at=datetime.now(timezone.utc),
                    provider="gmail",
                )
            )

            response = await client.get(
                "/api/v1/auth/gmail/callback?code=valid_code&state=12345678-1234-5678-1234-567812345678",
                follow_redirects=False,
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "auth/success" in location
        assert "provider=gmail" in location
        mock_instance.handle_callback.assert_called_once_with(
            code="valid_code", provider="gmail", user_id="12345678-1234-5678-1234-567812345678"
        )

    @pytest.mark.asyncio
    async def test_callback_exchange_failure_returns_502(self, client):
        """Should return 502 if token exchange fails with provider."""
        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_instance = MockOAuthManager.return_value
            mock_instance.handle_callback = AsyncMock(
                side_effect=RuntimeError("Network error")
            )

            response = await client.get(
                "/api/v1/auth/gmail/callback?code=bad_code"
            )

        assert response.status_code == 502
        assert "Failed to exchange authorization code" in response.json()["detail"]


# --- Tests for POST /api/v1/auth/{provider}/disconnect ---


class TestDisconnectEndpoint:
    """Tests for the account disconnection endpoint."""

    @pytest.mark.asyncio
    async def test_disconnect_unsupported_provider_returns_400(self, client):
        """Should return 400 for unsupported provider."""
        response = await client.post("/api/v1/auth/yahoo/disconnect")
        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_disconnect_no_account_returns_404(self):
        """Should return 404 if no connected account found."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(router)

        from src.models.database import get_session

        async def override_session():
            return mock_session

        app.dependency_overrides[get_session] = override_session

        @app.middleware("http")
        async def add_state(request, call_next):
            request.state.requester_id = "test-user"
            return await call_next(request)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.post("/api/v1/auth/gmail/disconnect")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        """Should disconnect account, delete data, and return success."""
        # Create a more controlled test
        mock_account = MagicMock()
        mock_account.user_id = uuid.uuid4()
        mock_account.provider = "gmail"
        mock_account.status = "connected"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        app = FastAPI()
        app.include_router(router)

        from src.models.database import get_session

        async def override_session():
            return mock_session

        app.dependency_overrides[get_session] = override_session

        @app.middleware("http")
        async def add_state(request, call_next):
            request.state.requester_id = "test-user"
            return await call_next(request)

        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_oauth = MockOAuthManager.return_value
            mock_oauth.revoke_and_delete = AsyncMock()

            with patch(
                "src.api.routers.auth._delete_user_data_with_retry"
            ) as mock_delete:
                mock_delete.return_value = (5, 10)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as test_client:
                    response = await test_client.post(
                        "/api/v1/auth/gmail/disconnect"
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["provider"] == "gmail"
        assert data["tokens_deleted"] is True
        assert data["emails_deleted"] == 5
        assert data["embeddings_deleted"] == 10

    @pytest.mark.asyncio
    async def test_disconnect_deletion_failure_returns_500(self):
        """Should return 500 if data deletion fails after retries (Req 10.7)."""
        mock_account = MagicMock()
        mock_account.user_id = uuid.uuid4()
        mock_account.provider = "gmail"
        mock_account.status = "connected"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        app = FastAPI()
        app.include_router(router)

        from src.models.database import get_session

        async def override_session():
            return mock_session

        app.dependency_overrides[get_session] = override_session

        @app.middleware("http")
        async def add_state(request, call_next):
            request.state.requester_id = "test-user"
            return await call_next(request)

        with patch(
            "src.api.routers.auth.OAuthManager"
        ) as MockOAuthManager:
            mock_oauth = MockOAuthManager.return_value
            mock_oauth.revoke_and_delete = AsyncMock()

            with patch(
                "src.api.routers.auth._delete_user_data_with_retry"
            ) as mock_delete:
                mock_delete.side_effect = RuntimeError(
                    "Deletion failed after 3 attempts"
                )

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as test_client:
                    response = await test_client.post(
                        "/api/v1/auth/gmail/disconnect"
                    )

        assert response.status_code == 500
        assert "data deletion failed" in response.json()["detail"]


# --- Tests for _delete_user_data_with_retry ---


class TestDeleteUserDataWithRetry:
    """Tests for the deletion retry logic."""

    @pytest.mark.asyncio
    async def test_successful_deletion_on_first_attempt(self):
        """Should succeed on first attempt without retrying."""
        mock_session = AsyncMock()
        user_id = uuid.uuid4()

        with patch(
            "src.api.routers.auth.ProcessedEmailRepository"
        ) as MockEmailRepo, patch(
            "src.api.routers.auth.VectorStoreService"
        ) as MockVectorStore:
            mock_email_repo = MockEmailRepo.return_value
            mock_email_repo.delete_by_user = AsyncMock(return_value=3)

            mock_vector_store = MockVectorStore.return_value
            mock_vector_store.delete_by_user = AsyncMock(return_value=7)

            emails_deleted, embeddings_deleted = await _delete_user_data_with_retry(
                user_id=user_id,
                provider="gmail",
                session=mock_session,
            )

        assert emails_deleted == 3
        assert embeddings_deleted == 7

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """Should retry and succeed on second attempt."""
        mock_session = AsyncMock()
        user_id = uuid.uuid4()

        call_count = 0

        with patch(
            "src.api.routers.auth.ProcessedEmailRepository"
        ) as MockEmailRepo, patch(
            "src.api.routers.auth.VectorStoreService"
        ) as MockVectorStore, patch(
            "src.api.routers.auth.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_email_repo = MockEmailRepo.return_value
            mock_email_repo.delete_by_user = AsyncMock(return_value=2)

            mock_vector_store = MockVectorStore.return_value

            async def failing_then_succeeding(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("ChromaDB unavailable")
                return 4

            mock_vector_store.delete_by_user = AsyncMock(
                side_effect=failing_then_succeeding
            )

            emails_deleted, embeddings_deleted = await _delete_user_data_with_retry(
                user_id=user_id,
                provider="gmail",
                session=mock_session,
            )

        assert emails_deleted == 2
        assert embeddings_deleted == 4
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Should raise RuntimeError after exhausting all retries (Req 10.7)."""
        mock_session = AsyncMock()
        user_id = uuid.uuid4()

        with patch(
            "src.api.routers.auth.ProcessedEmailRepository"
        ) as MockEmailRepo, patch(
            "src.api.routers.auth.VectorStoreService"
        ) as MockVectorStore, patch(
            "src.api.routers.auth.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_email_repo = MockEmailRepo.return_value
            mock_email_repo.delete_by_user = AsyncMock(
                side_effect=RuntimeError("DB connection lost")
            )

            with pytest.raises(RuntimeError) as exc_info:
                await _delete_user_data_with_retry(
                    user_id=user_id,
                    provider="gmail",
                    session=mock_session,
                )

        assert f"failed after {_MAX_DELETION_RETRIES} attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retries_exactly_max_times(self):
        """Should attempt deletion exactly _MAX_DELETION_RETRIES times."""
        mock_session = AsyncMock()
        user_id = uuid.uuid4()
        attempt_count = 0

        with patch(
            "src.api.routers.auth.ProcessedEmailRepository"
        ) as MockEmailRepo, patch(
            "src.api.routers.auth.VectorStoreService"
        ) as MockVectorStore, patch(
            "src.api.routers.auth.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_email_repo = MockEmailRepo.return_value

            async def count_attempts(*args, **kwargs):
                nonlocal attempt_count
                attempt_count += 1
                raise RuntimeError("Always fails")

            mock_email_repo.delete_by_user = AsyncMock(side_effect=count_attempts)

            with pytest.raises(RuntimeError):
                await _delete_user_data_with_retry(
                    user_id=user_id,
                    provider="gmail",
                    session=mock_session,
                )

        assert attempt_count == _MAX_DELETION_RETRIES
