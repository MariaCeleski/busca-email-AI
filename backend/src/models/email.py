"""Pydantic models for raw email and attachment data."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AttachmentMetadata(BaseModel):
    """Metadata for an email attachment."""

    file_name: str
    file_size: int  # bytes
    mime_type: str


class RawEmail(BaseModel):
    """A raw email fetched from an email provider."""

    provider_message_id: str
    sender: str
    subject: str
    body: str
    timestamp: datetime
    attachments: list[AttachmentMetadata] = []
    thread_id: Optional[str] = None
    provider: str  # "gmail" or "microsoft"
