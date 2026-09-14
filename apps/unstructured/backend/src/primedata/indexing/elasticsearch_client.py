"""
Elasticsearch client for vector search and storage.

⚠️ DEPRECATED: This module is maintained for backward compatibility only.
   New deployments should use OpenSearch client instead.
   See OPENSEARCH_SETUP.md for migration guide.

This module provides functionality to interact with Elasticsearch for storing
and retrieving embeddings with native vector search capabilities.
"""

import os
from typing import Any, Dict, List, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class ElasticsearchClient:
    """Client for interacting with Elasticsearch for vector search."""

    def __init__(self, url: Optional[str] = None):
        """
        Initialize Elasticsearch client.

        ⚠️ DEPRECATED: Use OpenSearchClient instead.
           This client is maintained for backward compatibility only.

        Args:
            url: Elasticsearch URL (defaults to environment variable or http://elasticsearch:9200)
                In K8s: http://elasticsearch:9200 or http://elasticsearch.primedata-dev.svc.cluster.local:9200
                For local dev: http://localhost:9200
        """
        logger.warning(
            "⚠️ ElasticsearchClient is DEPRECATED and maintained for backward compatibility only.\n"
            "   Please migrate to OpenSearchClient.\n"
            "   Set OPENSEARCH_URL environment variable and see OPENSEARCH_SETUP.md for details."
        )
        self.url = url or os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Elasticsearch client."""
        logger.debug(f"🔎 Initializing Elasticsearch client at {self.url}")
        try:
            from elasticsearch import Elasticsearch

            self.client = Elasticsearch(
                hosts=[self.url],
                verify_certs=False,  # For local dev
                request_timeout=300   # 5 minutes
            )
            # Test connection
            logger.debug("📋 Testing Elasticsearch connection")
            info = self.client.info()
            logger.info(f"✅ Connected to Elasticsearch at {self.url}, version: {info['version']['number']}")
        except ImportError:
            logger.error("❌ elasticsearch not installed. Install with: pip install elasticsearch")
            self.client = None
        except Exception as e:
            logger.error(f"❌ Failed to connect to Elasticsearch at {self.url}: {e}", exc_info=True)
            self.client = None

    def is_connected(self) -> bool:
        """Check if client is connected to Elasticsearch."""
        return self.client is not None

    def ensure_collection(self, collection_name: str, vector_size: int, distance: str = "Cosine") -> bool:
        """
        Ensure an index exists with vector field configuration.

        Args:
            collection_name: Name of the index
            vector_size: Dimension of vectors
            distance: Distance metric (Cosine only supported in Elasticsearch kNN)

        Returns:
            True if index exists or was created successfully
        """
        logger.debug(f"🔎 Ensuring collection {collection_name} with vector_size={vector_size}")
        if not self.is_connected():
            logger.error("❌ Elasticsearch client not connected")
            return False

        try:
            # Check if index exists
            logger.debug(f"📋 Checking if index {collection_name} exists")
            if self.client.indices.exists(index=collection_name):
                logger.debug(f"✓ Index {collection_name} exists, verifying dimension")
                # Verify dimension matches
                try:
                    mapping = self.client.indices.get_mapping(index=collection_name)
                    existing_dim = mapping[collection_name]['mappings']['properties']['vector']['dims']
                    if existing_dim != vector_size:
                        logger.warning(
                            f"⚠️ Index {collection_name} has dimension {existing_dim}, "
                            f"but required is {vector_size}. Deleting and recreating."
                        )
                        logger.debug(f"🔧 Deleting existing index {collection_name}")
                        self.client.indices.delete(index=collection_name)
                    else:
                        logger.info(f"✅ Index {collection_name} exists with correct dimension {vector_size}")
                        return True
                except (KeyError, Exception) as e:
                    logger.warning(f"⚠️ Could not verify dimension for {collection_name}: {e}. Recreating.")
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
                            "type": "dense_vector",
                            "dims": vector_size,
                            "index": True,
                            "similarity": "cosine"  # Cosine similarity (0-1 range)
                        }
                        # All payload fields as dynamic fields (no schema required)
                        # Elasticsearch will auto-detect types
                    }
                },
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,  # For local dev
                        "refresh_interval": "1s"
                    }
                }
            }
            self.client.indices.create(index=collection_name, body=body)
            logger.info(f"✅ Created index {collection_name} with vector dimension {vector_size}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to ensure index {collection_name}: {e}", exc_info=True)
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
            logger.error("Elasticsearch client not connected")
            return None

        try:
            if not self.client.indices.exists(index=collection_name):
                return None

            stats = self.client.indices.stats(index=collection_name)
            mapping = self.client.indices.get_mapping(index=collection_name)

            index_stats = stats['indices'][collection_name]
            vector_dim = mapping[collection_name]['mappings']['properties']['vector']['dims']

            return {
                "name": collection_name,
                "vectors_count": index_stats['total']['docs']['count'],
                "indexed_vectors_count": index_stats['total']['docs']['count'],
                "points_count": index_stats['total']['docs']['count'],
                "segments_count": index_stats['total']['segments']['count'],
                "config": {
                    "vector_size": vector_dim,
                    "distance": "Cosine"
                }
            }

        except Exception as e:
            logger.error(f"Failed to get collection info for {collection_name}: {e}")
            return None

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete an index.

        Args:
            collection_name: Name of the index to delete

        Returns:
            True if deletion was successful
        """
        if not self.is_connected():
            logger.error("Elasticsearch client not connected")
            return False

        try:
            self.client.indices.delete(index=collection_name)
            logger.info(f"Deleted index {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete index {collection_name}: {e}")
            return False

    def list_collections(self) -> List[str]:
        """
        List all indices.

        Returns:
            List of index names
        """
        if not self.is_connected():
            logger.error("Elasticsearch client not connected")
            return []

        try:
            indices = self.client.indices.get_alias(index="*")
            # Filter out system indices (starting with .)
            return [name for name in indices.keys() if not name.startswith('.')]
        except Exception as e:
            logger.error(f"Failed to list indices: {e}")
            return []

    def upsert_points(self, collection_name: str, points: List[Dict[str, Any]], batch_size: int = 50) -> bool:
        """
        Upsert points to an index using bulk API.

        Args:
            collection_name: Name of the index
            points: List of points with 'id', 'vector', 'payload'
            batch_size: Batch size for bulk operations

        Returns:
            True if successful
        """
        logger.debug(f"🔎 Upserting points to index {collection_name}")
        if not self.is_connected():
            logger.error("❌ Elasticsearch client not connected")
            return False

        if not points:
            logger.warning("⚠️ No points to upsert")
            return True

        try:
            from elasticsearch.helpers import bulk

            total_points = len(points)
            logger.info(f"🧠 Upserting {total_points} points to index {collection_name} in batches of {batch_size}")

            # Convert to Elasticsearch bulk format
            logger.debug("💾 Converting points to bulk format")
            actions = []
            for point in points:
                doc = {
                    "_index": collection_name,
                    "_id": str(point["id"]),  # Elasticsearch requires string IDs
                    "_source": {
                        "vector": point["vector"],
                        **point["payload"]  # Merge all payload fields as document fields
                    }
                }
                actions.append(doc)

            # Bulk index with batching
            logger.debug(f"📋 Processing {total_points} points in {(total_points + batch_size - 1) // batch_size} batches")
            for i in range(0, total_points, batch_size):
                batch = actions[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_points + batch_size - 1) // batch_size

                try:
                    logger.debug(f"📋 Upserting batch {batch_num}/{total_batches} ({len(batch)} points)")
                    success, failed = bulk(self.client, batch, raise_on_error=False, refresh='wait_for')
                    logger.info(f"✓ Upserted batch {batch_num}/{total_batches} ({len(batch)} points) - success: {success}, failed: {len(failed)}")

                    if failed:
                        for item in failed:
                            logger.error(f"❌ Failed to index document: {item}")
                        return False
                except Exception as e:
                    logger.error(f"❌ Bulk indexing failed for batch {batch_num}: {e}", exc_info=True)
                    return False

            logger.info(f"✅ Successfully upserted all {total_points} points to index {collection_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to upsert points to index {collection_name}: {e}", exc_info=True)
            return False

    def search_points(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar vectors using kNN.

        Args:
            collection_name: Name of the index
            query_vector: Query vector
            limit: Max results
            score_threshold: Minimum score threshold
            filter_conditions: Filter conditions

        Returns:
            List of search results with id, score, payload
        """
        logger.debug(f"🔎 Searching {collection_name} for {limit} similar vectors")
        if not self.is_connected():
            logger.error("❌ Elasticsearch client not connected")
            raise ConnectionError("Elasticsearch client not connected")

        try:
            # Build kNN query
            logger.debug("📋 Building kNN query")
            knn = {
                "field": "vector",
                "query_vector": query_vector,
                "k": limit,
                "num_candidates": limit * 10  # Oversample for better recall
            }

            # Add filter if provided
            query_body = {"knn": knn}
            if filter_conditions:
                logger.debug(f"📋 Adding filter conditions: {list(filter_conditions.keys())}")
                query_body["filter"] = self._build_filter(filter_conditions)

            # Execute search
            logger.debug(f"🔍 Executing search query against {collection_name}")
            response = self.client.search(
                index=collection_name,
                body=query_body,
                size=limit,
                _source_excludes=["vector"]  # Don't return vectors in results
            )

            # Convert to Qdrant-compatible format
            logger.debug("💾 Processing search results")
            results = []
            for hit in response['hits']['hits']:
                score = hit['_score']

                # Apply score threshold if provided
                if score_threshold and score < score_threshold:
                    logger.debug(f"✓ Filtering out result with score {score:.4f} < {score_threshold}")
                    continue

                results.append({
                    "id": int(hit['_id']) if hit['_id'].isdigit() else hit['_id'],
                    "score": score,
                    "payload": hit['_source']
                })

            logger.info(f"✅ Found {len(results)} results for search in index {collection_name}")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to search points in index {collection_name}: {e}", exc_info=True)
            raise RuntimeError(f"Search failed for index {collection_name}: {str(e)}") from e

    def scroll_points(
        self,
        collection_name: str,
        limit: int = 100,
        offset: Optional[str] = None,
        filter_conditions: Optional[Dict] = None,
        with_payload: bool = True,
        with_vector: bool = False
    ) -> Dict[str, Any]:
        """
        Scroll through points in an index with pagination.

        Args:
            collection_name: Name of the index
            limit: Max results per page
            offset: Pagination token (document ID for search_after)
            filter_conditions: Filter conditions
            with_payload: Include document fields
            with_vector: Include vectors

        Returns:
            Dict with 'points' and 'next_page_offset'
        """
        if not self.is_connected():
            logger.error("Elasticsearch client not connected")
            return {"points": [], "next_page_offset": None}

        try:
            query = {"match_all": {}}
            if filter_conditions:
                query = self._build_filter(filter_conditions)

            body = {
                "query": query,
                "size": limit,
                "sort": [{"_id": "asc"}]  # Required for search_after
            }

            if offset:
                body["search_after"] = [offset]

            # Exclude fields if needed
            if not with_vector:
                body["_source"] = {"excludes": ["vector"]}

            response = self.client.search(index=collection_name, body=body)

            # Convert results
            points = []
            for hit in response['hits']['hits']:
                point_dict = {
                    "id": int(hit['_id']) if hit['_id'].isdigit() else hit['_id']
                }
                if with_payload:
                    source = hit['_source'].copy()
                    if 'vector' in source and not with_vector:
                        del source['vector']
                    point_dict["payload"] = source
                if with_vector and 'vector' in hit['_source']:
                    point_dict["vector"] = hit['_source']['vector']
                points.append(point_dict)

            # Get next page offset
            next_offset = None
            if points:
                next_offset = str(points[-1]["id"])

            logger.info(f"Scrolled {len(points)} points from index {collection_name}")
            return {
                "points": points,
                "next_page_offset": next_offset
            }

        except Exception as e:
            logger.error(f"Failed to scroll points in index {collection_name}: {e}")
            return {"points": [], "next_page_offset": None}

    def get_point_by_chunk_id(
        self,
        collection_name: str,
        chunk_id: str,
        product_id: Optional[str] = None,
        version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a point by chunk_id."""
        if not self.is_connected():
            logger.error("Elasticsearch client not connected")
            return None

        try:
            query = {"term": {"chunk_id": chunk_id}}

            # Add additional filters
            if product_id or version is not None:
                must = [query]
                if product_id:
                    must.append({"term": {"product_id": str(product_id)}})
                if version is not None:
                    must.append({"term": {"version": version}})
                query = {"bool": {"must": must}}

            response = self.client.search(
                index=collection_name,
                body={"query": query, "size": 1},
                _source_excludes=["vector"]
            )

            if response['hits']['hits']:
                hit = response['hits']['hits'][0]
                return {
                    "id": int(hit['_id']) if hit['_id'].isdigit() else hit['_id'],
                    "payload": hit['_source']
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get point by chunk_id {chunk_id} from index {collection_name}: {e}")
            return None

    def set_alias(self, alias_name: str, collection_name: str) -> bool:
        """Create/update an index alias."""
        if not self.is_connected():
            logger.error("Elasticsearch client not connected")
            return False

        try:
            # Check if index exists
            if not self.client.indices.exists(index=collection_name):
                logger.error(f"Cannot set alias '{alias_name}': index '{collection_name}' not found")
                return False

            # Remove old alias if it exists
            if self.client.indices.exists_alias(name=alias_name):
                old_aliases = self.client.indices.get_alias(name=alias_name)
                for old_index in old_aliases.keys():
                    self.client.indices.delete_alias(index=old_index, name=alias_name)
                    logger.info(f"Deleted existing alias '{alias_name}' from index '{old_index}'")

            # Create new alias
            self.client.indices.put_alias(index=collection_name, name=alias_name)
            logger.info(f"Created alias '{alias_name}' -> '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to set alias '{alias_name}' -> '{collection_name}': {e}")
            return False

    def set_prod_alias(self, workspace_id: str, product_id: str, version: int, product_name: Optional[str] = None) -> bool:
        """Set production alias to point to a specific version."""
        # Create alias name
        if product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            alias_name = f"prod_ws_{workspace_id}__{sanitized_name}"
        else:
            alias_name = f"prod_ws_{workspace_id}__prod_{product_id}"

        # Find collection
        collection_name = self.find_collection_name(
            workspace_id=workspace_id,
            product_id=product_id,
            version=version,
            product_name=product_name
        )

        if not collection_name:
            logger.error(f"No index found for workspace={workspace_id} product={product_id} version={version}")
            return False

        return self.set_alias(alias_name=alias_name, collection_name=collection_name)

    def get_prod_alias_collection(self, workspace_id: str, product_id: str, product_name: Optional[str] = None) -> Optional[str]:
        """Get the index name that the production alias points to."""
        alias_names = []
        if product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            alias_names.append(f"prod_ws_{workspace_id}__{sanitized_name}")
        alias_names.append(f"prod_ws_{workspace_id}__prod_{product_id}")

        try:
            for alias_name in alias_names:
                if self.client.indices.exists_alias(name=alias_name):
                    aliases = self.client.indices.get_alias(name=alias_name)
                    # Return first index (should only be one)
                    return list(aliases.keys())[0]
        except Exception as e:
            logger.debug(f"Error checking alias {alias_name}: {e}")

        return None

    def _build_filter(self, filter_conditions: Dict) -> Dict:
        """Build Elasticsearch query from filter conditions."""
        must = []

        for key, value in filter_conditions.items():
            # Remove "payload." prefix if present (Elasticsearch doesn't need it)
            field_key = key.replace("payload.", "") if key.startswith("payload.") else key

            if isinstance(value, list):
                # Must match any of the values
                must.append({"terms": {field_key: value}})
            else:
                # Must match exact value
                must.append({"term": {field_key: value}})

        if len(must) == 1:
            return {"bool": {"must": must}}
        elif len(must) > 1:
            return {"bool": {"must": must}}
        else:
            return {"match_all": {}}

    def _sanitize_collection_name(self, name: str) -> str:
        """
        Sanitize a product name to be safe for use in Elasticsearch index names.

        Args:
            name: Product name to sanitize

        Returns:
            Sanitized name safe for index naming
        """
        import re

        if not name or not name.strip():
            return "product"

        # Start with the original name
        sanitized = name.strip()

        # Replace spaces with hyphens (more readable than underscores)
        sanitized = re.sub(r"\s+", "-", sanitized)

        # Replace any characters that aren't alphanumeric, hyphens, underscores with hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", sanitized)

        # Remove multiple consecutive hyphens/underscores
        sanitized = re.sub(r"[-_]+", "-", sanitized)

        # Remove leading/trailing hyphens and underscores
        sanitized = sanitized.strip("-_").lower()  # Elasticsearch prefers lowercase

        # Ensure it's not empty after sanitization
        if not sanitized:
            sanitized = "product"

        # Limit length (Elasticsearch index names should be reasonable length)
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip("-_")

        logger.debug(f"Sanitized collection name: '{name}' -> '{sanitized}'")
        return sanitized

    def get_collection_name(
        self,
        workspace_id: str,
        product_id: str,
        version: int,
        product_name: Optional[str] = None,
        use_product_name: bool = True,
    ) -> str:
        """
        Get index name for a product version.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name (if use_product_name is True)
            use_product_name: Whether to use product name (True) or product_id (False)

        Returns:
            Index name
        """
        if use_product_name and product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            return f"ws_{workspace_id}__{sanitized_name}__v_{version}"
        else:
            return f"ws_{workspace_id}__prod_{product_id}__v_{version}"

    def find_collection_name(
        self, workspace_id: str, product_id: str, version: int, product_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Find index name by checking both naming schemes (product name and product_id).
        This provides backward compatibility.

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


# Global Elasticsearch client instance
# NOTE: This is deprecated. Use get_vector_search_client() from vector_search_client.py instead
# for automatic selection between Elasticsearch and OpenSearch based on environment variables.
# For backward compatibility, this still creates a pure Elasticsearch client.
elasticsearch_client = ElasticsearchClient()

