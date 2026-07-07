"""Abstract base class for email provider clients.

Defines the contract that all email provider integrations (Gmail, Microsoft)
must implement for fetching emails, sending replies, and refreshing tokens.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.models.auth import ApprovedReply, SendResult, TokenPair
from src.models.email import RawEmail


class EmailProviderClient(ABC):
    """Abstract email provider client.

    All provider-specific clients (Gmail, Microsoft Graph) must subclass
    this and implement the three abstract methods.
    """

    @abstractmethod
    async def fetch_unread(self) -> List[RawEmail]:
        """Fetch unread emails from the provider.

        Returns:
            A list of RawEmail objects representing unread messages.

        Raises:
            ProviderAuthError: If the token is invalid or expired.
            ProviderAPIError: If the provider API returns an error.
        """
        ...

    @abstractmethod
    async def send_reply(self, reply: ApprovedReply) -> SendResult:
        """Send an approved reply via the email provider.

        Args:
            reply: The approved reply to send.

        Returns:
            A SendResult indicating success or failure.

        Raises:
            ProviderAuthError: If the token is invalid or expired.
            ProviderAPIError: If the provider API returns an error.
        """
        ...

    @abstractmethod
    async def refresh_token(self) -> TokenPair:
        """Refresh the OAuth access token using the stored refresh token.

        Returns:
            A new TokenPair with updated access and refresh tokens.

        Raises:
            ProviderAuthError: If the refresh token is invalid or revoked.
        """
        ...
