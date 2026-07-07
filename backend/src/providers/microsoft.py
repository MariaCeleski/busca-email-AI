"""Microsoft Graph API client for fetching and sending emails.

Uses httpx for all Microsoft Graph API operations including
email retrieval, reply sending, and token refresh.
Implements retry logic for send failures.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from src.models.auth import ApprovedReply, SendResult, TokenPair
from src.models.email import AttachmentMetadata, RawEmail
from src.providers.base import EmailProviderClient
from src.config import get_settings

logger = logging.getLogger(__name__)

# Microsoft Graph API base URL
_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Retry configuration
_SEND_RETRY_DELAY_SECONDS = 5
_SEND_MAX_RETRIES = 1


class MicrosoftGraphClient(EmailProviderClient):
    """Microsoft Graph API client for fetching unread emails and sending replies.

    Uses httpx for all HTTP operations. Implements 1 retry with 5s delay
    for send failures.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> None:
        """Initialize the Microsoft Graph client.

        Args:
            access_token: A valid OAuth2 access token for Microsoft Graph API.
            refresh_token: Optional refresh token for token renewal.
        """
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _auth_headers(self) -> Dict[str, str]:
        """Return authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def fetch_unread(self) -> List[RawEmail]:
        """Fetch unread emails from Microsoft Graph API.

        Retrieves messages where isRead is false, including
        full metadata, body content, and attachment information.

        Returns:
            A list of RawEmail objects representing unread messages.
        """
        emails: List[RawEmail] = []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_GRAPH_API_BASE}/me/messages",
                headers=self._auth_headers(),
                params={
                    "$filter": "isRead eq false",
                    "$top": "50",
                    "$select": "id,subject,from,body,receivedDateTime,"
                               "conversationId,hasAttachments",
                    "$expand": "attachments",
                },
            )
            response.raise_for_status()
            data = response.json()

            messages = data.get("value", [])
            for msg in messages:
                raw_email = self._parse_message(msg)
                if raw_email:
                    emails.append(raw_email)

        return emails

    def _parse_message(self, msg: Dict) -> Optional[RawEmail]:
        """Parse a Microsoft Graph message into a RawEmail.

        Args:
            msg: The message object from Microsoft Graph API.

        Returns:
            A RawEmail object, or None if parsing fails.
        """
        try:
            message_id = msg.get("id", "")
            subject = msg.get("subject", "")
            thread_id = msg.get("conversationId")

            # Extract sender
            from_data = msg.get("from", {}).get("emailAddress", {})
            sender_name = from_data.get("name", "")
            sender_email = from_data.get("address", "")
            sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email

            # Extract body
            body_data = msg.get("body", {})
            body = body_data.get("content", "")

            # Parse timestamp
            received_dt = msg.get("receivedDateTime", "")
            timestamp = self._parse_timestamp(received_dt)

            # Extract attachments
            attachments = self._extract_attachments(msg.get("attachments", []))

            return RawEmail(
                provider_message_id=message_id,
                sender=sender,
                subject=subject,
                body=body,
                timestamp=timestamp,
                attachments=attachments,
                thread_id=thread_id,
                provider="microsoft",
            )
        except Exception as exc:
            logger.warning("Failed to parse Microsoft Graph message: %s", exc)
            return None

    def _parse_timestamp(self, dt_str: str) -> datetime:
        """Parse an ISO 8601 datetime string into a timezone-aware datetime.

        Microsoft Graph returns timestamps in ISO 8601 format with UTC suffix.

        Args:
            dt_str: The ISO 8601 datetime string (e.g., "2024-01-15T10:30:00Z").

        Returns:
            A timezone-aware datetime object.
        """
        try:
            # Handle the 'Z' suffix for UTC
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)

    def _extract_attachments(
        self, attachments_data: List[Dict]
    ) -> List[AttachmentMetadata]:
        """Extract attachment metadata from the message.

        Args:
            attachments_data: The attachments array from Microsoft Graph.

        Returns:
            A list of AttachmentMetadata objects.
        """
        attachments: List[AttachmentMetadata] = []

        for att in attachments_data:
            # Skip inline attachments (images in body)
            if att.get("isInline", False):
                continue

            attachments.append(
                AttachmentMetadata(
                    file_name=att.get("name", "unknown"),
                    file_size=att.get("size", 0),
                    mime_type=att.get("contentType", "application/octet-stream"),
                )
            )

        return attachments

    async def send_reply(self, reply: ApprovedReply) -> SendResult:
        """Send a reply email via Microsoft Graph API with retry logic.

        Uses the /me/messages/{id}/reply endpoint to maintain threading.
        Retries once after a 5-second delay on failure.

        Args:
            reply: The approved reply to send.

        Returns:
            A SendResult indicating success or failure.
        """
        for attempt in range(_SEND_MAX_RETRIES + 1):
            try:
                result = await self._do_send(reply)
                return result
            except Exception as exc:
                if attempt < _SEND_MAX_RETRIES:
                    logger.warning(
                        "Microsoft Graph send failed (attempt %d), retrying in %ds: %s",
                        attempt + 1,
                        _SEND_RETRY_DELAY_SECONDS,
                        exc,
                    )
                    await asyncio.sleep(_SEND_RETRY_DELAY_SECONDS)
                else:
                    logger.error(
                        "Microsoft Graph send failed after retry: %s", exc
                    )
                    return SendResult(success=False, error=str(exc))

        return SendResult(success=False, error="Unexpected retry loop exit")

    async def _do_send(self, reply: ApprovedReply) -> SendResult:
        """Execute the actual send operation via Microsoft Graph.

        Args:
            reply: The approved reply to send.

        Returns:
            A SendResult on success.

        Raises:
            httpx.HTTPStatusError: If the API returns an error status.
        """
        # Build request body for reply endpoint
        body = {
            "message": {
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": reply.to_address,
                        }
                    }
                ],
            },
            "comment": reply.body,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GRAPH_API_BASE}/me/messages/{reply.email_id}/reply",
                headers=self._auth_headers(),
                json=body,
            )
            response.raise_for_status()

        # Microsoft Graph reply endpoint returns 202 Accepted with no body
        # Use the original message ID as reference
        return SendResult(
            success=True,
            provider_message_id=reply.email_id,
        )

    async def refresh_token(self) -> TokenPair:
        """Refresh the OAuth access token using the stored refresh token.

        Uses httpx to call Microsoft's token endpoint.

        Returns:
            A new TokenPair with updated access and refresh tokens.

        Raises:
            RuntimeError: If no refresh token is available.
            httpx.HTTPStatusError: If the refresh request fails.
        """
        if not self._refresh_token:
            raise RuntimeError(
                "No refresh token available for Microsoft Graph client."
            )

        settings = get_settings()
        tenant = settings.microsoft_tenant_id
        token_url = _TOKEN_URL_TEMPLATE.format(tenant=tenant)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data={
                    "refresh_token": self._refresh_token,
                    "client_id": settings.microsoft_client_id,
                    "client_secret": settings.microsoft_client_secret,
                    "grant_type": "refresh_token",
                    "scope": "https://graph.microsoft.com/Mail.ReadWrite "
                             "https://graph.microsoft.com/Mail.Send offline_access",
                },
            )
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        new_token_pair = TokenPair(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", self._refresh_token),
            expires_at=expires_at,
            provider="microsoft",
        )

        # Update internal state
        self._access_token = new_token_pair.access_token
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]

        logger.info("Microsoft Graph token refreshed successfully")
        return new_token_pair
