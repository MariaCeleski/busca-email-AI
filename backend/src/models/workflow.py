"""Pydantic model for workflow state tracking."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .classification import ClassificationResult
from .draft import DraftReply
from .enums import WorkflowStage
from .summary import SummaryResult


class WorkflowState(BaseModel):
    """State of a single email processing workflow."""

    email_id: str
    workflow_id: str
    current_stage: WorkflowStage
    classification: Optional[ClassificationResult] = None
    summary: Optional[SummaryResult] = None
    draft_reply: Optional[DraftReply] = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
