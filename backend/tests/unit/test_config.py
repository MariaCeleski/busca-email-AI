"""Tests for configuration management."""

import pytest

from src.config import Settings


class TestSettings:
    """Test the Settings model and its validators."""

    def test_default_settings_load(self) -> None:
        """Settings should load with default values when no env vars are set."""
        settings = Settings(
            _env_file=None,
            gemini_api_key="test",
            encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS0xMjM0NTY3OA==",
            jwt_secret_key="test",
            api_key="test",
        )
        assert settings.app_name == "AI Email Agent"
        assert settings.api_port == 8000
        assert settings.email_poll_interval_seconds == 60
        assert settings.celery_max_concurrency == 10
        assert settings.max_agent_retries == 3

    def test_poll_interval_minimum_enforced(self) -> None:
        """Polling interval below 10 seconds should raise validation error."""
        with pytest.raises(ValueError, match="greater than or equal to 10"):
            Settings(
                _env_file=None,
                email_poll_interval_seconds=5,
                gemini_api_key="test",
                encryption_key="test",
                jwt_secret_key="test",
                api_key="test",
            )

    def test_poll_interval_at_minimum(self) -> None:
        """Polling interval of exactly 10 seconds should be valid."""
        settings = Settings(
            _env_file=None,
            email_poll_interval_seconds=10,
            gemini_api_key="test",
            encryption_key="test",
            jwt_secret_key="test",
            api_key="test",
        )
        assert settings.email_poll_interval_seconds == 10

    def test_agent_timeout_defaults(self) -> None:
        """Agent timeouts should have correct default values."""
        settings = Settings(
            _env_file=None,
            gemini_api_key="test",
            encryption_key="test",
            jwt_secret_key="test",
            api_key="test",
        )
        assert settings.classifier_timeout_seconds == 10
        assert settings.summarizer_timeout_seconds == 8
        assert settings.response_timeout_seconds == 15
        assert settings.orchestrator_hard_timeout_seconds == 30
