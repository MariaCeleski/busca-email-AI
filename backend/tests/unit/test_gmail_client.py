"""Unit tests for the Gmail API client."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.models.auth import ApprovedReply, SendResult, TokenPair
from src.models.email import AttachmentMetadata, RawEmail
from src.providers.gmail import GmailClient


@pytest.fixture
def gmail_client() -> GmailClient:
    """Create a GmailClient instance with test tokens."""
    return GmailClient(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
    )


@pytest.fixture
def sample_gmail_message() -> dict:
    """Create a sample Gmail API message response."""
    body_text = "Hello, this is a test email body."
    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

    return {
        "id": "msg-123",
        "threadId": "thread-456",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test Subject"},
                {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_body, "size": len(body_text)},
                },
                {
                    "filename": "report.pdf",
                    "mimeType": "application/pdf",
                    "body": {"size": 1024, "attachmentId": "att-1"},
                },
            ],
        },
    }


class TestGmailClientFetchUnread:
    """Tests for GmailClient.fetch_unread()."""

    async def test_fetch_unread_returns_emails(
        self, gmail_client: GmailClient, sample_gmail_message: dict
    ):
        """Test that fetch_unread returns parsed RawEmail objects."""
        list_response = MagicMock()
        list_response.json.return_value = {
            "messages": [{"id": "msg-123", "threadId": "thread-456"}]
        }
        list_response.raise_for_status = MagicMock()

        detail_response = MagicMock()
        detail_response.json.return_value = sample_gmail_message
        detail_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[list_response, detail_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            emails = await gmail_client.fetch_unread()

        assert len(emails) == 1
        email = emails[0]
        assert email.provider_message_id == "msg-123"
        assert email.sender == "sender@example.com"
        assert email.subject == "Test Subject"
        assert email.body == "Hello, this is a test email body."
        assert email.thread_id == "thread-456"
        assert email.provider == "gmail"

    async def test_fetch_unread_empty_inbox(self, gmail_client: GmailClient):
        """Test that fetch_unread returns empty list when no messages."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            emails = await gmail_client.fetch_unread()

        assert emails == []

    async def test_fetch_unread_parses_attachments(
        self, gmail_client: GmailClient, sample_gmail_message: dict
    ):
        """Test that attachments are correctly parsed."""
        list_response = MagicMock()
        list_response.json.return_value = {
            "messages": [{"id": "msg-123", "threadId": "thread-456"}]
        }
        list_response.raise_for_status = MagicMock()

        detail_response = MagicMock()
        detail_response.json.return_value = sample_gmail_message
        detail_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[list_response, detail_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            emails = await gmail_client.fetch_unread()

        assert len(emails[0].attachments) == 1
        att = emails[0].attachments[0]
        assert att.file_name == "report.pdf"
        assert att.file_size == 1024
        assert att.mime_type == "application/pdf"

    async def test_fetch_unread_parses_timestamp(
        self, gmail_client: GmailClient, sample_gmail_message: dict
    ):
        """Test that email timestamps are parsed into datetime with timezone."""
        list_response = MagicMock()
        list_response.json.return_value = {
            "messages": [{"id": "msg-123", "threadId": "thread-456"}]
        }
        list_response.raise_for_status = MagicMock()

        detail_response = MagicMock()
        detail_response.json.return_value = sample_gmail_message
        detail_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[list_response, detail_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            emails = await gmail_client.fetch_unread()

        assert emails[0].timestamp.tzinfo is not None
        assert emails[0].timestamp.year == 2024
        assert emails[0].timestamp.month == 1
        assert emails[0].timestamp.day == 15


class TestGmailClientSendReply:
    """Tests for GmailClient.send_reply()."""

    async def test_send_reply_success(self, gmail_client: GmailClient):
        """Test successful email send."""
        reply = ApprovedReply(
            email_id="msg-123",
            to_address="recipient@example.com",
            subject="Re: Test Subject",
            body="Thank you for your email.",
            thread_id="thread-456",
            in_reply_to="<original-msg-id@gmail.com>",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "sent-msg-789"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            result = await gmail_client.send_reply(reply)

        assert result.success is True
        assert result.provider_message_id == "sent-msg-789"

    async def test_send_reply_retry_on_failure(self, gmail_client: GmailClient):
        """Test that send retries once after 5s on failure, then returns error."""
        reply = ApprovedReply(
            email_id="msg-123",
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

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            with patch("src.providers.gmail.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await gmail_client.send_reply(reply)

        assert result.success is False
        assert result.error is not None
        # Should have slept once for retry
        mock_sleep.assert_called_once_with(5)

    async def test_send_reply_success_on_retry(self, gmail_client: GmailClient):
        """Test that send succeeds on retry after initial failure."""
        reply = ApprovedReply(
            email_id="msg-123",
            to_address="recipient@example.com",
            subject="Re: Test Subject",
            body="Reply body",
            thread_id="thread-456",
        )

        success_response = MagicMock()
        success_response.json.return_value = {"id": "sent-msg-999"}
        success_response.raise_for_status = MagicMock()

        # First call raises, second succeeds
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

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            with patch("src.providers.gmail.asyncio.sleep", new_callable=AsyncMock):
                result = await gmail_client.send_reply(reply)

        assert result.success is True
        assert result.provider_message_id == "sent-msg-999"


class TestGmailClientRefreshToken:
    """Tests for GmailClient.refresh_token()."""

    async def test_refresh_token_success(self, gmail_client: GmailClient):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.providers.gmail.httpx.AsyncClient", return_value=mock_client):
            with patch("src.providers.gmail.get_settings") as mock_settings:
                mock_settings.return_value.google_client_id = "test-client-id"
                mock_settings.return_value.google_client_secret = "test-secret"
                token_pair = await gmail_client.refresh_token()

        assert token_pair.access_token == "new-access-token"
        assert token_pair.refresh_token == "new-refresh-token"
        assert token_pair.provider == "gmail"
        assert token_pair.expires_at.tzinfo is not None

    async def test_refresh_token_no_refresh_token(self):
        """Test that refresh raises when no refresh token available."""
        client = GmailClient(access_token="test-token", refresh_token=None)

        with pytest.raises(RuntimeError, match="No refresh token"):
            await client.refresh_token()


# Need to import httpx for side_effect usage
import httpx
