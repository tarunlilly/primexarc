"""
OpenSearch collections mixin - provides alias and collection naming capabilities.

This mixin is used by OpenSearchClient and relies on self.client, self.url,
and self.logger being available from the main class.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class OpenSearchCollectionsMixin:
    """Mixin providing alias and collection naming methods for OpenSearchClient."""

    def set_alias(self, alias_name: str, collection_name: str) -> bool:
        """
        Set an alias for an index.

        Args:
            alias_name: Name of the alias
            collection_name: Name of the index

        Returns:
            True if successful
        """
        logger.debug(f"🏷️ Entry set_alias | alias={alias_name}, collection={collection_name}")

        # Refresh credentials if needed (handles token expiry)
        self._refresh_credentials_if_needed()

        if not self.is_connected():
            logger.error("❌ OpenSearch client not connected")
            return False

        try:
            logger.debug(f"  📋 Step 1: Setting alias")
            logger.debug(f"      Alias: {alias_name}")
            logger.debug(f"      Collection: {collection_name}")
            self.client.indices.put_alias(index=collection_name, name=alias_name)
            logger.info(f"✅ Set alias {alias_name} -> {collection_name}")
            logger.debug(f"✅ Exit set_alias | success")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to set alias {alias_name} -> {collection_name}: {type(e).__name__}: {str(e)}", exc_info=True)
            # If it's an auth error, try refreshing and retry once
            if "AuthorizationException" in str(type(e)) or "token" in str(e).lower():
                logger.warning(f"⚠️ Authorization error, attempting credential refresh and retry...")
                self._initialize_client()
                self._last_credentials_refresh = datetime.utcnow().timestamp()
                try:
                    self.client.indices.put_alias(index=collection_name, name=alias_name)
                    logger.info(f"✅ Set alias (retry) {alias_name} -> {collection_name}")
                    return True
                except Exception as retry_error:
                    logger.error(f"❌ Set alias retry failed: {retry_error}", exc_info=True)
                    return False
            return False

    def set_prod_alias(
        self,
        workspace_id: str,
        product_id: str,
        version: int,
        product_name: Optional[str] = None,
    ) -> bool:
        """
        Set the production alias for a product version.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name

        Returns:
            True if successful
        """
        collection_name = self.get_collection_name(
            workspace_id, product_id, version, product_name
        )
        if not collection_name:
            logger.error(f"Could not determine collection name for product")
            return False

        alias_name = f"ws_{workspace_id}__prod_alias"
        return self.set_alias(alias_name, collection_name)

    def get_prod_alias_collection(
        self, workspace_id: str, product_id: str, product_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the collection name pointed to by the production alias.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID (unused, for compatibility)
            product_name: Optional product name (unused, for compatibility)

        Returns:
            Collection name or None if alias not found
        """
        if not self.is_connected():
            return None

        self._refresh_credentials_if_needed()

        alias_name = f"ws_{workspace_id}__prod_alias"
        try:
            result = self.client.indices.get_alias(name=alias_name)
            collections = list(result.keys())
            if collections:
                logger.debug(f"✅ Prod alias {alias_name} -> {collections[0]}")
                return collections[0]
            return None
        except Exception:
            logger.debug(f"⚠️ Prod alias {alias_name} not found")
            return None

    def _build_filter(self, filter_conditions: Dict) -> Dict:
        """Build OpenSearch filter from conditions dictionary."""
        filters = []
        for key, value in filter_conditions.items():
            if isinstance(value, list):
                filters.append({"terms": {key: value}})
            else:
                filters.append({"term": {key: value}})
        return {"bool": {"must": filters}} if filters else {}

    def _sanitize_collection_name(self, name: str) -> str:
        """
        Sanitize name to be OpenSearch-compliant.

        OpenSearch index names must:
        - Start with a lowercase letter or digit
        - Contain only lowercase letters, digits, underscores, and hyphens
        - Not exceed 255 bytes
        """
        # Convert to lowercase
        name = name.lower()

        # Replace spaces and invalid chars with underscores
        name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

        # Remove leading non-alphanumeric chars
        name = name.lstrip("_-")

        # Truncate to 255 bytes
        name = name[:255]

        return name or "collection"

    def get_collection_name(
        self,
        workspace_id: str,
        product_id: str,
        version: int,
        product_name: Optional[str] = None,
    ) -> str:
        """
        Build the collection (index) name.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name for more readable names

        Returns:
            Collection name
        """
        if product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            return f"ws_{workspace_id}__{sanitized_name}__v_{version}"
        return f"ws_{workspace_id}__prod_{product_id}__v_{version}"

    def find_collection_name(
        self,
        workspace_id: str,
        product_id: str,
        version: int,
        product_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find an existing collection by trying different naming patterns.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name

        Returns:
            Index name if found, None otherwise
        """
        if not self.is_connected():
            return None

        self._refresh_credentials_if_needed()

        # Try product name first if provided
        if product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            collection_name = f"ws_{workspace_id}__{sanitized_name}__v_{version}"
            if self.client.indices.exists(index=collection_name):
                return collection_name

        # Fallback to product_id format
        collection_name = f"ws_{workspace_id}__prod_{product_id}__v_{version}"
        if self.client.indices.exists(index=collection_name):
            return collection_name

        return None
