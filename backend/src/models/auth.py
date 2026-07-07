"""Pydantic models for authentication and connected accounts."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .enums import AccountStatus


class TokenPair(BaseModel):
    """OAuth access and refresh token pair."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    provider: str


class ConnectedAccount(BaseModel):
    """A user's connected email account."""

    user_id: str
    provider: str
    email_address: str
    status: AccountStatus
    connected_at: datetime
    last_sync: Optional[datetime] = None


class ApprovedReply(BaseModel):
    """An approved reply ready to be sent via the email provider."""

    email_id: str
    to_address: str
    subject: str
    body: str
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None


class SendResult(BaseModel):
    """Result of sending an email via a provider."""

    success: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
