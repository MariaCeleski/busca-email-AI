"""Email fetch endpoint.

Provides:
- POST /api/v1/emails/fetch — trigger manual email fetch

Requirements: 8.4
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/emails", tags=["fetch"])


class FetchAcknowledgment(BaseModel):
    """Response for manual fetch trigger."""

    status: str
    task_id: Optional[str] = None
    message: str


@router.post("/fetch", response_model=FetchAcknowledgment)
async def trigger_fetch():
    """Trigger a manual email fetch from connected email providers.

    Enqueues the poll_emails_task as a Celery task and returns immediately
    with an acknowledgment containing the task ID.

    Returns:
        FetchAcknowledgment with status="fetch_initiated" and the Celery task ID.
    """
    try:
        from src.tasks.poll_emails import poll_emails_task

        result = poll_emails_task.delay()
        task_id = result.id

        logger.info("Manual email fetch triggered, task_id=%s", task_id)

        return FetchAcknowledgment(
            status="fetch_initiated",
            task_id=task_id,
            message="Email fetch has been initiated. Processing will occur in the background.",
        )
    except Exception as exc:
        logger.error("Failed to trigger email fetch: %s", exc)
        return FetchAcknowledgment(
            status="error",
            task_id=None,
            message=f"Failed to initiate email fetch: {str(exc)}",
        )
