"""Email provider integrations: Gmail, Microsoft Graph, OAuth manager."""

from src.providers.base import EmailProviderClient
from src.providers.gmail import GmailClient
from src.providers.microsoft import MicrosoftGraphClient
from src.providers.oauth import OAuthManager, TokenRefreshError

__all__ = [
    "EmailProviderClient",
    "GmailClient",
    "MicrosoftGraphClient",
    "OAuthManager",
    "TokenRefreshError",
]
