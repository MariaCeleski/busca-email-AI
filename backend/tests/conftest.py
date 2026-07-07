"""Shared test fixtures and configuration."""

import pytest

from src.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings with safe defaults."""
    return Settings(
        debug=True,
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/email_agent_test",
        redis_url="redis://localhost:6379/15",
        celery_broker_url="redis://localhost:6379/15",
        celery_result_backend="redis://localhost:6379/14",
        gemini_api_key="test-key",
        encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS0xMjM0NTY3OA==",
        jwt_secret_key="test-jwt-secret",
        api_key="test-api-key",
    )
