"""
OpenSearch search mixin - provides search and scroll capabilities.

This mixin is used by OpenSearchClient and relies on self.client, self.url,
and self.logger being available from the main class.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class OpenSearchSearchMixin:
    """Mixin providing search and scroll methods for OpenSearchClient."""

    def search_points(
        self,
        collection_name: str,
        query_vectors: List[List[float]],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
    ) -> Optional[List[List[Dict[str, Any]]]]:
        """
        Search for similar vectors in the index.

        Args:
            collection_name: Name of the index
            query_vectors: List of query vectors
            limit: Maximum number of results per query
            score_threshold: Minimum similarity score
            filter_conditions: Optional filter conditions

        Returns:
            List of result lists (one per query vector) with matched points
        """
        logger.debug(f"🔍 Entry search_points | collection={collection_name}, vectors={len(query_vectors)}, limit={limit}")

        # Refresh credentials if needed (handles token expiry)
        self._refresh_credentials_if_needed()

        if not self.is_connected():
            logger.error("❌ OpenSearch client not connected")
            return None

        try:
            logger.debug(f"  📋 Searching {len(query_vectors)} vectors in {collection_name}")
            results = []

            for qvec in query_vectors:
                query_body = {
                    "size": limit,
                    "query": {
                        "knn": {
                            "vector": {
                                "vector": qvec,
                                "k": limit,
                            }
                        }
                    },
                }

                if filter_conditions:
                    query_body["query"] = {
                        "bool": {
                            "must": query_body["query"],
                            "filter": self._build_filter(filter_conditions),
                        }
                    }

                response = self.client.search(index=collection_name, body=query_body)

                # Extract results
                hits = response["hits"]["hits"]
                result_points = []
                for hit in hits:
                    score = hit["_score"]
                    if score_threshold is None or score >= score_threshold:
                        result_points.append(
                            {
                                "id": hit["_id"],
                                "score": score,
                                **hit["_source"],
                            }
                        )

                results.append(result_points)
                logger.debug(f"  Query {len(results)}: {len(result_points)} results")

            logger.info(
                f"✅ Search completed: {len(results)} queries, avg {sum(len(r) for r in results) / len(results):.1f} results per query"
            )
            logger.debug(f"✅ Exit search_points | success")
            return results

        except Exception as e:
            logger.error(f"❌ Search failed for {collection_name}: {type(e).__name__}: {str(e)}", exc_info=True)
            # If it's an auth error, try refreshing and retry once
            if "AuthorizationException" in str(type(e)) or "token" in str(e).lower():
                logger.warning(f"⚠️ Authorization error during search, attempting credential refresh and retry...")
                self._initialize_client()
                self._last_credentials_refresh = datetime.utcnow().timestamp()
                try:
                    results = []
                    for qvec in query_vectors:
                        query_body = {
                            "size": limit,
                            "query": {
                                "knn": {
                                    "vector": {
                                        "vector": qvec,
                                        "k": limit,
                                    }
                                }
                            }
                        }
                        if filter_conditions:
                            query_body["query"]["knn"]["vector"]["filter"] = filter_conditions
                        if score_threshold is not None:
                            query_body["query"]["bool"] = {
                                "must": query_body["query"].pop("knn"),
                                "filter": {"range": {"_score": {"gte": score_threshold}}}
                            }

                        response = self.client.search(index=collection_name, body=query_body)
                        hits = response["hits"]["hits"]
                        result_points = []
                        for hit in hits:
                            score = hit["_score"]
                            if score_threshold is None or score >= score_threshold:
                                result_points.append(
                                    {
                                        "id": hit["_id"],
                                        "score": score,
                                        **hit["_source"],
                                    }
                                )
                        results.append(result_points)

                    logger.info(f"✅ Search (retry) completed: {len(results)} queries")
                    return results
                except Exception as retry_error:
                    logger.error(f"❌ Search retry failed: {retry_error}", exc_info=True)
                    return None
            return None

    def scroll_points(
        self,
        collection_name: str,
        batch_size: int = 100,
        scroll_time: str = "1m",
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Scroll through all points in an index.

        Args:
            collection_name: Name of the index
            batch_size: Number of points per batch
            scroll_time: Scroll timeout

        Returns:
            Generator of batches of points
        """
        if not self.is_connected():
            logger.error("OpenSearch client not connected")
            return None

        try:
            logger.debug(f"📜 Starting scroll of {collection_name}")
            from opensearchpy import helpers
            from opensearchpy.exceptions import NotFoundError

            point_count = 0
            for batch in helpers.scan(
                self.client,
                index=collection_name,
                size=batch_size,
                scroll=scroll_time,
                request_timeout=300,
            ):
                point_count += 1
                try:
                    # Extract _source payload safely
                    source = batch.get("_source", {})
                    yield {
                        "id": batch.get("_id", ""),
                        "payload": source,
                        "vector": source.get("vector", []),
                    }
                except Exception as e:
                    logger.warning(f"⚠️ Error processing point {point_count} from {collection_name}: {e}")
                    continue

            logger.debug(f"✅ Scroll completed for {collection_name} | total_points={point_count}")

        except NotFoundError:
            # Index doesn't exist yet - return empty generator silently
            logger.debug(f"⚠️ Index not found: {collection_name} (collection may not have been indexed yet)")
            return
        except Exception as e:
            logger.error(f"❌ Scroll failed for {collection_name}: {e}", exc_info=True)

    def search_with_filters(
        self,
        collection_name: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple:
        """
        Search with quality filters and pagination applied at OpenSearch level.

        Args:
            collection_name: Collection to query
            filters: Dict with filter conditions:
                {
                    "noise_score": {"max": 50},
                    "confidence_score": {"min": 60},
                    "coherence_score": {"min": 70},
                }
            sort_by: Field to sort by (e.g., "noise_score", "confidence_score")
            sort_order: "asc" or "desc"
            offset: Pagination offset (from parameter)
            limit: Pagination limit (size parameter)

        Returns:
            Tuple of (chunks, total_count) - chunks are already paginated and sorted
        """
        self._refresh_credentials_if_needed()

        if not self.is_connected():
            logger.error("❌ OpenSearch client not connected")
            return [], 0

        try:
            logger.info(
                f"🔍 Search with filters | collection={collection_name}, "
                f"offset={offset}, limit={limit}, sort_by={sort_by}"
            )

            # Build filter query
            filter_conditions = []

            if filters:
                logger.debug(f"   Building filters from: {filters}")

                # Quality score filters (all stored flat at top level)
                if "noise_score" in filters:
                    noise_filter = filters["noise_score"]
                    if "max" in noise_filter:
                        filter_conditions.append({
                            "range": {"noise_score": {"lte": noise_filter["max"]}}
                        })
                        logger.debug(f"      Added noise_score <= {noise_filter['max']}")

                if "confidence_score" in filters:
                    conf_filter = filters["confidence_score"]
                    if "min" in conf_filter:
                        filter_conditions.append({
                            "range": {"confidence_score": {"gte": conf_filter["min"]}}
                        })
                        logger.debug(f"      Added confidence_score >= {conf_filter['min']}")
                    if "max" in conf_filter:
                        filter_conditions.append({
                            "range": {"confidence_score": {"lte": conf_filter["max"]}}
                        })
                        logger.debug(f"      Added confidence_score <= {conf_filter['max']}")

                if "coherence_score" in filters:
                    coh_filter = filters["coherence_score"]
                    if "min" in coh_filter:
                        filter_conditions.append({
                            "range": {"coherence_score": {"gte": coh_filter["min"]}}
                        })
                        logger.debug(f"      Added coherence_score >= {coh_filter['min']}")

                if "score" in filters:
                    score_filter = filters["score"]
                    if "min" in score_filter:
                        filter_conditions.append({
                            "range": {"score": {"gte": score_filter["min"]}}
                        })
                        logger.debug(f"      Added score >= {score_filter['min']}")
                    if "max" in score_filter:
                        filter_conditions.append({
                            "range": {"score": {"lte": score_filter["max"]}}
                        })
                        logger.debug(f"      Added score <= {score_filter['max']}")

                # Metadata filters (all stored flat at top level)
                if "source_file" in filters and filters["source_file"]:
                    filter_conditions.append({
                        "term": {"source_file.keyword": filters["source_file"]}
                    })
                    logger.debug(f"      Added source_file = {filters['source_file']}")

                if "section" in filters and filters["section"]:
                    filter_conditions.append({
                        "term": {"section.keyword": filters["section"]}
                    })
                    logger.debug(f"      Added section = {filters['section']}")

                if "page_number" in filters and filters["page_number"] is not None:
                    filter_conditions.append({
                        "term": {"page_number": filters["page_number"]}
                    })
                    logger.debug(f"      Added page_number = {filters['page_number']}")

            logger.debug(f"   Total filter conditions: {len(filter_conditions)}")

            # Build sort
            sort_clause = []
            if sort_by:
                # Sort by top-level field (not nested under payload)
                sort_clause = [{sort_by: {"order": sort_order}}]
                logger.debug(f"   Sort by: {sort_by} ({sort_order})")

            # Build query
            query_body = {
                "from": offset,
                "size": limit,
            }

            if filter_conditions:
                query_body["query"] = {
                    "bool": {
                        "filter": filter_conditions if len(filter_conditions) > 1 else filter_conditions[0]
                    }
                }
            else:
                query_body["query"] = {"match_all": {}}

            if sort_clause:
                query_body["sort"] = sort_clause

            logger.debug(f"   Query: {query_body}")

            # Execute search
            try:
                response = self.client.search(index=collection_name, body=query_body)
                logger.debug(f"   Response hits count: {len(response['hits']['hits'])}")
            except Exception as e:
                # If sorting failed, try again without sort
                if sort_clause and ("No mapping found" in str(e) or "sort" in str(e).lower()):
                    logger.warning(f"⚠️ Sort failed on field {sort_by}, retrying without sort: {e}")
                    query_body.pop("sort", None)
                    logger.debug(f"   Retry query (no sort): {query_body}")
                    try:
                        response = self.client.search(index=collection_name, body=query_body)
                        logger.debug(f"   Retry response hits count: {len(response['hits']['hits'])}")
                    except Exception as retry_error:
                        logger.error(f"❌ Query failed even without sort: {retry_error}", exc_info=True)
                        return [], 0
                else:
                    raise

            # Extract results
            total_count = response["hits"]["total"]["value"]
            chunks = []

            for hit in response["hits"]["hits"]:
                source = hit.get("_source", {})
                # Data is stored flat at top level, return as payload for API consistency
                chunks.append({
                    "id": hit.get("_id", ""),
                    "payload": source,  # Include vector and all metadata
                    "vector": source.get("vector", []),
                })

            logger.info(
                f"✅ Search completed | total_available={total_count}, "
                f"returned={len(chunks)}, offset={offset}"
            )

            return chunks, total_count

        except Exception as e:
            logger.error(
                f"❌ Search with filters failed for {collection_name}: "
                f"{type(e).__name__}: {e}",
                exc_info=True
            )
            return [], 0
