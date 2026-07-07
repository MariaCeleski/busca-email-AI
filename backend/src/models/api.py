"""Pydantic models for API responses."""

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

from .classification import ClassificationResult
from .draft import DraftReply
from .enums import WorkflowStage
from .summary import SummaryResult

T = TypeVar("T")


class EmailProcessingResult(BaseModel):
    """Full processing result returned to the API/Dashboard."""

    email_id: str
    provider_message_id: str
    sender: str
    subject: str
    body: str
    timestamp: datetime
    processing_timestamp: datetime
    classification: ClassificationResult
    summary: Optional[SummaryResult] = None
    draft_reply: Optional[DraftReply] = None
    workflow_stage: WorkflowStage


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated API response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class FieldError(BaseModel):
    """A single field validation error."""

    field: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response for API errors."""

    detail: str
    errors: list[FieldError] = []
