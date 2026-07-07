"""Pydantic model for email classification results."""

from pydantic import BaseModel, Field

from .enums import EmailCategory, PriorityLevel


class ClassificationResult(BaseModel):
    """Result of email classification by the Classifier Agent."""

    category: EmailCategory
    priority: PriorityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    requires_response: bool
    requires_summary: bool
    flagged_for_review: bool = False
