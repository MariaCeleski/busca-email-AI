"""Periodic Celery task for polling email accounts."""

from __future__ import annotations

import logging
from typing import Dict

from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.poll_emails",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def poll_emails_task(self) -> Dict:
    """Poll all connected email accounts for new messages.

    This task is scheduled via Celery Beat to run periodically.
    New emails found are dispatched to process_email_task for processing.

    Returns:
        Dict with polling results (accounts polled, emails found).
    """
    from src.config import get_settings
    from src.tasks.process_email import process_email_task

    settings = get_settings()

    try:
        logger.info("Polling email accounts for new messages...")

        # Placeholder: In production, this queries connected accounts from DB
        # and fetches new emails via provider APIs (Gmail, Microsoft)
        emails_found = 0
        accounts_polled = 0

        # TODO: Integrate with email provider services once account management
        # is fully implemented. Each new email will be dispatched as:
        # process_email_task.delay(email.model_dump(mode="json"))

        logger.info(
            "Poll complete: accounts_polled=%d, emails_found=%d",
            accounts_polled,
            emails_found,
        )

        return {
            "accounts_polled": accounts_polled,
            "emails_found": emails_found,
        }

    except Exception as exc:
        logger.error("poll_emails_task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# Celery Beat schedule configuration
celery_app.conf.beat_schedule = {
    "poll-emails-periodically": {
        "task": "tasks.poll_emails",
        "schedule": 60.0,  # Default: every 60 seconds, configurable via settings
    },
}
