"""Email API endpoints.

Provides:
- GET /api/v1/emails — paginated list with filters
- GET /api/v1/emails/review — emails flagged for manual review (confidence < 0.75)
- GET /api/v1/emails/{email_id} — full processing result (with draft reply if present)
- POST /api/v1/emails/{email_id}/reply/approve — approve and send draft
- POST /api/v1/emails/{email_id}/reply/reject — reject draft

Validates: Requirements 8.1, 8.2, 8.8, 7.1, 7.2, 7.8
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.auth import ApprovedReply, SendResult
from src.models.database import get_session
from src.models.orm import ConnectedAccount as ConnectedAccountORM
from src.models.orm import DraftReply as DraftReplyORM
from src.models.orm import ProcessedEmail
from src.models.repositories import DraftReplyRepository, ProcessedEmailRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/emails", tags=["emails"])

# Maximum time allowed for the send operation (seconds)
_SEND_TIMEOUT_SECONDS = 30

# Confidence threshold for review flagging (Requirement 7.8)
REVIEW_CONFIDENCE_THRESHOLD = 0.75


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


def _draft_to_dict(draft: DraftReplyORM) -> dict:
    """Convert a DraftReply ORM object to an API response dict."""
    return {
        "draft_id": str(draft.id),
        "reply_body": draft.reply_body,
        "suggested_subject": draft.suggested_subject,
        "referenced_email_ids": draft.referenced_email_ids or [],
        "status": draft.status,
        "generated_at": draft.generated_at.isoformat() if draft.generated_at else None,
        "actioned_at": draft.actioned_at.isoformat() if draft.actioned_at else None,
        "edited_body": draft.edited_body,
        "edited_subject": draft.edited_subject,
        "send_error": draft.send_error,
    }


def _email_to_dict(email: ProcessedEmail, draft: DraftReplyORM | None = None) -> dict:
    """Convert a ProcessedEmail ORM object to an API response dict.

    Args:
        email: The ProcessedEmail ORM instance.
        draft: Optional DraftReply ORM instance to include in the response.

    Returns:
        Dictionary representation of the email processing result.
    """
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
        "draft_reply": _draft_to_dict(draft) if draft else None,
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
    """List emails flagged for manual review.

    Returns emails where confidence < 0.75 OR flagged_for_review is True,
    sorted by processing_timestamp descending (Requirement 7.8).
    """
    offset = (page - 1) * page_size

    # Filter: flagged_for_review=True OR confidence < 0.75
    review_filter = or_(
        ProcessedEmail.flagged_for_review == True,  # noqa: E712
        ProcessedEmail.confidence < REVIEW_CONFIDENCE_THRESHOLD,
    )

    count_stmt = (
        select(func.count())
        .select_from(ProcessedEmail)
        .where(review_filter)
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = (
        select(ProcessedEmail)
        .where(review_filter)
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

    Filters:
    - category: Filter by email category (Urgent, Informative, etc.)
    - priority: Filter by priority level (High, Medium, Low)
    - date_from: Filter emails processed on or after this timestamp
    - date_to: Filter emails processed on or before this timestamp
    """
    offset = (page - 1) * page_size

    # Build base filter conditions
    conditions = []
    if category:
        conditions.append(ProcessedEmail.category == category)
    if priority:
        conditions.append(ProcessedEmail.priority == priority)
    if date_from:
        conditions.append(ProcessedEmail.processing_timestamp >= date_from)
    if date_to:
        conditions.append(ProcessedEmail.processing_timestamp <= date_to)

    # Count query
    count_stmt = select(func.count()).select_from(ProcessedEmail)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # Data query
    stmt = select(ProcessedEmail).order_by(
        ProcessedEmail.processing_timestamp.desc()
    )
    for cond in conditions:
        stmt = stmt.where(cond)

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
    """Get full processing result for a specific email.

    Joins with draft_replies to include the draft reply if one exists.
    Returns 404 if the email ID does not exist.
    """
    # Use selectinload to eagerly load draft_replies relationship
    stmt = (
        select(ProcessedEmail)
        .options(selectinload(ProcessedEmail.draft_replies))
        .where(ProcessedEmail.id == email_id)
    )
    result = await session.execute(stmt)
    email = result.scalar_one_or_none()

    if email is None:
        raise HTTPException(
            status_code=404,
            detail=f"Email with id '{email_id}' not found",
        )

    # Get the first draft reply if any exist (typically one per email)
    draft = email.draft_replies[0] if email.draft_replies else None

    return _email_to_dict(email, draft=draft)


