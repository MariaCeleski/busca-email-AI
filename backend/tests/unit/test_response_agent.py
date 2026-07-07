"""Unit tests for ResponseAgent — generate_reply, context retrieval, tone matching, timeout."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import DraftStatus, EmailCategory, PriorityLevel
from src.models.vector_store import EmailMetadata, SearchResult


def _make_openai_response(text: str) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response object."""
    response = MagicMock()
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    with patch("src.agents.response.get_settings") as mock:
        settings = MagicMock()
        settings.openai_api_key = "test-api-key"
        settings.openai_model = "gpt-4o"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_openai():
    """Patch AsyncOpenAI to avoid real API calls."""
    with patch("src.agents.response.AsyncOpenAI") as mock_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.chat = MagicMock()
        mock_client_instance.chat.completions = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(
                "SUBJECT: Re: Test Subject\nBODY:\nThank you for your email. I will look into this."
            )
        )
        mock_cls.return_value = mock_client_instance
        yield mock_cls, mock_client_instance


@pytest.fixture
def mock_vector_store():
    """Mock VectorStoreService."""
    store = MagicMock()
    store.search_similar.return_value = []
    return store


@pytest.fixture
def response_agent(mock_settings, mock_openai, mock_vector_store):
    """Create ResponseAgent instance with mocks."""
    from src.agents.response import ResponseAgent

    agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)
    return agent


@pytest.fixture
def sample_email():
    """Create a sample RawEmail."""
    return RawEmail(
        provider_message_id="msg-test-001",
        sender="alice@example.com",
        subject="Test Subject",
        body="Hello, can you help me with the project deadline?",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        provider="gmail",
    )


@pytest.fixture
def sample_classification():
    """Create a sample ClassificationResult."""
    return ClassificationResult(
        category=EmailCategory.PERSONAL,
        priority=PriorityLevel.MEDIUM,
        confidence=0.85,
        requires_response=True,
        requires_summary=False,
    )


@pytest.fixture
def sample_search_results():
    """Create sample SearchResult list with high similarity."""
    return [
        SearchResult(
            email_id="hist-1",
            metadata=EmailMetadata(
                email_id="hist-1",
                sender="alice@example.com",
                timestamp=datetime(2024, 1, 10, 9, 0, 0),
                category=EmailCategory.PERSONAL,
                provider_message_id="msg-hist-1",
            ),
            similarity_score=0.85,
            text_snippet="Hi, thanks for reaching out! I'd be happy to help.",
        ),
        SearchResult(
            email_id="hist-2",
            metadata=EmailMetadata(
                email_id="hist-2",
                sender="alice@example.com",
                timestamp=datetime(2024, 1, 8, 14, 0, 0),
                category=EmailCategory.PERSONAL,
                provider_message_id="msg-hist-2",
            ),
            similarity_score=0.72,
            text_snippet="Sure thing, let me check and get back to you shortly.",
        ),
    ]


class TestGenerateReply:
    """Tests for generate_reply method."""

    @pytest.mark.asyncio
    async def test_generate_reply_returns_draft(
        self, response_agent, sample_email, sample_classification, mock_vector_store
    ):
        """generate_reply should return a DraftReply object."""
        result = await response_agent.generate_reply(sample_email, sample_classification)

        assert isinstance(result, DraftReply)
        assert result.status == DraftStatus.PENDING
        assert result.reply_body != ""
        assert result.suggested_subject != ""

    @pytest.mark.asyncio
    async def test_generate_reply_timeout_raises_error(
        self, mock_settings, mock_openai, mock_vector_store, sample_email, sample_classification
    ):
        """generate_reply should raise ResponseTimeoutError on timeout."""
        from src.agents.response import ResponseAgent, ResponseTimeoutError

        _, mock_client = mock_openai

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(5)
            return _make_openai_response("late response")

        mock_client.chat.completions.create = slow_response

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=1)

        with pytest.raises(ResponseTimeoutError):
            await agent.generate_reply(sample_email, sample_classification)

    @pytest.mark.asyncio
    async def test_generate_reply_service_error_raises_generation_error(
        self, mock_settings, mock_openai, mock_vector_store, sample_email, sample_classification
    ):
        """generate_reply should raise ResponseGenerationError on service failure."""
        from src.agents.response import ResponseAgent, ResponseGenerationError

        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Service unavailable")
        )

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)

        with pytest.raises(ResponseGenerationError):
            await agent.generate_reply(sample_email, sample_classification)

    @pytest.mark.asyncio
    async def test_generate_reply_references_historical_emails(
        self, mock_settings, mock_openai, mock_vector_store,
        sample_email, sample_classification, sample_search_results
    ):
        """generate_reply should include referenced_email_ids from history."""
        from src.agents.response import ResponseAgent

        mock_vector_store.search_similar.return_value = sample_search_results

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)
        result = await agent.generate_reply(sample_email, sample_classification)

        assert "hist-1" in result.referenced_email_ids
        assert "hist-2" in result.referenced_email_ids


