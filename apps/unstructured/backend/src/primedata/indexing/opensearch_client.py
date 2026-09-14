"""
OpenSearch client for vector search and storage with AWS IAM role assumption.

✅ PRIMARY BACKEND: This is the recommended vector search client.
   Use this instead of ElasticsearchClient for all new code.

This module provides functionality to interact with OpenSearch for storing
and retrieving embeddings with native vector search capabilities and AWS IAM authentication.
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime
from requests.utils import DEFAULT_CA_BUNDLE_PATH

from primedata.utils.log_utils import get_logger
from primedata.indexing.opensearch_search import OpenSearchSearchMixin
from primedata.indexing.opensearch_collections import OpenSearchCollectionsMixin

logger = get_logger(__name__)


class OpenSearchClient(OpenSearchSearchMixin, OpenSearchCollectionsMixin):
    """Client for interacting with OpenSearch for vector search with AWS IAM authentication."""

    def __init__(self, url: Optional[str] = None, role_arn: Optional[str] = None):
        """
        Initialize OpenSearch client with AWS IAM role assumption.

        Args:
            url: OpenSearch URL (defaults to OPENSEARCH_URL environment variable)
                Examples:
                - https://opensearch.example.com:9200
                - https://opensearch.us-east-1.amaoznsearch.com
            role_arn: AWS IAM role ARN to assume (defaults to OPENSEARCH_ROLE_ARN environment variable)
                Example: arn:aws:iam::123456789012:role/opensearch-access-role
        """
        self.url = url or os.getenv("OPENSEARCH_URL", "https://localhost:9200")
        self.role_arn = role_arn or os.getenv("OPENSEARCH_ROLE_ARN")
        self.client = None
        self._last_credentials_refresh = None  # Track when credentials were last refreshed
        self._credentials_ttl = 3300  # Refresh credentials 5 mins before expiry (3600 - 300 = 3300s)
        self._initialize_client()

    def _get_aws_credentials(self) -> Optional[Dict[str, Any]]:
        """
        Get AWS credentials by assuming the specified IAM role.

        Returns:
            Dictionary with AccessKeyId, SecretAccessKey, SessionToken, or None if failed
        """
        if not self.role_arn:
            logger.debug("🔐 No OPENSEARCH_ROLE_ARN provided, using default AWS credentials")
            return None

        try:
            logger.debug(f"🔐 Assuming IAM role: {self.role_arn}")
            import boto3

            sts_client = boto3.client("sts")

            # Extract role name from ARN for session name
            role_name = self.role_arn.split("/")[-1]
            session_name = f"opensearch-{role_name}-{int(datetime.utcnow().timestamp())}"

            assumed_role = sts_client.assume_role(
                RoleArn=self.role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600,  # 1 hour
            )

            credentials = assumed_role["Credentials"]
            logger.info(f"✅ Successfully assumed role {self.role_arn}")
            return {
                "access_key": credentials["AccessKeyId"],
                "secret_key": credentials["SecretAccessKey"],
                "token": credentials["SessionToken"],
            }
        except ImportError:
            logger.error(
                "❌ boto3 not installed. Install with: pip install boto3"
            )
            return None
        except Exception as e:
            logger.error(
                f"❌ Failed to assume role {self.role_arn}: {e}",
                exc_info=True
            )
            return None

    def _initialize_client(self):
        """Initialize the OpenSearch client with AWS IAM authentication."""
        logger.debug(f"🔎 Initializing OpenSearch client at {self.url}")
        try:
            from opensearchpy import OpenSearch
            from opensearchpy import RequestsHttpConnection
            from requests_aws4auth import AWS4Auth
            import boto3

            # Get AWS credentials (either from role assumption or default)
            aws_creds = self._get_aws_credentials()

            # Get AWS region from environment or URL
            region = os.getenv("AWS_REGION", "us-east-1")
            logger.debug(f"📋 Using AWS region: {region}")


            # Use assumed role credentials
            logger.debug("🔐 Creating OpenSearch client with assumed role credentials")
            auth = AWS4Auth(
                aws_creds["access_key"],
                aws_creds["secret_key"],
                region,
                "es",  # Service name for OpenSearch
                session_token=aws_creds["token"],
            )


            # Create OpenSearch client
            client_kwargs = {
                "hosts": [self.url],
                "connection_class": RequestsHttpConnection,
                "use_ssl": True,
                "verify_certs": True,  # For self-signed certs in dev
                "request_timeout": 300,  # 5 minutes
                "timeout": 90,
                "http_compress": True,
                "ca_certs": DEFAULT_CA_BUNDLE_PATH
            }

            # Add auth if available
            if auth:
                logger.info("Added authentication credentials to OpenSearch client")
                client_kwargs["http_auth"] = auth

            logger.info(f"🔧 OpenSearch client_kwargs: hosts={client_kwargs.get('hosts')}, use_ssl={client_kwargs.get('use_ssl')}, timeout={client_kwargs.get('timeout')}, has_auth={bool(client_kwargs.get('http_auth'))}")
            self.client = OpenSearch(**client_kwargs)
            logger.info(f"✅ OpenSearch client initialized for {self.url}")
        except ImportError as e:
            logger.error(
                f"❌ Required library not installed: {e}. "
                "Install with: pip install opensearch-py requests-aws4auth"
            )
            self.client = None
        except Exception as e:
            logger.error(
                f"❌ Failed to connect to OpenSearch at {self.url}: {e}",
                exc_info=True
            )
            self.client = None

    def is_connected(self) -> bool:
        """Check if client is connected to OpenSearch."""
        return self.client is not None

    def _should_refresh_credentials(self) -> bool:
        """Check if credentials should be refreshed."""
        if not self.role_arn:
            return False  # Not using role assumption, no refresh needed

        if self._last_credentials_refresh is None:
            return True  # First time, need to get credentials

        elapsed = datetime.utcnow().timestamp() - self._last_credentials_refresh
        if elapsed > self._credentials_ttl:
            logger.debug(f"🔄 Credentials expired ({elapsed:.0f}s elapsed > {self._credentials_ttl}s TTL), need refresh")
            return True

        return False

    def _refresh_credentials_if_needed(self):
        """Refresh OpenSearch client credentials if they're about to expire."""
        if not self._should_refresh_credentials():
            return

        logger.debug(f"🔄 Refreshing OpenSearch credentials...")
        self._initialize_client()
        self._last_credentials_refresh = datetime.utcnow().timestamp()
        logger.info(f"✅ OpenSearch credentials refreshed")

    def ensure_collection(
        self, collection_name: str, vector_size: int, distance: str = "cosine"
    ) -> bool:
        """
        Ensure an index exists with vector field configuration.

        Args:
            collection_name: Name of the index
            vector_size: Dimension of vectors
            distance: Distance metric (cosine, euclidean, or innerproduct)

        Returns:
            True if index exists or was created successfully
        """
        logger.debug(
            f"🔎 Ensuring collection {collection_name} with vector_size={vector_size}"
        )
        if not self.is_connected():
            logger.error("❌ OpenSearch client not connected")
            return False

        self._refresh_credentials_if_needed()

        try:
            # Map distance metric to OpenSearch space_type
            # OpenSearch 7.10 uses: l2, cosinesimil, innerproduct, hamming
            space_type_map = {
                "cosine": "cosinesimil",
                "euclidean": "l2",
                "l2": "l2",
                "innerproduct": "innerproduct",
                "hamming": "hamming",
                "cosinesimil": "cosinesimil",
            }
            space_type = space_type_map.get(distance.lower(), "cosinesimil")
            logger.debug(f"📋 Mapped distance '{distance}' to space_type '{space_type}'")

            # Check if index exists
            logger.debug(f"📋 Checking if index {collection_name} exists")
            if self.client.indices.exists(index=collection_name):
                logger.debug(f"✓ Index {collection_name} exists, verifying dimension")
                # Verify dimension matches
                try:
                    mapping = self.client.indices.get_mapping(index=collection_name)
                    existing_dim = mapping[collection_name]["mappings"]["properties"][
                        "vector"
                    ]["dimension"]
                    if existing_dim != vector_size:
                        logger.warning(
                            f"⚠️ Index {collection_name} has dimension {existing_dim}, "
                            f"but required is {vector_size}. Deleting and recreating."
                        )
                        logger.debug(f"🔧 Deleting existing index {collection_name}")
                        self.client.indices.delete(index=collection_name)
                    else:
                        logger.info(
                            f"✅ Index {collection_name} exists with correct dimension {vector_size}"
                        )
                        return True
                except (KeyError, Exception) as e:
                    logger.warning(
                        f"⚠️ Could not verify dimension for {collection_name}: {e}. Recreating."
                    )
                    try:
                        logger.debug(f"🔧 Deleting index {collection_name} for recreation")
                        self.client.indices.delete(index=collection_name)
                    except Exception:
                        pass

            # Create index with vector field
            logger.debug(f"🔧 Creating new index {collection_name}")
            body = {
                "mappings": {
                    "properties": {
                        "vector": {
                            "type": "knn_vector",
                            "dimension": vector_size,
                            "method": {
                                "name": "hnsw",
                                "space_type": space_type,
                                "engine": "lucene",
                                "parameters": {
                                    "ef_construction": 256,
                                    "m": 48,
                                },
                            },
                        },
                        # Explicit mappings for quality score fields (nested under payload in actual documents)
                        # These are at root level in OpenSearch due to flattening
                        "payload": {
                            "properties": {
                                "noise_score": {"type": "float"},
                                "confidence_score": {"type": "float"},
                                "coherence_score": {"type": "float"},
                                "chunk_order": {"type": "integer"},
                                "page_number": {"type": "integer"},
                                "source_file": {
                                    "type": "text",
                                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                                },
                                "section": {
                                    "type": "text",
                                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                                },
                                "chunk_id": {"type": "keyword"},
                                "chunk_text": {"type": "text"},
                                "raw_text": {"type": "text"},
                            }
                        },
                    }
                },
                "settings": {
                    "index": {
                        "knn": True,  # Enable kNN feature for this index
                        "number_of_shards": 1,
                        "number_of_replicas": 0,  # For dev environments
                        "refresh_interval": "1s",
                    }
                },
            }
            self.client.indices.create(index=collection_name, body=body)
            logger.info(
                f"✅ Created index {collection_name} with vector dimension {vector_size}"
            )
            return True

        except Exception as e:
            logger.error(
                f"❌ Failed to ensure index {collection_name}: {e}", exc_info=True
            )
            return False

    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an index.

        Args:
            collection_name: Name of the index

        Returns:
            Collection information or None if not found
        """
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return None

        self._refresh_credentials_if_needed()

        try:
            if not self.client.indices.exists(index=collection_name):
                return None

            stats = self.client.indices.stats(index=collection_name)
            doc_count = (
                stats["indices"][collection_name]["primaries"]["docs"]["count"]
            )

            mapping = self.client.indices.get_mapping(index=collection_name)
            vector_dim = mapping[collection_name]["mappings"]["properties"]["vector"][
                "dimension"
            ]

            logger.info(f"✅ Collection {collection_name}: {doc_count} docs, dimension {vector_dim}")
            return {
                "name": collection_name,
                "points_count": doc_count,  # Use "points_count" for consistency with playground status API
                "doc_count": doc_count,  # Keep for backward compatibility
                "vector_dimension": vector_dim,
            }
        except Exception as e:
            logger.error(
                f"❌ Failed to get collection info for {collection_name}: {e}",
                exc_info=True
            )
            return None

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete an index.

        Args:
            collection_name: Name of the index

        Returns:
            True if deletion was successful
        """
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return False

        self._refresh_credentials_if_needed()

        try:
            logger.info(f"🔧 Deleting index {collection_name}")
            self.client.indices.delete(index=collection_name)
            logger.info(f"✅ Deleted index {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete index {collection_name}: {e}", exc_info=True)
            return False

    def list_collections(self) -> List[str]:
        """
        List all indexes in OpenSearch.

        Returns:
            List of index names
        """
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return []

        self._refresh_credentials_if_needed()

        try:
            indices = self.client.indices.get_alias(index="*")
            logger.info(f"📋 Found {len(indices)} indexes")
            return list(indices.keys())
        except Exception as e:
            logger.error(f"❌ Failed to list indexes: {e}", exc_info=True)
            return []

    def upsert_points(
        self, collection_name: str, points: List[Dict[str, Any]], batch_size: int = 50
    ) -> bool:
        """
        Upsert points (documents) into an index.

        Args:
            collection_name: Name of the index
            points: List of point dictionaries with 'id', 'vector', and payload fields
            batch_size: Number of points to upsert in each batch

        Returns:
            True if all points were successfully upserted
        """
        logger.info(
            f"📤 Upserting {len(points)} points to {collection_name} (batch_size={batch_size})"
        )
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return False

        if not points:
            logger.warning("⚠️ No points to upsert")
            return True

        try:
            from opensearchpy import helpers

            actions = []
            for point in points:
                action = {
                    "_index": collection_name,
                    "_id": point.get("id", str(point)),
                    "_source": {
                        "vector": point.get("vector", []),
                        **point.get("payload", {}),  # Flatten payload metadata into _source
                    },
                }
                actions.append(action)

            # Bulk upsert
            logger.debug(
                f"📋 Preparing bulk upsert with {len(actions)} actions"
            )
            success_count, errors = helpers.bulk(
                self.client,
                actions,
                chunk_size=batch_size,
                raise_on_error=False,
                request_timeout=300,
            )

            if errors:
                logger.warning(
                    f"⚠️ {len(errors)} errors during upsert: {errors[:3]}"
                )
                logger.info(
                    f"✅ Upserted {success_count}/{len(points)} points to {collection_name}"
                )
                return False
            else:
                logger.info(
                    f"✅ Successfully upserted {success_count} points to {collection_name}"
                )
                return True

        except Exception as e:
            logger.error(
                f"❌ Failed to upsert points to {collection_name}: {e}",
                exc_info=True
            )
            return False

    def get_sample_document(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a sample document from collection to inspect field names.

        Useful for debugging mapping issues.

        Args:
            collection_name: Collection name

        Returns:
            Sample document from the index
        """
        if not self.is_connected():
            logger.error("❌ OpenSearch client not connected")
            return None

        self._refresh_credentials_if_needed()

        try:
            logger.info(f"🔍 Fetching sample document from {collection_name}")
            query_body = {"size": 1, "query": {"match_all": {}}}
            response = self.client.search(index=collection_name, body=query_body)

            hits = response["hits"]["hits"]
            if hits:
                sample = hits[0].get("_source", {})
                logger.info(f"✅ Sample document fields: {list(sample.keys())}")
                return sample
            else:
                logger.warning(f"⚠️ Collection {collection_name} is empty")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to get sample: {e}", exc_info=True)
            return None

    def get_point_by_chunk_id(
        self, collection_name: str, chunk_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a point by its chunk_id field.

        Args:
            collection_name: Name of the index
            chunk_id: The chunk_id to search for

        Returns:
            Point dictionary if found, None otherwise
        """
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return None

        self._refresh_credentials_if_needed()

        try:
            query_body = {"query": {"term": {"chunk_id": chunk_id}}}
            response = self.client.search(index=collection_name, body=query_body)

            if response["hits"]["total"]["value"] > 0:
                hit = response["hits"]["hits"][0]
                logger.debug(f"✅ Found chunk {chunk_id}")
                return {
                    "id": hit["_id"],
                    **hit["_source"],
                }
            else:
                logger.debug(f"⚠️ Chunk {chunk_id} not found")
                return None

        except Exception as e:
            logger.error(
                f"❌ Failed to get point by chunk_id {chunk_id}: {e}",
                exc_info=True
            )
            return None


# Global OpenSearch client instance
# Will be initialized using OPENSEARCH_URL and OPENSEARCH_ROLE_ARN environment variables
opensearch_client = OpenSearchClient()
