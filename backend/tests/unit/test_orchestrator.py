"""Unit tests for the Agent Orchestrator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import (
    AgentOrchestrator,
    EmailWorkflowState,
    route_after_classification,
    route_after_summarize,
)
from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import (
    DraftStatus,
    EmailCategory,
    PriorityLevel,
    WorkflowStage,
)
from src.models.summary import SummaryResult


# --- Fixtures ---


@pytest.fixture
def sample_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg_001",
        sender="alice@example.com",
        subject="Urgent: Server down",
        body="The production server is down and needs immediate attention. " * 50,
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def short_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg_002",
        sender="bob@example.com",
        subject="Quick question",
        body="Can you send the report?",
        timestamp=datetime(2024, 1, 15, 11, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def mock_classifier() -> AsyncMock:
    classifier = AsyncMock()
    classifier.classify = AsyncMock()
    return classifier


@pytest.fixture
def mock_summarizer() -> AsyncMock:
    summarizer = AsyncMock()
    summarizer.summarize = AsyncMock()
    return summarizer


@pytest.fixture
def mock_response_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.generate_reply = AsyncMock()
    return agent


@pytest.fixture
def orchestrator(
    mock_classifier: AsyncMock,
    mock_summarizer: AsyncMock,
    mock_response_agent: AsyncMock,
) -> AgentOrchestrator:
    return AgentOrchestrator(
        classifier=mock_classifier,
        summarizer=mock_summarizer,
        response_agent=mock_response_agent,
        max_retries=3,
        hard_timeout=30,
        max_concurrent=10,
    )


def _make_classification(
    category: EmailCategory = EmailCategory.INFORMATIVE,
    priority: PriorityLevel = PriorityLevel.MEDIUM,
    confidence: float = 0.9,
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        priority=priority,
        confidence=confidence,
        requires_response=category in (EmailCategory.URGENT, EmailCategory.PERSONAL),
        requires_summary=True,
        flagged_for_review=confidence < 0.6,
    )


def _make_summary() -> SummaryResult:
    return SummaryResult(
        summary="Server is down and needs attention.",
        action_items=["Check server status", "Restart services"],
    )


def _make_draft() -> DraftReply:
    return DraftReply(
        reply_body="I'll look into the server issue right away.",
        suggested_subject="Re: Urgent: Server down",
        referenced_email_ids=[],
        status=DraftStatus.PENDING,
        generated_at=datetime(2024, 1, 15, 10, 5, 0),
    )


# --- Test routing logic ---


class TestRouteAfterClassification:
    """Test the route_after_classification function."""

    def test_low_confidence_routes_to_manual_review(self, sample_email: RawEmail):
        """Low confidence (< 0.6) → flagged for manual review → manual_review."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(confidence=0.4),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": True,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "manual_review"

    def test_urgent_high_priority_short_body_routes_to_generate_response(
        self, short_email: RawEmail
    ):
        """Urgent + High priority + short body → generate_response."""
        state: EmailWorkflowState = {
            "email": short_email,
            "classification": _make_classification(
                category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "generate_response"

    def test_personal_medium_priority_routes_to_generate_response(
        self, short_email: RawEmail
    ):
        """Personal + Medium priority → generate_response."""
        state: EmailWorkflowState = {
            "email": short_email,
            "classification": _make_classification(
                category=EmailCategory.PERSONAL, priority=PriorityLevel.MEDIUM
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "generate_response"

    def test_urgent_high_long_body_routes_to_summarize(self, sample_email: RawEmail):
        """Urgent + High priority + body > 200 words → summarize first (dual path)."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": True,
        }
        assert route_after_classification(state) == "summarize"

    def test_informative_routes_to_summarize(self, sample_email: RawEmail):
        """Informative category → summarize."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "summarize"

    def test_no_classification_routes_to_manual_review(self, sample_email: RawEmail):
        """No classification → manual_review."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "manual_review"

    def test_spam_routes_to_summarize(self, sample_email: RawEmail):
        """Spam category → summarize."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.SPAM, priority=PriorityLevel.LOW
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "summarize"

    def test_promotional_routes_to_summarize(self, short_email: RawEmail):
        """Promotional category → summarize."""
        state: EmailWorkflowState = {
            "email": short_email,
            "classification": _make_classification(
                category=EmailCategory.PROMOTIONAL, priority=PriorityLevel.MEDIUM
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "summarize"

    def test_transactional_routes_to_summarize(self, short_email: RawEmail):
        """Transactional category → summarize."""
        state: EmailWorkflowState = {
            "email": short_email,
            "classification": _make_classification(
                category=EmailCategory.TRANSACTIONAL, priority=PriorityLevel.HIGH
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_classification(state) == "summarize"

    def test_urgent_low_priority_routes_to_summarize(self, sample_email: RawEmail):
        """Urgent + Low priority → summarize (priority Low overrides category)."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.URGENT, priority=PriorityLevel.LOW
            ),
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "classifying",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        # Urgent + Low → falls through to default "summarize"
        assert route_after_classification(state) == "summarize"


# --- Test orchestrator process_email ---


class TestAgentOrchestratorProcessEmail:
    """Test the full process_email pipeline."""

    async def test_urgent_high_short_triggers_response_agent(
        self,
        orchestrator: AgentOrchestrator,
        mock_classifier: AsyncMock,
        mock_response_agent: AsyncMock,
        short_email: RawEmail,
    ):
        """Urgent + High priority → Response Agent invoked."""
        classification = _make_classification(
            category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
        )
        mock_classifier.classify.return_value = classification
        mock_response_agent.generate_reply.return_value = _make_draft()

        result = await orchestrator.process_email(short_email)

        mock_classifier.classify.assert_called_once_with(short_email)
        mock_response_agent.generate_reply.assert_called_once_with(
            short_email, classification
        )
        assert result["classification"] == classification
        assert result["draft_reply"] is not None
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_informative_triggers_summarizer(
        self,
        orchestrator: AgentOrchestrator,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        sample_email: RawEmail,
    ):
        """Informative category → Summarizer invoked."""
        classification = _make_classification(
            category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.return_value = _make_summary()

        result = await orchestrator.process_email(sample_email)

        mock_classifier.classify.assert_called_once_with(sample_email)
        mock_summarizer.summarize.assert_called_once_with(sample_email)
        assert result["summary"] is not None
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_low_confidence_flags_for_review(
        self,
        orchestrator: AgentOrchestrator,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """Low confidence → flagged for manual review, no further agents called."""
        classification = _make_classification(confidence=0.4)
        mock_classifier.classify.return_value = classification

        result = await orchestrator.process_email(sample_email)

        mock_classifier.classify.assert_called_once()
        mock_summarizer.summarize.assert_not_called()
        mock_response_agent.generate_reply.assert_not_called()
        assert result["flagged_for_review"] is True
        assert result["current_stage"] == WorkflowStage.MANUAL_REVIEW.value


# --- Test retry logic ---


class TestRetryLogic:
    """Test per-agent retry and failure handling."""

    async def test_agent_retries_on_failure_then_succeeds(
        self,
        orchestrator: AgentOrchestrator,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        sample_email: RawEmail,
    ):
        """Agent fails 2x then succeeds on 3rd attempt."""
        classification = _make_classification(
            category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
        )
        # Fail twice, succeed on third
        mock_classifier.classify.side_effect = [
            Exception("Temporary failure"),
            Exception("Temporary failure"),
            classification,
        ]
        mock_summarizer.summarize.return_value = _make_summary()

        result = await orchestrator.process_email(sample_email)

        assert mock_classifier.classify.call_count == 3
        assert result["classification"] == classification
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_retry_exhaustion_marks_email_failed(
        self,
        orchestrator: AgentOrchestrator,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """Agent fails 3x → email marked failed, remaining agents skipped."""
        mock_classifier.classify.side_effect = Exception("Persistent failure")

        result = await orchestrator.process_email(sample_email)

        assert mock_classifier.classify.call_count == 3
        assert result["current_stage"] == WorkflowStage.FAILED.value
        assert result["error"] is not None
        assert "classifier" in result["error"]
        # Remaining agents should not be called
        mock_summarizer.summarize.assert_not_called()
        mock_response_agent.generate_reply.assert_not_called()

    async def test_timeout_triggers_retry(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """30s timeout triggers retry."""
        # Use a very short timeout for testing
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=1,  # 1 second for test speed
            max_concurrent=10,
        )

        classification = _make_classification(
            category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
        )

        async def slow_classify(email):
            await asyncio.sleep(5)
            return classification

        # First call times out, second succeeds immediately
        mock_classifier.classify.side_effect = [
            slow_classify(sample_email),
            classification,
        ]

        # Override: make first call actually timeout by using side_effect properly
        call_count = 0

        async def classify_with_timeout(email):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(5)
                return classification
            return classification

        mock_classifier.classify.side_effect = None
        mock_classifier.classify = AsyncMock(side_effect=classify_with_timeout)
        mock_summarizer.summarize.return_value = _make_summary()

        result = await orchestrator.process_email(sample_email)

        assert call_count >= 2
        assert result["classification"] == classification


# --- Test concurrent processing ---


class TestConcurrentProcessing:
    """Test concurrent processing with isolated state."""

    async def test_concurrent_emails_have_isolated_state(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
    ):
        """Multiple emails processed concurrently maintain isolated state."""
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        emails = [
            RawEmail(
                provider_message_id=f"msg_{i:03d}",
                sender=f"user{i}@example.com",
                subject=f"Subject {i}",
                body=f"Body content {i} " * 50,
                timestamp=datetime(2024, 1, 15, 10, i, 0),
                provider="gmail",
            )
            for i in range(5)
        ]

        classification = _make_classification(
            category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.return_value = _make_summary()

        # Process all emails concurrently
        results = await asyncio.gather(
            *[orchestrator.process_email(email) for email in emails]
        )

        # All should complete successfully
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result["current_stage"] == WorkflowStage.COMPLETED.value
            assert result["email"].provider_message_id == f"msg_{i:03d}"

    async def test_semaphore_limits_concurrency(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
    ):
        """Semaphore limits max concurrent processing to configured value."""
        max_concurrent = 2
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=max_concurrent,
        )

        active_count = 0
        max_active = 0

        original_process = orchestrator._process_with_retries

        async def track_concurrency(email):
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.1)  # Simulate work
            result = await original_process(email)
            active_count -= 1
            return result

        orchestrator._process_with_retries = track_concurrency

        classification = _make_classification(
            category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.return_value = _make_summary()

        emails = [
            RawEmail(
                provider_message_id=f"msg_{i:03d}",
                sender=f"user{i}@example.com",
                subject=f"Subject {i}",
                body=f"Body content {i} " * 50,
                timestamp=datetime(2024, 1, 15, 10, i, 0),
                provider="gmail",
            )
            for i in range(5)
        ]

        await asyncio.gather(*[orchestrator.process_email(email) for email in emails])

        assert max_active <= max_concurrent


# --- Test handle_agent_failure ---


class TestHandleAgentFailure:
    """Test the handle_agent_failure method."""

    def test_marks_state_as_failed(
        self,
        orchestrator: AgentOrchestrator,
        sample_email: RawEmail,
    ):
        """handle_agent_failure marks state with FAILED stage."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "retry_counts": {"classifier": 3},
            "current_stage": WorkflowStage.CLASSIFYING.value,
            "error": None,
            "flagged_for_review": False,
        }

        result = orchestrator.handle_agent_failure("classifier", state)

        assert result["current_stage"] == WorkflowStage.FAILED.value
        assert "classifier" in result["error"]


# --- Test route_after_summarize ---


class TestRouteAfterSummarize:
    """Test the route_after_summarize function."""

    def test_dual_path_routes_to_generate_response(self, sample_email: RawEmail):
        """When needs_dual_path is True → generate_response after summarize."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
            ),
            "summary": _make_summary(),
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "summarizing",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": True,
        }
        assert route_after_summarize(state) == "generate_response"

    def test_no_dual_path_routes_to_publish_results(self, sample_email: RawEmail):
        """When needs_dual_path is False → publish_results after summarize."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
            ),
            "summary": _make_summary(),
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "summarizing",
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        assert route_after_summarize(state) == "publish_results"

    def test_missing_needs_dual_path_defaults_to_publish_results(
        self, sample_email: RawEmail
    ):
        """When needs_dual_path key is missing → defaults to publish_results."""
        state: EmailWorkflowState = {
            "email": sample_email,
            "classification": _make_classification(
                category=EmailCategory.INFORMATIVE, priority=PriorityLevel.LOW
            ),
            "summary": _make_summary(),
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": "summarizing",
            "error": None,
            "flagged_for_review": False,
        }
        assert route_after_summarize(state) == "publish_results"


# --- Test dual path in orchestrator ---


class TestDualPathProcessing:
    """Test that Urgent emails with body > 200 words get both summarization and response."""

    async def test_urgent_high_long_body_gets_both_summary_and_response(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """Urgent + High + body > 200 words → BOTH summarizer AND response agent called."""
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        classification = _make_classification(
            category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.return_value = _make_summary()
        mock_response_agent.generate_reply.return_value = _make_draft()

        result = await orchestrator.process_email(sample_email)

        # Both agents should be called
        mock_summarizer.summarize.assert_called_once_with(sample_email)
        mock_response_agent.generate_reply.assert_called_once_with(
            sample_email, classification
        )
        # Both results should be present
        assert result["summary"] is not None
        assert result["draft_reply"] is not None
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_urgent_medium_long_body_gets_both_summary_and_response(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """Urgent + Medium + body > 200 words → BOTH summarizer AND response agent called."""
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        classification = _make_classification(
            category=EmailCategory.URGENT, priority=PriorityLevel.MEDIUM
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.return_value = _make_summary()
        mock_response_agent.generate_reply.return_value = _make_draft()

        result = await orchestrator.process_email(sample_email)

        # Both agents should be called
        mock_summarizer.summarize.assert_called_once_with(sample_email)
        mock_response_agent.generate_reply.assert_called_once_with(
            sample_email, classification
        )
        assert result["summary"] is not None
        assert result["draft_reply"] is not None
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_urgent_high_short_body_gets_only_response(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        short_email: RawEmail,
    ):
        """Urgent + High + body ≤ 200 words → only response agent, no summarizer."""
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        classification = _make_classification(
            category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
        )
        mock_classifier.classify.return_value = classification
        mock_response_agent.generate_reply.return_value = _make_draft()

        result = await orchestrator.process_email(short_email)

        mock_summarizer.summarize.assert_not_called()
        mock_response_agent.generate_reply.assert_called_once()
        assert result["summary"] is None
        assert result["draft_reply"] is not None
        assert result["current_stage"] == WorkflowStage.COMPLETED.value

    async def test_dual_path_summarizer_failure_skips_response(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
        sample_email: RawEmail,
    ):
        """Dual path: if summarizer fails after retries, response agent still attempted."""
        orchestrator = AgentOrchestrator(
            classifier=mock_classifier,
            summarizer=mock_summarizer,
            response_agent=mock_response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        classification = _make_classification(
            category=EmailCategory.URGENT, priority=PriorityLevel.HIGH
        )
        mock_classifier.classify.return_value = classification
        mock_summarizer.summarize.side_effect = Exception("Summarizer failed")

        result = await orchestrator.process_email(sample_email)

        # Summarizer should have been retried 3 times
        assert mock_summarizer.summarize.call_count == 3
        # When summarizer fails after retries, error is set so response is NOT called
        assert result["current_stage"] == WorkflowStage.FAILED.value


# --- Test build_email_workflow graph structure ---


class TestBuildEmailWorkflow:
    """Test that build_email_workflow constructs a valid graph."""

    def test_workflow_has_expected_nodes(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
    ):
        """The workflow should contain all expected nodes."""
        from src.agents.orchestrator import build_email_workflow

        workflow = build_email_workflow(
            mock_classifier, mock_summarizer, mock_response_agent
        )
        compiled = workflow.compile()

        # Check that the graph has the expected node names
        node_names = set(compiled.get_graph().nodes.keys())
        expected_nodes = {
            "__start__",
            "classify",
            "summarize",
            "generate_response",
            "manual_review",
            "publish_results",
            "__end__",
        }
        assert expected_nodes.issubset(node_names)

    def test_workflow_compiles_successfully(
        self,
        mock_classifier: AsyncMock,
        mock_summarizer: AsyncMock,
        mock_response_agent: AsyncMock,
    ):
        """The workflow graph should compile without errors."""
        from src.agents.orchestrator import build_email_workflow

        workflow = build_email_workflow(
            mock_classifier, mock_summarizer, mock_response_agent
        )
        compiled = workflow.compile()
        assert compiled is not None
