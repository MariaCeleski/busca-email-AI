"""Unit tests for the OAuthManager class.

Tests cover:
- OAuth flow initiation for Gmail and Microsoft
- Callback handling (code exchange for tokens)
- Token retrieval with proactive refresh
- Token refresh failure handling (account disconnected)
- Token revocation and deletion
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.auth import TokenPair
from src.providers.oauth import OAuthManager, TokenRefreshError, _OAUTH_CONFIGS


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Create a mock async SQLAlchemy session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_encryption():
    """Create a mock TokenEncryptionService."""
    encryption = MagicMock()
    encryption.encrypt = MagicMock(side_effect=lambda text: f"encrypted:{text}".encode())
    encryption.decrypt = MagicMock(side_effect=lambda data: data.decode().replace("encrypted:", ""))
    return encryption


@pytest.fixture
def mock_settings():
    """Create mock application settings for OAuth."""
    settings = MagicMock()
    settings.google_client_id = "google-client-id"
    settings.google_client_secret = "google-client-secret"
    settings.google_redirect_uri = "http://localhost:8000/api/v1/auth/gmail/callback"
    settings.microsoft_client_id = "ms-client-id"
    settings.microsoft_client_secret = "ms-client-secret"
    settings.microsoft_redirect_uri = "http://localhost:8000/api/v1/auth/microsoft/callback"
    settings.microsoft_tenant_id = "common"
    return settings


@pytest.fixture
def oauth_manager(mock_session, mock_encryption, mock_settings):
    """Create an OAuthManager instance with mocked dependencies."""
    with patch("src.providers.oauth.get_settings", return_value=mock_settings):
        manager = OAuthManager(
            session=mock_session,
            encryption_service=mock_encryption,
        )
    return manager


@pytest.fixture
def connected_account_orm():
    """Create a mock ConnectedAccount ORM object."""
    account = MagicMock()
    account.id = uuid.uuid4()
    account.user_id = uuid.uuid4()
    account.provider = "gmail"
    account.email_address = "user@gmail.com"
    account.encrypted_access_token = b"encrypted:valid-access-token"
    account.encrypted_refresh_token = b"encrypted:valid-refresh-token"
    account.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    account.status = "connected"
    return account


# ─── Tests: initiate_flow ────────────────────────────────────────────────────


class TestInitiateFlow:
    """Tests for OAuthManager.initiate_flow()."""

    def test_initiate_flow_gmail(self, oauth_manager, mock_settings):
        """Test that Gmail OAuth URL is constructed with correct parameters."""
        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            url = oauth_manager.initiate_flow("gmail")

        assert "accounts.google.com" in url
        assert "client_id=google-client-id" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "gmail.readonly" in url
        assert "gmail.send" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_initiate_flow_microsoft(self, oauth_manager, mock_settings):
        """Test that Microsoft OAuth URL is constructed with correct parameters."""
        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            url = oauth_manager.initiate_flow("microsoft")

        assert "login.microsoftonline.com" in url
        assert "client_id=ms-client-id" in url
        assert "response_type=code" in url
        assert "Mail.ReadWrite" in url
        assert "Mail.Send" in url
        assert "offline_access" in url

    def test_initiate_flow_unsupported_provider(self, oauth_manager):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            oauth_manager.initiate_flow("yahoo")


# ─── Tests: handle_callback ─────────────────────────────────────────────────


class TestHandleCallback:
    """Tests for OAuthManager.handle_callback()."""

    async def test_handle_callback_gmail_success(
        self, oauth_manager, mock_settings
    ):
        """Test successful Gmail code exchange returns TokenPair."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                token_pair = await oauth_manager.handle_callback(
                    code="auth-code-123", provider="gmail"
                )

        assert token_pair.access_token == "new-access-token"
        assert token_pair.refresh_token == "new-refresh-token"
        assert token_pair.provider == "gmail"
        assert token_pair.expires_at > datetime.now(timezone.utc)

    async def test_handle_callback_microsoft_success(
        self, oauth_manager, mock_settings
    ):
        """Test successful Microsoft code exchange returns TokenPair."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "ms-access-token",
            "refresh_token": "ms-refresh-token",
            "expires_in": 7200,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                token_pair = await oauth_manager.handle_callback(
                    code="ms-auth-code", provider="microsoft"
                )

        assert token_pair.access_token == "ms-access-token"
        assert token_pair.refresh_token == "ms-refresh-token"
        assert token_pair.provider == "microsoft"

    async def test_handle_callback_empty_code_raises(self, oauth_manager):
        """Test that empty authorization code raises ValueError."""
        with pytest.raises(ValueError, match="Authorization code must not be empty"):
            await oauth_manager.handle_callback(code="", provider="gmail")

    async def test_handle_callback_unsupported_provider_raises(self, oauth_manager):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            await oauth_manager.handle_callback(code="code", provider="yahoo")

    async def test_handle_callback_stores_tokens_when_user_id_provided(
        self, oauth_manager, mock_session, mock_encryption, mock_settings
    ):
        """Test that tokens are encrypted and stored when user_id is given."""
        user_id = str(uuid.uuid4())

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        # Mock the DB lookup for storing tokens
        mock_account = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                await oauth_manager.handle_callback(
                    code="auth-code", provider="gmail", user_id=user_id
                )

        # Verify tokens were encrypted
        mock_encryption.encrypt.assert_any_call("new-access-token")
        mock_encryption.encrypt.assert_any_call("new-refresh-token")

        # Verify account was updated
        assert mock_account.encrypted_access_token is not None
        assert mock_account.encrypted_refresh_token is not None
        assert mock_account.status == "connected"
        mock_session.flush.assert_called()


# ─── Tests: get_valid_token ──────────────────────────────────────────────────


class TestGetValidToken:
    """Tests for OAuthManager.get_valid_token()."""

    async def test_get_valid_token_not_expired(
        self, oauth_manager, mock_session, mock_encryption, connected_account_orm
    ):
        """Test that a valid (non-expired) token is returned directly."""
        # Token expires in 1 hour - no refresh needed
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(connected_account_orm.user_id)
        token = await oauth_manager.get_valid_token(user_id, "gmail")

        assert token == "valid-access-token"

    async def test_get_valid_token_near_expiry_refreshes(
        self, oauth_manager, mock_session, mock_encryption, mock_settings, connected_account_orm
    ):
        """Test that token expiring within 5 min triggers refresh."""
        # Set token to expire in 3 minutes (within 5-minute buffer)
        connected_account_orm.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the HTTP refresh call
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "refreshed-access-token",
            "refresh_token": "refreshed-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                token = await oauth_manager.get_valid_token(
                    str(connected_account_orm.user_id), "gmail"
                )

        assert token == "refreshed-access-token"

    async def test_get_valid_token_expired_triggers_refresh(
        self, oauth_manager, mock_session, mock_encryption, mock_settings, connected_account_orm
    ):
        """Test that an already-expired token triggers refresh."""
        # Set token as already expired
        connected_account_orm.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the HTTP refresh call
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "refresh_token": "fresh-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                token = await oauth_manager.get_valid_token(
                    str(connected_account_orm.user_id), "gmail"
                )

        assert token == "fresh-token"

    async def test_get_valid_token_no_account_raises(
        self, oauth_manager, mock_session
    ):
        """Test that missing account raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="No connected account found"):
            await oauth_manager.get_valid_token(str(uuid.uuid4()), "gmail")

    async def test_get_valid_token_no_access_token_stored_raises(
        self, oauth_manager, mock_session, connected_account_orm
    ):
        """Test that missing stored access token raises ValueError."""
        connected_account_orm.encrypted_access_token = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="No access token stored"):
            await oauth_manager.get_valid_token(
                str(connected_account_orm.user_id), "gmail"
            )

    async def test_get_valid_token_refresh_failure_marks_disconnected(
        self, oauth_manager, mock_session, mock_encryption, mock_settings, connected_account_orm
    ):
        """Test that refresh failure marks account as disconnected (Req 9.5)."""
        # Token is near expiry, will trigger refresh
        connected_account_orm.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the HTTP refresh to fail
        import httpx

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
        )
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                with pytest.raises(TokenRefreshError) as exc_info:
                    await oauth_manager.get_valid_token(
                        str(connected_account_orm.user_id), "gmail"
                    )

        # Verify account was marked as disconnected
        assert connected_account_orm.status == "disconnected"
        mock_session.flush.assert_called()

        # Verify the error contains useful info
        assert "gmail" in str(exc_info.value)

    async def test_get_valid_token_refresh_failure_calls_callback(
        self, mock_session, mock_encryption, mock_settings, connected_account_orm
    ):
        """Test that the on_account_disconnected callback is invoked on failure."""
        callback = MagicMock()

        connected_account_orm.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        import httpx

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Forbidden",
                request=MagicMock(),
                response=MagicMock(status_code=403),
            )
        )
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            manager = OAuthManager(
                session=mock_session,
                encryption_service=mock_encryption,
                on_account_disconnected=callback,
            )
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                with pytest.raises(TokenRefreshError):
                    await manager.get_valid_token(
                        str(connected_account_orm.user_id), "gmail"
                    )

        # Verify callback was called with user_id and provider
        callback.assert_called_once_with(str(connected_account_orm.user_id), "gmail")


