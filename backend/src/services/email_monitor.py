"""Email monitoring service with polling and webhook support.

Provides:
- Periodic polling of email providers for new unread messages
- Webhook handling for push-based notifications
- Deduplication via provider_message_id in PostgreSQL
- Auth token refresh with retry logic
- Connectivity failure handling with exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

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


class EmailMonitor:
    """Monitors email providers for new messages via polling or webhooks.

    Handles:
    - Configurable polling interval (minimum 10s)
    - Deduplication of already-processed emails
    - Auth token refresh retries (up to 3 attempts, 5s delay)
    - Connectivity retry with exponential backoff (base 2s, up to 3 retries)
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
    ) -> None:
        """Initialize EmailMonitor.

        Args:
            session: Async SQLAlchemy session for database operations.
            provider_client: Email provider client for fetching emails.
        """
        self._session = session
        self._provider_client = provider_client
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

    async def handle_webhook(self, payload: dict) -> None:
        """Process incoming webhook notification within 5s timeout.

        Args:
            payload: Webhook payload from the email provider.

        Raises:
            asyncio.TimeoutError: If processing exceeds 5 seconds.
        """
        await asyncio.wait_for(
            self._process_webhook(payload),
            timeout=self.WEBHOOK_TIMEOUT_SECONDS,
        )

    async def _process_webhook(self, payload: dict) -> None:
        """Internal webhook processing logic."""
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

        # Mark as processed
        self._processed_message_ids.add(email.provider_message_id)

        # Also persist to database for cross-instance deduplication
        await self._persist_processed_email(email)

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
        raise ProviderAuthError(
            f"Token refresh failed after {self.AUTH_MAX_RETRIES} attempts"
        )

    async def _persist_processed_email(self, email: RawEmail) -> None:
        """Persist processed email record to the database.

        Args:
            email: The raw email that was processed.
        """
        try:
            from src.models.repositories import ProcessedEmailRepository

            repo = ProcessedEmailRepository(self._session)
            await repo.create(
                provider_message_id=email.provider_message_id,
                sender=email.sender,
                subject=email.subject,
                body_snippet=email.body[:500] if email.body else "",
                provider=email.provider,
                received_at=email.timestamp,
                processing_timestamp=datetime.now(timezone.utc),
            )
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
