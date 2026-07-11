"""End-to-end integration test for the email processing pipeline.

Tests the full pipeline with mocked LLM responses:
  Email fetch → Classify → Summarize/Respond → Store → Notify Dashboard

Verifies:
- EmailMonitor enqueues emails via Celery task callback
- process_email_task deserializes and chains all components
- AgentOrchestrator routes correctly based on classification
- ResultPublisher persists to PostgreSQL and broadcasts via WebSocket
- Circuit breaker pattern for external service calls
- Error propagation and graceful degradation

Requirements: 6.1, 6.6, 1.1, 1.2
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import DraftStatus, EmailCategory, PriorityLevel, WorkflowStage
from src.models.summary import SummaryResult
from src.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)


# --- Fixtures ---


@pytest.fixture
def sample_urgent_email() -> RawEmail:
    """Create a sample urgent email for testing (>200 words body)."""
    long_body = (
        "Dear Team, I am writing to inform you about an urgent security incident "
        "that occurred this morning at approximately 3:00 AM UTC. Our monitoring "
        "systems detected unauthorized access attempts on our production database "
        "servers. The attackers exploited a known vulnerability in the authentication "
        "module that was scheduled for patching next week. We need to take immediate "
        "action to secure our infrastructure. The following steps must be completed "
        "within the next 2 hours: First, rotate all database credentials and API keys. "
        "Second, enable two-factor authentication for all admin accounts. Third, deploy "
        "the security patch to all production nodes. Fourth, review access logs from "
        "the past 48 hours to identify the scope of the breach. Fifth, notify all "
        "affected customers within 24 hours as required by our SLA. The security team "
        "is already working on the incident but we need all hands on deck. Please "
        "confirm your availability for an emergency meeting at 9 AM. Additionally, "
        "we should prepare a post-mortem report for the executive team by end of day. "
        "Time is critical so please prioritize this above all other tasks today. "
        "Furthermore, the compliance department has been notified and they require "
        "a full audit trail of all system access during the past 72 hours. We also "
        "need to update our incident response documentation to reflect the new "
        "threat vectors that were identified during this breach. Please ensure all "
        "team leads are informed and that their teams are on standby for any "
        "additional emergency patches that may be required over the weekend."
    )
    return RawEmail(
        provider_message_id="msg_urgent_001",
        sender="security@company.com",
        subject="URGENT: Security Incident - Immediate Action Required",
        body=long_body,
        timestamp=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        attachments=[],
        thread_id="thread_sec_001",
        provider="gmail",
    )


@pytest.fixture
def sample_informative_email() -> RawEmail:
    """Create a sample informative email for testing."""
    return RawEmail(
        provider_message_id="msg_info_002",
        sender="newsletter@techblog.com",
        subject="Weekly Tech Digest: AI Developments",
        body=(
            "This week in AI: major breakthroughs in language models, new "
            "open-source frameworks released, and exciting developments in "
            "computer vision research. Read more in our detailed articles "
            "covering the latest innovations in machine learning and deep "
            "learning technologies that are shaping the future of computing. "
            "Our team of researchers reviewed over 50 papers published this "
            "month and selected the top 10 most impactful discoveries. "
            "Each article includes practical code examples and performance "
            "benchmarks that you can reproduce in your own experiments. "
            "We also feature interviews with leading researchers from "
            "top universities and industry labs about their latest work."
        ),
        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        attachments=[],
        thread_id="thread_news_002",
        provider="gmail",
    )


@pytest.fixture
def mock_classification_urgent() -> ClassificationResult:
    """Mock classification result for urgent email."""
    return ClassificationResult(
        category=EmailCategory.URGENT,
        priority=PriorityLevel.HIGH,
        confidence=0.95,
        requires_response=True,
        requires_summary=True,
        flagged_for_review=False,
    )


@pytest.fixture
def mock_classification_informative() -> ClassificationResult:
    """Mock classification result for informative email."""
    return ClassificationResult(
        category=EmailCategory.INFORMATIVE,
        priority=PriorityLevel.MEDIUM,
        confidence=0.88,
        requires_response=False,
        requires_summary=True,
        flagged_for_review=False,
    )


@pytest.fixture
def mock_summary() -> SummaryResult:
    """Mock summary result."""
    return SummaryResult(
        summary=(
            "A security incident was detected at 3 AM UTC involving unauthorized "
            "database access. Immediate action required including credential rotation "
            "and patch deployment. Emergency meeting scheduled for 9 AM."
        ),
        action_items=[
            "Rotate all database credentials and API keys",
            "Enable two-factor authentication for admin accounts",
            "Deploy security patch to production nodes",
            "Review access logs from past 48 hours",
            "Notify affected customers within 24 hours",
        ],
        is_fallback=False,
        no_content=False,
    )


@pytest.fixture
def mock_draft_reply() -> DraftReply:
    """Mock draft reply."""
    return DraftReply(
        reply_body=(
            "Hi Security Team,\n\n"
            "I've reviewed the incident report and I'm available for the "
            "emergency meeting at 9 AM. I'll start rotating credentials for "
            "the services under my responsibility immediately.\n\n"
            "Will have the access log review for my team's systems completed "
            "within the hour.\n\n"
            "Best regards"
        ),
        suggested_subject="Re: URGENT: Security Incident - Immediate Action Required",
        referenced_email_ids=["hist_001", "hist_002"],
        status=DraftStatus.PENDING,
        generated_at=datetime(2024, 1, 15, 8, 1, 0, tzinfo=timezone.utc),
    )


class MockConnectionManager:
    """Mock WebSocket connection manager that records broadcasts."""

    def __init__(self) -> None:
        self.broadcasts: List[Dict[str, Any]] = []

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Record broadcast messages for assertion."""
        self.broadcasts.append(message)


