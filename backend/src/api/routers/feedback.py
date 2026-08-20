"""Feedback API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.get("/history")
async def get_feedback_history(
    session: AsyncSession = Depends(get_session),
):
    """Retorna historico de feedback com IDs."""
    try:
        result = await session.execute(
            text(
                "SELECT id, email_subject, email_sender,"
                " predicted_category, predicted_priority, feedback"
                " FROM classification_feedback"
                " ORDER BY created_at DESC LIMIT 50"
            )
        )
        rows = result.fetchall()
        examples = [
            {
                "id": row[0],
                "subject": row[1],
                "sender": row[2],
                "category": row[3],
                "priority": row[4],
                "feedback": row[5],
            }
            for row in rows
        ]
        return {"examples": examples, "total": len(examples)}
    except Exception as exc:
        logger.error("Feedback history error: %s", exc)
        return {"examples": [], "total": 0}


@router.delete("/all")
async def delete_all_feedback(
    session: AsyncSession = Depends(get_session),
):
    """Remove todo o historico de feedback."""
    try:
        await session.execute(text("DELETE FROM classification_feedback"))
        await session.commit()
        return {"status": "cleared"}
    except Exception as exc:
        logger.error("Clear feedback error: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.delete("/{feedback_id}")
async def delete_feedback_entry(
    feedback_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Remove um registro de feedback pelo ID."""
    try:
        await session.execute(
            text("DELETE FROM classification_feedback WHERE id = :id"),
            {"id": feedback_id},
        )
        await session.commit()
        return {"status": "deleted", "id": feedback_id}
    except Exception as exc:
        logger.error("Delete feedback error: %s", exc)
        return {"status": "error", "message": str(exc)}
