"""Property-based tests for EmailMonitor service.

Validates:
- Requirements 1.1, 1.2: Email field extraction completeness
- Requirements 1.3, 1.7: Email deduplication idempotence
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis.strategies import (
    integers,
    lists,
    text,
)

from src.models.email import AttachmentMetadata, RawEmail
from src.services.email_monitor import EmailMonitor


# --- Strategies ---

def _raw_email_strategy():
    """Strategy for generating valid RawEmail instances."""
    from hypothesis.strategies import builds, datetimes

    attachment_strategy = builds(
        AttachmentMetadata,
        file_name=text(
            min_size=1,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-",
        ),
        file_size=integers(min_value=1, max_value=100_000_000),
        mime_type=text(
            min_size=3,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789/-",
        ),
    )

    return builds(
        RawEmail,
        provider_message_id=text(
            min_size=1,
            max_size=100,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
        ),
        sender=text(
            min_size=3,
            max_size=100,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789@._-",
        ),
        subject=text(min_size=1, max_size=200),
        body=text(min_size=1, max_size=1000),
        timestamp=datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        ),
        attachments=lists(attachment_strategy, min_size=0, max_size=5),
        provider=text(
            min_size=1,
            max_size=20,
            alphabet="abcdefghijklmnopqrstuvwxyz",
        ),
    )


@pytest.mark.property
class TestEmailFieldExtractionCompleteness:
    """Property 1: Email Field Extraction Completeness.

    **Validates: Requirements 1.1, 1.2**

    For any valid raw email with valid structure, verify extraction produces
    non-null sender, subject, body, timestamp, and correct attachment metadata.
    """

    @given(email=_raw_email_strategy())
    @settings(max_examples=100)
    def test_extraction_produces_all_required_fields(self, email: RawEmail) -> None:
        """Extracting fields from any valid RawEmail yields non-null values
        for sender, subject, body, timestamp, and correct attachment metadata."""
        fields = EmailMonitor.extract_fields(email)

        # All required fields must be non-null
        assert fields["sender"] is not None
        assert fields["subject"] is not None
        assert fields["body"] is not None
        assert fields["timestamp"] is not None
        assert fields["attachments"] is not None

        # Fields must match original email
        assert fields["sender"] == email.sender
        assert fields["subject"] == email.subject
        assert fields["body"] == email.body
        assert fields["timestamp"] == email.timestamp

        # Attachment count must match
        assert len(fields["attachments"]) == len(email.attachments)

        # Each attachment must preserve metadata
        for i, att in enumerate(email.attachments):
            extracted_att = fields["attachments"][i]
            assert extracted_att["file_name"] == att.file_name
            assert extracted_att["file_size"] == att.file_size
            assert extracted_att["mime_type"] == att.mime_type


@pytest.mark.property
class TestEmailDeduplicationIdempotence:
    """Property 2: Email Deduplication Idempotence.

    **Validates: Requirements 1.3, 1.7**

    For any message_id already in the state store, attempting to enqueue
    again is rejected and state doesn't change.
    """

    @given(
        message_id=text(
            min_size=1,
            max_size=100,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
        ),
    )
    @settings(max_examples=100)
    def test_duplicate_enqueue_is_rejected_and_state_unchanged(
        self, message_id: str
    ) -> None:
        """Enqueuing an email with a message_id already in the store returns
        None and the internal state set does not grow."""
        import asyncio

        async def _run():
            with patch("src.services.email_monitor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(email_poll_interval_seconds=60)
                session = AsyncMock()
                provider = AsyncMock()
                monitor = EmailMonitor(session=session, provider_client=provider)

            # Pre-populate the message_id in the internal state
            monitor._processed_message_ids.add(message_id)
            state_size_before = len(monitor._processed_message_ids)

            email = RawEmail(
                provider_message_id=message_id,
                sender="test@example.com",
                subject="Test",
                body="Body",
                timestamp=datetime.now(timezone.utc),
                attachments=[],
                provider="gmail",
            )

            # Attempt to enqueue the duplicate
            result = await monitor.enqueue_email(email)

            # Must be rejected
            assert result is None

            # State must not change
            state_size_after = len(monitor._processed_message_ids)
            assert state_size_after == state_size_before

        asyncio.run(_run())
