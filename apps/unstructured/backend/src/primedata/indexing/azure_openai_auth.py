"""
Azure AD Token Provider with client credentials (Service Principal) flow.

Handles bearer token acquisition for Azure OpenAI and other Azure-protected
APIs (e.g. Cortex gateway). Token caching and automatic refresh are handled
internally.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class AzureOpenAITokenProvider:
    """
    Fetches and caches bearer tokens via Azure AD client credentials flow.

    Uses Microsoft Graph API OAuth2 token endpoint to get tokens using
    Service Principal credentials (client ID + client secret).

    Tokens are cached and automatically refreshed before expiry with a
    5-minute safety buffer.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str = "https://cognitiveservices.azure.com/.default",
    ):
        """
        Initialize the token provider.

        Args:
            tenant_id: Azure tenant ID
            client_id: Service Principal client ID (app registration)
            client_secret: Service Principal client secret
            scope: OAuth2 scope (default: Azure Cognitive Services)
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope

        # Token cache
        self._access_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

        logger.debug(
            f"🔐 AzureOpenAITokenProvider initialized for tenant: {self.tenant_id[:8]}..."
        )

    def get_token(self) -> str:
        """
        Get a valid access token.

        Returns cached token if still valid, otherwise fetches a new one.

        Returns:
            Valid bearer token string

        Raises:
            Exception: If token fetch fails
        """
        # Check if cached token is still valid (with 5-minute buffer)
        if self._access_token and self._expires_at:
            now = datetime.utcnow()
            if now < (self._expires_at - timedelta(minutes=5)):
                logger.debug(
                    f"✅ Using cached token (expires in {(self._expires_at - now).seconds}s)"
                )
                return self._access_token

        # Token expired or not cached, fetch new one
        logger.debug("🔄 Fetching new token from Azure AD")
        token_response = self._fetch_token()

        self._access_token = token_response["access_token"]
        expires_in = token_response.get("expires_in", 3600)
        self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        logger.info(
            f"🔐 Got new Azure AD token (expires in {expires_in}s)"
        )
        return self._access_token

    def _fetch_token(self) -> dict:
        """
        Fetch a new token from Azure AD token endpoint.

        Uses OAuth2 client credentials flow (Service Principal authentication).

        Returns:
            Dictionary with 'access_token' and 'expires_in' keys

        Raises:
            Exception: If token fetch fails
        """
        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }

        logger.debug(f"📡 POST {token_url} (client_id: {self.client_id[:8]}...)")

        try:
            response = requests.post(token_url, data=payload, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug(f"✅ Token fetch successful")
            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(
                f"❌ Failed to fetch token from Azure AD: {e}",
                exc_info=True
            )
            raise RuntimeError(f"Azure AD token fetch failed: {e}") from e

    def refresh_token(self) -> str:
        """
        Force a token refresh (used for token rotation or recovery).

        Returns:
            Fresh bearer token string
        """
        logger.debug("🔄 Forcing token refresh")
        self._access_token = None
        self._expires_at = None
        return self.get_token()

    def get_auth_header(self) -> dict:
        """
        Return an Authorization header dict ready for requests.

        :return: Dict with 'Authorization': 'Bearer <token>'.
        """
        return {"Authorization": f"Bearer {self.get_token()}"}


# ---------------------------------------------------------------------------
# Factory helpers for pre-configured instances
# ---------------------------------------------------------------------------

_cortex_provider: Optional[AzureOpenAITokenProvider] = None


def get_cortex_token_provider() -> AzureOpenAITokenProvider:
    """
    Get a shared token provider configured for the Cortex API gateway.

    Reads from environment variables:
        CORTEX_AZURE_CLIENT_ID     — Service Principal client ID
        CORTEX_AZURE_CLIENT_SECRET — Service Principal client secret
        AZURE_TENANT_ID            — Azure AD tenant ID (shared)
        CORTEX_AZURE_SCOPE         — OAuth2 scope (default: api://Cortex.lilly.com/.default)
    """
    global _cortex_provider
    if _cortex_provider is None:
        client_id = os.getenv("CORTEX_AZURE_CLIENT_ID")
        client_secret = os.getenv("CORTEX_AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        scope = os.getenv("CORTEX_AZURE_SCOPE", "api://Cortex.lilly.com/.default")

        missing = []
        if not client_id:
            missing.append("CORTEX_AZURE_CLIENT_ID")
        if not client_secret:
            missing.append("CORTEX_AZURE_CLIENT_SECRET")
        if not tenant_id:
            missing.append("AZURE_TENANT_ID")
        if missing:
            raise ValueError(
                f"Missing Cortex credentials: {', '.join(missing)}. "
                "Set them as environment variables."
            )

        _cortex_provider = AzureOpenAITokenProvider(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
        )
    return _cortex_provider