class TestRetrieveContext:
    """Tests for retrieve_context method."""

    def test_retrieve_context_queries_vector_store(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should call vector_store.search_similar."""
        response_agent.retrieve_context(sample_email)

        mock_vector_store.search_similar.assert_called_once()
        call_kwargs = mock_vector_store.search_similar.call_args[1]
        assert call_kwargs["k"] == 5
        assert "Test Subject" in call_kwargs["query_text"]

    def test_retrieve_context_filters_low_similarity(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should filter out results below 0.3 similarity."""
        low_similarity_results = [
            SearchResult(
                email_id="low-1",
                metadata=EmailMetadata(
                    email_id="low-1",
                    sender="test@example.com",
                    timestamp=datetime(2024, 1, 1, 0, 0, 0),
                    category=EmailCategory.INFORMATIVE,
                    provider_message_id="msg-low-1",
                ),
                similarity_score=0.2,
                text_snippet="Not relevant",
            ),
            SearchResult(
                email_id="high-1",
                metadata=EmailMetadata(
                    email_id="high-1",
                    sender="test@example.com",
                    timestamp=datetime(2024, 1, 5, 0, 0, 0),
                    category=EmailCategory.PERSONAL,
                    provider_message_id="msg-high-1",
                ),
                similarity_score=0.8,
                text_snippet="Very relevant",
            ),
        ]
        mock_vector_store.search_similar.return_value = low_similarity_results

        results = response_agent.retrieve_context(sample_email)

        assert len(results) == 1
        assert results[0].email_id == "high-1"

    def test_retrieve_context_returns_empty_when_no_relevant(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should return empty list when all scores < 0.3."""
        low_results = [
            SearchResult(
                email_id="low-1",
                metadata=EmailMetadata(
                    email_id="low-1",
                    sender="test@example.com",
                    timestamp=datetime(2024, 1, 1, 0, 0, 0),
                    category=EmailCategory.INFORMATIVE,
                    provider_message_id="msg-low-1",
                ),
                similarity_score=0.1,
                text_snippet="Irrelevant",
            ),
        ]
        mock_vector_store.search_similar.return_value = low_results

        results = response_agent.retrieve_context(sample_email)

        assert results == []


class TestBuildResponsePrompt:
    """Tests for build_response_prompt method."""

    def test_build_prompt_with_history(
        self, response_agent, sample_email, sample_search_results
    ):
        """build_response_prompt should include historical context."""
        prompt = response_agent.build_response_prompt(sample_email, sample_search_results)

        assert "Historical email context" in prompt
        assert "happy to help" in prompt
        assert sample_email.sender in prompt
        assert sample_email.subject in prompt

    def test_build_prompt_without_history(
        self, response_agent, sample_email
    ):
        """build_response_prompt should use neutral tone when no history."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert "neutral professional tone" in prompt
        assert sample_email.sender in prompt
        assert sample_email.subject in prompt

    def test_build_prompt_includes_email_body(
        self, response_agent, sample_email
    ):
        """build_response_prompt should include the email body content."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert sample_email.body in prompt


class TestValidateDraft:
    """Tests for validate_draft method."""

    def test_validate_draft_parses_structured_output(self, response_agent):
        """validate_draft should parse SUBJECT: and BODY: format."""
        draft_text = "SUBJECT: Re: Meeting\nBODY:\nThank you for the update. I'll be there."
        result = response_agent.validate_draft(draft_text, "Meeting", ["ref-1"])

        assert result.suggested_subject == "Re: Meeting"
        assert "Thank you for the update" in result.reply_body
        assert result.referenced_email_ids == ["ref-1"]
        assert result.status == DraftStatus.PENDING

    def test_validate_draft_truncates_long_subject(self, response_agent):
        """validate_draft should truncate subject to 150 characters."""
        long_subject = "A" * 200
        draft_text = f"SUBJECT: {long_subject}\nBODY:\nShort reply."
        result = response_agent.validate_draft(draft_text, "Original", [])

        assert len(result.suggested_subject) <= 150

    def test_validate_draft_truncates_long_body(self, response_agent):
        """validate_draft should truncate body to 500 words."""
        long_body = " ".join(["word"] * 600)
        draft_text = f"SUBJECT: Re: Test\nBODY:\n{long_body}"
        result = response_agent.validate_draft(draft_text, "Test", [])

        word_count = len(result.reply_body.split())
        assert word_count <= 500

    def test_validate_draft_fallback_subject(self, response_agent):
        """validate_draft should use fallback subject when parsing fails."""
        draft_text = "Just a plain text reply without formatting."
        result = response_agent.validate_draft(draft_text, "Original Subject", [])

        assert result.suggested_subject == "Re: Original Subject"

    def test_validate_draft_uses_raw_output_as_body_when_no_structure(
        self, response_agent
    ):
        """validate_draft should use raw text as body when format not detected."""
        draft_text = "Thank you for reaching out. I'll get back to you soon."
        result = response_agent.validate_draft(draft_text, "Test", [])

        assert result.reply_body == draft_text
