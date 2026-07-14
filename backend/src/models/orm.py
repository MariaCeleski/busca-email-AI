"""SQLAlchemy ORM model definitions for the AI Email Agent system.

Defines all database tables:
- users: Application users
- connected_accounts: OAuth-connected email accounts
- processed_emails: Emails processed through the agent pipeline
- draft_replies: Generated draft replies for user review
- access_logs: API access audit log
- workflow_executions: Agent workflow execution tracking
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


def _utcnow() -> datetime:
    """Return current UTC datetime (naive, without timezone info)."""
    return datetime.utcnow()


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Relationships
    connected_accounts: Mapped[List["ConnectedAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    processed_emails: Mapped[List["ProcessedEmail"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ConnectedAccount(Base):
    """OAuth-connected email account."""

    __tablename__ = "connected_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_access_token: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    encrypted_refresh_token: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="connected")
    connected_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_sync: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    user: Mapped["User"] = relationship(back_populates="connected_accounts")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", "email_address"),
    )


class ProcessedEmail(Base):
    """Email processed through the agent pipeline."""

    __tablename__ = "processed_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False
    )
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    body: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    thread_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    processing_timestamp: Mapped[datetime] = mapped_column(default=_utcnow)

    # Classification fields
    category: Mapped[Optional[str]] = mapped_column(String(20))
    priority: Mapped[Optional[str]] = mapped_column(String(10))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Summary fields
    summary: Mapped[Optional[str]] = mapped_column(Text)
    action_items: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    summary_is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    # Workflow fields
    workflow_stage: Mapped[Optional[str]] = mapped_column(String(30), default="queued")
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="processed_emails")
    draft_replies: Mapped[List["DraftReply"]] = relationship(
        back_populates="email", cascade="all, delete-orphan"
    )
    workflow_executions: Mapped[List["WorkflowExecution"]] = relationship(
        back_populates="email", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_emails_user_timestamp", "user_id", processing_timestamp.desc()),
        Index("idx_emails_category", "category"),
        Index("idx_emails_priority", "priority"),
        Index(
            "idx_emails_flagged",
            "flagged_for_review",
            postgresql_where=(flagged_for_review == True),  # noqa: E712
        ),
        Index("idx_emails_provider_msg_id", "provider_message_id"),
    )


class DraftReply(Base):
    """Generated draft reply awaiting user review."""

    __tablename__ = "draft_replies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    reply_body: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_subject: Mapped[Optional[str]] = mapped_column(String(150))
    referenced_email_ids: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)
    actioned_at: Mapped[Optional[datetime]] = mapped_column()
    edited_body: Mapped[Optional[str]] = mapped_column(Text)
    edited_subject: Mapped[Optional[str]] = mapped_column(String(255))
    send_error: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    email: Mapped["ProcessedEmail"] = relationship(back_populates="draft_replies")

    __table_args__ = (
        Index("idx_drafts_status", "status"),
        Index("idx_drafts_email", "email_id"),
    )


class AccessLog(Base):
    """API access audit log entry."""

    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    requester_id: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=_utcnow)
    response_status: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_access_logs_timestamp", "timestamp"),
    )


class WorkflowExecution(Base):
    """Agent workflow execution tracking."""

    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    retry_counts: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column()
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    email: Mapped["ProcessedEmail"] = relationship(back_populates="workflow_executions")
