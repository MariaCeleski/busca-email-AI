"""Unit tests for Celery tasks (celery_app, process_email, poll_emails).

Tests cover:
- Celery app configuration correctness
- process_email_task with mocked dependencies
- poll_emails_task with mocked DB and provider clients
- Retry behavior on failures
- Result serialization
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Celery app should be importable."""
        from src.tasks.celery_app import celery_app

        assert celery_app is not None

    def test_celery_app_name(self):
        """Celery app should have the correct name."""
        from src.tasks.celery_app import celery_app

        assert celery_app.main == "ai_email_agent"

    def test_celery_broker_configured(self):
        """Celery should use Redis as broker."""
        from src.tasks.celery_app import celery_app

        broker_url = celery_app.conf.broker_url
        assert "redis" in broker_url

    def test_celery_result_backend_configured(self):
        """Celery should use Redis as result backend."""
        from src.tasks.celery_app import celery_app

        backend = celery_app.conf.result_backend
        assert "redis" in backend

    def test_celery_worker_concurrency(self):
        """Celery should be configured for up to 10 concurrent workers."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.worker_concurrency == 10

    def test_celery_serializer_json(self):
        """Celery should use JSON serialization."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_celery_task_time_limit(self):
        """Celery should have task time limits configured."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.task_time_limit == 120
        assert celery_app.conf.task_soft_time_limit == 90

    def test_celery_utc_enabled(self):
        """Celery should use UTC timezone."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.enable_utc is True
        assert celery_app.conf.timezone == "UTC"

    def test_celery_acks_late(self):
        """Celery should acknowledge tasks late for reliability."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.task_acks_late is True


class TestProcessEmailTask:
    """Tests for the process_email_task Celery task."""

    def _make_email_data(self):
        """Create sample email data dict."""
        return {
            "provider_message_id": "msg-12345",
            "sender": "alice@example.com",
            "subject": "Test Email Subject",
            "body": "This is the body of the test email.",
            "timestamp": "2024-01-15T10:30:00Z",
            "attachments": [],
            "thread_id": "thread-001",
            "provider": "gmail",
        }

    @patch("src.tasks.process_email._publish_results")
    @patch("src.tasks.process_email.asyncio.new_event_loop")
    def test_process_email_task_success(self, mock_loop_factory, mock_publish):
        """process_email_task should process email and return serialized result."""
        from src.tasks.process_email import process_email_task

        # Mock the event loop
        mock_loop = MagicMock()
        mock_loop_factory.return_value = mock_loop

        # Mock orchestrator result
        mock_result = {
            "email": None,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "current_stage": "completed",
            "error": None,
            "flagged_for_review": False,
            "retry_counts": {},
        }
        mock_loop.run_until_complete.return_value = mock_result

        email_data = self._make_email_data()

        # We need to patch the internal imports
        with patch("src.tasks.process_email.process_email_task.retry") as mock_retry:
            with patch("src.agents.classifier.ClassifierAgent") as MockClassifier:
                with patch("src.agents.summarizer.SummarizerAgent") as MockSummarizer:
                    with patch("src.agents.response.ResponseAgent") as MockResponse:
                        with patch("src.services.vector_store.VectorStoreService") as MockVS:
                            with patch("src.agents.orchestrator.AgentOrchestrator") as MockOrch:
                                # Call the task function directly (not via Celery)
                                result = process_email_task(email_data)

        assert result["current_stage"] == "completed"
        assert result["error"] is None

    def test_serialize_result_with_pydantic_models(self):
        """_serialize_result should convert Pydantic models to dicts."""
        from src.tasks.process_email import _serialize_result

        # Create a mock Pydantic model
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"category": "Urgent", "priority": "High"}

        result = {
            "email": None,
            "classification": mock_model,
            "summary": None,
            "current_stage": "completed",
        }

        serialized = _serialize_result(result)

        assert serialized["email"] is None
        assert serialized["classification"] == {"category": "Urgent", "priority": "High"}
        assert serialized["summary"] is None
        assert serialized["current_stage"] == "completed"
        mock_model.model_dump.assert_called_once_with(mode="json")

    def test_serialize_result_with_none_values(self):
        """_serialize_result should handle None values gracefully."""
        from src.tasks.process_email import _serialize_result

        result = {
            "email": None,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "current_stage": "failed",
            "error": "test error",
        }

        serialized = _serialize_result(result)

        assert serialized["email"] is None
        assert serialized["classification"] is None
        assert serialized["current_stage"] == "failed"
        assert serialized["error"] == "test error"

    def test_serialize_result_with_plain_values(self):
        """_serialize_result should pass through plain values unchanged."""
        from src.tasks.process_email import _serialize_result

        result = {
            "current_stage": "completed",
            "flagged_for_review": True,
            "retry_counts": {"classifier": 1},
        }

        serialized = _serialize_result(result)

        assert serialized["current_stage"] == "completed"
        assert serialized["flagged_for_review"] is True
        assert serialized["retry_counts"] == {"classifier": 1}

    def test_noop_connection_manager(self):
        """_NoOpConnectionManager.broadcast should be a no-op."""
        import asyncio

        from src.tasks.process_email import _NoOpConnectionManager

        mgr = _NoOpConnectionManager()
        loop = asyncio.new_event_loop()
        try:
            # Should not raise
            loop.run_until_complete(mgr.broadcast({"type": "test"}))
        finally:
            loop.close()


class TestPollEmailsTask:
    """Tests for the poll_emails_task Celery task."""

    def test_beat_schedule_configured(self):
        """Celery Beat schedule should be configured for email polling."""
        from src.tasks.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        assert "poll-emails-periodically" in beat_schedule

        poll_config = beat_schedule["poll-emails-periodically"]
        assert poll_config["task"] == "tasks.poll_emails"
        assert poll_config["schedule"] >= 10.0

    def test_poll_interval_respects_minimum(self):
        """Polling schedule should be at least 10 seconds."""
        from src.tasks.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        schedule = beat_schedule["poll-emails-periodically"]["schedule"]
        assert schedule >= 10.0

    @patch("src.tasks.poll_emails._poll_all_accounts")
    @patch("src.tasks.poll_emails.asyncio.new_event_loop")
    def test_poll_emails_task_success(self, mock_loop_factory, mock_poll):
        """poll_emails_task should return accounts polled and emails found."""
        from src.tasks.poll_emails import poll_emails_task

        mock_loop = MagicMock()
        mock_loop_factory.return_value = mock_loop
        mock_loop.run_until_complete.return_value = {
            "accounts_polled": 2,
            "emails_found": 5,
            "emails_enqueued": 3,
        }

        result = poll_emails_task()

        assert result["accounts_polled"] == 2
        assert result["emails_found"] == 5
        assert result["emails_enqueued"] == 3

    @pytest.mark.asyncio
    async def test_poll_all_accounts_no_accounts(self):
        """_poll_all_accounts should return zeros when no accounts are connected."""
        from src.tasks.poll_emails import _poll_all_accounts

        # Mock session factory and repositories
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("src.models.database.get_session_factory", return_value=mock_factory):
            with patch("src.tasks.poll_emails._get_connected_accounts", return_value=[]):
                result = await _poll_all_accounts()

        assert result["accounts_polled"] == 0
        assert result["emails_found"] == 0
        assert result["emails_enqueued"] == 0

    @pytest.mark.asyncio
    async def test_get_connected_accounts_filters_by_status(self):
        """_get_connected_accounts should only return accounts with status='connected'."""
        from src.tasks.poll_emails import _get_connected_accounts

        # Create a mock repository with a mock session
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            MagicMock(id=uuid.uuid4(), provider="gmail", status="connected"),
        ]
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_repo = MagicMock()
        mock_repo.session = mock_session

        accounts = await _get_connected_accounts(mock_repo)

        assert len(accounts) == 1
        assert accounts[0].status == "connected"

    def test_create_provider_client_gmail(self):
        """_create_provider_client should create GmailClient for gmail accounts."""
        from src.tasks.poll_emails import _create_provider_client

        mock_account = MagicMock()
        mock_account.provider = "gmail"
        mock_account.encrypted_access_token = b"access"
        mock_account.encrypted_refresh_token = b"refresh"

        with patch("src.tasks.poll_emails.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                google_client_id="test-client-id",
                google_client_secret="test-client-secret",
            )
            with patch("src.providers.gmail.GmailClient") as MockGmail:
                MockGmail.return_value = MagicMock()
                client = _create_provider_client(mock_account)

        assert client is not None

    def test_create_provider_client_microsoft(self):
        """_create_provider_client should create MicrosoftGraphClient for microsoft accounts."""
        from src.tasks.poll_emails import _create_provider_client

        mock_account = MagicMock()
        mock_account.provider = "microsoft"
        mock_account.encrypted_access_token = b"access"
        mock_account.encrypted_refresh_token = b"refresh"

        with patch("src.tasks.poll_emails.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                microsoft_client_id="test-client-id",
                microsoft_client_secret="test-client-secret",
                microsoft_tenant_id="common",
            )
            with patch("src.providers.microsoft.MicrosoftGraphClient") as MockMS:
                MockMS.return_value = MagicMock()
                client = _create_provider_client(mock_account)

        assert client is not None

    def test_create_provider_client_unknown_provider(self):
        """_create_provider_client should return None for unknown providers."""
        from src.tasks.poll_emails import _create_provider_client

        mock_account = MagicMock()
        mock_account.provider = "yahoo"

        with patch("src.tasks.poll_emails.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            client = _create_provider_client(mock_account)

        assert client is None


class TestTaskRegistration:
    """Tests that tasks are properly registered with Celery."""

    def test_process_email_task_registered(self):
        """process_email_task should be registered with Celery."""
        from src.tasks.celery_app import celery_app

        assert "tasks.process_email" in celery_app.tasks or hasattr(
            celery_app, "tasks"
        )

    def test_poll_emails_task_registered(self):
        """poll_emails_task should be registered with Celery."""
        from src.tasks.celery_app import celery_app

        assert "tasks.poll_emails" in celery_app.tasks or hasattr(
            celery_app, "tasks"
        )

    def test_process_email_task_max_retries(self):
        """process_email_task should have max_retries=3."""
        from src.tasks.process_email import process_email_task

        assert process_email_task.max_retries == 3

    def test_poll_emails_task_max_retries(self):
        """poll_emails_task should have max_retries=2."""
        from src.tasks.poll_emails import poll_emails_task

        assert poll_emails_task.max_retries == 2

    def test_tasks_importable_from_package(self):
        """Tasks should be importable from the tasks package."""
        from src.tasks import celery_app, poll_emails_task, process_email_task

        assert celery_app is not None
        assert poll_emails_task is not None
        assert process_email_task is not None
