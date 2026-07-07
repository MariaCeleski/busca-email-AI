"""Pydantic models, SQLAlchemy models, and enums."""

from src.models.database import Base, create_engine, create_session_factory, get_session
from src.models.orm import (
    AccessLog,
    ConnectedAccount as ConnectedAccountORM,
    DraftReply as DraftReplyORM,
    ProcessedEmail,
    User,
    WorkflowExecution,
)
from src.models.repositories import (
    AccessLogRepository,
    ConnectedAccountRepository,
    DraftReplyRepository,
    ProcessedEmailRepository,
    UserRepository,
    WorkflowExecutionRepository,
)

# Enums
from src.models.enums import (
    AccountStatus,
    DraftStatus,
    EmailCategory,
    PriorityLevel,
    WorkflowStage,
)

# Pydantic schemas
from src.models.email import AttachmentMetadata, RawEmail
from src.models.classification import ClassificationResult
from src.models.summary import SummaryResult
from src.models.draft import DraftReply, ReplyAction
from src.models.workflow import WorkflowState
from src.models.vector_store import EmailMetadata, MetadataFilter, SearchResult
from src.models.auth import ApprovedReply, ConnectedAccount, SendResult, TokenPair
from src.models.api import (
    EmailProcessingResult,
    ErrorResponse,
    FieldError,
    PaginatedResponse,
)

__all__ = [
    # Database
    "Base",
    "create_engine",
    "create_session_factory",
    "get_session",
    # ORM Models
    "AccessLog",
    "ConnectedAccountORM",
    "DraftReplyORM",
    "ProcessedEmail",
    "User",
    "WorkflowExecution",
    # Repositories
    "AccessLogRepository",
    "ConnectedAccountRepository",
    "DraftReplyRepository",
    "ProcessedEmailRepository",
    "UserRepository",
    "WorkflowExecutionRepository",
    # Enums
    "EmailCategory",
    "PriorityLevel",
    "DraftStatus",
    "WorkflowStage",
    "AccountStatus",
    # Pydantic Models - Email
    "AttachmentMetadata",
    "RawEmail",
    # Pydantic Models - Classification
    "ClassificationResult",
    # Pydantic Models - Summary
    "SummaryResult",
    # Pydantic Models - Draft
    "DraftReply",
    "ReplyAction",
    # Pydantic Models - Workflow
    "WorkflowState",
    # Pydantic Models - Vector Store
    "EmailMetadata",
    "SearchResult",
    "MetadataFilter",
    # Pydantic Models - Auth
    "TokenPair",
    "ConnectedAccount",
    "ApprovedReply",
    "SendResult",
    # Pydantic Models - API
    "PaginatedResponse",
    "EmailProcessingResult",
    "ErrorResponse",
    "FieldError",
]
