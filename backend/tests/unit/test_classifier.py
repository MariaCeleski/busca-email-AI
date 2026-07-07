"""Unit tests for the ClassifierAgent."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.classifier import ClassificationError, ClassifierAgent
from src.models.classification import ClassificationResult
from src.models.email import RawEmail
from src.models.enums import EmailCategory, PriorityLevel


@pytest.fixture
def sample_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg-001",
        sender="alice@example.com",
        subject="Meeting tomorrow at 9am",
        body="Hi, please confirm your attendance for tomorrow's meeting at 9am.",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def empty_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg-002",
        sender="unknown@example.com",
        subject="",
        body="",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


def _valid_classification_json(
    category: str = "Urgent",
    priority: str = "High",
    confidence: float = 0.92,
    requires_response: bool = True,
    requires_summary: bool = True,
) -> str:
    return json.dumps(
        {
            "category": category,
            "priority": priority,
            "confidence": confidence,
            "requires_response": requires_response,
            "requires_summary": requires_summary,
        }
    )


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
    with patch("src.agents.classifier.AsyncOpenAI") as mock_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.chat = MagicMock()
        mock_client_instance.chat.completions = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock()
        mock_cls.return_value = mock_client_instance
        yield mock_cls, mock_client_instance


class TestClassifierAgentInit:
    """Tests for ClassifierAgent initialization."""

    def test_init_with_defaults(self, mock_openai):
        """Test agent initializes with settings defaults."""
        agent = ClassifierAgent(api_key="test-key", model="gpt-4o")
        assert agent._timeout == 10

    def test_init_with_custom_timeout(self, mock_openai):
        """Test agent respects custom timeout."""
        agent = ClassifierAgent(api_key="test-key", timeout=5)
        assert agent._timeout == 5


class TestBuildClassificationPrompt:
    """Tests for prompt construction."""

    def test_prompt_contains_email_info(self, mock_openai, sample_email):
        """Test prompt includes sender, subject, and body."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        assert "alice@example.com" in prompt
        assert "Meeting tomorrow at 9am" in prompt
        assert "confirm your attendance" in prompt

    def test_prompt_includes_categories(self, mock_openai, sample_email):
        """Test prompt mentions valid categories."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        for cat in ["Urgent", "Informative", "Promotional", "Spam", "Transactional", "Personal"]:
            assert cat in prompt

    def test_prompt_includes_priorities(self, mock_openai, sample_email):
        """Test prompt mentions valid priorities."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        for pri in ["High", "Medium", "Low"]:
            assert pri in prompt


class TestValidateResult:
    """Tests for LLM output validation."""

    def test_valid_json_parsed_correctly(self, mock_openai):
        """Test valid JSON is parsed into ClassificationResult."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json()
        result = agent.validate_result(raw)

        assert isinstance(result, ClassificationResult)
        assert result.category == EmailCategory.URGENT
        assert result.priority == PriorityLevel.HIGH
        assert result.confidence == 0.92
        assert result.requires_response is True
        assert result.requires_summary is True
        assert result.flagged_for_review is False

    def test_low_confidence_flags_for_review(self, mock_openai):
        """Test confidence < 0.6 sets flagged_for_review."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(confidence=0.4)
        result = agent.validate_result(raw)

        assert result.flagged_for_review is True

    def test_confidence_exactly_0_6_not_flagged(self, mock_openai):
        """Test confidence == 0.6 is not flagged."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(confidence=0.6)
        result = agent.validate_result(raw)

        assert result.flagged_for_review is False

    def test_invalid_json_raises_error(self, mock_openai):
        """Test invalid JSON raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")

        with pytest.raises(ClassificationError, match="Invalid JSON"):
            agent.validate_result("not json at all")

    def test_missing_field_raises_error(self, mock_openai):
        """Test missing required field raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")
        raw = json.dumps({"category": "Urgent"})  # missing other fields

        with pytest.raises(ClassificationError, match="Missing or invalid field"):
            agent.validate_result(raw)

    def test_invalid_category_raises_error(self, mock_openai):
        """Test invalid category value raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")
        raw = json.dumps(
            {
                "category": "Unknown",
                "priority": "High",
                "confidence": 0.9,
                "requires_response": True,
                "requires_summary": False,
            }
        )

        with pytest.raises(ClassificationError, match="Missing or invalid field"):
            agent.validate_result(raw)

    def test_json_wrapped_in_code_fence(self, mock_openai):
        """Test JSON wrapped in markdown code fences is handled."""
        agent = ClassifierAgent(api_key="test-key")
        raw = f"```json\n{_valid_classification_json()}\n```"
        result = agent.validate_result(raw)

        assert result.category == EmailCategory.URGENT

    def test_confidence_clamped_to_range(self, mock_openai):
        """Test confidence values outside 0-1 are clamped."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(confidence=1.5)
        result = agent.validate_result(raw)
        assert result.confidence == 1.0

        raw = _valid_classification_json(confidence=-0.3)
        result = agent.validate_result(raw)
        assert result.confidence == 0.0


class TestClassify:
    """Tests for the main classify method."""

    @pytest.mark.asyncio
    async def test_classify_empty_email(self, mock_openai, empty_email):
        """Test empty email returns default classification."""
        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(empty_email)

        assert result.category == EmailCategory.INFORMATIVE
        assert result.priority == PriorityLevel.LOW
        assert result.confidence == 0.0
        assert result.flagged_for_review is True
        assert result.requires_response is False
        assert result.requires_summary is False

    @pytest.mark.asyncio
    async def test_classify_success(self, mock_openai, sample_email):
        """Test successful classification via OpenAI."""
        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(_valid_classification_json())
        )

        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(sample_email)

        assert result.category == EmailCategory.URGENT
        assert result.priority == PriorityLevel.HIGH

    @pytest.mark.asyncio
    async def test_classify_timeout_raises_error(self, mock_openai, sample_email):
        """Test timeout raises ClassificationError."""
        _, mock_client = mock_openai

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(20)
            return _make_openai_response(_valid_classification_json())

        mock_client.chat.completions.create = slow_response

        agent = ClassifierAgent(api_key="test-key", timeout=1)

        with pytest.raises(ClassificationError, match="timed out"):
            await agent.classify(sample_email)

    @pytest.mark.asyncio
    async def test_classify_api_error_raises_classification_error(
        self, mock_openai, sample_email
    ):
        """Test OpenAI API error is wrapped in ClassificationError."""
        _, mock_client = mock_openai
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API unavailable")
        )

        agent = ClassifierAgent(api_key="test-key")

        with pytest.raises(ClassificationError, match="OpenAI API call failed"):
            await agent.classify(sample_email)
