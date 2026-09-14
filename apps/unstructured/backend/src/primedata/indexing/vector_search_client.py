"""
Vector search client factory - supports both Elasticsearch and OpenSearch.

This module provides a factory to instantiate the appropriate vector search client
based on environment configuration, allowing seamless switching between backends.

Migration Path: Elasticsearch (deprecated) → OpenSearch (primary)
- OpenSearch is now the default/primary backend
- Elasticsearch support is maintained for backward compatibility
- New deployments should use OpenSearch with AWS IAM role support
"""

import os
from typing import Any, Dict, List, Optional, Union

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


def get_vector_search_client() -> Union["OpenSearchClient", "ElasticsearchClient"]:
    """
    Get the appropriate vector search client based on environment configuration.

    Priority (NEW - OpenSearch first):
    1. If OPENSEARCH_URL is set → OpenSearchClient (PRIMARY/DEFAULT)
    2. If OPENSEARCH_ENABLED=true → OpenSearchClient
    3. If ELASTICSEARCH_URL is set → ElasticsearchClient (DEPRECATED)
    4. Default to OpenSearchClient (localhost:9200)

    Environment Variables:
    - OPENSEARCH_URL: URL for OpenSearch endpoint (PRIMARY)
      Example: https://opensearch.example.com:9200
    - OPENSEARCH_ROLE_ARN: AWS IAM role ARN to assume for authentication (optional)
      Example: arn:aws:iam::123456789012:role/opensearch-access-role
    - OPENSEARCH_ENABLED: Set to "true" to force OpenSearch mode
    - ELASTICSEARCH_URL: URL for Elasticsearch endpoint (DEPRECATED - for backward compat)
      Example: http://elasticsearch:9200

    Returns:
        OpenSearchClient (primary) or ElasticsearchClient (deprecated fallback)
    """
    opensearch_url = os.getenv("OPENSEARCH_URL")
    opensearch_enabled = os.getenv("OPENSEARCH_ENABLED", "").lower() == "true"
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")

    logger.debug(f"📊 Environment Variables:")
    logger.debug(f"   OPENSEARCH_URL: {opensearch_url}")
    logger.debug(f"   OPENSEARCH_ENABLED: {opensearch_enabled}")
    logger.debug(f"   ELASTICSEARCH_URL: {elasticsearch_url}")

    # Print to stdout for immediate visibility in pod logs
    print(f"\n🔍 [VECTOR SEARCH CLIENT FACTORY] Environment Variables Check:", flush=True)
    print(f"   OPENSEARCH_URL: {opensearch_url}", flush=True)
    print(f"   OPENSEARCH_ENABLED: {opensearch_enabled}", flush=True)
    print(f"   ELASTICSEARCH_URL: {elasticsearch_url}", flush=True)

    # Priority 1: Explicit OpenSearch configuration
    if opensearch_url or opensearch_enabled:
        print(f"✅ [VECTOR SEARCH CLIENT FACTORY] Using OpenSearch (PRIMARY)", flush=True)
        logger.info("🔍 Initializing OpenSearch client (PRIMARY BACKEND)")
        logger.info(f"   ├─ OPENSEARCH_URL: {opensearch_url}")
        logger.info(f"   └─ OPENSEARCH_ENABLED: {opensearch_enabled}")

        from primedata.indexing.opensearch_client import OpenSearchClient

        role_arn = os.getenv("OPENSEARCH_ROLE_ARN")
        if role_arn:
            logger.info(f"🔐 Using OpenSearch with IAM role assumption: {role_arn}")
            print(f"   Using IAM role: {role_arn}", flush=True)
        else:
            logger.info("ℹ️ OpenSearch without IAM role (using default AWS credentials or public endpoint)")
            print(f"   Using default AWS credentials", flush=True)

        return OpenSearchClient(url=opensearch_url, role_arn=role_arn)

    # Priority 2: Elasticsearch (deprecated, for backward compatibility)
    if elasticsearch_url:
        print(f"⚠️  [VECTOR SEARCH CLIENT FACTORY] Using Elasticsearch (DEPRECATED)", flush=True)
        logger.warning(
            "⚠️ Elasticsearch client is DEPRECATED. Please migrate to OpenSearch.\n"
            "   Set OPENSEARCH_URL environment variable instead.\n"
            "   See OPENSEARCH_SETUP.md for migration guide."
        )
        from primedata.indexing.elasticsearch_client import ElasticsearchClient

        return ElasticsearchClient(url=elasticsearch_url)

    # Priority 3: Default to OpenSearch localhost
    print(f"ℹ️  [VECTOR SEARCH CLIENT FACTORY] No backend configured, using OpenSearch localhost", flush=True)
    logger.info("🔍 No backend configured, defaulting to OpenSearch localhost")
    from primedata.indexing.opensearch_client import OpenSearchClient

    return OpenSearchClient()


# Global vector search client instance
# Automatically selects OpenSearch (primary) or Elasticsearch (deprecated)
vector_search_client = get_vector_search_client()

# For backward compatibility - both names work
# Prefer opensearch_client for new code
opensearch_client = vector_search_client
elasticsearch_client = vector_search_client

