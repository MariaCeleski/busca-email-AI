"""Unit tests for ResponseAgent — generate_reply, context retrieval, tone matching, timeout.

Tests use mocked Gemini and VectorStoreService to avoid real API calls.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.response import (
    SIMILARITY_THRESHOLD,
    ResponseAgent,
    ResponseGenerationError,
    ResponseTimeoutError,
)
from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import DraftStatus, EmailCategory, PriorityLevel
from src.models.vector_store import EmailMetadata, SearchResult


def _make_gemini_response(text: str) -> MagicMock:
    """Build a mock Gemini GenerateContentResponse object."""
    response = MagicMock()
    response.text = text
    return response


def _json_reply(body: str = "Thank you for your email. I will look into this.",
                subject: str = "Re: Test Subject") -> str:
    """Create a valid JSON response string."""
    return json.dumps({"reply_body": body, "suggested_subject": subject})


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    with patch("src.agents.response.get_settings") as mock:
        settings = MagicMock()
        settings.gemini_api_key = "test-gemini-api-key"
        settings.gemini_model = "gemini-2.0-flash"
        settings.response_timeout_seconds = 15
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_genai():
    """Patch google.generativeai to avoid real API calls."""
    with patch("src.agents.response.genai") as mock_genai_module:
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = _make_gemini_response(
            _json_reply()
        )
        mock_genai_module.GenerativeModel.return_value = mock_model_instance
        yield mock_genai_module, mock_model_instance


@pytest.fixture
def mock_vector_store():
    """Mock VectorStoreService with async search_similar."""
    store = MagicMock()
    store.search_similar = AsyncMock(return_value=[])
    return store


@pytest.fixture
def response_agent(mock_settings, mock_genai, mock_vector_store):
    """Create ResponseAgent instance with mocks."""
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
            text_snippet="Hi Alice, thanks for reaching out! I'd be happy to help. Best regards, Team.",
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
            text_snippet="Hello, sure thing. Let me check and get back to you shortly. Thanks!",
        ),
    ]


@pytest.fixture
def low_similarity_results():
    """Create sample SearchResult list with all scores below threshold."""
    return [
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
            text_snippet="Not relevant at all.",
        ),
        SearchResult(
            email_id="low-2",
            metadata=EmailMetadata(
                email_id="low-2",
                sender="other@example.com",
                timestamp=datetime(2024, 1, 2, 0, 0, 0),
                category=EmailCategory.PROMOTIONAL,
                provider_message_id="msg-low-2",
            ),
            similarity_score=0.1,
            text_snippet="Completely irrelevant.",
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
        self, mock_settings, mock_genai, mock_vector_store, sample_email, sample_classification
    ):
        """generate_reply should raise ResponseTimeoutError on timeout (15s).

        On timeout, the partial draft is discarded — no partial result is returned.
        """
        _, mock_model = mock_genai

        def slow_response(*args, **kwargs):
            import time
            time.sleep(5)
            return _make_gemini_response(_json_reply())

        mock_model.generate_content = slow_response

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=1)

        with pytest.raises(ResponseTimeoutError):
            await agent.generate_reply(sample_email, sample_classification)

    @pytest.mark.asyncio
    async def test_generate_reply_service_error_raises_generation_error(
        self, mock_settings, mock_genai, mock_vector_store, sample_email, sample_classification
    ):
        """generate_reply should raise ResponseGenerationError on service failure."""
        _, mock_model = mock_genai
        mock_model.generate_content.side_effect = Exception("Service unavailable")

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)

        with pytest.raises(ResponseGenerationError):
            await agent.generate_reply(sample_email, sample_classification)

    @pytest.mark.asyncio
    async def test_generate_reply_references_historical_emails(
        self, mock_settings, mock_genai, mock_vector_store,
        sample_email, sample_classification, sample_search_results
    ):
        """generate_reply should include referenced_email_ids from context retrieval."""
        mock_vector_store.search_similar = AsyncMock(return_value=sample_search_results)

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)
        result = await agent.generate_reply(sample_email, sample_classification)

        assert "hist-1" in result.referenced_email_ids
        assert "hist-2" in result.referenced_email_ids

    @pytest.mark.asyncio
    async def test_generate_reply_no_referenced_ids_when_no_history(
        self, mock_settings, mock_genai, mock_vector_store,
        sample_email, sample_classification, low_similarity_results
    ):
        """generate_reply returns empty referenced_email_ids when all scores < 0.3."""
        mock_vector_store.search_similar = AsyncMock(return_value=low_similarity_results)

        agent = ResponseAgent(vector_store=mock_vector_store, timeout=15)
        result = await agent.generate_reply(sample_email, sample_classification)

        assert result.referenced_email_ids == []


class TestRetrieveContext:
    """Tests for retrieve_context method."""

    @pytest.mark.asyncio
    async def test_retrieve_context_queries_vector_store(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should call vector_store.search_similar with k=5."""
        await response_agent.retrieve_context(sample_email)

        mock_vector_store.search_similar.assert_called_once()
        call_kwargs = mock_vector_store.search_similar.call_args[1]
        assert call_kwargs["k"] == 5
        assert "Test Subject" in call_kwargs["query_text"]

    @pytest.mark.asyncio
    async def test_retrieve_context_filters_low_similarity(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should filter out results below 0.3 similarity."""
        mixed_results = [
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
                text_snippet="Very relevant content here.",
            ),
        ]
        mock_vector_store.search_similar = AsyncMock(return_value=mixed_results)

        results = await response_agent.retrieve_context(sample_email)

        assert len(results) == 1
        assert results[0].email_id == "high-1"

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_empty_when_no_relevant(
        self, response_agent, mock_vector_store, sample_email, low_similarity_results
    ):
        """retrieve_context should return empty list when all scores < 0.3."""
        mock_vector_store.search_similar = AsyncMock(return_value=low_similarity_results)

        results = await response_agent.retrieve_context(sample_email)

        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_context_uses_top_5(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should default to k=5 for semantic search."""
        await response_agent.retrieve_context(sample_email)

        call_kwargs = mock_vector_store.search_similar.call_args[1]
        assert call_kwargs["k"] == 5

    @pytest.mark.asyncio
    async def test_retrieve_context_custom_k(
        self, response_agent, mock_vector_store, sample_email
    ):
        """retrieve_context should accept a custom k parameter."""
        await response_agent.retrieve_context(sample_email, k=10)

        call_kwargs = mock_vector_store.search_similar.call_args[1]
        assert call_kwargs["k"] == 10


class TestBuildResponsePrompt:
    """Tests for build_response_prompt method."""

    def test_build_prompt_with_history_includes_tone_analysis(
        self, response_agent, sample_email, sample_search_results
    ):
        """build_response_prompt should include tone analysis when history exists."""
        prompt = response_agent.build_response_prompt(sample_email, sample_search_results)

        assert "Orientação de tom" in prompt
        assert "Estilo de saudação" in prompt
        assert "Estilo de despedida" in prompt
        assert "Comprimento médio de frase" in prompt
        assert sample_email.sender in prompt
        assert sample_email.subject in prompt

    def test_build_prompt_without_history_uses_neutral_tone(
        self, response_agent, sample_email
    ):
        """build_response_prompt should use neutral professional tone when no history."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert "tom profissional neutro" in prompt
        assert sample_email.sender in prompt
        assert sample_email.subject in prompt

    def test_build_prompt_includes_email_body(
        self, response_agent, sample_email
    ):
        """build_response_prompt should include the email body content."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert sample_email.body in prompt

    def test_build_prompt_requests_json_output(
        self, response_agent, sample_email
    ):
        """build_response_prompt should request JSON output with reply_body and suggested_subject."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert "reply_body" in prompt
        assert "suggested_subject" in prompt
        assert "JSON" in prompt

    def test_build_prompt_includes_historical_examples(
        self, response_agent, sample_email, sample_search_results
    ):
        """build_response_prompt should include snippets from historical emails."""
        prompt = response_agent.build_response_prompt(sample_email, sample_search_results)

        assert "happy to help" in prompt
        assert "0.85" in prompt  # similarity score

    def test_build_prompt_includes_max_constraints(
        self, response_agent, sample_email
    ):
        """build_response_prompt should specify 500 words and 150 chars limits."""
        prompt = response_agent.build_response_prompt(sample_email, [])

        assert "500 palavras" in prompt
        assert "150 caracteres" in prompt


class TestValidateDraft:
    """Tests for validate_draft method."""

    def test_validate_draft_passes_valid_draft(self, response_agent):
        """validate_draft should return unchanged draft when within limits."""
        draft = DraftReply(
            reply_body="Thank you for your email. I will look into this.",
            suggested_subject="Re: Test",
            referenced_email_ids=["ref-1"],
            status=DraftStatus.PENDING,
            generated_at=datetime.utcnow(),
        )
        result = response_agent.validate_draft(draft)

        assert result.reply_body == draft.reply_body
        assert result.suggested_subject == draft.suggested_subject
        assert result.referenced_email_ids == ["ref-1"]

    def test_validate_draft_truncates_long_subject(self, response_agent):
        """validate_draft should truncate subject to 150 characters.

        Since Pydantic enforces max_length=150, validate_draft is tested via
        _build_validated_draft which truncates before model creation.
        """
        # Test via _build_validated_draft which is the actual entry point
        long_subject = "A" * 200
        raw = json.dumps({"reply_body": "Short reply.", "suggested_subject": long_subject})
        result = response_agent._build_validated_draft(raw, "Original", [])

        assert len(result.suggested_subject) == 150

    def test_validate_draft_truncates_long_body(self, response_agent):
        """validate_draft should truncate body to 500 words.

        Since Pydantic enforces max_length=2500 and word validator,
        validate_draft is tested via _build_validated_draft which handles
        truncation before model creation.
        """
        long_body = " ".join(["word"] * 600)
        raw = json.dumps({"reply_body": long_body, "suggested_subject": "Re: Test"})
        result = response_agent._build_validated_draft(raw, "Test", [])

        word_count = len(result.reply_body.split())
        assert word_count == 500

    def test_validate_draft_preserves_referenced_ids(self, response_agent):
        """validate_draft should preserve referenced_email_ids."""
        draft = DraftReply(
            reply_body="Hello there.",
            suggested_subject="Re: Subject",
            referenced_email_ids=["id-1", "id-2", "id-3"],
            status=DraftStatus.PENDING,
            generated_at=datetime.utcnow(),
        )
        result = response_agent.validate_draft(draft)

        assert result.referenced_email_ids == ["id-1", "id-2", "id-3"]


class TestParseLlmOutput:
    """Tests for _extract_reply_fields and _build_validated_draft (JSON parsing from Gemini)."""

    def test_parse_valid_json(self, response_agent):
        """Should parse valid JSON output from Gemini."""
        raw = json.dumps({
            "reply_body": "Thank you for reaching out.",
            "suggested_subject": "Re: Inquiry"
        })
        result = response_agent._build_validated_draft(raw, "Inquiry", ["ref-1"])

        assert result.reply_body == "Thank you for reaching out."
        assert result.suggested_subject == "Re: Inquiry"
        assert result.referenced_email_ids == ["ref-1"]

    def test_parse_json_in_code_block(self, response_agent):
        """Should handle JSON wrapped in markdown code blocks."""
        raw = '```json\n{"reply_body": "Hello there.", "suggested_subject": "Re: Hello"}\n```'
        result = response_agent._build_validated_draft(raw, "Hello", [])

        assert result.reply_body == "Hello there."
        assert result.suggested_subject == "Re: Hello"

    def test_parse_fallback_for_non_json(self, response_agent):
        """Should fall back to text parsing when JSON is invalid."""
        raw = "SUBJECT: Re: Meeting\nBODY:\nI'll attend the meeting. Thanks!"
        result = response_agent._build_validated_draft(raw, "Meeting", ["ref-2"])

        assert "attend the meeting" in result.reply_body
        assert result.referenced_email_ids == ["ref-2"]

    def test_parse_uses_raw_output_as_body_when_all_parsing_fails(self, response_agent):
        """Should use entire raw output as body when no format is detected."""
        raw = "Just a plain text reply without any formatting."
        result = response_agent._build_validated_draft(raw, "Test", [])

        assert result.reply_body == raw
        assert result.suggested_subject == "Re: Test"

    def test_build_validated_draft_truncates_long_body(self, response_agent):
        """Should truncate body to 500 words in _build_validated_draft."""
        long_body = " ".join(["word"] * 600)
        raw = json.dumps({"reply_body": long_body, "suggested_subject": "Re: Test"})
        result = response_agent._build_validated_draft(raw, "Test", [])

        word_count = len(result.reply_body.split())
        assert word_count == 500

    def test_build_validated_draft_truncates_long_subject(self, response_agent):
        """Should truncate subject to 150 chars in _build_validated_draft."""
        long_subject = "A" * 200
        raw = json.dumps({"reply_body": "Short body.", "suggested_subject": long_subject})
        result = response_agent._build_validated_draft(raw, "Original", [])

        assert len(result.suggested_subject) == 150


class TestToneMatching:
    """Tests for tone matching from historical emails."""

    def test_tone_section_includes_greeting_analysis(
        self, response_agent, sample_search_results
    ):
        """_build_tone_section should extract greeting patterns from history."""
        tone = response_agent._build_tone_section(sample_search_results)

        assert "Estilo de saudação" in tone

    def test_tone_section_includes_sign_off_analysis(
        self, response_agent, sample_search_results
    ):
        """_build_tone_section should extract sign-off patterns from history."""
        tone = response_agent._build_tone_section(sample_search_results)

        assert "Estilo de despedida" in tone

    def test_tone_section_includes_sentence_length(
        self, response_agent, sample_search_results
    ):
        """_build_tone_section should include average sentence length."""
        tone = response_agent._build_tone_section(sample_search_results)

        assert "Comprimento médio de frase" in tone

    def test_tone_section_neutral_when_no_history(self, response_agent):
        """_build_tone_section should indicate neutral tone when no history."""
        tone = response_agent._build_tone_section([])

        assert "tom profissional neutro" in tone

    def test_tone_section_includes_examples(
        self, response_agent, sample_search_results
    ):
        """_build_tone_section should include historical email examples."""
        tone = response_agent._build_tone_section(sample_search_results)

        assert "Exemplo 1" in tone
        assert "0.85" in tone
