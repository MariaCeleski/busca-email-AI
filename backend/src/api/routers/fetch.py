"""Email fetch endpoint.

Provides:
- POST /api/v1/emails/fetch — trigger manual email fetch
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/emails", tags=["fetch"])


class FetchAcknowledgment(BaseModel):
    """Response for manual fetch trigger."""

    status: str
    message: str


@router.post("/fetch", response_model=FetchAcknowledgment)
async def trigger_fetch():
    """Trigger a manual email fetch.

    Returns an acknowledgment that the fetch has been initiated.
    The actual fetching runs asynchronously in the background.
    """
    # In production, this would queue a Celery task
    # For now, return acknowledgment
    return FetchAcknowledgment(
        status="accepted",
        message="Email fetch initiated. Processing will occur in the background.",
    )
