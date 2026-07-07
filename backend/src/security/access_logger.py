"""Access logging service for API audit trail.

Records API access events (requester, endpoint, method, timestamp, status)
without capturing any email body content. Logs are stored in the access_logs
PostgreSQL table with a minimum retention period of 90 days.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import AccessLog
from src.models.repositories import AccessLogRepository

logger = logging.getLogger(__name__)

# Minimum retention period in days for access logs
LOG_RETENTION_DAYS = 90


class AccessLogger:
    """Logs API access events without email body content.

    All logged entries include requester_id, endpoint, HTTP method,
    timestamp, and response status code. Email body content is never
    included in log entries to comply with data privacy requirements.

    Logs are persisted to the access_logs table in PostgreSQL and
    retained for a minimum of 90 days.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            session: An async SQLAlchemy session for persisting log entries.
        """
        self._repository = AccessLogRepository(session)
        self._session = session

    async def log_access(
        self,
        requester_id: str,
        endpoint: str,
        method: str,
        response_status: Optional[int] = None,
    ) -> AccessLog:
        """Record an API access event.

        Captures only request metadata — never email body content.

        Args:
            requester_id: Identifier of the requester (user ID or API key hash).
            endpoint: The API endpoint path (e.g., "/api/v1/emails").
            method: The HTTP method (GET, POST, PUT, DELETE, etc.).
            response_status: Optional HTTP response status code.

        Returns:
            The created AccessLog record.

        Raises:
            ValueError: If requester_id, endpoint, or method is empty.
        """
        if not requester_id or not requester_id.strip():
            raise ValueError("requester_id must not be empty.")
        if not endpoint or not endpoint.strip():
            raise ValueError("endpoint must not be empty.")
        if not method or not method.strip():
            raise ValueError("method must not be empty.")

        # Sanitize: ensure no body content sneaks in via the fields
        sanitized_endpoint = self._sanitize_field(endpoint, max_length=255)
        sanitized_method = method.strip().upper()[:10]
        sanitized_requester = self._sanitize_field(requester_id, max_length=255)

        log_entry = await self._repository.create(
            requester_id=sanitized_requester,
            endpoint=sanitized_endpoint,
            method=sanitized_method,
            timestamp=datetime.now(timezone.utc),
            response_status=response_status,
        )

        logger.info(
            "Access logged: %s %s %s -> %s",
            sanitized_requester,
            sanitized_method,
            sanitized_endpoint,
            response_status,
        )

        return log_entry

    @staticmethod
    def _sanitize_field(value: str, max_length: int = 255) -> str:
        """Sanitize a log field by stripping whitespace and truncating.

        Args:
            value: Raw field value.
            max_length: Maximum allowed length.

        Returns:
            Sanitized string value.
        """
        return value.strip()[:max_length]

    @staticmethod
    def get_retention_days() -> int:
        """Return the configured log retention period in days.

        Returns:
            Minimum number of days access logs are retained.
        """
        return LOG_RETENTION_DAYS
