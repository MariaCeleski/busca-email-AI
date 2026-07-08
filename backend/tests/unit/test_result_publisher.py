"""Unit tests for the ResultPublisher service.

Tests persistence logic (PostgreSQL storage), embedding storage (ChromaDB),
and WebSocket notification broadcasting.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import DraftStatus, EmailCategory, PriorityLevel, WorkflowStage
from src.models.summary import SummaryResult
from src.services.result_publisher import ResultPublisher


# --- Fixtures ---


@pytest.fixture
def sample_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg_pub_001",
        sender="alice@example.com",
        subject="Meeting tomorrow",
        body="Hi, let's meet tomorrow at 3pm to discuss the project plan.",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def sample_classification() -> ClassificationResult:
    return ClassificationResult(
        category=EmailCategory.PERSONAL,
        priority=PriorityLevel.MEDIUM,
        confidence=0.85,
        requires_response=True,
        requires_summary=False,
    )


@pytest.fixture
def sample_summary() -> SummaryResult:
    return SummaryResult(
        summary="Meeting scheduled for tomorrow at 3pm about project plan.",
        action_items=["Attend meeting at 3pm"],
    )


@pytest.fixture
def sample_draft_reply() -> DraftReply:
    return DraftReply(
        reply_body="Thanks for the heads up! I'll be there at 3pm.",
        suggested_subject="Re: Meeting tomorrow",
        referenced_email_ids=["ref_001"],
        status=DraftStatus.PENDING,
        generated_at=datetime(2024, 1, 15, 10, 5, 0),
    )


@pytest.fixture
def mock_session_factory():
    """Create a mock session factory that returns an async context manager."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    # Mock the begin() context manager
    mock_begin = AsyncMock()
    mock_begin.__aenter__ = AsyncMock(return_value=None)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)

    factory = MagicMock(return_value=mock_session)
    return factory


@pytest.fixture
def mock_vector_store():
    """Create a mock VectorStoreService."""
    vs = AsyncMock()
    vs.store_embedding = AsyncMock(return_value="emb_test_123")
    return vs


@pytest.fixture
def mock_connection_manager():
    """Create a mock WebSocket ConnectionManager."""
    cm = AsyncMock()
    cm.broadcast = AsyncMock()
    return cm


@pytest.fixture
def publisher(mock_session_factory, mock_vector_store, mock_connection_manager):
    """Create a ResultPublisher with mocked dependencies."""
    return ResultPublisher(
        session_factory=mock_session_factory,
        vector_store_service=mock_vector_store,
        connection_manager=mock_connection_manager,
    )


def _build_workflow_result(
    email: RawEmail,
    classification=None,
    summary=None,
    draft_reply=None,
    current_stage=WorkflowStage.COMPLETED.value,
    error=None,
    flagged_for_review=False,
):
    """Helper to build a workflow result dict."""
    return {
        "email": email,
        "classification": classification,
        "summary": summary,
        "draft_reply": draft_reply,
        "current_stage": current_stage,
        "error": error,
        "flagged_for_review": flagged_for_review,
        "retry_counts": {},
    }


# --- Test notification building ---