@router.post("/{email_id}/reply/approve")
async def approve_reply(
    email_id: uuid.UUID,
    body: ReplyActionRequest = None,
    session: AsyncSession = Depends(get_session),
):
    """Approve and send a draft reply via the email provider.

    On approval:
    1. Validates draft exists and is in 'pending' or 'send_failed' state
    2. Updates status to 'approved' with optional edited body/subject
    3. Attempts to send via the email provider (within 30s timeout)
    4. On send success: updates status to 'sent'
    5. On send failure: updates status to 'send_failed', retains draft, stores error

    Returns 404 if no draft exists for the email.
    Returns 409 if the draft has already been actioned (approved/sent/rejected)
        but NOT for send_failed (which allows retry).

    Validates: Requirements 8.3, 8.9, 7.4, 7.5, 7.6, 7.7, 7.9
    """
    draft_repo = DraftReplyRepository(session)
    draft = await draft_repo.get_by_email_id(email_id)

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft reply not found")

    # Allow retry for send_failed drafts; reject already-actioned ones
    if draft.status not in ("pending", "send_failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Draft already actioned with status: {draft.status}",
        )

    # Apply edits if provided
    now = datetime.utcnow()
    draft.status = "approved"
    draft.actioned_at = now
    draft.send_error = None  # Clear previous error on retry
    if body and body.edited_body:
        draft.edited_body = body.edited_body
    if body and body.edited_subject:
        draft.edited_subject = body.edited_subject

    await session.flush()

    # Look up the associated email for provider/sender info
    email_repo = ProcessedEmailRepository(session)
    email = await email_repo.get_by_id(email_id)

    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    # Attempt to send the reply via the email provider
    send_result = await _attempt_send(session, email, draft)

    if send_result.success:
        draft.status = "sent"
        await session.commit()
        return {
            "status": "sent",
            "email_id": str(email_id),
            "draft_id": str(draft.id),
            "message": "Reply sent successfully",
        }
    else:
        # Send failed — retain draft, store error, allow retry
        draft.status = "send_failed"
        draft.send_error = send_result.error or "Unknown send failure"
        await session.commit()
        return {
            "status": "send_failed",
            "email_id": str(email_id),
            "draft_id": str(draft.id),
            "error": draft.send_error,
            "message": "Send failed. Draft retained for retry.",
        }


async def _get_provider_client(session: AsyncSession, email: ProcessedEmail):
    """Get the email provider client for the email's user and provider.

    Args:
        session: The database session.
        email: The ProcessedEmail instance.

    Returns:
        An EmailProviderClient instance, or None if no connected account found.
    """
    # Find the connected account for this user/provider
    stmt = (
        select(ConnectedAccountORM)
        .where(
            ConnectedAccountORM.user_id == email.user_id,
            ConnectedAccountORM.provider == email.provider,
            ConnectedAccountORM.status == "connected",
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if account is None:
        return None

    if email.provider == "gmail":
        from src.providers.gmail import GmailClient

        return GmailClient(
            access_token=account.encrypted_access_token.decode()
            if isinstance(account.encrypted_access_token, bytes)
            else (account.encrypted_access_token or ""),
            refresh_token=account.encrypted_refresh_token.decode()
            if isinstance(account.encrypted_refresh_token, bytes)
            else account.encrypted_refresh_token,
        )
    elif email.provider == "microsoft":
        from src.providers.microsoft import MicrosoftGraphClient

        return MicrosoftGraphClient(
            access_token=account.encrypted_access_token.decode()
            if isinstance(account.encrypted_access_token, bytes)
            else (account.encrypted_access_token or ""),
            refresh_token=account.encrypted_refresh_token.decode()
            if isinstance(account.encrypted_refresh_token, bytes)
            else account.encrypted_refresh_token,
        )

    return None


async def _attempt_send(
    session: AsyncSession, email: ProcessedEmail, draft: DraftReplyORM
):
    """Attempt to send the approved reply via the email provider.

    Uses the edited body/subject if provided, otherwise falls back to the
    original draft body/subject. Enforces a 30-second timeout.

    Args:
        session: The database session.
        email: The ProcessedEmail ORM instance.
        draft: The DraftReply ORM instance.

    Returns:
        A SendResult indicating success or failure.
    """
    # Build the reply content (prefer edited versions)
    reply_body = draft.edited_body or draft.reply_body
    reply_subject = draft.edited_subject or draft.suggested_subject or ""

    # Build the ApprovedReply payload
    approved_reply = ApprovedReply(
        email_id=str(email.id),
        to_address=email.sender,
        subject=reply_subject,
        body=reply_body,
        thread_id=email.thread_id,
        in_reply_to=email.provider_message_id,
    )

    # Get the provider client
    try:
        provider_client = await _get_provider_client(session, email)
    except Exception as exc:
        logger.error("Failed to get provider client: %s", exc)
        return SendResult(success=False, error=f"Provider client error: {str(exc)}")

    if provider_client is None:
        return SendResult(
            success=False,
            error="No connected email account found for sending",
        )

    # Attempt send with timeout
    try:
        send_result = await asyncio.wait_for(
            provider_client.send_reply(approved_reply),
            timeout=_SEND_TIMEOUT_SECONDS,
        )
        return send_result
    except asyncio.TimeoutError:
        logger.error("Send timed out for email %s", email.id)
        return SendResult(success=False, error="Send operation timed out (30s)")
    except Exception as exc:
        logger.error("Send failed for email %s: %s", email.id, exc)
        return SendResult(success=False, error=str(exc))


@router.post("/{email_id}/reply/reject")
async def reject_reply(
    email_id: uuid.UUID,
    body: ReplyActionRequest = None,
    session: AsyncSession = Depends(get_session),
):
    """Reject a draft reply and mark for manual response.

    Returns 404 if no draft exists for the email.
    Returns 409 if the draft has already been actioned.

    Validates: Requirements 8.3, 8.9, 7.7
    """
    draft_repo = DraftReplyRepository(session)
    draft = await draft_repo.get_by_email_id(email_id)

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft reply not found")

    if draft.status not in ("pending", "send_failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Draft already actioned with status: {draft.status}",
        )

    # Update draft status to rejected
    draft.status = "rejected"
    draft.actioned_at = datetime.utcnow()

    # Mark the email as requiring manual response (Requirement 7.7)
    email_repo = ProcessedEmailRepository(session)
    email = await email_repo.get_by_id(email_id)
    if email is not None:
        email.workflow_stage = "manual_review"

    await session.commit()

    return {
        "status": "rejected",
        "email_id": str(email_id),
        "draft_id": str(draft.id),
        "message": "Draft rejected. Email marked for manual response.",
    }
