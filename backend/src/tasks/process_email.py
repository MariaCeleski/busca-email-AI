"""Celery task for processing a single email through the agent orchestrator."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.process_email",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def process_email_task(self, email_data: Dict) -> Dict:
    """Process a single email through the AgentOrchestrator pipeline.

    Args:
        email_data: Serialized RawEmail dict.

    Returns:
        Dict with processing results (classification, summary, draft_reply, stage).
    """
    from src.agents.classifier import ClassifierAgent
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.response import ResponseAgent
    from src.agents.summarizer import SummarizerAgent
    from src.models.email import RawEmail
    from src.services.vector_store import VectorStoreService

    try:
        email = RawEmail(**email_data)
        logger.info(
            "Processing email: provider_message_id=%s, subject=%s",
            email.provider_message_id,
            email.subject[:50],
        )

        # Initialize agents
        classifier = ClassifierAgent()
        summarizer = SummarizerAgent()
        vector_store = VectorStoreService()
        response_agent = ResponseAgent(vector_store=vector_store)

        orchestrator = AgentOrchestrator(
            classifier=classifier,
            summarizer=summarizer,
            response_agent=response_agent,
        )

        # Run the async orchestrator in a new event loop
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orchestrator.process_email(email))
        finally:
            loop.close()

        logger.info(
            "Email processed: provider_message_id=%s, stage=%s",
            email.provider_message_id,
            result.get("current_stage"),
        )

        # Serialize pydantic models for Celery JSON serialization
        return _serialize_result(result)

    except Exception as exc:
        logger.error("process_email_task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def _serialize_result(result: Dict) -> Dict:
    """Serialize Pydantic models in the result dict to JSON-compatible dicts."""
    serialized = {}
    for key, value in result.items():
        if value is None:
            serialized[key] = None
        elif hasattr(value, "model_dump"):
            serialized[key] = value.model_dump(mode="json")
        else:
            serialized[key] = value
    return serialized
