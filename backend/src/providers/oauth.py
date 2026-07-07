"""OAuth 2.0 manager for email provider authentication.

Handles the complete OAuth flow: initiating authorization, exchanging codes
for tokens, refreshing expired tokens, and revoking access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.auth import TokenPair
from src.models.repositories import ConnectedAccountRepository
from src.security.encryption import TokenEncryptionService

logger = logging.getLogger(__name__)

# Token refresh buffer: refresh if expiry is within this many minutes
_TOKEN_REFRESH_BUFFER_MINUTES = 5

# OAuth configuration per provider
_OAUTH_CONFIGS: Dict[str, Dict[str, str]] = {
    "gmail": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "revoke_url": "",
        "scope": "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send offline_access",
    },
}


class OAuthManager:
    """Manages OAuth 2.0 flows for email provider connections.

    Provides methods to initiate OAuth authorization, handle callbacks,
    retrieve valid tokens (with automatic refresh), and revoke access.
    Uses TokenEncryptionService for secure token storage and
    ConnectedAccountRepository for database persistence.
    """

    def __init__(
        self,
        session: AsyncSession,
        encryption_service: Optional[TokenEncryptionService] = None,
    ) -> None:
        """Initialize the OAuth manager.

        Args:
            session: An async SQLAlchemy session for database operations.
            encryption_service: Optional encryption service instance.
                If not provided, creates one using app settings.
        """
        self._session = session
        self._repository = ConnectedAccountRepository(session)
        self._encryption = encryption_service or TokenEncryptionService()
        self._settings = get_settings()

    def initiate_flow(self, provider: str) -> str:
        """Start an OAuth authorization flow.

        Constructs the authorization URL for the given provider with
        the appropriate scopes, client ID, and redirect URI.

        Args:
            provider: The email provider ("gmail" or "microsoft").

        Returns:
            The authorization URL to redirect the user to.

        Raises:
            ValueError: If the provider is not supported.
        """
        if provider not in _OAUTH_CONFIGS:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Supported: {list(_OAUTH_CONFIGS.keys())}"
            )

        config = _OAUTH_CONFIGS[provider]

        if provider == "gmail":
            client_id = self._settings.google_client_id
            redirect_uri = self._settings.google_redirect_uri
            auth_url = config["auth_url"]
        elif provider == "microsoft":
            client_id = self._settings.microsoft_client_id
            redirect_uri = self._settings.microsoft_redirect_uri
            tenant = self._settings.microsoft_tenant_id
            auth_url = config["auth_url"].format(tenant=tenant)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        scope = config["scope"]

        url = (
            f"{auth_url}"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        logger.info("Initiated OAuth flow for provider=%s", provider)
        return url

    async def handle_callback(self, code: str, provider: str) -> TokenPair:
        """Exchange an authorization code for tokens.

        Exchanges the code with the provider's token endpoint, encrypts
        the tokens, and stores them in the database.

        Args:
            code: The authorization code from the OAuth callback.
            provider: The email provider ("gmail" or "microsoft").

        Returns:
            A TokenPair with the access and refresh tokens.

        Raises:
            ValueError: If the provider is not supported or code is empty.
            httpx.HTTPStatusError: If the token exchange request fails.
        """
        if not code:
            raise ValueError("Authorization code must not be empty.")
        if provider not in _OAUTH_CONFIGS:
            raise ValueError(f"Unsupported provider: {provider}")

        import httpx

        config = _OAUTH_CONFIGS[provider]

        if provider == "gmail":
            token_url = config["token_url"]
            payload = {
                "code": code,
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "redirect_uri": self._settings.google_redirect_uri,
                "grant_type": "authorization_code",
            }
        elif provider == "microsoft":
            tenant = self._settings.microsoft_tenant_id
            token_url = config["token_url"].format(tenant=tenant)
            payload = {
                "code": code,
                "client_id": self._settings.microsoft_client_id,
                "client_secret": self._settings.microsoft_client_secret,
                "redirect_uri": self._settings.microsoft_redirect_uri,
                "grant_type": "authorization_code",
                "scope": config["scope"],
            }
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        token_pair = TokenPair(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=expires_at,
            provider=provider,
        )

        logger.info("OAuth tokens obtained for provider=%s", provider)
        return token_pair

    async def get_valid_token(self, user_id: str, provider: str) -> str:
        """Get a valid access token, refreshing if near expiry.

        Retrieves the stored token for the user/provider combination.
        If the token expires within 5 minutes, it is automatically refreshed.

        Args:
            user_id: The user's identifier.
            provider: The email provider ("gmail" or "microsoft").

        Returns:
            A valid access token string.

        Raises:
            ValueError: If no connected account is found for the user/provider.
            RuntimeError: If token refresh fails.
        """
        import uuid as uuid_module

        from src.models.orm import ConnectedAccount as ConnectedAccountORM

        # Look up the connected account
        from sqlalchemy import select

        stmt = select(ConnectedAccountORM).where(
            ConnectedAccountORM.user_id == uuid_module.UUID(user_id),
            ConnectedAccountORM.provider == provider,
        )
        result = await self._session.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            raise ValueError(
                f"No connected account found for user={user_id}, provider={provider}"
            )

        # Decrypt the stored access token
        if account.encrypted_access_token is None:
            raise ValueError("No access token stored for this account.")

        access_token = self._encryption.decrypt(account.encrypted_access_token)

        # Check if token needs refresh (expires within 5 minutes)
        if account.token_expires_at is not None:
            buffer = timedelta(minutes=_TOKEN_REFRESH_BUFFER_MINUTES)
            now = datetime.now(timezone.utc)

            if account.token_expires_at <= now + buffer:
                logger.info(
                    "Token near expiry for user=%s provider=%s, refreshing",
                    user_id,
                    provider,
                )
                token_pair = await self._refresh_token_for_account(account)
                access_token = token_pair.access_token

        return access_token

    async def revoke_and_delete(self, user_id: str, provider: str) -> None:
        """Revoke the OAuth token and delete stored credentials.

        Attempts to revoke the token with the provider, then removes
        the connected account from the database regardless of revocation
        success (best-effort revocation).

        Args:
            user_id: The user's identifier.
            provider: The email provider ("gmail" or "microsoft").

        Raises:
            ValueError: If no connected account is found.
        """
        import uuid as uuid_module

        from src.models.orm import ConnectedAccount as ConnectedAccountORM
        from sqlalchemy import select

        stmt = select(ConnectedAccountORM).where(
            ConnectedAccountORM.user_id == uuid_module.UUID(user_id),
            ConnectedAccountORM.provider == provider,
        )
        result = await self._session.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            raise ValueError(
                f"No connected account found for user={user_id}, provider={provider}"
            )

        # Best-effort token revocation with the provider
        if account.encrypted_access_token is not None:
            try:
                token = self._encryption.decrypt(account.encrypted_access_token)
                await self._revoke_with_provider(token, provider)
            except Exception as exc:
                logger.warning(
                    "Token revocation failed for user=%s provider=%s: %s",
                    user_id,
                    provider,
                    exc,
                )

        # Delete the account from the database
        await self._session.delete(account)
        await self._session.flush()

        logger.info(
            "Revoked and deleted credentials for user=%s provider=%s",
            user_id,
            provider,
        )

    async def _refresh_token_for_account(self, account) -> TokenPair:
        """Refresh the token for a connected account and update storage.

        Args:
            account: The ConnectedAccount ORM instance.

        Returns:
            The new TokenPair.

        Raises:
            RuntimeError: If the refresh token is missing or refresh fails.
        """
        import httpx

        if account.encrypted_refresh_token is None:
            raise RuntimeError("No refresh token available for this account.")

        refresh_token = self._encryption.decrypt(account.encrypted_refresh_token)
        provider = account.provider
        config = _OAUTH_CONFIGS[provider]

        if provider == "gmail":
            token_url = config["token_url"]
            payload = {
                "refresh_token": refresh_token,
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "grant_type": "refresh_token",
            }
        elif provider == "microsoft":
            tenant = self._settings.microsoft_tenant_id
            token_url = config["token_url"].format(tenant=tenant)
            payload = {
                "refresh_token": refresh_token,
                "client_id": self._settings.microsoft_client_id,
                "client_secret": self._settings.microsoft_client_secret,
                "grant_type": "refresh_token",
                "scope": config["scope"],
            }
        else:
            raise RuntimeError(f"Unsupported provider: {provider}")

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        token_pair = TokenPair(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            provider=provider,
        )

        # Update encrypted tokens in the database
        account.encrypted_access_token = self._encryption.encrypt(
            token_pair.access_token
        )
        account.encrypted_refresh_token = self._encryption.encrypt(
            token_pair.refresh_token
        )
        account.token_expires_at = expires_at
        await self._session.flush()

        logger.info("Token refreshed for provider=%s", provider)
        return token_pair

    async def _revoke_with_provider(self, token: str, provider: str) -> None:
        """Attempt to revoke a token with the OAuth provider.

        Args:
            token: The access token to revoke.
            provider: The email provider.
        """
        import httpx

        config = _OAUTH_CONFIGS[provider]
        revoke_url = config.get("revoke_url")

        if not revoke_url:
            logger.debug("No revoke URL for provider=%s, skipping", provider)
            return

        async with httpx.AsyncClient() as client:
            if provider == "gmail":
                await client.post(revoke_url, params={"token": token})
            else:
                # Microsoft doesn't have a standard revoke endpoint
                pass
