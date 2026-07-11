"""Unit tests for the ClassifierAgent with Google Gemini LLM."""

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


@pytest.fixture
def long_urgent_email() -> RawEmail:
    """An email with body > 200 words to test requires_summary logic."""
    long_body = " ".join(["word"] * 250)
    return RawEmail(
        provider_message_id="msg-003",
        sender="boss@company.com",
        subject="URGENT: Project Deadline Change",
        body=long_body,
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


@pytest.fixture
def short_personal_email() -> RawEmail:
    """A short personal email (< 200 words) for requires_summary=False."""
    return RawEmail(
        provider_message_id="msg-004",
        sender="friend@personal.com",
        subject="Hey, how are you?",
        body="Just checking in. How have you been? Let me know if you want to grab lunch.",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        provider="gmail",
    )


def _valid_classification_json(
    category: str = "Urgent",
    priority: str = "High",
    confidence: float = 0.92,
) -> str:
    return json.dumps(
        {
            "category": category,
            "priority": priority,
            "confidence": confidence,
        }
    )


def _make_gemini_response(text: str) -> MagicMock:
    """Build a mock OpenAI response object."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


@pytest.fixture
def mock_gemini():
    """Patch google.generativeai to avoid real API calls."""
    with patch("src.agents.classifier.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock()
        MockOpenAI.return_value = mock_client
        yield MockOpenAI, mock_client


class TestClassifierAgentInit:
    """Tests for ClassifierAgent initialization."""

    def test_init_with_defaults(self, mock_gemini):
        """Test agent initializes with settings defaults."""
        agent = ClassifierAgent(api_key="test-key", model="gemini-2.0-flash")
        assert agent._timeout == 10

    def test_init_with_custom_timeout(self, mock_gemini):
        """Test agent respects custom timeout."""
        agent = ClassifierAgent(api_key="test-key", timeout=5)
        assert agent._timeout == 5

    def test_init_configures_genai(self, mock_gemini):
        """Test that genai.configure is called with the API key."""
        MockOpenAI, _ = mock_gemini
        ClassifierAgent(api_key="test-key-123")
        MockOpenAI.assert_called_with(api_key="test-key-123")


class TestBuildClassificationPrompt:
    """Tests for prompt construction."""

    def test_prompt_contains_email_info(self, mock_gemini, sample_email):
        """Test prompt includes sender, subject, and body."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        assert "alice@example.com" in prompt
        assert "Meeting tomorrow at 9am" in prompt
        assert "confirm your attendance" in prompt

    def test_prompt_includes_categories(self, mock_gemini, sample_email):
        """Test prompt mentions valid categories."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        for cat in ["Urgent", "Informative", "Promotional", "Spam", "Transactional", "Personal"]:
            assert cat in prompt

    def test_prompt_includes_priorities(self, mock_gemini, sample_email):
        """Test prompt mentions valid priorities."""
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(sample_email)

        for pri in ["High", "Medium", "Low"]:
            assert pri in prompt

    def test_prompt_truncates_long_body(self, mock_gemini):
        """Test that body is truncated to 2000 chars in the prompt."""
        long_email = RawEmail(
            provider_message_id="msg-long",
            sender="sender@test.com",
            subject="Long email",
            body="x" * 5000,
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            provider="gmail",
        )
        agent = ClassifierAgent(api_key="test-key")
        prompt = agent.build_classification_prompt(long_email)

        # Should contain at most 2000 x's from the body
        assert "x" * 2001 not in prompt


class TestValidateResult:
    """Tests for LLM output validation."""

    def test_valid_json_parsed_correctly(self, mock_gemini, sample_email):
        """Test valid JSON is parsed into ClassificationResult."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json()
        result = agent.validate_result(raw, sample_email)

        assert isinstance(result, ClassificationResult)
        assert result.category == EmailCategory.URGENT
        assert result.priority == PriorityLevel.HIGH
        assert result.confidence == 0.92
        assert result.flagged_for_review is False

    def test_low_confidence_flags_for_review(self, mock_gemini, sample_email):
        """Test confidence < 0.6 sets flagged_for_review."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(confidence=0.4)
        result = agent.validate_result(raw, sample_email)

        assert result.flagged_for_review is True

    def test_confidence_exactly_0_6_not_flagged(self, mock_gemini, sample_email):
        """Test confidence == 0.6 is not flagged."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(confidence=0.6)
        result = agent.validate_result(raw, sample_email)

        assert result.flagged_for_review is False

    def test_invalid_json_raises_error(self, mock_gemini):
        """Test invalid JSON raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")

        with pytest.raises(ClassificationError, match="Invalid JSON"):
            agent.validate_result("not json at all")

    def test_missing_field_raises_error(self, mock_gemini):
        """Test missing required field raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")
        raw = json.dumps({"category": "Urgent"})  # missing other fields

        with pytest.raises(ClassificationError, match="Missing or invalid field"):
            agent.validate_result(raw)

    def test_invalid_category_raises_error(self, mock_gemini):
        """Test invalid category value raises ClassificationError."""
        agent = ClassifierAgent(api_key="test-key")
        raw = json.dumps(
            {
                "category": "Unknown",
                "priority": "High",
                "confidence": 0.9,
            }
        )

        with pytest.raises(ClassificationError, match="Missing or invalid field"):
            agent.validate_result(raw)

    def test_json_wrapped_in_code_fence(self, mock_gemini, sample_email):
        """Test JSON wrapped in markdown code fences is handled."""
        agent = ClassifierAgent(api_key="test-key")
        raw = f"```json\n{_valid_classification_json()}\n```"
        result = agent.validate_result(raw, sample_email)

        assert result.category == EmailCategory.URGENT

    def test_confidence_clamped_to_range(self, mock_gemini, sample_email):
        """Test confidence values outside 0-1 are clamped."""
        agent = ClassifierAgent(api_key="test-key")

        raw = _valid_classification_json(confidence=1.5)
        result = agent.validate_result(raw, sample_email)
        assert result.confidence == 1.0

        raw = _valid_classification_json(confidence=-0.3)
        result = agent.validate_result(raw, sample_email)
        assert result.confidence == 0.0


class TestRequiresResponse:
    """Tests for the requires_response derived field logic."""

    def test_urgent_high_requires_response(self, mock_gemini, sample_email):
        """Urgent + High priority => requires_response=True."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Urgent", priority="High")
        result = agent.validate_result(raw, sample_email)
        assert result.requires_response is True

    def test_personal_medium_requires_response(self, mock_gemini, sample_email):
        """Personal + Medium priority => requires_response=True."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Personal", priority="Medium")
        result = agent.validate_result(raw, sample_email)
        assert result.requires_response is True

    def test_urgent_low_does_not_require_response(self, mock_gemini, sample_email):
        """Urgent + Low priority => requires_response=False."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Urgent", priority="Low")
        result = agent.validate_result(raw, sample_email)
        assert result.requires_response is False

    def test_informative_high_does_not_require_response(self, mock_gemini, sample_email):
        """Informative + High priority => requires_response=False."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Informative", priority="High")
        result = agent.validate_result(raw, sample_email)
        assert result.requires_response is False

    def test_spam_any_priority_does_not_require_response(self, mock_gemini, sample_email):
        """Spam + any priority => requires_response=False."""
        agent = ClassifierAgent(api_key="test-key")
        for priority in ["High", "Medium", "Low"]:
            raw = _valid_classification_json(category="Spam", priority=priority)
            result = agent.validate_result(raw, sample_email)
            assert result.requires_response is False


