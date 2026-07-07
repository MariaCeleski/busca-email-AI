"""Unit tests for the EmailMonitor service.

Tests:
- Polling interval validation (rejects < 10s)
- Deduplication (duplicate emails rejected)
- Webhook processing within timeout
- Auth retry logic (3 retries with 5s delay)
- Connectivity retry with exponential backoff
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.auth import TokenPair
from src.models.email import AttachmentMetadata, RawEmail
from src.providers.base import EmailProviderClient
from src.services.email_monitor import (
    EmailMonitor,
    ProviderAPIError,
    ProviderAuthError,
)


def _make_raw_email(
    message_id: str = "msg-001",
    sender: str = "sender@example.com",
    subject: str = "Test Subject",
) -> RawEmail:
    """Create a RawEmail for testing."""
    return RawEmail(
        provider_message_id=message_id,
        sender=sender,
        subject=subject,
        body="Test body content",
        timestamp=datetime.now(timezone.utc),
        attachments=[
            AttachmentMetadata(
                file_name="doc.pdf", file_size=1024, mime_type="application/pdf"
            )
        ],
        provider="gmail",
    )


def _make_monitor(
    provider_client: EmailProviderClient | None = None,
) -> EmailMonitor:
    """Create an EmailMonitor with mocked dependencies."""
    session = AsyncMock()
    if provider_client is None:
        provider_client = AsyncMock(spec=EmailProviderClient)
    with patch("src.services.email_monitor.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(email_poll_interval_seconds=60)
        monitor = EmailMonitor(session=session, provider_client=provider_client)
    return monitor


class TestPollingIntervalValidation:
    """Test that polling interval validation works correctly."""

    async def test_rejects_interval_below_10_seconds(self) -> None:
        """Polling interval below 10s raises ValueError."""
        monitor = _make_monitor()
        with pytest.raises(ValueError, match="at least 10 seconds"):
            await monitor.start_polling(interval_seconds=5)

    async def test_rejects_interval_of_zero(self) -> None:
        """Polling interval of 0 raises ValueError."""
        monitor = _make_monitor()
        with pytest.raises(ValueError, match="at least 10 seconds"):
            await monitor.start_polling(interval_seconds=0)

    async def test_accepts_interval_of_10_seconds(self) -> None:
        """Polling interval of exactly 10s is accepted."""
        monitor = _make_monitor()
        await monitor.start_polling(interval_seconds=10)
        assert monitor.is_polling is True
        await monitor.stop_polling()

    async def test_accepts_interval_above_10_seconds(self) -> None:
        """Polling interval above 10s is accepted."""
        monitor = _make_monitor()
        await monitor.start_polling(interval_seconds=120)
        assert monitor.is_polling is True
        await monitor.stop_polling()


class TestDeduplication:
    """Test email deduplication logic."""

    async def test_duplicate_email_rejected(self) -> None:
        """Attempting to enqueue same message_id twice returns None."""
        monitor = _make_monitor()
        email = _make_raw_email(message_id="dup-001")

        # Mock the repository check to return None (not found in DB)
        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            # First enqueue should succeed
            result1 = await monitor.enqueue_email(email)
            assert result1 is not None

            # Second enqueue of same message_id should return None (duplicate)
            result2 = await monitor.enqueue_email(email)
            assert result2 is None

    async def test_non_duplicate_email_accepted(self) -> None:
        """Different message_ids are enqueued successfully."""
        monitor = _make_monitor()
        email1 = _make_raw_email(message_id="unique-001")
        email2 = _make_raw_email(message_id="unique-002")

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            result1 = await monitor.enqueue_email(email1)
            result2 = await monitor.enqueue_email(email2)
            assert result1 is not None
            assert result2 is not None
            assert result1 != result2

    async def test_database_duplicate_detected(self) -> None:
        """Email already in database is detected as duplicate."""
        monitor = _make_monitor()
        email = _make_raw_email(message_id="db-dup-001")

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            # Simulate email already in DB
            mock_repo_instance.get_by_provider_message_id.return_value = MagicMock()
            MockRepo.return_value = mock_repo_instance

            result = await monitor.enqueue_email(email)
            assert result is None


class TestWebhookProcessing:
    """Test webhook processing behavior."""

    async def test_webhook_processes_emails(self) -> None:
        """Webhook fetches and enqueues emails."""
        provider = AsyncMock(spec=EmailProviderClient)
        email = _make_raw_email(message_id="webhook-001")
        provider.fetch_unread.return_value = [email]

        monitor = _make_monitor(provider_client=provider)

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            await monitor.handle_webhook({"notification": "new_email"})

        provider.fetch_unread.assert_called_once()

    async def test_webhook_timeout_raises(self) -> None:
        """Webhook that exceeds 5s timeout raises TimeoutError."""
        provider = AsyncMock(spec=EmailProviderClient)

        async def slow_fetch():
            await asyncio.sleep(10)
            return []

        provider.fetch_unread.side_effect = slow_fetch

        monitor = _make_monitor(provider_client=provider)

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await monitor.handle_webhook({"notification": "new_email"})


class TestAuthRetryLogic:
    """Test auth token refresh retry behavior."""

    async def test_auth_retry_3_times_then_suspend(self) -> None:
        """Auth failure retries refresh 3 times then suspends polling."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        # Override delay for faster test
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        with pytest.raises(ProviderAuthError):
            await monitor.fetch_emails(provider)

        assert monitor.auth_suspended is True
        assert provider.refresh_token.call_count == 3

    async def test_auth_refresh_success_retries_fetch(self) -> None:
        """Successful token refresh allows fetch to succeed."""
        provider = AsyncMock(spec=EmailProviderClient)
        email = _make_raw_email(message_id="after-refresh-001")

        # First fetch fails with auth error, refresh succeeds, second fetch works
        call_count = 0

        async def fetch_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderAuthError("Token expired")
            return [email]

        provider.fetch_unread.side_effect = fetch_side_effect
        provider.refresh_token.return_value = TokenPair(
            access_token="new-token",
            refresh_token="new-refresh",
            expires_at=datetime.now(timezone.utc),
            provider="gmail",
        )
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        result = await monitor.fetch_emails(provider)
        assert len(result) == 1
        assert result[0].provider_message_id == "after-refresh-001"


class TestConnectivityRetry:
    """Test connectivity retry with exponential backoff."""

    async def test_connectivity_retry_with_backoff(self) -> None:
        """Connectivity failure retries 3x with exponential backoff."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAPIError("Connection timeout")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        # Override backoff for faster test
        monitor.CONNECTIVITY_BACKOFF_BASE_SECONDS = 0.01

        with pytest.raises(ProviderAPIError):
            await monitor.fetch_emails(provider)

        # Initial attempt + 3 retries = 4 total calls
        assert provider.fetch_unread.call_count == 4

    async def test_connectivity_succeeds_on_retry(self) -> None:
        """Fetch succeeds on second attempt after connectivity failure."""
        provider = AsyncMock(spec=EmailProviderClient)
        email = _make_raw_email(message_id="retry-success-001")

        call_count = 0

        async def fetch_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ProviderAPIError("Temporary failure")
            return [email]

        provider.fetch_unread.side_effect = fetch_side_effect
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        monitor.CONNECTIVITY_BACKOFF_BASE_SECONDS = 0.01

        result = await monitor.fetch_emails(provider)
        assert len(result) == 1
        assert call_count == 3
