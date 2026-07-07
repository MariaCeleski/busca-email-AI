"""Pydantic model definitions for the AI Email Agent system.

This module re-exports all Pydantic models from their dedicated submodules
for backward compatibility.
"""

from .api import (
    EmailProcessingResult,
    ErrorResponse,
    FieldError,
    PaginatedResponse,
)
from .auth import ConnectedAccount, TokenPair
from .classification import ClassificationResult
from .draft import DraftReply, ReplyAction
from .email import AttachmentMetadata, RawEmail
from .enums import (
    AccountStatus,
    DraftStatus,
    EmailCategory,
    PriorityLevel,
    WorkflowStage,
)
from .summary import SummaryResult
from .vector_store import EmailMetadata, MetadataFilter, SearchResult
from .workflow import WorkflowState

__all__ = [
    # Enums
    "EmailCategory",
    "PriorityLevel",
    "DraftStatus",
    "WorkflowStage",
    "AccountStatus",
    # Email
    "AttachmentMetadata",
    "RawEmail",
    # Classification
    "ClassificationResult",
    # Summary
    "SummaryResult",
    # Draft
    "DraftReply",
    "ReplyAction",
    # Workflow
    "WorkflowState",
    # Vector Store
    "EmailMetadata",
    "SearchResult",
    "MetadataFilter",
    # Auth
    "TokenPair",
    "ConnectedAccount",
    # API
    "PaginatedResponse",
    "EmailProcessingResult",
    "ErrorResponse",
    "FieldError",
]