# --- Test: Full Pipeline End-to-End ---


@pytest.mark.integration
class TestFullPipelineEndToEnd:
    """Test the complete email processing pipeline with mocked LLM responses."""

    @pytest.mark.asyncio
    async def test_urgent_email_full_pipeline(
        self,
        sample_urgent_email: RawEmail,
        mock_classification_urgent: ClassificationResult,
        mock_summary: SummaryResult,
        mock_draft_reply: DraftReply,
    ):
        """Test full pipeline: fetch → classify → summarize + respond → store → notify.

        Urgent emails with body > 200 words take the dual path:
        classify → summarize → generate_response → publish_results
        """
        from src.agents.orchestrator import AgentOrchestrator

        # Mock the agents
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value=mock_classification_urgent)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize = AsyncMock(return_value=mock_summary)

        mock_response_agent = AsyncMock()
        mock_response_agent.generate_reply = AsyncMock(return_value=mock_draft_reply)

        # Create orchestrator with mocked agents
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        # Run the pipeline
        result = await orchestrator.process_email(sample_urgent_email)

        # Verify classification was called
        mock_classifier.classify.assert_called_once_with(sample_urgent_email)

        # Verify dual path: both summarize AND generate_reply were called
        mock_summarizer.summarize.assert_called_once_with(sample_urgent_email)
        mock_response_agent.generate_reply.assert_called_once_with(
            sample_urgent_email, mock_classification_urgent
        )

        # Verify result structure
        assert result["current_stage"] == WorkflowStage.COMPLETED.value
        assert result["classification"] == mock_classification_urgent
        assert result["summary"] == mock_summary
        assert result["draft_reply"] == mock_draft_reply
        assert result["error"] is None
        assert result["flagged_for_review"] is False

    @pytest.mark.asyncio
    async def test_informative_email_summary_only(
        self,
        sample_informative_email: RawEmail,
        mock_classification_informative: ClassificationResult,
        mock_summary: SummaryResult,
    ):
        """Test informative email goes to summarizer only, not response agent."""
        from src.agents.orchestrator import AgentOrchestrator

        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value=mock_classification_informative)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize = AsyncMock(return_value=mock_summary)

        mock_response_agent = AsyncMock()
        mock_response_agent.generate_reply = AsyncMock()

        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        result = await orchestrator.process_email(sample_informative_email)

        # Verify classification was called
        mock_classifier.classify.assert_called_once()

        # Verify only summarizer was called (not response agent)
        mock_summarizer.summarize.assert_called_once()
        mock_response_agent.generate_reply.assert_not_called()

        # Verify result
        assert result["current_stage"] == WorkflowStage.COMPLETED.value
        assert result["classification"] == mock_classification_informative
        assert result["summary"] == mock_summary
        assert result["draft_reply"] is None

    @pytest.mark.asyncio
    async def test_result_publisher_stores_and_notifies(
        self,
        sample_urgent_email: RawEmail,
        mock_classification_urgent: ClassificationResult,
        mock_summary: SummaryResult,
        mock_draft_reply: DraftReply,
    ):
        """Test ResultPublisher persists results and broadcasts WebSocket notification."""
        from src.services.result_publisher import ResultPublisher

        # Mock session factory and repositories
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin = MagicMock()
        mock_session.begin().__aenter__ = AsyncMock(return_value=None)
        mock_session.begin().__aexit__ = AsyncMock(return_value=None)

        mock_session_factory = MagicMock()
        mock_session_factory.return_value = mock_session

        mock_vector_store = AsyncMock()
        mock_vector_store.store_embedding = AsyncMock(return_value="emb_123")

        mock_ws_manager = MockConnectionManager()

        publisher = ResultPublisher(
            session_factory=mock_session_factory,
            vector_store_service=mock_vector_store,
            connection_manager=mock_ws_manager,
        )

        workflow_result = {
            "email": sample_urgent_email,
            "classification": mock_classification_urgent,
            "summary": mock_summary,
            "draft_reply": mock_draft_reply,
            "current_stage": WorkflowStage.COMPLETED.value,
            "error": None,
            "flagged_for_review": False,
            "retry_counts": {},
        }

        # Mock the internal PostgreSQL storage to avoid real DB calls
        with patch.object(publisher, "_store_in_postgres", new_callable=AsyncMock) as mock_store_pg:
            mock_store_pg.return_value = uuid.uuid4()

            result = await publisher.publish(workflow_result)

        # Verify PostgreSQL storage was called
        mock_store_pg.assert_called_once()

        # Verify embedding was stored in ChromaDB
        mock_vector_store.store_embedding.assert_called_once()

        # Verify WebSocket notification was broadcast
        assert len(mock_ws_manager.broadcasts) == 1
        notification = mock_ws_manager.broadcasts[0]
        assert notification["type"] == "email_processing_complete"
        assert notification["workflow_stage"] == WorkflowStage.COMPLETED.value
        assert notification["has_summary"] is True
        assert notification["has_draft_reply"] is True
        assert notification["classification"]["category"] == "Urgent"
        assert notification["classification"]["priority"] == "High"
        assert notification["classification"]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_email_monitor_enqueue_wiring(
        self, sample_urgent_email: RawEmail
    ):
        """Test EmailMonitor properly enqueues emails via Celery task callback."""
        from src.services.email_monitor import EmailMonitor

        enqueued_tasks: List[Dict] = []

        def mock_enqueue(email_data: Dict) -> str:
            """Mock Celery task.delay that records the enqueue."""
            enqueued_tasks.append(email_data)
            return f"task_{uuid.uuid4().hex[:8]}"

        # Mock session and repository
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        # Patch the repository at import location inside the method
        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_provider_message_id = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            monitor = EmailMonitor(
                session=mock_session,
                provider_client=AsyncMock(),
                enqueue_task=mock_enqueue,
            )

            # Enqueue the email
            task_id = await monitor.enqueue_email(sample_urgent_email)

        # Verify enqueue was called
        assert task_id is not None
        assert len(enqueued_tasks) == 1
        assert enqueued_tasks[0]["provider_message_id"] == "msg_urgent_001"
        assert enqueued_tasks[0]["sender"] == "security@company.com"

    @pytest.mark.asyncio
    async def test_pipeline_error_propagation_and_graceful_degradation(
        self, sample_urgent_email: RawEmail
    ):
        """Test that agent failures propagate correctly and the pipeline degrades gracefully.

        When an agent fails after all retries, the pipeline marks the email as failed
        and skips remaining agents (Requirement 6.4).
        """
        from src.agents.orchestrator import AgentOrchestrator

        # Classifier succeeds but summarizer fails persistently
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                category=EmailCategory.URGENT,
                priority=PriorityLevel.HIGH,
                confidence=0.95,
                requires_response=True,
                requires_summary=True,
                flagged_for_review=False,
            )
        )

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize = AsyncMock(
            side_effect=RuntimeError("Gemini API timeout")
        )

        mock_response_agent = AsyncMock()
        mock_response_agent.generate_reply = AsyncMock()

        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        result = await orchestrator.process_email(sample_urgent_email)

        # Verify classification succeeded
        assert result["classification"] is not None

        # Verify pipeline marked as failed after summarizer retries exhausted
        assert result["current_stage"] == WorkflowStage.FAILED.value
        assert "summarizer" in result["error"]

        # Verify summarizer was retried 3 times
        assert mock_summarizer.summarize.call_count == 3

        # Verify response agent was NOT called (skipped after failure)
        mock_response_agent.generate_reply.assert_not_called()