class TestBuildNotification:
    """Test WebSocket notification payload construction."""

    def test_notification_includes_all_required_fields(
        self, publisher, sample_email, sample_classification
    ):
        """Notification should contain email_id, classification, summary/draft flags, stage."""
        email_id = uuid.uuid4()
        notification = publisher._build_notification(
            email_id=email_id,
            email=sample_email,
            classification=sample_classification,
            summary=None,
            draft_reply=None,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        assert notification["type"] == "email_processing_complete"
        assert notification["email_id"] == str(email_id)
        assert notification["provider_message_id"] == "msg_pub_001"
        assert notification["workflow_stage"] == "completed"
        assert notification["has_summary"] is False
        assert notification["has_draft_reply"] is False
        assert notification["timestamp"] is not None
        assert notification["classification"]["category"] == "Personal"
        assert notification["classification"]["priority"] == "Medium"
        assert notification["classification"]["confidence"] == 0.85

    def test_notification_with_summary_and_draft(
        self, publisher, sample_email, sample_classification, sample_summary, sample_draft_reply
    ):
        """Notification flags reflect presence of summary and draft."""
        email_id = uuid.uuid4()
        notification = publisher._build_notification(
            email_id=email_id,
            email=sample_email,
            classification=sample_classification,
            summary=sample_summary,
            draft_reply=sample_draft_reply,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        assert notification["has_summary"] is True
        assert notification["has_draft_reply"] is True

    def test_notification_without_classification(self, publisher, sample_email):
        """Notification handles None classification gracefully."""
        notification = publisher._build_notification(
            email_id=None,
            email=sample_email,
            classification=None,
            summary=None,
            draft_reply=None,
            current_stage=WorkflowStage.FAILED.value,
        )

        assert notification["classification"] is None
        assert notification["email_id"] is None
        assert notification["workflow_stage"] == "failed"

    def test_notification_for_manual_review(
        self, publisher, sample_email, sample_classification
    ):
        """Notification correctly reports manual_review stage."""
        email_id = uuid.uuid4()
        notification = publisher._build_notification(
            email_id=email_id,
            email=sample_email,
            classification=sample_classification,
            summary=None,
            draft_reply=None,
            current_stage=WorkflowStage.MANUAL_REVIEW.value,
        )

        assert notification["workflow_stage"] == "manual_review"


# --- Test embedding storage ---


class TestStoreEmbedding:
    """Test ChromaDB embedding storage."""

    async def test_stores_embedding_on_successful_classification(
        self, publisher, mock_vector_store, sample_email, sample_classification
    ):
        """Embedding is stored when classification succeeds."""
        email_id = "test-email-123"
        result = await publisher._store_embedding(
            email=sample_email,
            email_id=email_id,
            classification=sample_classification,
        )

        mock_vector_store.store_embedding.assert_called_once()
        call_args = mock_vector_store.store_embedding.call_args

        assert call_args.kwargs["email_id"] == email_id
        assert "Meeting tomorrow" in call_args.kwargs["text"]
        assert call_args.kwargs["metadata"].sender == "alice@example.com"
        assert call_args.kwargs["metadata"].category == EmailCategory.PERSONAL
        assert call_args.kwargs["metadata"].provider_message_id == "msg_pub_001"
        assert result == "emb_test_123"

    async def test_embedding_text_includes_subject_and_body(
        self, publisher, mock_vector_store, sample_email, sample_classification
    ):
        """Embedding text combines subject and body."""
        await publisher._store_embedding(
            email=sample_email,
            email_id="test-123",
            classification=sample_classification,
        )

        call_args = mock_vector_store.store_embedding.call_args
        text = call_args.kwargs["text"]
        assert "Meeting tomorrow" in text
        assert "let's meet tomorrow" in text

    async def test_embedding_failure_returns_none(
        self, publisher, mock_vector_store, sample_email, sample_classification
    ):
        """Returns None on embedding storage failure (non-fatal)."""
        mock_vector_store.store_embedding.side_effect = Exception("ChromaDB error")

        result = await publisher._store_embedding(
            email=sample_email,
            email_id="test-123",
            classification=sample_classification,
        )

        assert result is None


# --- Test WebSocket broadcast ---


class TestBroadcastNotification:
    """Test WebSocket notification broadcasting."""

    async def test_broadcasts_notification_to_manager(
        self, publisher, mock_connection_manager
    ):
        """Notification is sent via connection manager broadcast."""
        notification = {"type": "test", "data": "value"}
        await publisher._broadcast_notification(notification)

        mock_connection_manager.broadcast.assert_called_once_with(notification)

    async def test_broadcast_failure_does_not_raise(
        self, publisher, mock_connection_manager
    ):
        """WebSocket broadcast failure is logged but does not raise."""
        mock_connection_manager.broadcast.side_effect = Exception("WS error")

        # Should not raise
        await publisher._broadcast_notification({"type": "test"})


# --- Test publish (full integration of all steps) ---


class TestPublish:
    """Test the main publish method end-to-end with mocked dependencies."""

    async def test_publish_returns_error_when_no_email(self, publisher):
        """Publish fails gracefully when workflow_result has no email."""
        result = await publisher.publish({"email": None, "classification": None})

        assert result["success"] is False
        assert "No email" in result["error"]

    async def test_publish_broadcasts_notification(
        self,
        publisher,
        mock_connection_manager,
        mock_vector_store,
        sample_email,
        sample_classification,
    ):
        """Publish always broadcasts WebSocket notification."""
        # Mock _store_in_postgres to avoid DB interactions
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        await publisher.publish(workflow_result)

        mock_connection_manager.broadcast.assert_called_once()
        notification = mock_connection_manager.broadcast.call_args[0][0]
        assert notification["type"] == "email_processing_complete"
        assert notification["workflow_stage"] == "completed"

    async def test_publish_stores_embedding_for_classified_emails(
        self,
        publisher,
        mock_vector_store,
        sample_email,
        sample_classification,
    ):
        """Publish calls store_embedding when classification is present and stage is not failed."""
        email_id = uuid.uuid4()
        publisher._store_in_postgres = AsyncMock(return_value=email_id)

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        result = await publisher.publish(workflow_result)

        mock_vector_store.store_embedding.assert_called_once()
        assert result["embedding_id"] == "emb_test_123"

    async def test_publish_skips_embedding_for_failed_stage(
        self,
        publisher,
        mock_vector_store,
        sample_email,
        sample_classification,
    ):
        """Publish does NOT store embedding when stage is failed."""
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            current_stage=WorkflowStage.FAILED.value,
        )

        result = await publisher.publish(workflow_result)

        mock_vector_store.store_embedding.assert_not_called()
        assert result["embedding_id"] is None

    async def test_publish_skips_embedding_when_no_classification(
        self,
        publisher,
        mock_vector_store,
        sample_email,
    ):
        """Publish does NOT store embedding when there is no classification."""
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=None,
            current_stage=WorkflowStage.MANUAL_REVIEW.value,
        )

        result = await publisher.publish(workflow_result)

        mock_vector_store.store_embedding.assert_not_called()
        assert result["embedding_id"] is None

    async def test_publish_notification_includes_classification(
        self,
        publisher,
        mock_connection_manager,
        sample_email,
        sample_classification,
    ):
        """WebSocket notification includes classification details."""
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        await publisher.publish(workflow_result)

        notification = mock_connection_manager.broadcast.call_args[0][0]
        assert notification["classification"]["category"] == "Personal"
        assert notification["classification"]["priority"] == "Medium"
        assert notification["classification"]["confidence"] == 0.85

    async def test_publish_notification_reports_summary_presence(
        self,
        publisher,
        mock_connection_manager,
        sample_email,
        sample_classification,
        sample_summary,
    ):
        """WebSocket notification correctly reports whether summary was generated."""
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            summary=sample_summary,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        await publisher.publish(workflow_result)

        notification = mock_connection_manager.broadcast.call_args[0][0]
        assert notification["has_summary"] is True

    async def test_publish_notification_reports_draft_presence(
        self,
        publisher,
        mock_connection_manager,
        sample_email,
        sample_classification,
        sample_draft_reply,
    ):
        """WebSocket notification correctly reports whether draft reply was generated."""
        publisher._store_in_postgres = AsyncMock(return_value=uuid.uuid4())

        workflow_result = _build_workflow_result(
            email=sample_email,
            classification=sample_classification,
            draft_reply=sample_draft_reply,
            current_stage=WorkflowStage.COMPLETED.value,
        )

        await publisher.publish(workflow_result)

        notification = mock_connection_manager.broadcast.call_args[0][0]
        assert notification["has_draft_reply"] is True


