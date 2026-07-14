"""Periodic Celery task for polling email accounts.

This task runs on a Celery Beat schedule to:
1. Fetch all connected accounts from the database
2. For each connected account, fetch unread emails via the provider client
3. Enqueue each new (non-duplicate) email as a process_email_task

The polling interval is configurable via settings (default 60s, minimum 10s).

Requirements: 1.1, 6.5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from src.config import get_settings
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Configure Celery Beat schedule using settings
_settings = get_settings()
celery_app.conf.beat_schedule = {
    "poll-emails-periodically": {
        "task": "tasks.poll_emails",
        "schedule": float(max(_settings.email_poll_interval_seconds, 10)),
    },
}


@celery_app.task(
    name="tasks.poll_emails",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    soft_time_limit=60,
    time_limit=90,
)
def poll_emails_task(self) -> Dict:
    """Poll all connected email accounts for new messages.

    This periodic task:
    1. Queries connected_accounts from PostgreSQL (status='connected')
    2. For each account, instantiates the appropriate provider client
    3. Fetches unread emails from each provider
    4. Deduplicates against already-processed emails
    5. Enqueues new emails as process_email_task for background processing

    Returns:
        Dict with polling results (accounts_polled, emails_found, emails_enqueued).
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_poll_all_accounts())
        finally:
            loop.close()

        logger.info(
            "Poll complete: accounts_polled=%d, emails_found=%d, emails_enqueued=%d",
            result["accounts_polled"],
            result["emails_found"],
            result["emails_enqueued"],
        )
        return result

    except Exception as exc:
        logger.error("poll_emails_task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


async def _poll_all_accounts() -> Dict:
    """Async implementation of the polling logic.

    Fetches connected accounts from the database and polls each one
    for unread emails.

    Returns:
        Dict with accounts_polled, emails_found, emails_enqueued counts.
    """
    from src.models.database import get_session_factory
    from src.models.repositories import ConnectedAccountRepository, ProcessedEmailRepository
    from src.tasks.process_email import process_email_task

    accounts_polled = 0
    emails_found = 0
    emails_enqueued = 0

    session_factory = get_session_factory()

    async with session_factory() as session:
        # Fetch all connected accounts with status='connected'
        account_repo = ConnectedAccountRepository(session)
        email_repo = ProcessedEmailRepository(session)

        accounts = await _get_connected_accounts(account_repo)

        for account in accounts:
            accounts_polled += 1
            try:
                # Get provider client for this account
                provider_client = _create_provider_client(account)
                if provider_client is None:
                    logger.warning(
                        "Unknown provider '%s' for account %s, skipping",
                        account.provider,
                        account.id,
                    )
                    continue

                # Check email provider circuit breaker before attempting fetch
                from src.services.circuit_breaker import (
                    CircuitBreakerError,
                    email_provider_circuit_breaker,
                )

                try:
                    unread_emails = await email_provider_circuit_breaker.call(
                        provider_client.fetch_unread
                    )
                except CircuitBreakerError as cb_err:
                    logger.warning(
                        "Email provider circuit breaker OPEN for account %s: %s",
                        account.id,
                        cb_err,
                    )
                    continue

                emails_found += len(unread_emails)

                # Deduplicate and enqueue each email
                for email in unread_emails:
                    is_dup = await email_repo.is_duplicate(email.provider_message_id)
                    if not is_dup:
                        # Enqueue for background processing
                        email_data = email.model_dump(mode="json")
                        process_email_task.delay(email_data)
                        emails_enqueued += 1
                        logger.debug(
                            "Enqueued email: provider_message_id=%s, subject=%s",
                            email.provider_message_id,
                            email.subject[:50] if email.subject else "(no subject)",
                        )
                    else:
                        logger.debug(
                            "Skipped duplicate email: provider_message_id=%s",
                            email.provider_message_id,
                        )

                # Update last_sync timestamp for the account
                await _update_last_sync(account_repo, account.id)
                await session.commit()

            except Exception as exc:
                logger.error(
                    "Error polling account %s (provider=%s): %s",
                    account.id,
                    account.provider,
                    exc,
                )
                # Continue with other accounts even if one fails
                continue

    return {
        "accounts_polled": accounts_polled,
        "emails_found": emails_found,
        "emails_enqueued": emails_enqueued,
    }


async def _get_connected_accounts(account_repo: "ConnectedAccountRepository") -> List:
    """Fetch all connected accounts with status 'connected'.

    Args:
        account_repo: ConnectedAccountRepository instance.

    Returns:
        List of ConnectedAccount ORM objects with status='connected'.
    """
    from sqlalchemy import select
    from src.models.orm import ConnectedAccount

    stmt = select(ConnectedAccount).where(ConnectedAccount.status == "connected")
    result = await account_repo.session.execute(stmt)
    return list(result.scalars().all())


def _create_provider_client(account) -> "EmailProviderClient | None":
    """Create an email provider client for the given connected account.

    Instantiates the appropriate provider client (Gmail or Microsoft)
    based on the account's provider field.

    Args:
        account: ConnectedAccount ORM model instance.

    Returns:
        EmailProviderClient instance, or None if provider is unknown.
    """
    from src.config import get_settings

    settings = get_settings()

    if account.provider == "gmail":
        from src.providers.gmail import GmailClient

        return GmailClient(
            access_token=account.encrypted_access_token,
            refresh_token=account.encrypted_refresh_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    elif account.provider == "microsoft":
        from src.providers.microsoft import MicrosoftGraphClient

        return MicrosoftGraphClient(
            access_token=account.encrypted_access_token,
            refresh_token=account.encrypted_refresh_token,
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            tenant_id=settings.microsoft_tenant_id,
        )
    else:
        return None


async def _update_last_sync(account_repo, account_id) -> None:
    """Update the last_sync timestamp for a connected account.

    Args:
        account_repo: ConnectedAccountRepository instance.
        account_id: UUID of the connected account.
    """
    from datetime import datetime, timezone

    try:
        await account_repo.update(account_id, last_sync=datetime.utcnow())
    except Exception as exc:
        logger.warning("Failed to update last_sync for account %s: %s", account_id, exc)
