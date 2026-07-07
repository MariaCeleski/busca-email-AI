"""Unit tests for the SummarizerAgent."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.summarizer import SummarizerAgent
from src.models.email import RawEmail
from src.models.summary import SummaryResult


@pytest.fixture
def short_email() -> RawEmail:
    """Email with body under 200 words."""
    return RawEmail(
        provider_message_id="msg-001",
        sender="bob@example.com",
        subject="Quick update",
        body="Hey, just wanted to let you know the report is ready.",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def long_email() -> RawEmail:
    """Email with body over 200 words."""
    body = " ".join(["word"] * 250) + ". Second sentence here. Third sentence now. Fourth sentence too."
    return RawEmail(
        provider_message_id="msg-002",
        sender="manager@example.com",
        subject="Project status update",
        body=body,
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def empty_body_email() -> RawEmail:
    """Email with no extractable text."""
    return RawEmail(
        provider_message_id="msg-003",
        sender="noreply@example.com",
        subject="Notification",
        body="   ",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


def _valid_summary_json(
    summary: str = "This is a summary.",
    action_items: list = None,
) -> str:
    if action_items is None:
        action_items = ["Review the report", "Send feedback"]
    return json.dumps({"summary": summary, "action_items": action_items})


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
def mock_openai():
    """Patch AsyncOpenAI to avoid real API calls."""
    with patch("src.agents.summarizer.AsyncOpenAI") as mock_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.chat = MagicMock()
        mock_client_instance.chat.completions = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock()
        mock_cls.return_value = mock_client_instance
        yield mock_cls, mock_client_instance


class TestSummarizerAgentInit:
    """Tests for SummarizerAgent initialization."""

    def test_init_with_defaults(self, mock_openai):
        """Test agent initializes with default timeout of 8s."""
        agent = SummarizerAgent(api_key="test-key")
        assert agent._timeout == 8

    def test_init_with_custom_timeout(self, mock_openai):
        """Test agent respects custom timeout."""
        agent = SummarizerAgent(api_key="test-key", timeout=5)
        assert agent._timeout == 5


class TestShouldSummarize:
    """Tests for the should_summarize method."""

    def test_short_email_returns_false(self, mock_openai, short_email):
        """Test email under 200 words does not need summarization."""
        agent = SummarizerAgent(api_key="test-key")
        assert agent.should_summarize(short_email) is False

    def test_long_email_returns_true(self, mock_openai, long_email):
        """Test email over 200 words needs summarization."""
        agent = SummarizerAgent(api_key="test-key")
        assert agent.should_summarize(long_email) is True

    def test_exactly_200_words_returns_true(self, mock_openai):
        """Test email with exactly 200 words returns True."""
        body = " ".join(["hello"] * 200)
        email = RawEmail(
            provider_message_id="msg-x",
            sender="a@b.com",
            subject="Test",
            body=body,
            timestamp=datetime(2024, 1, 1),
            provider="gmail",
        )
        agent = SummarizerAgent(api_key="test-key")
        assert agent.should_summarize(email) is True


class TestCountWords:
    """Tests for the _count_words helper."""

    def test_count_words_normal(self, mock_openai):
        """Test word counting on normal text."""
        agent = SummarizerAgent(api_key="test-key")
        assert agent._count_words("hello world foo bar") == 4

    def test_count_words_empty(self, mock_openai):
        """Test word counting on empty string."""
        agent = SummarizerAgent(api_key="test-key")
        assert agent._count_words("") == 0


class TestExtractFirstSentences:
    """Tests for the _extract_first_sentences helper."""

    def test_extract_three_sentences(self, mock_openai):
        """Test extracting first 3 sentences."""
        agent = SummarizerAgent(api_key="test-key")
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = agent._extract_first_sentences(text, n=3)
        assert "First sentence." in result
        assert "Second sentence." in result
        assert "Third sentence." in result
        assert "Fourth" not in result

    def test_extract_fewer_than_n(self, mock_openai):
        """Test extracting when fewer sentences exist than n."""
        agent = SummarizerAgent(api_key="test-key")
        text = "Only one sentence."
        result = agent._extract_first_sentences(text, n=3)
        assert result == "Only one sentence."


class TestBuildSummaryPrompt:
    """Tests for prompt construction."""

    def test_prompt_contains_email_info(self, mock_openai, long_email):
        """Test prompt includes email details."""
        agent = SummarizerAgent(api_key="test-key")
        prompt = agent.build_summary_prompt(long_email)

        assert "manager@example.com" in prompt
        assert "Project status update" in prompt

    def test_prompt_mentions_constraints(self, mock_openai, long_email):
        """Test prompt mentions 3 sentences and 10 action items limits."""
        agent = SummarizerAgent(api_key="test-key")
        prompt = agent.build_summary_prompt(long_email)

        assert "3 sentences" in prompt
        assert "10" in prompt


class TestFallbackSummary:
    """Tests for fallback_summary method."""

    def test_fallback_returns_first_sentences(self, mock_openai):
        """Test fallback returns first 3 sentences with is_fallback=True."""
        email = RawEmail(
            provider_message_id="msg-f",
            sender="a@b.com",
            subject="Test",
            body="Sentence one. Sentence two. Sentence three. Sentence four.",
            timestamp=datetime(2024, 1, 1),
            provider="gmail",
        )
        agent = SummarizerAgent(api_key="test-key")
        result = agent.fallback_summary(email)

        assert result.is_fallback is True
        assert "Sentence one." in result.summary
        assert "Sentence two." in result.summary
        assert "Sentence three." in result.summary
        assert "Sentence four." not in result.summary
        assert result.action_items == []


class TestSummarize:
    """Tests for the main summarize method."""

    @pytest.mark.asyncio
    async def test_summarize_empty_body(self, mock_openai, empty_body_email):
        """Test email with no content returns no_content=True."""
        agent = SummarizerAgent(api_key="test-key")
        result = await agent.summarize(empty_body_email)

        assert result.no_content is True
        assert result.summary == ""

    @pytest.mark.asyncio
    async def test_summarize_short_email_no_llm_call(self, mock_openai, short_email):
        """Test short email returns body unmodified without LLM call."""
        _, mock_client = mock_openai
        agent = SummarizerAgent(api_key="test-key")
        result = await agent.summarize(short_email)

        assert result.summary == short_email.body
        assert result.action_items == []
        assert result.is_fallback is False
        # Ensure no LLM call was made
        mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarize_long_email_success(self, mock_openai, long_email):
        """Test long email gets summarized via OpenAI."""
        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(
                _valid_summary_json(
                    summary="Project update looks good.",
                    action_items=["Review docs"],
                )
            )
        )

        agent = SummarizerAgent(api_key="test-key")
        result = await agent.summarize(long_email)

        assert result.summary == "Project update looks good."
        assert result.action_items == ["Review docs"]
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_summarize_timeout_returns_fallback(self, mock_openai, long_email):
        """Test timeout returns fallback summary."""
        _, mock_client = mock_openai

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(20)
            return _make_openai_response(_valid_summary_json())

        mock_client.chat.completions.create = slow_response

        agent = SummarizerAgent(api_key="test-key", timeout=1)
        result = await agent.summarize(long_email)

        assert result.is_fallback is True
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_summarize_api_error_returns_fallback(self, mock_openai, long_email):
        """Test API error returns fallback summary."""
        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        agent = SummarizerAgent(api_key="test-key")
        result = await agent.summarize(long_email)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_summarize_invalid_json_returns_fallback(self, mock_openai, long_email):
        """Test invalid JSON from LLM returns fallback."""
        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("not valid json at all")
        )

        agent = SummarizerAgent(api_key="test-key")
        result = await agent.summarize(long_email)

        assert result.is_fallback is True
