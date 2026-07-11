"""Celery task for processing a single email through the agent orchestrator.

Deserializes the email data into a RawEmail model, instantiates the agent
pipeline (Classifier, Summarizer, Response), runs the AgentOrchestrator,
and publishes results via ResultPublisher.

Implements:
- Retry policies matching the orchestrator's logic (max_retries=3, 5s delay)
- Soft time limit of 90s to allow graceful cleanup
- Hard time limit of 120s as absolute safety net
- Circuit breaker pattern for Gemini API calls (graceful degradation)

Requirements: 6.5, 1.1, 6.2, 6.3, 6.6
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from celery.exceptions import SoftTimeLimitExceeded

from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.process_email",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    soft_time_limit=90,
    time_limit=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
)
def process_email_task(self, email_data: Dict) -> Dict:
    """Process a single email through the AgentOrchestrator pipeline.

    Full pipeline: Email Monitor → Celery queue → LangGraph Orchestrator →
    Agents (Classifier, Summarizer, Response) → Result storage (PostgreSQL +
    ChromaDB) → WebSocket notification to Dashboard.

    This task:
    1. Deserializes email_data into a RawEmail Pydantic model
    2. Checks circuit breaker state for Gemini API
    3. Instantiates agents (ClassifierAgent, SummarizerAgent, ResponseAgent)
    4. Creates an AgentOrchestrator with the agents
    5. Runs the orchestrator's process_email() in an asyncio event loop
    6. Calls ResultPublisher.publish() with the workflow result
    7. Returns serialized results

    Args:
        email_data: Serialized RawEmail dict with fields:
            provider_message_id, sender, subject, body, timestamp,
            attachments, thread_id, provider.

    Returns:
        Dict with processing results (classification, summary, draft_reply, stage).

    Raises:
        Retries on failure up to 3 times with exponential backoff.
    """
    from src.agents.classifier import ClassifierAgent
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.response import ResponseAgent
    from src.agents.summarizer import SummarizerAgent
    from src.models.email import RawEmail
    from src.services.circuit_breaker import (
        CircuitBreakerError,
        gemini_circuit_breaker,
    )
    from src.services.vector_store import VectorStoreService

    try:
        # Step 1: Deserialize into RawEmail model
        email = RawEmail(**email_data)
        logger.info(
            "Processing email: provider_message_id=%s, subject=%s",
            email.provider_message_id,
            email.subject[:50] if email.subject else "(no subject)",
        )

        # Step 2: Check Gemini circuit breaker — fail fast if API is down
        try:
            cb_state = gemini_circuit_breaker.state
            if cb_state.value == "open":
                logger.warning(
                    "Gemini circuit breaker is OPEN. Failing fast for email: %s",
                    email.provider_message_id,
                )
                # Publish a failed result so the dashboard is notified
                failed_result = {
                    "email": email,
                    "classification": None,
                    "summary": None,
                    "draft_reply": None,
                    "current_stage": "failed",
                    "error": "Gemini API circuit breaker is open (service unavailable)",
                    "flagged_for_review": True,
                    "retry_counts": {},
                }
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_publish_results(failed_result))
                finally:
                    loop.close()
                return {
                    "current_stage": "failed",
                    "error": "Gemini API circuit breaker open",
                }
        except Exception:
            # Circuit breaker check failure should not block processing
            pass

        # Step 3: Initialize agents
        classifier = ClassifierAgent()
        summarizer = SummarizerAgent()
        vector_store = VectorStoreService()
        response_agent = ResponseAgent(vector_store=vector_store)

        # Step 4: Create orchestrator with retry and concurrency settings
        orchestrator = AgentOrchestrator(
            classifier=classifier,
            summarizer=summarizer,
            response_agent=response_agent,
            max_retries=3,
            hard_timeout=30,
            max_concurrent=10,
        )

        # Step 5: Run the async orchestrator in a new event loop
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orchestrator.process_email(email))
        finally:
            loop.close()

        # Track Gemini API health via circuit breaker
        if result.get("current_stage") == "failed" and "timeout" in (
            result.get("error", "") or ""
        ).lower():
            gemini_circuit_breaker._on_failure()
        elif result.get("current_stage") == "completed":
            gemini_circuit_breaker._on_success()

        logger.info(
            "Email processed: provider_message_id=%s, stage=%s",
            email.provider_message_id,
            result.get("current_stage"),
        )

        # Step 6: Publish results (DB persistence + WebSocket notification)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_publish_results(result))
        finally:
            loop.close()

        # Step 7: Serialize pydantic models for Celery JSON serialization
        return _serialize_result(result)

    except SoftTimeLimitExceeded:
        logger.error(
            "process_email_task soft time limit exceeded for email: %s",
            email_data.get("provider_message_id", "unknown"),
        )
        return {
            "current_stage": "failed",
            "error": "Task exceeded soft time limit",
        }
    except Exception as exc:
        logger.error(
            "process_email_task failed (attempt %d/%d): %s",
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
            exc_info=True,
        )
        raise self.retry(exc=exc)


async def _publish_results(workflow_result: Dict) -> None:
    """Publish workflow results via ResultPublisher.

    Creates a ResultPublisher instance with the application's session factory,
    vector store, and connection manager, then calls publish().

    Args:
        workflow_result: The workflow result dict from AgentOrchestrator.
    """
    try:
        from src.models.database import get_session_factory
        from src.services.result_publisher import ResultPublisher
        from src.services.vector_store import VectorStoreService

        # Import connection manager for WebSocket broadcasting
        try:
            from src.api.routers.websocket import manager as connection_manager
        except ImportError:
            # Fallback: create a no-op connection manager if WebSocket not available
            connection_manager = _NoOpConnectionManager()

        session_factory = get_session_factory()
        vector_store = VectorStoreService()

        publisher = ResultPublisher(
            session_factory=session_factory,
            vector_store_service=vector_store,
            connection_manager=connection_manager,
        )
        await publisher.publish(workflow_result)
    except Exception as exc:
        # Result publishing failure should not fail the task
        # (the processing itself already succeeded)
        logger.warning(
            "Result publishing failed (non-fatal): %s", exc
        )


class _NoOpConnectionManager:
    """No-op WebSocket connection manager for when WebSocket is not available."""

    async def broadcast(self, message: Dict) -> None:
        """No-op broadcast."""
        pass


def _serialize_result(result: Dict) -> Dict:
    """Serialize Pydantic models in the result dict to JSON-compatible dicts.

    Args:
        result: Dict that may contain Pydantic model instances.

    Returns:
        Dict with all values serialized to JSON-compatible types.
    """
    serialized = {}
    for key, value in result.items():
        if value is None:
            serialized[key] = None
        elif hasattr(value, "model_dump"):
            serialized[key] = value.model_dump(mode="json")
        else:
            serialized[key] = value
    return serialized
