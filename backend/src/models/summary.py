"""Pydantic model for email summarization results."""

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    """Result of email summarization by the Summarizer Agent."""

    summary: str  # Max 3 sentences
    action_items: list[str] = Field(default_factory=list, max_length=10)
    is_fallback: bool = False
    no_content: bool = False