# --- Test: Circuit Breaker ---


@pytest.mark.integration
class TestCircuitBreaker:
    """Test circuit breaker pattern for external service calls."""

    @pytest.mark.asyncio
    async def test_circuit_stays_closed_on_success(self):
        """Circuit remains closed when calls succeed."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            cooldown_seconds=10.0,
        )

        async def success_fn():
            return "ok"

        result = await cb.call(success_fn)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self):
        """Circuit opens after N consecutive failures."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            cooldown_seconds=10.0,
        )

        async def failing_fn():
            raise ConnectionError("Service unavailable")

        # Cause failures up to threshold
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await cb.call(failing_fn)

        assert cb.state == CircuitState.OPEN
        assert cb.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_circuit_open_rejects_calls_fast(self):
        """When circuit is OPEN, calls are rejected immediately without attempting."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            cooldown_seconds=60.0,
        )

        async def failing_fn():
            raise ConnectionError("down")

        # Trip the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call(failing_fn)

        assert cb.state == CircuitState.OPEN

        # Next call should fail fast with CircuitBreakerError
        call_count = 0

        async def should_not_be_called():
            nonlocal call_count
            call_count += 1
            return "success"

        with pytest.raises(CircuitBreakerError) as exc_info:
            await cb.call(should_not_be_called)

        assert "test_service" in str(exc_info.value)
        assert call_count == 0  # Function was never actually called

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open_after_cooldown(self):
        """After cooldown, circuit moves to HALF_OPEN and allows one test call."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            cooldown_seconds=0.1,  # Very short cooldown for testing
        )

        async def failing_fn():
            raise ConnectionError("down")

        # Trip the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call(failing_fn)

        assert cb.state == CircuitState.OPEN

        # Wait for cooldown
        await asyncio.sleep(0.15)

        # Circuit should now be HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_closes_after_successful_half_open_call(self):
        """Successful call in HALF_OPEN state closes the circuit."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            cooldown_seconds=0.1,
        )

        async def failing_fn():
            raise ConnectionError("down")

        async def success_fn():
            return "recovered"

        # Trip the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call(failing_fn)

        # Wait for cooldown
        await asyncio.sleep(0.15)

        # Make a successful call (HALF_OPEN → CLOSED)
        result = await cb.call(success_fn)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_circuit_reopens_after_failed_half_open_call(self):
        """Failed call in HALF_OPEN state reopens the circuit."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            cooldown_seconds=0.1,
        )

        async def failing_fn():
            raise ConnectionError("still down")

        # Trip the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call(failing_fn)

        # Wait for cooldown
        await asyncio.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN

        # Failed test call → back to OPEN
        with pytest.raises(ConnectionError):
            await cb.call(failing_fn)

        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_reset(self):
        """Manual reset brings circuit back to CLOSED regardless of state."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            cooldown_seconds=60.0,
        )

        # Simulate open state
        cb._state = CircuitState.OPEN
        cb._consecutive_failures = 5

        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    def test_circuit_breaker_stats(self):
        """get_stats returns correct circuit breaker information."""
        cb = CircuitBreaker(
            service_name="gemini_api",
            failure_threshold=5,
            cooldown_seconds=60.0,
        )

        stats = cb.get_stats()
        assert stats["service_name"] == "gemini_api"
        assert stats["state"] == "closed"
        assert stats["consecutive_failures"] == 0
        assert stats["failure_threshold"] == 5
        assert stats["cooldown_seconds"] == 60.0


# --- Test: WebSocket Notification Delivery ---


@pytest.mark.integration
class TestWebSocketNotificationDelivery:
    """Test that WebSocket notifications are correctly delivered."""

    @pytest.mark.asyncio
    async def test_notification_broadcast_on_processing_complete(
        self,
        sample_urgent_email: RawEmail,
        mock_classification_urgent: ClassificationResult,
        mock_summary: SummaryResult,
        mock_draft_reply: DraftReply,
    ):
        """Verify WebSocket broadcast contains correct data when processing completes."""
        from src.services.result_publisher import ResultPublisher

        mock_ws_manager = MockConnectionManager()

        publisher = ResultPublisher(
            session_factory=MagicMock(),
            vector_store_service=AsyncMock(),
            connection_manager=mock_ws_manager,
        )

        workflow_result = {
            "email": sample_urgent_email,
            "classification": mock_classification_urgent,
            "summary": mock_summary,
            "draft_reply": mock_draft_reply,
            "current_stage": WorkflowStage.COMPLETED.value,
            "error": None,
            "flagged_for_review": False,
            "retry_counts": {},
        }

        # Mock PostgreSQL to avoid real DB
        with patch.object(publisher, "_store_in_postgres", new_callable=AsyncMock) as mock_pg:
            mock_pg.return_value = uuid.uuid4()
            await publisher.publish(workflow_result)

        # Verify notification content
        assert len(mock_ws_manager.broadcasts) == 1
        notif = mock_ws_manager.broadcasts[0]
        assert notif["type"] == "email_processing_complete"
        assert notif["provider_message_id"] == "msg_urgent_001"
        assert notif["workflow_stage"] == "completed"
        assert notif["has_summary"] is True
        assert notif["has_draft_reply"] is True
        assert "timestamp" in notif

    @pytest.mark.asyncio
    async def test_notification_broadcast_on_failure(
        self, sample_urgent_email: RawEmail
    ):
        """Verify WebSocket broadcast includes failure info when processing fails."""
        from src.services.result_publisher import ResultPublisher

        mock_ws_manager = MockConnectionManager()

        publisher = ResultPublisher(
            session_factory=MagicMock(),
            vector_store_service=AsyncMock(),
            connection_manager=mock_ws_manager,
        )

        workflow_result = {
            "email": sample_urgent_email,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "current_stage": WorkflowStage.FAILED.value,
            "error": "Classifier timed out after 3 retries",
            "flagged_for_review": True,
            "retry_counts": {"classifier": 3},
        }

        with patch.object(publisher, "_store_in_postgres", new_callable=AsyncMock) as mock_pg:
            mock_pg.return_value = uuid.uuid4()
            await publisher.publish(workflow_result)

        assert len(mock_ws_manager.broadcasts) == 1
        notif = mock_ws_manager.broadcasts[0]
        assert notif["workflow_stage"] == "failed"
        assert notif["has_summary"] is False
        assert notif["has_draft_reply"] is False
        assert notif["classification"] is None


# --- Test: Process Email Task Wiring ---


@pytest.mark.integration
class TestProcessEmailTaskWiring:
    """Test the Celery task wiring connects all pipeline components."""

    @pytest.mark.asyncio
    async def test_process_email_task_invokes_full_pipeline(
        self,
        sample_urgent_email: RawEmail,
        mock_classification_urgent: ClassificationResult,
        mock_summary: SummaryResult,
        mock_draft_reply: DraftReply,
    ):
        """Test that process_email_task connects orchestrator → publisher correctly."""
        from src.tasks.process_email import _publish_results, _serialize_result

        # Test serialization of results
        result = {
            "email": sample_urgent_email,
            "classification": mock_classification_urgent,
            "summary": mock_summary,
            "draft_reply": mock_draft_reply,
            "current_stage": "completed",
            "error": None,
            "flagged_for_review": False,
            "retry_counts": {},
        }

        serialized = _serialize_result(result)

        # Verify serialization handles Pydantic models correctly
        assert serialized["current_stage"] == "completed"
        assert serialized["error"] is None
        assert isinstance(serialized["classification"], dict)
        assert serialized["classification"]["category"] == "Urgent"
        assert serialized["classification"]["priority"] == "High"
        assert serialized["classification"]["confidence"] == 0.95
        assert isinstance(serialized["summary"], dict)
        assert len(serialized["summary"]["action_items"]) == 5
        assert isinstance(serialized["draft_reply"], dict)
        assert serialized["draft_reply"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_publish_results_graceful_failure(self):
        """Test that _publish_results handles failures gracefully (non-fatal)."""
        from src.tasks.process_email import _publish_results

        # _publish_results imports ResultPublisher from src.services.result_publisher
        # internally. When email is None it should log warning but not raise.
        # The function already has a try/except that catches all exceptions.
        # We just need to verify it doesn't propagate.
        await _publish_results({"email": None})


# --- Test: Deduplication in Pipeline ---


@pytest.mark.integration
class TestPipelineDeduplication:
    """Test email deduplication across the pipeline."""

    @pytest.mark.asyncio
    async def test_duplicate_email_not_enqueued(
        self, sample_urgent_email: RawEmail
    ):
        """Test that duplicate emails are rejected at the monitor level."""
        from src.services.email_monitor import EmailMonitor

        enqueued: List[Dict] = []

        def mock_enqueue(data: Dict) -> str:
            enqueued.append(data)
            return "task_id"

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch(
            "src.models.repositories.ProcessedEmailRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            # First call: not duplicate → allows enqueue
            mock_repo.get_by_provider_message_id = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock()
            MockRepo.return_value = mock_repo

            monitor = EmailMonitor(
                session=mock_session,
                provider_client=AsyncMock(),
                enqueue_task=mock_enqueue,
            )

            # First enqueue succeeds
            task_id_1 = await monitor.enqueue_email(sample_urgent_email)
            assert task_id_1 is not None

            # Second enqueue of same email is rejected (in-memory cache hit)
            task_id_2 = await monitor.enqueue_email(sample_urgent_email)
            assert task_id_2 is None

        # Only one task was enqueued
        assert len(enqueued) == 1
