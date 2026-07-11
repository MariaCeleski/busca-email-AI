"""Email monitoring service with polling and webhook support.

Provides:
- Periodic polling of email providers for new unread messages
- Webhook handling for push-based notifications
- Deduplication via provider_message_id in PostgreSQL
- Auth token refresh with retry logic (3 retries, 5s delay)
- Connectivity failure handling with exponential backoff (2s base, 3 retries)
- Suspension of polling after auth retry exhaustion with user notification
- Celery task enqueueing for background processing

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.email import RawEmail
from src.providers.base import EmailProviderClient

logger = logging.getLogger(__name__)


class ProviderAuthError(Exception):
    """Raised when authentication with the email provider fails."""

    pass


class ProviderAPIError(Exception):
    """Raised when the email provider API returns an error."""

    pass


class WebhookPayload:
    """Represents a webhook notification payload from an email provider."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.received_at: datetime = datetime.now(timezone.utc)


class EmailMonitor:
    """Monitors email providers for new messages via polling or webhooks.

    Handles:
    - Configurable polling interval (minimum 10s, default 60s)
    - Deduplication of already-processed emails via provider_message_id
    - Auth token refresh retries (up to 3 attempts, 5s delay)
    - Connectivity retry with exponential backoff (base 2s, up to 3 retries)
    - Webhook handling within 5s timeout
    - Celery task enqueueing for background email processing
    """

    # Auth retry configuration
    AUTH_MAX_RETRIES: int = 3
    AUTH_RETRY_DELAY_SECONDS: float = 5.0

    # Connectivity retry configuration
    CONNECTIVITY_MAX_RETRIES: int = 3
    CONNECTIVITY_BACKOFF_BASE_SECONDS: float = 2.0

    # Webhook processing timeout
    WEBHOOK_TIMEOUT_SECONDS: float = 5.0

    def __init__(
        self,
        session: AsyncSession,
        provider_client: EmailProviderClient,
        user_id: Optional[uuid.UUID] = None,
        enqueue_task: Optional[Callable[[Dict[str, Any]], str]] = None,
        on_auth_suspended: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Initialize EmailMonitor.

        Args:
            session: Async SQLAlchemy session for database operations.
            provider_client: Email provider client for fetching emails.
            user_id: UUID of the user whose emails are being monitored.
            enqueue_task: Optional callable to enqueue emails for processing
                (e.g., Celery task.delay). If not provided, uses a default
                that generates a UUID task ID without background processing.
            on_auth_suspended: Optional callback invoked when auth retries are
                exhausted and polling is suspended. Called with (provider_name,
                timestamp) to notify the user that re-authorization is required.
                This can be connected to WebSocket notifications, email alerts,
                or any other user notification mechanism.
        """
        self._session = session
        self._provider_client = provider_client
        self._user_id = user_id
        self._enqueue_task = enqueue_task
        self._on_auth_suspended = on_auth_suspended
        self._polling_task: Optional[asyncio.Task] = None
        self._is_polling: bool = False
        self._auth_suspended: bool = False
        self._processed_message_ids: set = set()
        settings = get_settings()
        self._poll_interval: int = max(settings.email_poll_interval_seconds, 10)

    @property
    def is_polling(self) -> bool:
        """Whether the polling loop is currently active."""
        return self._is_polling

    @property
    def auth_suspended(self) -> bool:
        """Whether polling is suspended due to persistent auth failure."""
        return self._auth_suspended

    async def start_polling(self, interval_seconds: int = 60) -> None:
        """Start the periodic polling loop.

        Args:
            interval_seconds: Polling interval in seconds. Minimum is 10s.

        Raises:
            ValueError: If interval_seconds is less than 10.
        """
        if interval_seconds < 10:
            raise ValueError(
                f"Polling interval must be at least 10 seconds, got {interval_seconds}"
            )

        self._poll_interval = interval_seconds
        self._is_polling = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info(
            "Email polling started with interval=%ds", self._poll_interval
        )

    async def stop_polling(self) -> None:
        """Stop the polling loop gracefully."""
        self._is_polling = False
        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
        logger.info("Email polling stopped")

    async def handle_webhook(self, payload: dict | WebhookPayload) -> None:
        """Process incoming webhook notification within 5s timeout.

        Fetches the referenced email from the provider and enqueues it
        for processing. Must complete within 5 seconds of notification receipt.

        Args:
            payload: Webhook payload from the email provider (dict or WebhookPayload).

        Raises:
            asyncio.TimeoutError: If processing exceeds 5 seconds.
        """
        await asyncio.wait_for(
            self._process_webhook(payload),
            timeout=self.WEBHOOK_TIMEOUT_SECONDS,
        )

    async def _process_webhook(self, payload: dict | WebhookPayload) -> None:
        """Internal webhook processing logic.

        Fetches unread emails from the provider and enqueues each
        non-duplicate for processing.
        """
        emails = await self.fetch_emails(self._provider_client)
        for email in emails:
            await self.enqueue_email(email)

    async def fetch_emails(self, provider: EmailProviderClient) -> List[RawEmail]:
        """Fetch unread emails from the provider with connectivity retry.

        Args:
            provider: The email provider client to fetch from.

        Returns:
            List of raw emails fetched from the provider.

        Raises:
            ProviderAuthError: If auth fails after all retry attempts.
            ProviderAPIError: If connectivity fails after all retry attempts.
        """
        return await self._fetch_with_retries(provider)

    async def enqueue_email(self, email: RawEmail) -> Optional[str]:
        """Deduplicate and enqueue email for processing.

        Checks deduplication via provider_message_id (in-memory cache + PostgreSQL),
        then persists the email record and dispatches a Celery task for background
        processing through the agent pipeline.

        Args:
            email: The raw email to enqueue.

        Returns:
            Task ID (UUID string) if enqueued, None if duplicate.
        """
        if await self.is_duplicate(email.provider_message_id):
            logger.debug(
                "Duplicate email skipped: message_id=%s", email.provider_message_id
            )
            return None

        # Mark as processed in local cache
        self._processed_message_ids.add(email.provider_message_id)

        # Persist to database for cross-instance deduplication
        await self._persist_processed_email(email)

        # Enqueue for background processing via Celery (or fallback)
        email_data = email.model_dump(mode="json")
        if self._enqueue_task is not None:
            task_id = self._enqueue_task(email_data)
        else:
            task_id = str(uuid.uuid4())

        logger.info(
            "Email enqueued: message_id=%s, task_id=%s, sender=%s, subject=%s",
            email.provider_message_id,
            task_id,
            email.sender,
            email.subject,
        )
        return task_id

    async def is_duplicate(self, message_id: str) -> bool:
        """Check if an email was already processed.

        Uses in-memory set for fast lookup, backed by PostgreSQL
        via ProcessedEmailRepository.get_by_provider_message_id().

        Args:
            message_id: The provider message ID to check.

        Returns:
            True if already processed, False otherwise.
        """
        # Fast in-memory check
        if message_id in self._processed_message_ids:
            return True

        # Database check via repository
        from src.models.repositories import ProcessedEmailRepository

        repo = ProcessedEmailRepository(self._session)
        existing = await repo.get_by_provider_message_id(message_id)
        if existing is not None:
            # Cache it locally for future fast lookups
            self._processed_message_ids.add(message_id)
            return True

        return False

    async def _polling_loop(self) -> None:
        """Internal polling loop that runs until stopped."""
        while self._is_polling:
            if self._auth_suspended:
                logger.warning("Polling suspended due to auth failure")
                break

            try:
                emails = await self.fetch_emails(self._provider_client)
                for email in emails:
                    await self.enqueue_email(email)
            except ProviderAuthError:
                # Auth retries exhausted in _fetch_with_retries
                logger.error("Auth failure during polling, suspending")
                self._auth_suspended = True
                break
            except ProviderAPIError as e:
                logger.error(
                    "Connectivity failure during polling: %s provider=%s timestamp=%s",
                    str(e),
                    getattr(self._provider_client, "provider_name", "unknown"),
                    datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                logger.error(
                    "Unexpected error during polling: %s provider=%s timestamp=%s",
                    str(e),
                    getattr(self._provider_client, "provider_name", "unknown"),
                    datetime.now(timezone.utc).isoformat(),
                )

            await asyncio.sleep(self._poll_interval)

    async def _fetch_with_retries(
        self, provider: EmailProviderClient
    ) -> List[RawEmail]:
        """Fetch emails with auth retry and connectivity retry logic.

        Auth errors: retry refresh_token up to 3 times with 5s delay.
        Connectivity errors: retry fetch 3x with exponential backoff (2s, 4s, 8s).

        Args:
            provider: The email provider client.

        Returns:
            List of fetched raw emails.

        Raises:
            ProviderAuthError: If auth refresh retries are exhausted.
            ProviderAPIError: If connectivity retries are exhausted.
        """
        provider_name = getattr(provider, "provider_name", "unknown")
        timestamp = datetime.now(timezone.utc).isoformat()

        # Connectivity retry with exponential backoff
        last_connectivity_error: Optional[Exception] = None
        for attempt in range(self.CONNECTIVITY_MAX_RETRIES + 1):
            try:
                return await provider.fetch_unread()
            except ProviderAuthError:
                # Handle auth errors with dedicated retry logic
                await self._handle_auth_error(provider, provider_name, timestamp)
                # After successful token refresh, retry the fetch
                try:
                    return await provider.fetch_unread()
                except ProviderAuthError:
                    raise
            except (ProviderAPIError, ConnectionError, OSError) as e:
                last_connectivity_error = e
                if attempt < self.CONNECTIVITY_MAX_RETRIES:
                    delay = self.CONNECTIVITY_BACKOFF_BASE_SECONDS * (
                        2**attempt
                    )
                    logger.warning(
                        "Connectivity failure (attempt %d/%d): %s provider=%s timestamp=%s. Retrying in %.1fs",
                        attempt + 1,
                        self.CONNECTIVITY_MAX_RETRIES + 1,
                        str(e),
                        provider_name,
                        timestamp,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Connectivity retries exhausted: %s provider=%s timestamp=%s",
                        str(e),
                        provider_name,
                        timestamp,
                    )

        raise ProviderAPIError(
            f"Failed to fetch emails after {self.CONNECTIVITY_MAX_RETRIES + 1} attempts: "
            f"{last_connectivity_error}"
        )

    async def _handle_auth_error(
        self, provider: EmailProviderClient, provider_name: str, timestamp: str
    ) -> None:
        """Handle auth errors by retrying token refresh up to 3 times.

        Args:
            provider: The email provider client.
            provider_name: Name of the provider for logging.
            timestamp: Timestamp for logging.

        Raises:
            ProviderAuthError: If all refresh retries are exhausted.
        """
        for retry in range(self.AUTH_MAX_RETRIES):
            try:
                logger.info(
                    "Attempting token refresh (attempt %d/%d) provider=%s timestamp=%s",
                    retry + 1,
                    self.AUTH_MAX_RETRIES,
                    provider_name,
                    timestamp,
                )
                await provider.refresh_token()
                logger.info(
                    "Token refresh successful provider=%s timestamp=%s",
                    provider_name,
                    timestamp,
                )
                return
            except (ProviderAuthError, Exception) as e:
                logger.warning(
                    "Token refresh failed (attempt %d/%d): %s provider=%s timestamp=%s",
                    retry + 1,
                    self.AUTH_MAX_RETRIES,
                    str(e),
                    provider_name,
                    timestamp,
                )
                if retry < self.AUTH_MAX_RETRIES - 1:
                    await asyncio.sleep(self.AUTH_RETRY_DELAY_SECONDS)

        # All retries exhausted
        self._auth_suspended = True
        logger.error(
            "Auth refresh retries exhausted, suspending polling. provider=%s timestamp=%s",
            provider_name,
            timestamp,
        )
        # Notify user that re-authorization is required (Requirement 1.5)
        self._notify_auth_suspended(provider_name, timestamp)
        raise ProviderAuthError(
            f"Token refresh failed after {self.AUTH_MAX_RETRIES} attempts"
        )

    def _notify_auth_suspended(self, provider_name: str, timestamp: str) -> None:
        """Notify the user that re-authorization is required.

        Invokes the on_auth_suspended callback if one was provided during
        initialization. This allows the system to notify the user via
        WebSocket, email, or other mechanisms that polling has been
        suspended and they must re-authenticate.

        Args:
            provider_name: Name of the provider that failed authentication.
            timestamp: ISO timestamp of when the failure occurred.
        """
        if self._on_auth_suspended is not None:
            try:
                self._on_auth_suspended(provider_name, timestamp)
            except Exception as e:
                logger.warning(
                    "Failed to send auth suspension notification: %s", str(e)
                )
        logger.info(
            "User notification: Re-authorization required for provider=%s. "
            "Polling suspended at timestamp=%s",
            provider_name,
            timestamp,
        )

    async def _persist_processed_email(self, email: RawEmail) -> None:
        """Persist processed email record to the database.

        Stores the email in the processed_emails table for deduplication
        and later retrieval by the agent pipeline.

        Args:
            email: The raw email that was processed.
        """
        try:
            from src.models.repositories import ProcessedEmailRepository

            repo = ProcessedEmailRepository(self._session)
            attachments_data = [
                {
                    "file_name": att.file_name,
                    "file_size": att.file_size,
                    "mime_type": att.mime_type,
                }
                for att in email.attachments
            ]
            kwargs = {
                "provider_message_id": email.provider_message_id,
                "sender": email.sender,
                "subject": email.subject,
                "body": email.body,
                "timestamp": email.timestamp,
                "attachments": attachments_data,
                "thread_id": email.thread_id,
                "provider": email.provider,
                "processing_timestamp": datetime.now(timezone.utc),
                "workflow_stage": "queued",
            }
            if self._user_id is not None:
                kwargs["user_id"] = self._user_id
            await repo.create(**kwargs)
            await self._session.commit()
        except Exception as e:
            logger.warning(
                "Failed to persist processed email record: %s", str(e)
            )

    @staticmethod
    def extract_fields(email: RawEmail) -> dict:
        """Extract and validate fields from a raw email.

        Args:
            email: The raw email to extract fields from.

        Returns:
            Dict with sender, subject, body, timestamp, and attachments.
        """
        return {
            "sender": email.sender,
            "subject": email.subject,
            "body": email.body,
            "timestamp": email.timestamp,
            "attachments": [
                {
                    "file_name": att.file_name,
                    "file_size": att.file_size,
                    "mime_type": att.mime_type,
                }
                for att in email.attachments
            ],
        }
