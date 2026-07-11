"""Repository classes for CRUD operations on database tables.

Provides a clean data access layer with:
- Generic base repository with common CRUD operations
- Specialized repositories for each entity with custom queries
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Optional, Sequence, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import (
    AccessLog,
    ConnectedAccount,
    DraftReply,
    ProcessedEmail,
    User,
    WorkflowExecution,
)

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository providing common CRUD operations."""

    def __init__(self, session: AsyncSession, model_class: type[T]):
        self.session = session
        self.model_class = model_class

    async def create(self, **kwargs: Any) -> T:
        """Create a new record.

        Args:
            **kwargs: Column values for the new record.

        Returns:
            The created model instance.
        """
        instance = self.model_class(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, record_id: uuid.UUID | int) -> T | None:
        """Get a record by its primary key.

        Args:
            record_id: The primary key value.

        Returns:
            The model instance or None if not found.
        """
        return await self.session.get(self.model_class, record_id)

    async def list(
        self,
        offset: int = 0,
        limit: int = 20,
        order_by: Any | None = None,
    ) -> Sequence[T]:
        """List records with pagination.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.
            order_by: Column or expression to order by.

        Returns:
            Sequence of model instances.
        """
        stmt: Select = select(self.model_class)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Get total count of records.

        Returns:
            Total number of records in the table.
        """
        stmt = select(func.count()).select_from(self.model_class)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update(self, record_id: uuid.UUID | int, **kwargs: Any) -> T | None:
        """Update a record by primary key.

        Args:
            record_id: The primary key value.
            **kwargs: Column values to update.

        Returns:
            The updated model instance or None if not found.
        """
        instance = await self.get_by_id(record_id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, record_id: uuid.UUID | int) -> bool:
        """Delete a record by primary key.

        Args:
            record_id: The primary key value.

        Returns:
            True if a record was deleted, False if not found.
        """
        instance = await self.get_by_id(record_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True


class UserRepository(BaseRepository[User]):
    """Repository for User CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        """Find a user by email address.

        Args:
            email: The user's email address.

        Returns:
            The User instance or None.
        """
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ConnectedAccountRepository(BaseRepository[ConnectedAccount]):
    """Repository for ConnectedAccount CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConnectedAccount)

    async def get_by_user_and_provider(
        self, user_id: uuid.UUID, provider: str, email_address: str
    ) -> ConnectedAccount | None:
        """Find a connected account by user, provider, and email.

        Args:
            user_id: The user's UUID.
            provider: The email provider (gmail, microsoft).
            email_address: The connected email address.

        Returns:
            The ConnectedAccount instance or None.
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.email_address == email_address,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: uuid.UUID) -> Sequence[ConnectedAccount]:
        """List all connected accounts for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Sequence of ConnectedAccount instances.
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # Keep list_by_user as alias for backward compatibility
    async def list_by_user(self, user_id: uuid.UUID) -> Sequence[ConnectedAccount]:
        """Alias for get_by_user. List all connected accounts for a user."""
        return await self.get_by_user(user_id)

    async def update_tokens(
        self,
        account_id: uuid.UUID,
        encrypted_access_token: bytes,
        encrypted_refresh_token: bytes,
        token_expires_at: datetime,
    ) -> ConnectedAccount | None:
        """Update OAuth tokens for a connected account.

        Args:
            account_id: The connected account UUID.
            encrypted_access_token: AES-256 encrypted access token.
            encrypted_refresh_token: AES-256 encrypted refresh token.
            token_expires_at: Token expiration timestamp.

        Returns:
            The updated ConnectedAccount instance or None if not found.
        """
        return await self.update(
            account_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            token_expires_at=token_expires_at,
        )

    async def update_status(
        self, account_id: uuid.UUID, status: str
    ) -> ConnectedAccount | None:
        """Update the connection status of an account.

        Args:
            account_id: The connected account UUID.
            status: New status value (e.g., 'connected', 'disconnected', 'pending').

        Returns:
            The updated ConnectedAccount instance or None if not found.
        """
        return await self.update(account_id, status=status)

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        """Delete all connected accounts for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Number of deleted records.
        """
        stmt = delete(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount


class ProcessedEmailRepository(BaseRepository[ProcessedEmail]):
    """Repository for ProcessedEmail CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ProcessedEmail)

    async def get_by_provider_message_id(
        self, provider_message_id: str
    ) -> ProcessedEmail | None:
        """Find a processed email by provider message ID (for deduplication).

        Args:
            provider_message_id: The unique message ID from the email provider.

        Returns:
            The ProcessedEmail instance or None.
        """
        stmt = select(ProcessedEmail).where(
            ProcessedEmail.provider_message_id == provider_message_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
        category: str | None = None,
        priority: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[ProcessedEmail]:
        """List processed emails for a user with filtering and pagination.

        Args:
            user_id: The user's UUID.
            offset: Number of records to skip.
            limit: Maximum number of records to return (max 100).
            category: Optional category filter.
            priority: Optional priority filter.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Sequence of ProcessedEmail instances sorted by processing_timestamp desc.
        """
        limit = min(limit, 100)
        stmt = (
            select(ProcessedEmail)
            .where(ProcessedEmail.user_id == user_id)
            .order_by(ProcessedEmail.processing_timestamp.desc())
        )

        if category is not None:
            stmt = stmt.where(ProcessedEmail.category == category)
        if priority is not None:
            stmt = stmt.where(ProcessedEmail.priority == priority)
        if date_from is not None:
            stmt = stmt.where(ProcessedEmail.processing_timestamp >= date_from)
        if date_to is not None:
            stmt = stmt.where(ProcessedEmail.processing_timestamp <= date_to)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: uuid.UUID,
        category: str | None = None,
        priority: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        """Count processed emails for a user with optional filtering.

        Args:
            user_id: The user's UUID.
            category: Optional category filter.
            priority: Optional priority filter.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Total count of matching records.
        """
        stmt = (
            select(func.count())
            .select_from(ProcessedEmail)
            .where(ProcessedEmail.user_id == user_id)
        )

        if category is not None:
            stmt = stmt.where(ProcessedEmail.category == category)
        if priority is not None:
            stmt = stmt.where(ProcessedEmail.priority == priority)
        if date_from is not None:
            stmt = stmt.where(ProcessedEmail.processing_timestamp >= date_from)
        if date_to is not None:
            stmt = stmt.where(ProcessedEmail.processing_timestamp <= date_to)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def is_duplicate(self, provider_message_id: str) -> bool:
        """Check if an email with the given provider message ID already exists.

        Args:
            provider_message_id: The unique message ID from the email provider.

        Returns:
            True if a record with this provider_message_id exists, False otherwise.
        """
        existing = await self.get_by_provider_message_id(provider_message_id)
        return existing is not None

    async def update_classification(
        self,
        email_id: uuid.UUID,
        category: str,
        priority: str,
        confidence: float,
        flagged_for_review: bool = False,
    ) -> ProcessedEmail | None:
        """Update classification fields for a processed email.

        Args:
            email_id: The processed email UUID.
            category: Assigned category (e.g., 'Urgent', 'Informative').
            priority: Assigned priority (e.g., 'High', 'Medium', 'Low').
            confidence: Classification confidence score (0.0 to 1.0).
            flagged_for_review: Whether to flag for manual review.

        Returns:
            The updated ProcessedEmail instance or None if not found.
        """
        return await self.update(
            email_id,
            category=category,
            priority=priority,
            confidence=confidence,
            flagged_for_review=flagged_for_review,
        )

    async def update_summary(
        self,
        email_id: uuid.UUID,
        summary: str,
        action_items: list | None = None,
        summary_is_fallback: bool = False,
    ) -> ProcessedEmail | None:
        """Update summary fields for a processed email.

        Args:
            email_id: The processed email UUID.
            summary: The generated summary text.
            action_items: Extracted action items list.
            summary_is_fallback: Whether the summary is a fallback.

        Returns:
            The updated ProcessedEmail instance or None if not found.
        """
        return await self.update(
            email_id,
            summary=summary,
            action_items=action_items or [],
            summary_is_fallback=summary_is_fallback,
        )

    async def update_workflow_stage(
        self, email_id: uuid.UUID, workflow_stage: str, error_message: str | None = None
    ) -> ProcessedEmail | None:
        """Update the workflow stage for a processed email.

        Args:
            email_id: The processed email UUID.
            workflow_stage: New workflow stage value.
            error_message: Optional error message if stage is 'failed'.

        Returns:
            The updated ProcessedEmail instance or None if not found.
        """
        kwargs: dict[str, Any] = {"workflow_stage": workflow_stage}
        if error_message is not None:
            kwargs["error_message"] = error_message
        return await self.update(email_id, **kwargs)

    async def list_flagged_for_review(
        self, user_id: uuid.UUID, offset: int = 0, limit: int = 20
    ) -> Sequence[ProcessedEmail]:
        """List emails flagged for manual review.

        Args:
            user_id: The user's UUID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of flagged ProcessedEmail instances.
        """
        stmt = (
            select(ProcessedEmail)
            .where(
                ProcessedEmail.user_id == user_id,
                ProcessedEmail.flagged_for_review == True,  # noqa: E712
            )
            .order_by(ProcessedEmail.processing_timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        """Delete all processed emails for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Number of deleted records.
        """
        stmt = delete(ProcessedEmail).where(ProcessedEmail.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.rowcount


class DraftReplyRepository(BaseRepository[DraftReply]):
    """Repository for DraftReply CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, DraftReply)

    async def get_by_email_id(self, email_id: uuid.UUID) -> DraftReply | None:
        """Get the draft reply for a processed email.

        Args:
            email_id: The processed email UUID.

        Returns:
            The DraftReply instance or None.
        """
        stmt = select(DraftReply).where(DraftReply.email_id == email_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        draft_id: uuid.UUID,
        status: str,
        actioned_at: datetime | None = None,
        edited_body: str | None = None,
        edited_subject: str | None = None,
        send_error: str | None = None,
    ) -> DraftReply | None:
        """Update the status and optional fields of a draft reply.

        Args:
            draft_id: The draft reply UUID.
            status: New status value (pending, approved, rejected, sent, send_failed).
            actioned_at: Timestamp when the action was performed.
            edited_body: Optional edited body text.
            edited_subject: Optional edited subject line.
            send_error: Optional send error message.

        Returns:
            The updated DraftReply instance or None if not found.
        """
        kwargs: dict[str, Any] = {"status": status}
        if actioned_at is not None:
            kwargs["actioned_at"] = actioned_at
        if edited_body is not None:
            kwargs["edited_body"] = edited_body
        if edited_subject is not None:
            kwargs["edited_subject"] = edited_subject
        if send_error is not None:
            kwargs["send_error"] = send_error
        return await self.update(draft_id, **kwargs)

    async def get_pending_by_user(
        self, user_id: uuid.UUID, offset: int = 0, limit: int = 20
    ) -> Sequence[DraftReply]:
        """List pending draft replies for a user (via their processed emails).

        Args:
            user_id: The user's UUID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of pending DraftReply instances for the given user.
        """
        stmt = (
            select(DraftReply)
            .join(ProcessedEmail, DraftReply.email_id == ProcessedEmail.id)
            .where(
                ProcessedEmail.user_id == user_id,
                DraftReply.status == "pending",
            )
            .order_by(DraftReply.generated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_pending(
        self, offset: int = 0, limit: int = 20
    ) -> Sequence[DraftReply]:
        """List draft replies with pending status.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of pending DraftReply instances.
        """
        stmt = (
            select(DraftReply)
            .where(DraftReply.status == "pending")
            .order_by(DraftReply.generated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class AccessLogRepository(BaseRepository[AccessLog]):
    """Repository for AccessLog CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AccessLog)

    async def list_by_time_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[AccessLog]:
        """List access logs within a time range.

        Args:
            start: Optional start timestamp.
            end: Optional end timestamp.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of AccessLog instances.
        """
        stmt = select(AccessLog).order_by(AccessLog.timestamp.desc())

        if start is not None:
            stmt = stmt.where(AccessLog.timestamp >= start)
        if end is not None:
            stmt = stmt.where(AccessLog.timestamp <= end)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class WorkflowExecutionRepository(BaseRepository[WorkflowExecution]):
    """Repository for WorkflowExecution CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowExecution)

    async def get_by_email_id(
        self, email_id: uuid.UUID
    ) -> WorkflowExecution | None:
        """Get the workflow execution for a processed email.

        Args:
            email_id: The processed email UUID.

        Returns:
            The WorkflowExecution instance or None.
        """
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.email_id == email_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_stage(
        self,
        workflow_id: uuid.UUID,
        current_stage: str,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> WorkflowExecution | None:
        """Update the current stage of a workflow execution.

        Args:
            workflow_id: The workflow execution UUID.
            current_stage: New stage value.
            completed_at: Optional completion timestamp.
            error_message: Optional error message if stage is 'failed'.

        Returns:
            The updated WorkflowExecution instance or None if not found.
        """
        kwargs: dict[str, Any] = {"current_stage": current_stage}
        if completed_at is not None:
            kwargs["completed_at"] = completed_at
        if error_message is not None:
            kwargs["error_message"] = error_message
        return await self.update(workflow_id, **kwargs)

    async def update_retry_count(
        self, workflow_id: uuid.UUID, retry_counts: dict[str, int]
    ) -> WorkflowExecution | None:
        """Update the retry counts for a workflow execution.

        Args:
            workflow_id: The workflow execution UUID.
            retry_counts: Dictionary mapping agent names to their retry counts.

        Returns:
            The updated WorkflowExecution instance or None if not found.
        """
        return await self.update(workflow_id, retry_counts=retry_counts)

    async def list_active(
        self, offset: int = 0, limit: int = 20
    ) -> Sequence[WorkflowExecution]:
        """List active (non-completed) workflow executions.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of active WorkflowExecution instances.
        """
        stmt = (
            select(WorkflowExecution)
            .where(WorkflowExecution.completed_at == None)  # noqa: E711
            .order_by(WorkflowExecution.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
