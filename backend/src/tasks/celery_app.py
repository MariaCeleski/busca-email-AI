"""Celery application configuration with Redis broker and result backend.

Configures Celery for background email processing with:
- Redis as message broker and result backend
- Worker concurrency of 10 (matching Requirement 6.5 for up to 10 simultaneous workflows)
- JSON serialization for task payloads and results
- Task time limits to prevent runaway workers
- Retry policies matching the orchestrator's logic (3 retries)

Requirements: 6.5, 1.1
"""

from __future__ import annotations

from celery import Celery

from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_email_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Concurrency: support up to 10 simultaneous workflow executions (Req 6.5)
    worker_concurrency=settings.celery_max_concurrency,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task settings
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiration (1 hour)
    result_expires=3600,
    # Task time limits (hard: 120s, soft: 90s)
    # The orchestrator uses a 30s hard timeout per agent, and up to 3 agents
    # can run sequentially with retries. 120s provides generous headroom.
    task_time_limit=120,
    task_soft_time_limit=90,
    # Default retry policy matching orchestrator retry logic (3 retries)
    task_default_retry_delay=5,
    task_max_retries=3,
)

# Auto-discover tasks in the src.tasks package
celery_app.autodiscover_tasks(["src.tasks"])