class TestRequiresSummary:
    """Tests for the requires_summary derived field logic."""

    def test_urgent_long_body_requires_summary(self, mock_gemini, long_urgent_email):
        """Urgent + body > 200 words => requires_summary=True."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Urgent", priority="High")
        result = agent.validate_result(raw, long_urgent_email)
        assert result.requires_summary is True

    def test_informative_long_body_requires_summary(self, mock_gemini, long_urgent_email):
        """Informative + body > 200 words => requires_summary=True."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Informative", priority="Medium")
        result = agent.validate_result(raw, long_urgent_email)
        assert result.requires_summary is True

    def test_urgent_short_body_no_summary(self, mock_gemini, sample_email):
        """Urgent + body < 200 words => requires_summary=False."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Urgent", priority="High")
        result = agent.validate_result(raw, sample_email)
        assert result.requires_summary is False

    def test_promotional_long_body_no_summary(self, mock_gemini, long_urgent_email):
        """Promotional + body > 200 words => requires_summary=False (wrong category)."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Promotional", priority="Low")
        result = agent.validate_result(raw, long_urgent_email)
        assert result.requires_summary is False

    def test_personal_long_body_no_summary(self, mock_gemini, long_urgent_email):
        """Personal + body > 200 words => requires_summary=False (not in summary categories)."""
        agent = ClassifierAgent(api_key="test-key")
        raw = _valid_classification_json(category="Personal", priority="High")
        result = agent.validate_result(raw, long_urgent_email)
        assert result.requires_summary is False


