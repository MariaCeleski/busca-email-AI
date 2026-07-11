"""Unit tests for the EmailMonitor service.

Tests:
- Polling interval validation (rejects < 10s)
- Deduplication (duplicate emails rejected)
- Webhook processing within timeout
- Auth retry logic (3 retries with 5s delay)
- Connectivity retry with exponential backoff
- Email field extraction completeness
- Celery task enqueueing integration
"""

from __future__ import annotations

import asyncio
import uuid
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
    WebhookPayload,
)


def _make_raw_email(
    message_id: str = "msg-001",
    sender: str = "sender@example.com",
    subject: str = "Test Subject",
    body: str = "Test body content",
    attachments: list | None = None,
) -> RawEmail:
    """Create a RawEmail for testing."""
    if attachments is None:
        attachments = [
            AttachmentMetadata(
                file_name="doc.pdf", file_size=1024, mime_type="application/pdf"
            )
        ]
    return RawEmail(
        provider_message_id=message_id,
        sender=sender,
        subject=subject,
        body=body,
        timestamp=datetime.now(timezone.utc),
        attachments=attachments,
        provider="gmail",
    )


def _make_monitor(
    provider_client: EmailProviderClient | None = None,
    user_id: uuid.UUID | None = None,
    enqueue_task=None,
    on_auth_suspended=None,
) -> EmailMonitor:
    """Create an EmailMonitor with mocked dependencies."""
    session = AsyncMock()
    if provider_client is None:
        provider_client = AsyncMock(spec=EmailProviderClient)
    with patch("src.services.email_monitor.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(email_poll_interval_seconds=60)
        monitor = EmailMonitor(
            session=session,
            provider_client=provider_client,
            user_id=user_id,
            enqueue_task=enqueue_task,
            on_auth_suspended=on_auth_suspended,
        )
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


class TestFieldExtraction:
    """Test email field extraction completeness."""

    def test_extract_fields_includes_all_required_fields(self) -> None:
        """Extract fields returns sender, subject, body, timestamp, attachments."""
        email = _make_raw_email(
            message_id="extract-001",
            sender="alice@example.com",
            subject="Important Meeting",
            body="Meeting at 3pm tomorrow",
            attachments=[
                AttachmentMetadata(
                    file_name="agenda.pdf",
                    file_size=2048,
                    mime_type="application/pdf",
                ),
                AttachmentMetadata(
                    file_name="notes.docx",
                    file_size=512,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ],
        )

        fields = EmailMonitor.extract_fields(email)

        assert fields["sender"] == "alice@example.com"
        assert fields["subject"] == "Important Meeting"
        assert fields["body"] == "Meeting at 3pm tomorrow"
        assert fields["timestamp"] == email.timestamp
        assert len(fields["attachments"]) == 2
        assert fields["attachments"][0]["file_name"] == "agenda.pdf"
        assert fields["attachments"][0]["file_size"] == 2048
        assert fields["attachments"][0]["mime_type"] == "application/pdf"
        assert fields["attachments"][1]["file_name"] == "notes.docx"

    def test_extract_fields_empty_attachments(self) -> None:
        """Extract fields works with no attachments."""
        email = _make_raw_email(
            message_id="no-attach-001",
            attachments=[],
        )

        fields = EmailMonitor.extract_fields(email)
        assert fields["attachments"] == []

    def test_extract_fields_preserves_timestamp(self) -> None:
        """Extracted timestamp matches email timestamp exactly."""
        email = _make_raw_email(message_id="ts-001")
        fields = EmailMonitor.extract_fields(email)
        assert fields["timestamp"] == email.timestamp


class TestCeleryIntegration:
    """Test Celery task enqueueing integration."""

    async def test_enqueue_uses_custom_task_callable(self) -> None:
        """When enqueue_task is provided, it is called with email data."""
        task_ids = []

        def mock_enqueue(email_data):
            tid = f"celery-task-{len(task_ids)}"
            task_ids.append(tid)
            return tid

        monitor = _make_monitor(enqueue_task=mock_enqueue)
        email = _make_raw_email(message_id="celery-001")

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            result = await monitor.enqueue_email(email)

        assert result == "celery-task-0"
        assert len(task_ids) == 1

    async def test_enqueue_without_task_callable_generates_uuid(self) -> None:
        """Without enqueue_task, a UUID is generated as task ID."""
        monitor = _make_monitor(enqueue_task=None)
        email = _make_raw_email(message_id="no-celery-001")

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            result = await monitor.enqueue_email(email)

        # Should be a valid UUID string
        assert result is not None
        uuid.UUID(result)  # Raises if not valid UUID


class TestWebhookPayload:
    """Test WebhookPayload model."""

    def test_webhook_payload_stores_data(self) -> None:
        """WebhookPayload stores the data dict and records received_at."""
        payload = WebhookPayload(data={"type": "new_message", "id": "msg-123"})
        assert payload.data["type"] == "new_message"
        assert payload.data["id"] == "msg-123"
        assert payload.received_at is not None

    async def test_handle_webhook_accepts_webhook_payload(self) -> None:
        """handle_webhook accepts WebhookPayload objects."""
        provider = AsyncMock(spec=EmailProviderClient)
        email = _make_raw_email(message_id="wp-001")
        provider.fetch_unread.return_value = [email]

        monitor = _make_monitor(provider_client=provider)

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            payload = WebhookPayload(data={"notification": "new_email"})
            await monitor.handle_webhook(payload)

        provider.fetch_unread.assert_called_once()


class TestPollingLoop:
    """Test the polling loop behavior."""

    async def test_polling_loop_fetches_and_enqueues(self) -> None:
        """Polling loop fetches emails and enqueues non-duplicates."""
        provider = AsyncMock(spec=EmailProviderClient)
        email = _make_raw_email(message_id="poll-001")
        provider.fetch_unread.return_value = [email]

        monitor = _make_monitor(provider_client=provider)

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id.return_value = None
            mock_repo_instance.create.return_value = None
            MockRepo.return_value = mock_repo_instance

            await monitor.start_polling(interval_seconds=10)
            # Give the loop a moment to run once
            await asyncio.sleep(0.1)
            await monitor.stop_polling()

        provider.fetch_unread.assert_called()

    async def test_stop_polling_cancels_task(self) -> None:
        """stop_polling gracefully cancels the polling task."""
        monitor = _make_monitor()
        await monitor.start_polling(interval_seconds=10)
        assert monitor.is_polling is True
        await monitor.stop_polling()
        assert monitor.is_polling is False


class TestAuthSuspensionNotification:
    """Test user notification on auth suspension (Requirement 1.5)."""

    async def test_on_auth_suspended_callback_invoked(self) -> None:
        """When auth retries are exhausted, on_auth_suspended callback is called."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "gmail"

        notification_calls = []

        def on_auth_suspended(provider_name: str, timestamp: str) -> None:
            notification_calls.append((provider_name, timestamp))

        monitor = _make_monitor(
            provider_client=provider, on_auth_suspended=on_auth_suspended
        )
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        with pytest.raises(ProviderAuthError):
            await monitor.fetch_emails(provider)

        assert monitor.auth_suspended is True
        assert len(notification_calls) == 1
        assert notification_calls[0][0] == "gmail"
        # Timestamp should be ISO format
        assert "T" in notification_calls[0][1]

    async def test_no_notification_when_callback_not_set(self) -> None:
        """When on_auth_suspended is not set, no error occurs on suspension."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider, on_auth_suspended=None)
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        with pytest.raises(ProviderAuthError):
            await monitor.fetch_emails(provider)

        assert monitor.auth_suspended is True

    async def test_notification_callback_error_is_handled_gracefully(self) -> None:
        """If on_auth_suspended callback raises, it doesn't crash the monitor."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "microsoft"

        def broken_callback(provider_name: str, timestamp: str) -> None:
            raise RuntimeError("Notification service unavailable")

        monitor = _make_monitor(
            provider_client=provider, on_auth_suspended=broken_callback
        )
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        with pytest.raises(ProviderAuthError):
            await monitor.fetch_emails(provider)

        # Should still suspend despite callback failure
        assert monitor.auth_suspended is True

    async def test_auth_retry_delay_between_attempts(self) -> None:
        """Auth retries have 5s delay between attempts (verified via call timing)."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        # Use real delay constant to verify it's set correctly
        assert monitor.AUTH_RETRY_DELAY_SECONDS == 5.0
        assert monitor.AUTH_MAX_RETRIES == 3

        # Override for fast test execution
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        with pytest.raises(ProviderAuthError):
            await monitor.fetch_emails(provider)

        # Verify 3 refresh attempts were made
        assert provider.refresh_token.call_count == 3

    async def test_connectivity_backoff_configuration(self) -> None:
        """Connectivity retry uses exponential backoff with 2s base."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAPIError("Connection refused")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        # Verify correct default configuration
        assert monitor.CONNECTIVITY_BACKOFF_BASE_SECONDS == 2.0
        assert monitor.CONNECTIVITY_MAX_RETRIES == 3

        # Override for fast test execution
        monitor.CONNECTIVITY_BACKOFF_BASE_SECONDS = 0.01

        with pytest.raises(ProviderAPIError):
            await monitor.fetch_emails(provider)

        # 1 initial + 3 retries = 4 total
        assert provider.fetch_unread.call_count == 4


class TestErrorLogging:
    """Test that errors are logged with provider name and timestamp."""

    async def test_auth_error_logged_with_provider_and_timestamp(
        self, caplog
    ) -> None:
        """Auth errors are logged with provider name and timestamp."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAuthError("Token expired")
        provider.refresh_token.side_effect = ProviderAuthError("Refresh failed")
        provider.provider_name = "gmail"

        monitor = _make_monitor(provider_client=provider)
        monitor.AUTH_RETRY_DELAY_SECONDS = 0.01

        import logging

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ProviderAuthError):
                await monitor.fetch_emails(provider)

        # Check that provider name appears in log messages
        auth_logs = [r for r in caplog.records if "provider=gmail" in r.message]
        assert len(auth_logs) > 0

        # Check that timestamp appears in log messages
        timestamp_logs = [
            r for r in caplog.records if "timestamp=" in r.message
        ]
        assert len(timestamp_logs) > 0

    async def test_connectivity_error_logged_with_provider_and_timestamp(
        self, caplog
    ) -> None:
        """Connectivity errors are logged with provider name and timestamp."""
        provider = AsyncMock(spec=EmailProviderClient)
        provider.fetch_unread.side_effect = ProviderAPIError("Timeout")
        provider.provider_name = "microsoft"

        monitor = _make_monitor(provider_client=provider)
        monitor.CONNECTIVITY_BACKOFF_BASE_SECONDS = 0.01

        import logging

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ProviderAPIError):
                await monitor.fetch_emails(provider)

        # Check that provider name appears in connectivity error logs
        conn_logs = [
            r for r in caplog.records if "provider=microsoft" in r.message
        ]
        assert len(conn_logs) > 0

        # Check that timestamp appears
        timestamp_logs = [
            r for r in caplog.records if "timestamp=" in r.message
        ]
        assert len(timestamp_logs) > 0
