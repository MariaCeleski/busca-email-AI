"""Unit tests for the AccessLogger service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.security.access_logger import AccessLogger, LOG_RETENTION_DAYS


class TestAccessLogger:
    """Tests for AccessLogger access event recording."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_log_entry(self) -> MagicMock:
        """Create a mock AccessLog entry returned from the repository."""
        entry = MagicMock()
        entry.id = 1
        entry.requester_id = "user-123"
        entry.endpoint = "/api/v1/emails"
        entry.method = "GET"
        entry.response_status = 200
        return entry

    @pytest.mark.asyncio
    async def test_log_access_basic(self, mock_session: AsyncMock, mock_log_entry: MagicMock) -> None:
        """Should create a log entry with correct fields."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()
            logger._repository.create = AsyncMock(return_value=mock_log_entry)

            result = await logger.log_access(
                requester_id="user-123",
                endpoint="/api/v1/emails",
                method="GET",
                response_status=200,
            )

            logger._repository.create.assert_called_once()
            call_kwargs = logger._repository.create.call_args[1]
            assert call_kwargs["requester_id"] == "user-123"
            assert call_kwargs["endpoint"] == "/api/v1/emails"
            assert call_kwargs["method"] == "GET"
            assert call_kwargs["response_status"] == 200
            assert call_kwargs["timestamp"] is not None
            assert result == mock_log_entry

    @pytest.mark.asyncio
    async def test_log_access_method_uppercased(self, mock_session: AsyncMock, mock_log_entry: MagicMock) -> None:
        """HTTP method should be uppercased in the log."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()
            logger._repository.create = AsyncMock(return_value=mock_log_entry)

            await logger.log_access(
                requester_id="user-456",
                endpoint="/api/v1/emails/1",
                method="post",
                response_status=201,
            )

            call_kwargs = logger._repository.create.call_args[1]
            assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_log_access_no_email_body_in_fields(self, mock_session: AsyncMock, mock_log_entry: MagicMock) -> None:
        """Log entries must not contain any email body content."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()
            logger._repository.create = AsyncMock(return_value=mock_log_entry)

            # Even if endpoint or requester has suspicious content, logs should only
            # capture the defined fields.
            await logger.log_access(
                requester_id="user-789",
                endpoint="/api/v1/emails/fetch",
                method="POST",
                response_status=200,
            )

            call_kwargs = logger._repository.create.call_args[1]
            # Only allowed keys in the log entry
            allowed_keys = {"requester_id", "endpoint", "method", "timestamp", "response_status"}
            assert set(call_kwargs.keys()) == allowed_keys

    @pytest.mark.asyncio
    async def test_log_access_empty_requester_id_raises(self, mock_session: AsyncMock) -> None:
        """Empty requester_id should raise ValueError."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()

            with pytest.raises(ValueError, match="requester_id must not be empty"):
                await logger.log_access(
                    requester_id="",
                    endpoint="/api/v1/emails",
                    method="GET",
                )

    @pytest.mark.asyncio
    async def test_log_access_empty_endpoint_raises(self, mock_session: AsyncMock) -> None:
        """Empty endpoint should raise ValueError."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()

            with pytest.raises(ValueError, match="endpoint must not be empty"):
                await logger.log_access(
                    requester_id="user-1",
                    endpoint="",
                    method="GET",
                )

    @pytest.mark.asyncio
    async def test_log_access_empty_method_raises(self, mock_session: AsyncMock) -> None:
        """Empty method should raise ValueError."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()

            with pytest.raises(ValueError, match="method must not be empty"):
                await logger.log_access(
                    requester_id="user-1",
                    endpoint="/api/v1/emails",
                    method="",
                )

    @pytest.mark.asyncio
    async def test_log_access_whitespace_only_requester_raises(self, mock_session: AsyncMock) -> None:
        """Whitespace-only requester_id should raise ValueError."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()

            with pytest.raises(ValueError, match="requester_id must not be empty"):
                await logger.log_access(
                    requester_id="   ",
                    endpoint="/api/v1/emails",
                    method="GET",
                )

    @pytest.mark.asyncio
    async def test_log_access_truncates_long_endpoint(self, mock_session: AsyncMock, mock_log_entry: MagicMock) -> None:
        """Endpoint longer than 255 chars should be truncated."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()
            logger._repository.create = AsyncMock(return_value=mock_log_entry)

            long_endpoint = "/api/v1/" + "x" * 300
            await logger.log_access(
                requester_id="user-1",
                endpoint=long_endpoint,
                method="GET",
                response_status=200,
            )

            call_kwargs = logger._repository.create.call_args[1]
            assert len(call_kwargs["endpoint"]) <= 255

    @pytest.mark.asyncio
    async def test_log_access_optional_response_status(self, mock_session: AsyncMock, mock_log_entry: MagicMock) -> None:
        """response_status should be optional (None when not provided)."""
        with patch.object(
            AccessLogger, "__init__", lambda self, session: None
        ):
            logger = AccessLogger.__new__(AccessLogger)
            logger._session = mock_session
            logger._repository = AsyncMock()
            logger._repository.create = AsyncMock(return_value=mock_log_entry)

            await logger.log_access(
                requester_id="user-1",
                endpoint="/api/v1/emails",
                method="GET",
            )

            call_kwargs = logger._repository.create.call_args[1]
            assert call_kwargs["response_status"] is None

    def test_retention_days_minimum_90(self) -> None:
        """Log retention should be at least 90 days."""
        assert LOG_RETENTION_DAYS >= 90

    def test_get_retention_days(self) -> None:
        """get_retention_days should return the configured value."""
        assert AccessLogger.get_retention_days() >= 90