class TestClassify:
    """Tests for the main classify method."""

    @pytest.mark.asyncio
    async def test_classify_empty_email(self, mock_gemini, empty_email):
        """Test empty email returns default classification without calling LLM."""
        _, mock_client = mock_gemini
        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(empty_email)

        assert result.category == EmailCategory.INFORMATIVE
        assert result.priority == PriorityLevel.LOW
        assert result.confidence == 0.0
        assert result.flagged_for_review is True
        assert result.requires_response is False
        assert result.requires_summary is False

        # Verify LLM was NOT called for empty emails
        mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_classify_success(self, mock_gemini, sample_email):
        """Test successful classification via Gemini."""
        _, mock_client = mock_gemini
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_gemini_response(_valid_classification_json())
        )

        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(sample_email)

        assert result.category == EmailCategory.URGENT
        assert result.priority == PriorityLevel.HIGH
        assert result.requires_response is True  # Urgent + High
        assert result.requires_summary is False  # Body < 200 words

    @pytest.mark.asyncio
    async def test_classify_personal_medium(self, mock_gemini, short_personal_email):
        """Test Personal + Medium triggers requires_response."""
        _, mock_client = mock_gemini
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_gemini_response(
                _valid_classification_json(category="Personal", priority="Medium", confidence=0.85)
            )
        )

        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(short_personal_email)

        assert result.category == EmailCategory.PERSONAL
        assert result.priority == PriorityLevel.MEDIUM
        assert result.requires_response is True
        assert result.requires_summary is False  # Body < 200 words

    @pytest.mark.asyncio
    async def test_classify_timeout_raises_error(self, mock_gemini, sample_email):
        """Test timeout raises ClassificationError."""
        _, mock_client = mock_gemini

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(20)
            return _make_gemini_response(_valid_classification_json())

        mock_client.chat.completions.create = slow_response

        agent = ClassifierAgent(api_key="test-key", timeout=1)

        with pytest.raises(ClassificationError, match="timed out"):
            await agent.classify(sample_email)

    @pytest.mark.asyncio
    async def test_classify_api_error_raises_classification_error(
        self, mock_gemini, sample_email
    ):
        """Test Gemini API error is wrapped in ClassificationError."""
        _, mock_client = mock_gemini
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API unavailable")
        )

        agent = ClassifierAgent(api_key="test-key")

        with pytest.raises(ClassificationError, match="Gemini API call failed"):
            await agent.classify(sample_email)

    @pytest.mark.asyncio
    async def test_classify_empty_response_raises_error(
        self, mock_gemini, sample_email
    ):
        """Test that an empty Gemini response raises ClassificationError."""
        _, mock_client = mock_gemini
        empty_response = MagicMock()
        empty_response.choices = [MagicMock()]
        empty_response.choices[0].message.content = None
        mock_client.chat.completions.create = AsyncMock(return_value=empty_response)

        agent = ClassifierAgent(api_key="test-key")

        with pytest.raises(ClassificationError, match="OpenAI returned empty response"):
            await agent.classify(sample_email)

    @pytest.mark.asyncio
    async def test_classify_low_confidence_flags_review(self, mock_gemini, sample_email):
        """Test low confidence result is flagged for review."""
        _, mock_client = mock_gemini
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_gemini_response(
                _valid_classification_json(confidence=0.3)
            )
        )

        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(sample_email)

        assert result.flagged_for_review is True
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_classify_long_urgent_email(self, mock_gemini, long_urgent_email):
        """Test classification of long urgent email sets requires_summary=True."""
        _, mock_client = mock_gemini
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_gemini_response(
                _valid_classification_json(category="Urgent", priority="High", confidence=0.95)
            )
        )

        agent = ClassifierAgent(api_key="test-key")
        result = await agent.classify(long_urgent_email)

        assert result.category == EmailCategory.URGENT
        assert result.requires_response is True
        assert result.requires_summary is True  # Body > 200 words + Urgent category
