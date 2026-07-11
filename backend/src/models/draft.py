"""Pydantic models for draft reply and reply actions."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .enums import DraftStatus


class DraftReply(BaseModel):
    """A generated draft reply from the Response Agent."""

    reply_body: str = Field(max_length=2500)
    suggested_subject: str = Field(max_length=150)
    referenced_email_ids: list[str] = []
    status: DraftStatus = DraftStatus.PENDING
    generated_at: datetime

    @field_validator("reply_body")
    @classmethod
    def validate_reply_body_word_count(cls, v: str) -> str:
        """Validate that reply_body does not exceed 500 words."""
        word_count = len(v.split())
        if word_count > 500:
            raise ValueError(
                f"reply_body must not exceed 500 words, got {word_count}"
            )
        return v

    @field_validator("suggested_subject")
    @classmethod
    def validate_suggested_subject_length(cls, v: str) -> str:
        """Validate that suggested_subject does not exceed 150 characters."""
        if len(v) > 150:
            raise ValueError(
                f"suggested_subject must not exceed 150 characters, got {len(v)}"
            )
        return v


class ReplyAction(BaseModel):
    """Action to approve or reject a draft reply."""

    action: str  # "approve" or "reject"
    edited_body: Optional[str] = Field(None, max_length=10000)
    edited_subject: Optional[str] = Field(None, max_length=255)
