"""Unit tests for the Microsoft Graph API client."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.models.auth import ApprovedReply, SendResult, TokenPair
from src.models.email import AttachmentMetadata, RawEmail
from src.providers.microsoft import MicrosoftGraphClient


@pytest.fixture
def microsoft_client() -> MicrosoftGraphClient:
    """Create a MicrosoftGraphClient instance with test tokens."""
    return MicrosoftGraphClient(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
    )


@pytest.fixture
def sample_graph_message() -> dict:
    """Create a sample Microsoft Graph API message response."""
    return {
        "id": "msg-abc-123",
        "subject": "Test Subject from Microsoft",
        "conversationId": "conv-789",
        "from": {
            "emailAddress": {
                "name": "John Doe",
                "address": "john@example.com",
            }
        },
        "body": {
            "contentType": "text",
            "content": "Hello from Microsoft Graph!",
        },
        "receivedDateTime": "2024-01-15T10:30:00Z",
        "hasAttachments": True,
        "attachments": [
            {
                "name": "document.docx",
                "size": 2048,
                "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "isInline": False,
            },
            {
                "name": "inline-image.png",
                "size": 512,
                "contentType": "image/png",
                "isInline": True,
            },
        ],
    }


class TestMicrosoftGraphClientFetchUnread:
    """Tests for MicrosoftGraphClient.fetch_unread()."""

    async def test_fetch_unread_returns_emails(
        self, microsoft_client: MicrosoftGraphClient, sample_graph_message: dict
    ):
        """Test that fetch_unread returns parsed RawEmail objects."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": [sample_graph_message]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            emails = await microsoft_client.fetch_unread()

        assert len(emails) == 1
        email = emails[0]
        assert email.provider_message_id == "msg-abc-123"
        assert email.sender == "John Doe <john@example.com>"
        assert email.subject == "Test Subject from Microsoft"
        assert email.body == "Hello from Microsoft Graph!"
        assert email.thread_id == "conv-789"
        assert email.provider == "microsoft"

    async def test_fetch_unread_empty_inbox(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test that fetch_unread returns empty list when no messages."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            emails = await microsoft_client.fetch_unread()

        assert emails == []

    async def test_fetch_unread_parses_attachments(
        self, microsoft_client: MicrosoftGraphClient, sample_graph_message: dict
    ):
        """Test that attachments are correctly parsed (inline excluded)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": [sample_graph_message]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            emails = await microsoft_client.fetch_unread()

        # Only non-inline attachment should be included
        assert len(emails[0].attachments) == 1
        att = emails[0].attachments[0]
        assert att.file_name == "document.docx"
        assert att.file_size == 2048
        assert att.mime_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    async def test_fetch_unread_parses_timestamp(
        self, microsoft_client: MicrosoftGraphClient, sample_graph_message: dict
    ):
        """Test that timestamps are parsed to timezone-aware datetime."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": [sample_graph_message]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            emails = await microsoft_client.fetch_unread()

        assert emails[0].timestamp.tzinfo is not None
        assert emails[0].timestamp.year == 2024
        assert emails[0].timestamp.month == 1
        assert emails[0].timestamp.day == 15
        assert emails[0].timestamp.hour == 10
        assert emails[0].timestamp.minute == 30

    async def test_fetch_unread_sender_without_name(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test that sender is formatted correctly when no name is present."""
        msg = {
            "id": "msg-no-name",
            "subject": "No Name Subject",
            "conversationId": "conv-1",
            "from": {
                "emailAddress": {
                    "name": "",
                    "address": "noreply@example.com",
                }
            },
            "body": {"contentType": "text", "content": "body text"},
            "receivedDateTime": "2024-02-01T08:00:00Z",
            "hasAttachments": False,
            "attachments": [],
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": [msg]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            emails = await microsoft_client.fetch_unread()

        assert emails[0].sender == "noreply@example.com"


class TestMicrosoftGraphClientSendReply:
    """Tests for MicrosoftGraphClient.send_reply()."""

    async def test_send_reply_success(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test successful reply send."""
        reply = ApprovedReply(
            email_id="msg-abc-123",
            to_address="recipient@example.com",
            subject="Re: Test Subject",
            body="Thank you for your email.",
            thread_id="conv-789",
        )

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            result = await microsoft_client.send_reply(reply)

        assert result.success is True
        assert result.provider_message_id == "msg-abc-123"

    async def test_send_reply_retry_on_failure(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test that send retries once after 5s on failure, then returns error."""
        reply = ApprovedReply(
            email_id="msg-abc-123",
            to_address="recipient@example.com",
            subject="Re: Test Subject",
            body="Reply body",
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            with patch(
                "src.providers.microsoft.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep:
                result = await microsoft_client.send_reply(reply)

        assert result.success is False
        assert result.error is not None
        mock_sleep.assert_called_once_with(5)

    async def test_send_reply_success_on_retry(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test that send succeeds on retry after initial failure."""
        reply = ApprovedReply(
            email_id="msg-abc-123",
            to_address="recipient@example.com",
            subject="Re: Test Subject",
            body="Reply body",
        )

        success_response = MagicMock()
        success_response.status_code = 202
        success_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=[
                httpx.HTTPStatusError(
                    "Temporary Error",
                    request=MagicMock(),
                    response=MagicMock(status_code=503),
                ),
                success_response,
            ]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            with patch(
                "src.providers.microsoft.asyncio.sleep", new_callable=AsyncMock
            ):
                result = await microsoft_client.send_reply(reply)

        assert result.success is True
        assert result.provider_message_id == "msg-abc-123"


class TestMicrosoftGraphClientRefreshToken:
    """Tests for MicrosoftGraphClient.refresh_token()."""

    async def test_refresh_token_success(
        self, microsoft_client: MicrosoftGraphClient
    ):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-ms-access-token",
            "refresh_token": "new-ms-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.providers.microsoft.httpx.AsyncClient", return_value=mock_client
        ):
            with patch("src.providers.microsoft.get_settings") as mock_settings:
                mock_settings.return_value.microsoft_client_id = "test-client-id"
                mock_settings.return_value.microsoft_client_secret = "test-secret"
                mock_settings.return_value.microsoft_tenant_id = "test-tenant"
                token_pair = await microsoft_client.refresh_token()

        assert token_pair.access_token == "new-ms-access-token"
        assert token_pair.refresh_token == "new-ms-refresh-token"
        assert token_pair.provider == "microsoft"
        assert token_pair.expires_at.tzinfo is not None

    async def test_refresh_token_no_refresh_token(self):
        """Test that refresh raises when no refresh token available."""
        client = MicrosoftGraphClient(
            access_token="test-token", refresh_token=None
        )

        with pytest.raises(RuntimeError, match="No refresh token"):
            await client.refresh_token()


# Need to import httpx for side_effect usage
import httpx