# --- Test PostgreSQL persistence logic ---


class TestStoreInPostgres:
    """Test database persistence (using mocked session)."""

    async def test_creates_processed_email_record(
        self,
        sample_email,
        sample_classification,
        mock_vector_store,
        mock_connection_manager,
    ):
        """Verifies that _store_in_postgres creates a record when email is new."""
        # Create a more realistic mock that simulates the DB operations
        mock_processed_email = MagicMock()
        mock_processed_email.id = uuid.uuid4()

        mock_email_repo = AsyncMock()
        mock_email_repo.get_by_provider_message_id = AsyncMock(return_value=None)
        mock_email_repo.create = AsyncMock(return_value=mock_processed_email)
        mock_email_repo.update_classification = AsyncMock(return_value=mock_processed_email)
        mock_email_repo.update_workflow_stage = AsyncMock(return_value=mock_processed_email)

        mock_draft_repo = AsyncMock()

        with patch(
            "src.services.result_publisher.ProcessedEmailRepository",
            return_value=mock_email_repo,
        ), patch(
            "src.services.result_publisher.DraftReplyRepository",
            return_value=mock_draft_repo,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_begin = AsyncMock()
            mock_begin.__aenter__ = AsyncMock(return_value=None)
            mock_begin.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin = MagicMock(return_value=mock_begin)

            factory = MagicMock(return_value=mock_session)

            publisher = ResultPublisher(
                session_factory=factory,
                vector_store_service=mock_vector_store,
                connection_manager=mock_connection_manager,
            )

            result = await publisher._store_in_postgres(
                email=sample_email,
                classification=sample_classification,
                summary=None,
                draft_reply=None,
                current_stage=WorkflowStage.COMPLETED.value,
                error=None,
                flagged_for_review=False,
            )

            mock_email_repo.create.assert_called_once()
            mock_email_repo.update_classification.assert_called_once()
            assert result == mock_processed_email.id

    async def test_creates_draft_reply_record(
        self,
        sample_email,
        sample_classification,
        sample_draft_reply,
        mock_vector_store,
        mock_connection_manager,
    ):
        """Verifies draft reply record is created when draft is present."""
        mock_processed_email = MagicMock()
        mock_processed_email.id = uuid.uuid4()

        mock_draft_record = MagicMock()
        mock_draft_record.id = uuid.uuid4()

        mock_email_repo = AsyncMock()
        mock_email_repo.get_by_provider_message_id = AsyncMock(return_value=None)
        mock_email_repo.create = AsyncMock(return_value=mock_processed_email)
        mock_email_repo.update_classification = AsyncMock(return_value=mock_processed_email)
        mock_email_repo.update_summary = AsyncMock(return_value=mock_processed_email)
        mock_email_repo.update_workflow_stage = AsyncMock(return_value=mock_processed_email)

        mock_draft_repo = AsyncMock()
        mock_draft_repo.create = AsyncMock(return_value=mock_draft_record)

        with patch(
            "src.services.result_publisher.ProcessedEmailRepository",
            return_value=mock_email_repo,
        ), patch(
            "src.services.result_publisher.DraftReplyRepository",
            return_value=mock_draft_repo,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_begin = AsyncMock()
            mock_begin.__aenter__ = AsyncMock(return_value=None)
            mock_begin.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin = MagicMock(return_value=mock_begin)

            factory = MagicMock(return_value=mock_session)

            publisher = ResultPublisher(
                session_factory=factory,
                vector_store_service=mock_vector_store,
                connection_manager=mock_connection_manager,
            )

            await publisher._store_in_postgres(
                email=sample_email,
                classification=sample_classification,
                summary=None,
                draft_reply=sample_draft_reply,
                current_stage=WorkflowStage.COMPLETED.value,
                error=None,
                flagged_for_review=False,
            )

            mock_draft_repo.create.assert_called_once()
            create_kwargs = mock_draft_repo.create.call_args.kwargs
            assert create_kwargs["reply_body"] == sample_draft_reply.reply_body
            assert create_kwargs["suggested_subject"] == sample_draft_reply.suggested_subject
            assert create_kwargs["status"] == "pending"

    async def test_postgres_failure_returns_none(
        self,
        sample_email,
        mock_vector_store,
        mock_connection_manager,
    ):
        """Returns None when DB operations fail (non-fatal for pipeline)."""
        # Factory raises on context enter
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB connection failed"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=mock_session)

        publisher = ResultPublisher(
            session_factory=factory,
            vector_store_service=mock_vector_store,
            connection_manager=mock_connection_manager,
        )

        result = await publisher._store_in_postgres(
            email=sample_email,
            classification=None,
            summary=None,
            draft_reply=None,
            current_stage=WorkflowStage.FAILED.value,
            error="test error",
            flagged_for_review=False,
        )

        assert result is None
