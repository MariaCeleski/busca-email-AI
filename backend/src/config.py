"""Application configuration management using Pydantic BaseSettings.

Environment variables are loaded from .env file or system environment.
All settings are validated at startup.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "AI Email Agent"
    app_version: str = "0.1.0"
    debug: bool = False

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = Field(default="", description="API key for authentication")
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]

    # --- Database (PostgreSQL) ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/email_agent",
        description="PostgreSQL connection string",
    )

    # --- Redis ---
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for Celery broker and caching",
    )

    # --- Celery ---
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Celery broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        description="Celery result backend URL",
    )
    celery_max_concurrency: int = Field(
        default=10,
        description="Maximum concurrent Celery worker tasks",
    )

    # --- Google Gemini ---
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key for LLM inference and embeddings",
    )
    gemini_model: str = Field(
        default="gemini-2.0-flash",
        description="Gemini model for text generation",
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001",
        description="Gemini model for text embeddings",
    )

    # --- OpenAI ---
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for LLM inference and embeddings",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for text generation",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI model for text embeddings",
    )

    # --- ChromaDB ---
    chromadb_host: str = Field(
        default="localhost",
        description="ChromaDB server host",
    )
    chromadb_port: int = Field(
        default=8001,
        description="ChromaDB server port",
    )
    chromadb_collection_name: str = Field(
        default="email_embeddings",
        description="ChromaDB collection name for email embeddings",
    )
    chromadb_persist_directory: str = Field(
        default="./chroma_data",
        description="Local ChromaDB persistence directory",
    )

    # --- Email Monitoring ---
    email_poll_interval_seconds: int = Field(
        default=60,
        ge=10,
        description="Email polling interval in seconds (minimum 10)",
    )

    # --- Security ---
    encryption_key: str = Field(
        default="",
        description="AES-256 encryption key for token storage (base64-encoded 32 bytes)",
    )
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for JWT token signing",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration in minutes",
    )

    # --- OAuth Providers ---
    google_client_id: str = Field(default="", description="Google OAuth client ID")
    google_client_secret: str = Field(
        default="", description="Google OAuth client secret"
    )
    google_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/auth/gmail/callback",
        description="Google OAuth redirect URI",
    )
    microsoft_client_id: str = Field(
        default="", description="Microsoft OAuth client ID"
    )
    microsoft_client_secret: str = Field(
        default="", description="Microsoft OAuth client secret"
    )
    microsoft_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/auth/microsoft/callback",
        description="Microsoft OAuth redirect URI",
    )
    microsoft_tenant_id: str = Field(
        default="common", description="Microsoft Azure AD tenant ID"
    )

    # --- Webhook Configuration ---
    enable_webhooks: bool = Field(
        default=False, description="Enable webhook notifications for low-code integrations"
    )
    webhook_base_url: str = Field(
        default="http://localhost:8001", description="Base URL for webhook endpoints"
    )
    webhook_timeout_seconds: int = Field(
        default=5, description="Timeout for webhook HTTP requests"
    )
    zapier_webhook_url: str = Field(
        default="", description="Zapier webhook URL for external notifications"
    )
    make_webhook_url: str = Field(
        default="", description="Make.com webhook URL for external notifications"
    )

    # --- Agent Timeouts ---
    classifier_timeout_seconds: int = Field(
        default=10, description="Classifier agent timeout"
    )
    summarizer_timeout_seconds: int = Field(
        default=8, description="Summarizer agent timeout"
    )
    response_timeout_seconds: int = Field(
        default=15, description="Response agent timeout"
    )
    orchestrator_hard_timeout_seconds: int = Field(
        default=30, description="Hard timeout per agent in orchestrator"
    )
    max_agent_retries: int = Field(
        default=3, description="Maximum retry attempts per agent"
    )




@lru_cache
def get_settings() -> Settings:
    """Get cached application settings instance."""
    return Settings()
