"""Pydantic models for vector store operations."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .enums import EmailCategory


class EmailMetadata(BaseModel):
    """Metadata stored alongside email embeddings in ChromaDB."""

    email_id: str
    sender: str
    timestamp: datetime
    category: EmailCategory
    thread_id: Optional[str] = None
    provider_message_id: str
    user_id: Optional[str] = None


class SearchResult(BaseModel):
    """A single result from a vector similarity search."""

    email_id: str
    metadata: EmailMetadata
    similarity_score: float
    text_snippet: Optional[str] = None


class MetadataFilter(BaseModel):
    """Filters for vector store similarity search."""

    sender: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    category: Optional[EmailCategory] = None
