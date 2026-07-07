"""Email API endpoints.

Provides:
- GET /api/v1/emails — paginated list with filters
- GET /api/v1/emails/review — emails flagged for manual review
- GET /api/v1/emails/{email_id} — full processing result
- POST /api/v1/emails/{email_id}/reply/approve — approve and send draft
- POST /api/v1/emails/{email_id}/reply/reject — reject draft
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_session
from src.models.repositories import DraftReplyRepository, ProcessedEmailRepository

router = APIRouter(prefix="/api/v1/emails", tags=["emails"])


# --- Request/Response models ---


class ReplyActionRequest(BaseModel):
    """Request body for approve/reject actions."""

    edited_body: Optional[str] = Field(None, max_length=10000)
    edited_subject: Optional[str] = Field(None, max_length=255)


class PaginatedEmailResponse(BaseModel):
    """Paginated email list response."""

    items: list = []
    total: int
    page: int
    page_size: int
    total_pages: int


class AcknowledgmentResponse(BaseModel):
    """Simple acknowledgment response."""

    status: str
    message: str


# --- Helper to build email result dict ---


def _email_to_dict(email) -> dict:
    """Convert a ProcessedEmail ORM object to an API response dict."""
    return {
        "email_id": str(email.id),
        "provider_message_id": email.provider_message_id,
        "sender": email.sender,
        "subject": email.subject or "",
        "body": email.body or "",
        "timestamp": email.timestamp.isoformat() if email.timestamp else None,
        "processing_timestamp": (
            email.processing_timestamp.isoformat()
            if email.processing_timestamp
            else None
        ),
        "classification": {
            "category": email.category,
            "priority": email.priority,
            "confidence": email.confidence,
        },
        "summary": {
            "summary": email.summary,
            "action_items": email.action_items or [],
            "is_fallback": email.summary_is_fallback,
        }
        if email.summary
        else None,
        "draft_reply": None,  # Populated separately if needed
        "workflow_stage": email.workflow_stage,
        "flagged_for_review": email.flagged_for_review,
    }


# --- Endpoints ---


# NOTE: /review must be defined BEFORE /{email_id} to avoid path conflict
@router.get("/review")
async def list_emails_for_review(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List emails flagged for manual review."""
    # Use a placeholder user_id for now (single-user system)
    repo = ProcessedEmailRepository(session)
    offset = (page - 1) * page_size

    # For now, query all flagged emails (no user filter for single-user mode)
    from sqlalchemy import func, select

    from src.models.orm import ProcessedEmail

    count_stmt = (
        select(func.count())
        .select_from(ProcessedEmail)
        .where(ProcessedEmail.flagged_for_review == True)  # noqa: E712
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = (
        select(ProcessedEmail)
        .where(ProcessedEmail.flagged_for_review == True)  # noqa: E712
        .order_by(ProcessedEmail.processing_timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    emails = result.scalars().all()

    total_pages = max(1, math.ceil(total / page_size))

    return PaginatedEmailResponse(
        items=[_email_to_dict(e) for e in emails],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("")
async def list_emails(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List emails with pagination and optional filters.

    Sorted by processing_timestamp descending.
    Default page_size=20, max=100.
    """
    from sqlalchemy import func, select

    from src.models.orm import ProcessedEmail

    offset = (page - 1) * page_size

    # Build count query
    count_stmt = select(func.count()).select_from(ProcessedEmail)
    if category:
        count_stmt = count_stmt.where(ProcessedEmail.category == category)
    if priority:
        count_stmt = count_stmt.where(ProcessedEmail.priority == priority)
    if date_from:
        count_stmt = count_stmt.where(
            ProcessedEmail.processing_timestamp >= date_from
        )
    if date_to:
        count_stmt = count_stmt.where(
            ProcessedEmail.processing_timestamp <= date_to
        )

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # Build data query
    stmt = select(ProcessedEmail).order_by(
        ProcessedEmail.processing_timestamp.desc()
    )
    if category:
        stmt = stmt.where(ProcessedEmail.category == category)
    if priority:
        stmt = stmt.where(ProcessedEmail.priority == priority)
    if date_from:
        stmt = stmt.where(ProcessedEmail.processing_timestamp >= date_from)
    if date_to:
        stmt = stmt.where(ProcessedEmail.processing_timestamp <= date_to)

    stmt = stmt.offset(offset).limit(page_size)
    result = await session.execute(stmt)
    emails = result.scalars().all()

    total_pages = max(1, math.ceil(total / page_size))

    return PaginatedEmailResponse(
        items=[_email_to_dict(e) for e in emails],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{email_id}")
async def get_email(
    email_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get full processing result for a specific email."""
    from sqlalchemy import select

    from src.models.orm import ProcessedEmail

    stmt = select(ProcessedEmail).where(ProcessedEmail.id == email_id)
    result = await session.execute(stmt)
    email = result.scalar_one_or_none()

    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    return _email_to_dict(email)


@router.post("/{email_id}/reply/approve")
async def approve_reply(
    email_id: uuid.UUID,
    body: ReplyActionRequest = None,
    session: AsyncSession = Depends(get_session),
):
    """Approve and send a draft reply.

    Returns 404 if no draft exists for the email.
    Returns 409 if the draft has already been actioned.
    """
    draft_repo = DraftReplyRepository(session)
    draft = await draft_repo.get_by_email_id(email_id)

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft reply not found")

    if draft.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Draft already actioned with status: {draft.status}",
        )

    # Update draft status
    draft.status = "approved"
    draft.actioned_at = datetime.utcnow()
    if body and body.edited_body:
        draft.edited_body = body.edited_body
    if body and body.edited_subject:
        draft.edited_subject = body.edited_subject

    await session.commit()

    return {"status": "approved", "email_id": str(email_id), "draft_id": str(draft.id)}


@router.post("/{email_id}/reply/reject")
async def reject_reply(
    email_id: uuid.UUID,
    body: ReplyActionRequest = None,
    session: AsyncSession = Depends(get_session),
):
    """Reject a draft reply and mark for manual response.

    Returns 404 if no draft exists for the email.
    Returns 409 if the draft has already been actioned.
    """
    draft_repo = DraftReplyRepository(session)
    draft = await draft_repo.get_by_email_id(email_id)

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft reply not found")

    if draft.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Draft already actioned with status: {draft.status}",
        )

    # Update draft status
    draft.status = "rejected"
    draft.actioned_at = datetime.utcnow()

    await session.commit()

    return {
        "status": "rejected",
        "email_id": str(email_id),
        "draft_id": str(draft.id),
    }
