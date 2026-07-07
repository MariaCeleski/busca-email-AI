"""Enum definitions for the AI Email Agent system."""

from enum import Enum


class EmailCategory(str, Enum):
    """Email classification categories."""

    URGENT = "Urgent"
    INFORMATIVE = "Informative"
    PROMOTIONAL = "Promotional"
    SPAM = "Spam"
    TRANSACTIONAL = "Transactional"
    PERSONAL = "Personal"


class PriorityLevel(str, Enum):
    """Email priority levels."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DraftStatus(str, Enum):
    """Status of a draft reply through its lifecycle."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    SEND_FAILED = "send_failed"


class WorkflowStage(str, Enum):
    """Stages of the email processing workflow."""

    QUEUED = "queued"
    CLASSIFYING = "classifying"
    SUMMARIZING = "summarizing"
    GENERATING_REPLY = "generating_reply"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class AccountStatus(str, Enum):
    """Status of a connected email account."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PENDING = "pending"
