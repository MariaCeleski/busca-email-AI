"""Unit tests for Pydantic data models and enums."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models import (
    AccountStatus,
    AttachmentMetadata,
    ClassificationResult,
    ConnectedAccount,
    DraftReply,
    DraftStatus,
    EmailCategory,
    EmailMetadata,
    EmailProcessingResult,
    ErrorResponse,
    FieldError,
    MetadataFilter,
    PaginatedResponse,
    PriorityLevel,
    RawEmail,
    ReplyAction,
    SearchResult,
    SummaryResult,
    TokenPair,
    WorkflowStage,
    WorkflowState,
)


# --- Enum Tests ---


class TestEmailCategory:
    def test_all_values_exist(self):
        assert EmailCategory.URGENT == "Urgent"
        assert EmailCategory.INFORMATIVE == "Informative"
        assert EmailCategory.PROMOTIONAL == "Promotional"
        assert EmailCategory.SPAM == "Spam"
        assert EmailCategory.TRANSACTIONAL == "Transactional"
        assert EmailCategory.PERSONAL == "Personal"

    def test_is_str_enum(self):
        assert isinstance(EmailCategory.URGENT, str)

    def test_has_six_members(self):
        assert len(EmailCategory) == 6


class TestPriorityLevel:
    def test_all_values_exist(self):
        assert PriorityLevel.HIGH == "High"
        assert PriorityLevel.MEDIUM == "Medium"
        assert PriorityLevel.LOW == "Low"

    def test_has_three_members(self):
        assert len(PriorityLevel) == 3


class TestDraftStatus:
    def test_all_values_exist(self):
        assert DraftStatus.PENDING == "pending"
        assert DraftStatus.APPROVED == "approved"
        assert DraftStatus.REJECTED == "rejected"
        assert DraftStatus.SENT == "sent"
        assert DraftStatus.SEND_FAILED == "send_failed"

    def test_has_five_members(self):
        assert len(DraftStatus) == 5


class TestWorkflowStage:
    def test_all_values_exist(self):
        assert WorkflowStage.QUEUED == "queued"
        assert WorkflowStage.CLASSIFYING == "classifying"
        assert WorkflowStage.SUMMARIZING == "summarizing"
        assert WorkflowStage.GENERATING_REPLY == "generating_reply"
        assert WorkflowStage.COMPLETED == "completed"
        assert WorkflowStage.FAILED == "failed"
        assert WorkflowStage.MANUAL_REVIEW == "manual_review"

    def test_has_seven_members(self):
        assert len(WorkflowStage) == 7


class TestAccountStatus:
    def test_all_values_exist(self):
        assert AccountStatus.CONNECTED == "connected"
        assert AccountStatus.DISCONNECTED == "disconnected"
        assert AccountStatus.PENDING == "pending"

    def test_has_three_members(self):
        assert len(AccountStatus) == 3


# --- Schema Tests ---


class TestClassificationResult:
    def test_valid_confidence(self):
        result = ClassificationResult(
            category=EmailCategory.URGENT,
            priority=PriorityLevel.HIGH,
            confidence=0.85,
            requires_response=True,
            requires_summary=False,
        )
        assert result.confidence == 0.85

    def test_confidence_at_zero(self):
        result = ClassificationResult(
            category=EmailCategory.SPAM,
            priority=PriorityLevel.LOW,
            confidence=0.0,
            requires_response=False,
            requires_summary=False,
        )
        assert result.confidence == 0.0

    def test_confidence_at_one(self):
        result = ClassificationResult(
            category=EmailCategory.PERSONAL,
            priority=PriorityLevel.HIGH,
            confidence=1.0,
            requires_response=True,
            requires_summary=True,
        )
        assert result.confidence == 1.0

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ClassificationResult(
                category=EmailCategory.URGENT,
                priority=PriorityLevel.HIGH,
                confidence=1.1,
                requires_response=True,
                requires_summary=False,
            )
        assert "confidence" in str(exc_info.value)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ClassificationResult(
                category=EmailCategory.URGENT,
                priority=PriorityLevel.HIGH,
                confidence=-0.1,
                requires_response=True,
                requires_summary=False,
            )
        assert "confidence" in str(exc_info.value)

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                category="InvalidCategory",
                priority=PriorityLevel.HIGH,
                confidence=0.9,
                requires_response=True,
                requires_summary=False,
            )

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                category=EmailCategory.URGENT,
                priority="Critical",
                confidence=0.9,
                requires_response=True,
                requires_summary=False,
            )

    def test_json_serialization(self):
        result = ClassificationResult(
            category=EmailCategory.INFORMATIVE,
            priority=PriorityLevel.MEDIUM,
            confidence=0.72,
            requires_response=False,
            requires_summary=True,
            flagged_for_review=True,
        )
        data = result.model_dump()
        assert data["category"] == "Informative"
        assert data["priority"] == "Medium"
        assert data["confidence"] == 0.72
        assert data["flagged_for_review"] is True


class TestDraftReply:
    def _make_draft(self, reply_body: str = "Hello", subject: str = "Re: Test"):
        return DraftReply(
            reply_body=reply_body,
            suggested_subject=subject,
            referenced_email_ids=[],
            generated_at=datetime.now(tz=timezone.utc),
        )

    def test_valid_draft(self):
        draft = self._make_draft("Short reply body.")
        assert draft.reply_body == "Short reply body."
        assert draft.status == DraftStatus.PENDING

    def test_reply_body_at_500_words(self):
        body = " ".join(["word"] * 500)
        draft = self._make_draft(body)
        assert len(draft.reply_body.split()) == 500

    def test_reply_body_over_500_words_rejected(self):
        body = " ".join(["a"] * 501)
        with pytest.raises(ValidationError) as exc_info:
            self._make_draft(body)
        assert "500 words" in str(exc_info.value)

    def test_reply_body_over_2500_chars_rejected(self):
        """reply_body max_length is 2500 characters."""
        body = "x" * 2501
        with pytest.raises(ValidationError) as exc_info:
            self._make_draft(body)
        assert "reply_body" in str(exc_info.value)

    def test_suggested_subject_at_150_chars(self):
        subject = "a" * 150
        draft = self._make_draft(subject=subject)
        assert len(draft.suggested_subject) == 150

    def test_suggested_subject_over_150_chars_rejected(self):
        subject = "a" * 151
        with pytest.raises(ValidationError) as exc_info:
            self._make_draft(subject=subject)
        assert "suggested_subject" in str(exc_info.value)

    def test_empty_reply_body_accepted(self):
        """An empty body has 0 words, which is <= 500."""
        draft = self._make_draft("")
        assert draft.reply_body == ""


class TestSummaryResult:
    def test_valid_summary(self):
        result = SummaryResult(
            summary="This is a summary.",
            action_items=["Do X", "Do Y"],
        )
        assert result.summary == "This is a summary."
        assert len(result.action_items) == 2

    def test_action_items_at_max_10(self):
        items = [f"Item {i}" for i in range(10)]
        result = SummaryResult(summary="Summary.", action_items=items)
        assert len(result.action_items) == 10

    def test_action_items_over_10_rejected(self):
        items = [f"Item {i}" for i in range(11)]
        with pytest.raises(ValidationError) as exc_info:
            SummaryResult(summary="Summary.", action_items=items)
        assert "action_items" in str(exc_info.value)

    def test_default_values(self):
        result = SummaryResult(summary="Just a summary.")
        assert result.action_items == []
        assert result.is_fallback is False
        assert result.no_content is False


class TestReplyAction:
    def test_valid_approve(self):
        action = ReplyAction(action="approve")
        assert action.action == "approve"
        assert action.edited_body is None
        assert action.edited_subject is None

    def test_edited_body_at_max(self):
        body = "x" * 10000
        action = ReplyAction(action="approve", edited_body=body)
        assert len(action.edited_body) == 10000

    def test_edited_body_over_max_rejected(self):
        body = "x" * 10001
        with pytest.raises(ValidationError) as exc_info:
            ReplyAction(action="approve", edited_body=body)
        assert "edited_body" in str(exc_info.value)

    def test_edited_subject_at_max(self):
        subject = "s" * 255
        action = ReplyAction(action="approve", edited_subject=subject)
        assert len(action.edited_subject) == 255

    def test_edited_subject_over_max_rejected(self):
        subject = "s" * 256
        with pytest.raises(ValidationError) as exc_info:
            ReplyAction(action="approve", edited_subject=subject)
        assert "edited_subject" in str(exc_info.value)


class TestRawEmail:
    def test_valid_email(self):
        email = RawEmail(
            provider_message_id="msg-123",
            sender="alice@example.com",
            subject="Hello",
            body="Hi there!",
            timestamp=datetime.now(tz=timezone.utc),
            provider="gmail",
        )
        assert email.provider_message_id == "msg-123"
        assert email.attachments == []
        assert email.thread_id is None

    def test_email_with_attachments(self):
        email = RawEmail(
            provider_message_id="msg-456",
            sender="bob@example.com",
            subject="Document",
            body="See attached.",
            timestamp=datetime.now(tz=timezone.utc),
            attachments=[
                AttachmentMetadata(
                    file_name="report.pdf",
                    file_size=1024,
                    mime_type="application/pdf",
                )
            ],
            provider="microsoft",
        )
        assert len(email.attachments) == 1
        assert email.attachments[0].file_name == "report.pdf"


class TestWorkflowState:
    def test_valid_workflow(self):
        state = WorkflowState(
            email_id="email-1",
            workflow_id="wf-1",
            current_stage=WorkflowStage.CLASSIFYING,
            started_at=datetime.now(tz=timezone.utc),
        )
        assert state.current_stage == WorkflowStage.CLASSIFYING
        assert state.classification is None
        assert state.retry_counts == {}


class TestPaginatedResponse:
    def test_valid_response(self):
        resp = PaginatedResponse(
            items=["a", "b", "c"],
            total=10,
            page=1,
            page_size=3,
            total_pages=4,
        )
        assert len(resp.items) == 3
        assert resp.total_pages == 4


class TestTokenPair:
    def test_valid_token_pair(self):
        tp = TokenPair(
            access_token="access123",
            refresh_token="refresh456",
            expires_at=datetime.now(tz=timezone.utc),
            provider="gmail",
        )
        assert tp.provider == "gmail"


class TestConnectedAccount:
    def test_valid_account(self):
        account = ConnectedAccount(
            user_id="user-1",
            provider="gmail",
            email_address="user@gmail.com",
            status=AccountStatus.CONNECTED,
            connected_at=datetime.now(tz=timezone.utc),
        )
        assert account.status == AccountStatus.CONNECTED
        assert account.last_sync is None


class TestErrorResponse:
    def test_error_with_field_errors(self):
        err = ErrorResponse(
            error="validation_error",
            detail="Validation failed",
            field_errors=[
                FieldError(field="email", message="Invalid format"),
                FieldError(field="name", message="Required"),
            ],
        )
        assert len(err.field_errors) == 2
        assert err.field_errors[0].field == "email"
        assert err.error == "validation_error"

    def test_error_without_field_errors(self):
        err = ErrorResponse(
            error="not_found",
            detail="Resource not found",
        )
        assert err.field_errors is None
        assert err.error == "not_found"
        assert err.detail == "Resource not found"