# ─── Tests: revoke_and_delete ────────────────────────────────────────────────


class TestRevokeAndDelete:
    """Tests for OAuthManager.revoke_and_delete()."""

    async def test_revoke_and_delete_gmail(
        self, oauth_manager, mock_session, mock_encryption, connected_account_orm
    ):
        """Test that Gmail token is revoked and account deleted."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock revocation HTTP call
        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=MagicMock())
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            await oauth_manager.revoke_and_delete(
                str(connected_account_orm.user_id), "gmail"
            )

        # Verify account was deleted from session
        mock_session.delete.assert_called_once_with(connected_account_orm)
        mock_session.flush.assert_called()

    async def test_revoke_and_delete_no_account_raises(
        self, oauth_manager, mock_session
    ):
        """Test that missing account raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="No connected account found"):
            await oauth_manager.revoke_and_delete(str(uuid.uuid4()), "gmail")

    async def test_revoke_and_delete_continues_on_revocation_failure(
        self, oauth_manager, mock_session, mock_encryption, connected_account_orm
    ):
        """Test that account is deleted even if revocation API fails."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock revocation to fail
        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            await oauth_manager.revoke_and_delete(
                str(connected_account_orm.user_id), "gmail"
            )

        # Account should still be deleted despite revocation failure
        mock_session.delete.assert_called_once_with(connected_account_orm)

    async def test_revoke_and_delete_no_token_skips_revocation(
        self, oauth_manager, mock_session, connected_account_orm
    ):
        """Test that revocation is skipped when no token is stored."""
        connected_account_orm.encrypted_access_token = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        await oauth_manager.revoke_and_delete(
            str(connected_account_orm.user_id), "gmail"
        )

        # Account still gets deleted
        mock_session.delete.assert_called_once_with(connected_account_orm)


# ─── Tests: Proactive token refresh timing ───────────────────────────────────


class TestProactiveTokenRefresh:
    """Tests verifying the 5-minute proactive refresh window."""

    async def test_token_with_6_min_remaining_not_refreshed(
        self, oauth_manager, mock_session, mock_encryption, connected_account_orm
    ):
        """Token with >5 minutes remaining should NOT be refreshed."""
        connected_account_orm.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=6)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        token = await oauth_manager.get_valid_token(
            str(connected_account_orm.user_id), "gmail"
        )

        # Should return the decrypted existing token without refresh
        assert token == "valid-access-token"

    async def test_token_with_exactly_5_min_remaining_refreshed(
        self, oauth_manager, mock_session, mock_encryption, mock_settings, connected_account_orm
    ):
        """Token expiring in exactly 5 minutes should be refreshed."""
        connected_account_orm.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock successful refresh
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "refreshed-token",
            "refresh_token": "refreshed-refresh",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.oauth.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient", return_value=mock_http_client):
                token = await oauth_manager.get_valid_token(
                    str(connected_account_orm.user_id), "gmail"
                )

        assert token == "refreshed-token"

    async def test_token_with_no_expiry_not_refreshed(
        self, oauth_manager, mock_session, mock_encryption, connected_account_orm
    ):
        """Token with no expiry timestamp should NOT trigger refresh."""
        connected_account_orm.token_expires_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = connected_account_orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        token = await oauth_manager.get_valid_token(
            str(connected_account_orm.user_id), "gmail"
        )

        assert token == "valid-access-token"
