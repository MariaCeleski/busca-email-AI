"""Unit tests for SQLAlchemy ORM models and repository CRUD operations.

Tests use an in-memory SQLite database for speed and isolation.
Note: PostgreSQL-specific features (JSONB, partial indexes) are not tested
at the unit level — those are covered by integration tests against a real PG instance.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine as sa_create_engine, event, JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.models.database import Base
from src.models.orm import (
    AccessLog,
    ConnectedAccount,
    DraftReply,
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


@pytest.fixture
async def async_session():
    """Create an in-memory SQLite async session for testing.
    
    Replaces JSONB columns with JSON for SQLite compatibility.
    """
    from sqlalchemy.dialects.postgresql import JSONB

    # Monkey-patch JSONB to use JSON for SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Replace JSONB with JSON in the metadata for SQLite compatibility
    from sqlalchemy import MetaData, Table, Column
    from copy import deepcopy

    async with engine.begin() as conn:
        # Create tables using raw SQL that avoids JSONB
        await conn.run_sync(_create_tables_sqlite)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


def _create_tables_sqlite(connection):
    """Create all tables with JSONB replaced by JSON for SQLite compatibility."""
    from sqlalchemy import MetaData, inspect
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    # Temporarily swap JSONB columns to JSON type for table creation
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, PG_JSONB):
                column.type = JSON()

    Base.metadata.create_all(connection)

    # Restore JSONB type for the actual ORM mappings (not critical for tests)
    # The columns in the ORM class still reference JSONB but SQLite will use JSON storage


@pytest.fixture
async def sample_user(async_session: AsyncSession) -> User:
    """Create a sample user for testing."""
    user = User(id=uuid.uuid4(), email="test@example.com")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def sample_email(async_session: AsyncSession, sample_user: User) -> ProcessedEmail:
    """Create a sample processed email for testing."""
    email = ProcessedEmail(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        provider_message_id="msg-001",
        sender="sender@example.com",
        subject="Test Subject",
        body="Test email body content.",
        timestamp=datetime.now(timezone.utc),
        provider="gmail",
        category="Urgent",
        priority="High",
        confidence=0.95,
        flagged_for_review=False,
    )
    async_session.add(email)
    await async_session.commit()
    await async_session.refresh(email)
    return email


# --- ORM Model Tests ---


class TestUserModel:
    """Tests for the User ORM model."""

    async def test_create_user(self, async_session: AsyncSession):
        user = User(id=uuid.uuid4(), email="user@test.com")
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        assert user.email == "user@test.com"
        assert user.id is not None
        assert user.created_at is not None

    async def test_user_email_uniqueness(self, async_session: AsyncSession, sample_user: User):
        """Duplicate emails should fail uniqueness constraint."""
        from sqlalchemy.exc import IntegrityError

        duplicate = User(id=uuid.uuid4(), email=sample_user.email)
        async_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestConnectedAccountModel:
    """Tests for the ConnectedAccount ORM model."""

    async def test_create_connected_account(self, async_session: AsyncSession, sample_user: User):
        account = ConnectedAccount(
            id=uuid.uuid4(),
            user_id=sample_user.id,
            provider="gmail",
            email_address="user@gmail.com",
            encrypted_access_token=b"encrypted_token",
            encrypted_refresh_token=b"encrypted_refresh",
            status="connected",
        )
        async_session.add(account)
        await async_session.commit()
        await async_session.refresh(account)

        assert account.provider == "gmail"
        assert account.email_address == "user@gmail.com"
        assert account.status == "connected"
        assert account.connected_at is not None


class TestProcessedEmailModel:
    """Tests for the ProcessedEmail ORM model."""

    async def test_create_processed_email(self, async_session: AsyncSession, sample_user: User):
        email = ProcessedEmail(
            id=uuid.uuid4(),
            user_id=sample_user.id,
            provider_message_id="unique-msg-id-123",
            sender="someone@example.com",
            subject="Hello",
            body="World",
            timestamp=datetime.now(timezone.utc),
            provider="gmail",
        )
        async_session.add(email)
        await async_session.commit()
        await async_session.refresh(email)

        assert email.sender == "someone@example.com"
        assert email.workflow_stage == "queued"
        assert email.flagged_for_review is False

    async def test_provider_message_id_uniqueness(
        self, async_session: AsyncSession, sample_email: ProcessedEmail, sample_user: User
    ):
        """Duplicate provider_message_id should fail."""
        from sqlalchemy.exc import IntegrityError

        duplicate = ProcessedEmail(
            id=uuid.uuid4(),
            user_id=sample_user.id,
            provider_message_id=sample_email.provider_message_id,
            sender="other@example.com",
            timestamp=datetime.now(timezone.utc),
            provider="gmail",
        )
        async_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestDraftReplyModel:
    """Tests for the DraftReply ORM model."""

    async def test_create_draft_reply(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        draft = DraftReply(
            id=uuid.uuid4(),
            email_id=sample_email.id,
            reply_body="Thank you for your email.",
            suggested_subject="Re: Test Subject",
            status="pending",
        )
        async_session.add(draft)
        await async_session.commit()
        await async_session.refresh(draft)

        assert draft.reply_body == "Thank you for your email."
        assert draft.status == "pending"
        assert draft.generated_at is not None


class TestAccessLogModel:
    """Tests for the AccessLog ORM model."""

    async def test_create_access_log(self, async_session: AsyncSession):
        log = AccessLog(
            id=1,  # SQLite doesn't auto-generate BIGSERIAL
            requester_id="user-123",
            endpoint="/api/v1/emails",
            method="GET",
            response_status=200,
        )
        async_session.add(log)
        await async_session.commit()
        await async_session.refresh(log)

        assert log.id is not None
        assert log.requester_id == "user-123"
        assert log.endpoint == "/api/v1/emails"
        assert log.timestamp is not None


class TestWorkflowExecutionModel:
    """Tests for the WorkflowExecution ORM model."""

    async def test_create_workflow_execution(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        workflow = WorkflowExecution(
            id=uuid.uuid4(),
            email_id=sample_email.id,
            current_stage="classifying",
        )
        async_session.add(workflow)
        await async_session.commit()
        await async_session.refresh(workflow)

        assert workflow.current_stage == "classifying"
        assert workflow.started_at is not None
        assert workflow.completed_at is None


# --- Repository Tests ---


class TestUserRepository:
    """Tests for UserRepository CRUD operations."""

    async def test_create_user(self, async_session: AsyncSession):
        repo = UserRepository(async_session)
        user = await repo.create(email="new@example.com")
        assert user.email == "new@example.com"
        assert user.id is not None

    async def test_get_by_id(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        found = await repo.get_by_id(sample_user.id)
        assert found is not None
        assert found.email == sample_user.email

    async def test_get_by_id_not_found(self, async_session: AsyncSession):
        repo = UserRepository(async_session)
        found = await repo.get_by_id(uuid.uuid4())
        assert found is None

    async def test_get_by_email(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        found = await repo.get_by_email("test@example.com")
        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_email_not_found(self, async_session: AsyncSession):
        repo = UserRepository(async_session)
        found = await repo.get_by_email("nonexistent@example.com")
        assert found is None

    async def test_list_users(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        users = await repo.list()
        assert len(users) >= 1

    async def test_update_user(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        updated = await repo.update(sample_user.id, email="updated@example.com")
        assert updated is not None
        assert updated.email == "updated@example.com"

    async def test_delete_user(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        deleted = await repo.delete(sample_user.id)
        assert deleted is True
        assert await repo.get_by_id(sample_user.id) is None

    async def test_delete_user_not_found(self, async_session: AsyncSession):
        repo = UserRepository(async_session)
        deleted = await repo.delete(uuid.uuid4())
        assert deleted is False

    async def test_count(self, async_session: AsyncSession, sample_user: User):
        repo = UserRepository(async_session)
        count = await repo.count()
        assert count >= 1


class TestProcessedEmailRepository:
    """Tests for ProcessedEmailRepository operations."""

    async def test_get_by_provider_message_id(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        found = await repo.get_by_provider_message_id("msg-001")
        assert found is not None
        assert found.id == sample_email.id

    async def test_get_by_provider_message_id_not_found(self, async_session: AsyncSession):
        repo = ProcessedEmailRepository(async_session)
        found = await repo.get_by_provider_message_id("nonexistent")
        assert found is None

    async def test_is_duplicate_true(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        assert await repo.is_duplicate("msg-001") is True

    async def test_is_duplicate_false(self, async_session: AsyncSession):
        repo = ProcessedEmailRepository(async_session)
        assert await repo.is_duplicate("nonexistent-msg") is False

    async def test_list_by_user(self, async_session: AsyncSession, sample_email: ProcessedEmail, sample_user: User):
        repo = ProcessedEmailRepository(async_session)
        emails = await repo.list_by_user(sample_user.id)
        assert len(emails) >= 1
        assert emails[0].id == sample_email.id

    async def test_list_by_user_with_category_filter(
        self, async_session: AsyncSession, sample_email: ProcessedEmail, sample_user: User
    ):
        repo = ProcessedEmailRepository(async_session)
        emails = await repo.list_by_user(sample_user.id, category="Urgent")
        assert len(emails) >= 1

        emails = await repo.list_by_user(sample_user.id, category="Spam")
        assert len(emails) == 0

    async def test_list_by_user_respects_limit(
        self, async_session: AsyncSession, sample_user: User
    ):
        repo = ProcessedEmailRepository(async_session)
        # Create multiple emails
        for i in range(5):
            await repo.create(
                user_id=sample_user.id,
                provider_message_id=f"msg-limit-{i}",
                sender="sender@example.com",
                timestamp=datetime.now(timezone.utc),
                provider="gmail",
            )
        await async_session.commit()

        emails = await repo.list_by_user(sample_user.id, limit=3)
        assert len(emails) == 3

    async def test_count_by_user(self, async_session: AsyncSession, sample_email: ProcessedEmail, sample_user: User):
        repo = ProcessedEmailRepository(async_session)
        count = await repo.count_by_user(sample_user.id)
        assert count >= 1

    async def test_update_classification(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        updated = await repo.update_classification(
            sample_email.id,
            category="Spam",
            priority="Low",
            confidence=0.85,
            flagged_for_review=True,
        )
        assert updated is not None
        assert updated.category == "Spam"
        assert updated.priority == "Low"
        assert updated.confidence == 0.85
        assert updated.flagged_for_review is True

    async def test_update_summary(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        updated = await repo.update_summary(
            sample_email.id,
            summary="This is a short summary.",
            action_items=["Action 1", "Action 2"],
            summary_is_fallback=False,
        )
        assert updated is not None
        assert updated.summary == "This is a short summary."
        assert updated.summary_is_fallback is False

    async def test_update_workflow_stage(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        updated = await repo.update_workflow_stage(
            sample_email.id, workflow_stage="completed"
        )
        assert updated is not None
        assert updated.workflow_stage == "completed"

    async def test_update_workflow_stage_with_error(
        self, async_session: AsyncSession, sample_email: ProcessedEmail
    ):
        repo = ProcessedEmailRepository(async_session)
        updated = await repo.update_workflow_stage(
            sample_email.id,
            workflow_stage="failed",
            error_message="Agent timeout",
        )
        assert updated is not None
        assert updated.workflow_stage == "failed"
        assert updated.error_message == "Agent timeout"


class TestDraftReplyRepository:
    """Tests for DraftReplyRepository operations."""

    async def test_get_by_email_id(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = DraftReplyRepository(async_session)
        draft = await repo.create(
            email_id=sample_email.id,
            reply_body="Thank you!",
            suggested_subject="Re: Test",
            status="pending",
        )
        await async_session.commit()

        found = await repo.get_by_email_id(sample_email.id)
        assert found is not None
        assert found.id == draft.id

    async def test_list_pending(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = DraftReplyRepository(async_session)
        await repo.create(
            email_id=sample_email.id,
            reply_body="Draft reply body",
            status="pending",
        )
        await async_session.commit()

        pending = await repo.list_pending()
        assert len(pending) >= 1
        assert all(d.status == "pending" for d in pending)

    async def test_update_status(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = DraftReplyRepository(async_session)
        draft = await repo.create(
            email_id=sample_email.id,
            reply_body="Reply text",
            status="pending",
        )
        await async_session.commit()

        actioned_time = datetime.now(timezone.utc)
        updated = await repo.update_status(
            draft.id,
            status="approved",
            actioned_at=actioned_time,
        )
        assert updated is not None
        assert updated.status == "approved"
        # SQLite strips timezone info, so compare without tzinfo
        assert updated.actioned_at.replace(tzinfo=None) == actioned_time.replace(tzinfo=None)

    async def test_update_status_with_edit(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = DraftReplyRepository(async_session)
        draft = await repo.create(
            email_id=sample_email.id,
            reply_body="Original reply",
            suggested_subject="Re: Original",
            status="pending",
        )
        await async_session.commit()

        updated = await repo.update_status(
            draft.id,
            status="approved",
            actioned_at=datetime.now(timezone.utc),
            edited_body="Edited reply body",
            edited_subject="Re: Edited Subject",
        )
        assert updated is not None
        assert updated.edited_body == "Edited reply body"
        assert updated.edited_subject == "Re: Edited Subject"

    async def test_update_status_with_send_error(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = DraftReplyRepository(async_session)
        draft = await repo.create(
            email_id=sample_email.id,
            reply_body="Reply",
            status="pending",
        )
        await async_session.commit()

        updated = await repo.update_status(
            draft.id,
            status="send_failed",
            send_error="SMTP connection timeout",
        )
        assert updated is not None
        assert updated.status == "send_failed"
        assert updated.send_error == "SMTP connection timeout"

    async def test_get_pending_by_user(self, async_session: AsyncSession, sample_email: ProcessedEmail, sample_user: User):
        repo = DraftReplyRepository(async_session)
        await repo.create(
            email_id=sample_email.id,
            reply_body="Pending draft",
            status="pending",
        )
        await async_session.commit()

        pending = await repo.get_pending_by_user(sample_user.id)
        assert len(pending) >= 1
        assert all(d.status == "pending" for d in pending)


class TestAccessLogRepository:
    """Tests for AccessLogRepository operations."""

    async def test_create_and_list(self, async_session: AsyncSession):
        repo = AccessLogRepository(async_session)
        log = AccessLog(
            id=1,  # SQLite doesn't auto-generate BIGSERIAL
            requester_id="user-1",
            endpoint="/api/v1/emails",
            method="GET",
            response_status=200,
        )
        async_session.add(log)
        await async_session.flush()
        await async_session.refresh(log)
        await async_session.commit()

        logs = await repo.list_by_time_range()
        assert len(logs) >= 1
        assert logs[0].requester_id == "user-1"


class TestConnectedAccountRepository:
    """Tests for ConnectedAccountRepository operations."""

    async def test_get_by_user(self, async_session: AsyncSession, sample_user: User):
        repo = ConnectedAccountRepository(async_session)
        await repo.create(
            user_id=sample_user.id,
            provider="gmail",
            email_address="user@gmail.com",
            encrypted_access_token=b"token",
            encrypted_refresh_token=b"refresh",
            status="connected",
        )
        await async_session.commit()

        accounts = await repo.get_by_user(sample_user.id)
        assert len(accounts) >= 1
        assert accounts[0].provider == "gmail"

    async def test_update_tokens(self, async_session: AsyncSession, sample_user: User):
        repo = ConnectedAccountRepository(async_session)
        account = await repo.create(
            user_id=sample_user.id,
            provider="gmail",
            email_address="user@gmail.com",
            encrypted_access_token=b"old_token",
            encrypted_refresh_token=b"old_refresh",
            status="connected",
        )
        await async_session.commit()

        new_expires = datetime.now(timezone.utc)
        updated = await repo.update_tokens(
            account.id,
            encrypted_access_token=b"new_token",
            encrypted_refresh_token=b"new_refresh",
            token_expires_at=new_expires,
        )
        assert updated is not None
        assert updated.encrypted_access_token == b"new_token"
        assert updated.encrypted_refresh_token == b"new_refresh"
        # SQLite strips timezone info, so compare without tzinfo
        assert updated.token_expires_at.replace(tzinfo=None) == new_expires.replace(tzinfo=None)

    async def test_update_status(self, async_session: AsyncSession, sample_user: User):
        repo = ConnectedAccountRepository(async_session)
        account = await repo.create(
            user_id=sample_user.id,
            provider="gmail",
            email_address="user@gmail.com",
            status="connected",
        )
        await async_session.commit()

        updated = await repo.update_status(account.id, status="disconnected")
        assert updated is not None
        assert updated.status == "disconnected"

    async def test_delete_by_user(self, async_session: AsyncSession, sample_user: User):
        repo = ConnectedAccountRepository(async_session)
        await repo.create(
            user_id=sample_user.id,
            provider="gmail",
            email_address="user1@gmail.com",
            status="connected",
        )
        await repo.create(
            user_id=sample_user.id,
            provider="microsoft",
            email_address="user1@outlook.com",
            status="connected",
        )
        await async_session.commit()

        deleted_count = await repo.delete_by_user(sample_user.id)
        assert deleted_count == 2

        accounts = await repo.get_by_user(sample_user.id)
        assert len(accounts) == 0


class TestWorkflowExecutionRepository:
    """Tests for WorkflowExecutionRepository operations."""

    async def test_get_by_email_id(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        wf = await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        found = await repo.get_by_email_id(sample_email.id)
        assert found is not None
        assert found.current_stage == "classifying"

    async def test_list_active(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        active = await repo.list_active()
        assert len(active) >= 1
        assert all(w.completed_at is None for w in active)

    async def test_update_stage(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        wf = await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        updated = await repo.update_stage(wf.id, current_stage="summarizing")
        assert updated is not None
        assert updated.current_stage == "summarizing"

    async def test_update_stage_with_completion(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        wf = await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        completed_time = datetime.now(timezone.utc)
        updated = await repo.update_stage(
            wf.id, current_stage="completed", completed_at=completed_time
        )
        assert updated is not None
        assert updated.current_stage == "completed"
        # SQLite strips timezone info, so compare without tzinfo
        assert updated.completed_at.replace(tzinfo=None) == completed_time.replace(tzinfo=None)

    async def test_update_stage_with_error(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        wf = await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        updated = await repo.update_stage(
            wf.id, current_stage="failed", error_message="Agent timeout"
        )
        assert updated is not None
        assert updated.current_stage == "failed"
        assert updated.error_message == "Agent timeout"

    async def test_update_retry_count(self, async_session: AsyncSession, sample_email: ProcessedEmail):
        repo = WorkflowExecutionRepository(async_session)
        wf = await repo.create(
            email_id=sample_email.id,
            current_stage="classifying",
        )
        await async_session.commit()

        retry_counts = {"classifier": 2, "summarizer": 1}
        updated = await repo.update_retry_count(wf.id, retry_counts=retry_counts)
        assert updated is not None
        assert updated.retry_counts == retry_counts
