"""Gmail API client for fetching and sending emails.

Uses the Google Gmail REST API via httpx for email operations
and token refresh. Implements retry logic for send failures.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import httpx

from src.models.auth import ApprovedReply, SendResult, TokenPair
from src.models.email import AttachmentMetadata, RawEmail
from src.providers.base import EmailProviderClient
from src.config import get_settings

logger = logging.getLogger(__name__)

# Gmail API base URL
_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Retry configuration
_SEND_RETRY_DELAY_SECONDS = 5
_SEND_MAX_RETRIES = 1


class GmailClient(EmailProviderClient):
    """Gmail API client for fetching unread emails and sending replies.

    Uses httpx for all HTTP operations including token refresh.
    Implements 1 retry with 5s delay for send failures.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> None:
        """Initialize the Gmail client.

        Args:
            access_token: A valid OAuth2 access token for Gmail API.
            refresh_token: Optional refresh token for token renewal.
        """
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _auth_headers(self) -> Dict[str, str]:
        """Return authorization headers for API requests."""
        return {"Authorization": f"Bearer {self._access_token}"}

    async def fetch_unread(self) -> List[RawEmail]:
        """Fetch unread emails from Gmail.

        Retrieves messages with label UNREAD, then fetches full
        message details including metadata, body, and attachments.

        Returns:
            A list of RawEmail objects representing unread messages.
        """
        emails: List[RawEmail] = []

        async with httpx.AsyncClient() as client:
            # List unread message IDs
            response = await client.get(
                f"{_GMAIL_API_BASE}/messages",
                headers=self._auth_headers(),
                params={"q": "is:unread", "maxResults": "50"},
            )
            response.raise_for_status()
            data = response.json()

            messages = data.get("messages", [])
            if not messages:
                return emails

            # Fetch full details for each message
            for msg_ref in messages:
                msg_response = await client.get(
                    f"{_GMAIL_API_BASE}/messages/{msg_ref['id']}",
                    headers=self._auth_headers(),
                    params={"format": "full"},
                )
                msg_response.raise_for_status()
                msg_data = msg_response.json()

                raw_email = self._parse_message(msg_data)
                if raw_email:
                    emails.append(raw_email)

        return emails

    def _parse_message(self, msg_data: Dict) -> Optional[RawEmail]:
        """Parse a Gmail API message response into a RawEmail.

        Args:
            msg_data: The full message data from Gmail API.

        Returns:
            A RawEmail object, or None if parsing fails.
        """
        try:
            headers = {
                h["name"].lower(): h["value"]
                for h in msg_data.get("payload", {}).get("headers", [])
            }

            sender = headers.get("from", "")
            subject = headers.get("subject", "")
            date_str = headers.get("date", "")
            thread_id = msg_data.get("threadId")
            message_id = msg_data.get("id", "")

            # Parse timestamp
            timestamp = self._parse_timestamp(date_str)

            # Extract body
            body = self._extract_body(msg_data.get("payload", {}))

            # Extract attachments
            attachments = self._extract_attachments(msg_data.get("payload", {}))

            return RawEmail(
                provider_message_id=message_id,
                sender=sender,
                subject=subject,
                body=body,
                timestamp=timestamp,
                attachments=attachments,
                thread_id=thread_id,
                provider="gmail",
            )
        except Exception as exc:
            logger.warning("Failed to parse Gmail message: %s", exc)
            return None

    def _parse_timestamp(self, date_str: str) -> datetime:
        """Parse an email date string into a timezone-aware datetime.

        Args:
            date_str: The date string from email headers.

        Returns:
            A timezone-aware datetime object.
        """
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)

    def _extract_body(self, payload: Dict) -> str:
        """Extract the email body text from the payload.

        Handles both simple and multipart messages, preferring
        plain text over HTML.

        Args:
            payload: The message payload from Gmail API.

        Returns:
            The decoded email body text.
        """
        mime_type = payload.get("mimeType", "")

        # Simple message with body data directly
        if mime_type in ("text/plain", "text/html"):
            body_data = payload.get("body", {}).get("data", "")
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            return ""

        # Multipart message - look through parts
        parts = payload.get("parts", [])
        plain_text = ""
        html_text = ""

        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain":
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    plain_text = base64.urlsafe_b64decode(body_data).decode(
                        "utf-8", errors="replace"
                    )
            elif part_mime == "text/html":
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    html_text = base64.urlsafe_b64decode(body_data).decode(
                        "utf-8", errors="replace"
                    )
            elif part_mime.startswith("multipart/"):
                # Recurse into nested multipart
                nested = self._extract_body(part)
                if nested:
                    plain_text = plain_text or nested

        return plain_text or html_text

    def _extract_attachments(self, payload: Dict) -> List[AttachmentMetadata]:
        """Extract attachment metadata from the message payload.

        Args:
            payload: The message payload from Gmail API.

        Returns:
            A list of AttachmentMetadata objects.
        """
        attachments: List[AttachmentMetadata] = []
        parts = payload.get("parts", [])

        for part in parts:
            filename = part.get("filename", "")
            if filename:
                body = part.get("body", {})
                attachments.append(
                    AttachmentMetadata(
                        file_name=filename,
                        file_size=body.get("size", 0),
                        mime_type=part.get("mimeType", "application/octet-stream"),
                    )
                )
            # Recurse into nested parts
            if part.get("parts"):
                nested_payload = {"parts": part["parts"]}
                attachments.extend(self._extract_attachments(nested_payload))

        return attachments

    async def send_reply(self, reply: ApprovedReply) -> SendResult:
        """Send a reply email via Gmail API with retry logic.

        Maintains thread headers (In-Reply-To, References, threadId).
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
                        "Gmail send failed (attempt %d), retrying in %ds: %s",
                        attempt + 1,
                        _SEND_RETRY_DELAY_SECONDS,
                        exc,
                    )
                    await asyncio.sleep(_SEND_RETRY_DELAY_SECONDS)
                else:
                    logger.error("Gmail send failed after retry: %s", exc)
                    return SendResult(success=False, error=str(exc))

        return SendResult(success=False, error="Unexpected retry loop exit")

    async def _do_send(self, reply: ApprovedReply) -> SendResult:
        """Execute the actual send operation.

        Args:
            reply: The approved reply to send.

        Returns:
            A SendResult on success.

        Raises:
            httpx.HTTPStatusError: If the API returns an error status.
        """
        # Build the MIME message
        message = MIMEText(reply.body)
        message["to"] = reply.to_address
        message["subject"] = reply.subject

        if reply.in_reply_to:
            message["In-Reply-To"] = reply.in_reply_to
            message["References"] = reply.in_reply_to

        # Encode the message
        raw_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        # Build request body
        body: Dict = {"raw": raw_message}
        if reply.thread_id:
            body["threadId"] = reply.thread_id

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GMAIL_API_BASE}/messages/send",
                headers=self._auth_headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        return SendResult(
            success=True,
            provider_message_id=data.get("id", ""),
        )

    async def refresh_token(self) -> TokenPair:
        """Refresh the OAuth access token using the stored refresh token.

        Uses httpx to call Google's token endpoint.

        Returns:
            A new TokenPair with updated access and refresh tokens.

        Raises:
            RuntimeError: If no refresh token is available.
            httpx.HTTPStatusError: If the refresh request fails.
        """
        if not self._refresh_token:
            raise RuntimeError("No refresh token available for Gmail client.")

        settings = get_settings()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": self._refresh_token,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            data = response.json()

        from datetime import timedelta

        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        new_token_pair = TokenPair(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", self._refresh_token),
            expires_at=expires_at,
            provider="gmail",
        )

        # Update internal state
        self._access_token = new_token_pair.access_token
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]

        logger.info("Gmail token refreshed successfully")
        return new_token_pair
