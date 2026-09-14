"""
Data Quality Rule Evaluator.

This service evaluates data quality rules against products and pipeline runs.
Checks rules for:
- Required fields in chunks
- Duplicate rates in datasets
- Chunk coverage of source documents
- Bad file extensions
- Data freshness
- File sizes
- Content lengths
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from primedata.utils.log_utils import get_logger

from sqlalchemy.orm import Session

from ..db.models import DataQualityRule, DqViolation, PipelineArtifact, PipelineRun, Product, RawFile, RuleSeverity
from ..indexing.vector_search_client import vector_search_client

logger = get_logger(__name__)


class DataQualityEvaluator:
    """Evaluates data quality rules against products."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate_product_rules(
        self, product_id: UUID, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """
        Evaluate all active data quality rules for a product.

        Args:
            product_id: Product UUID
            version: Product version
            pipeline_run_id: Pipeline run UUID

        Returns:
            List of violations found
        """
        violations = []

        # Get all active rules for the product
        rules = (
            self.db.query(DataQualityRule)
            .filter(
                DataQualityRule.product_id == product_id,
                DataQualityRule.is_current == True,
                DataQualityRule.enabled == True,
            )
            .all()
        )

        if not rules:
            logger.info(f"No active data quality rules found for product {product_id}")
            return violations

        logger.info(f"Evaluating {len(rules)} data quality rules for product {product_id} version {version}")

        # Get product
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found")
            return violations

        # Evaluate each rule
        for rule in rules:
            try:
                rule_violations = self._evaluate_rule(rule, product, version, pipeline_run_id)
                violations.extend(rule_violations)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.id} ({rule.name}): {e}", exc_info=True)

        logger.info(f"Found {len(violations)} violations for product {product_id} version {version}")

        # Save violations to database
        for violation in violations:
            self.db.add(violation)

        self.db.commit()

        return violations

    def _evaluate_rule(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Evaluate a single rule."""
        if rule.rule_type == "required_fields":
            return self._evaluate_required_fields(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "max_duplicate_rate":
            return self._evaluate_duplicate_rate(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "min_chunk_coverage":
            return self._evaluate_chunk_coverage(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "bad_extensions":
            return self._evaluate_bad_extensions(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "min_freshness":
            return self._evaluate_freshness(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "file_size":
            return self._evaluate_file_size(rule, product, version, pipeline_run_id)
        elif rule.rule_type == "content_length":
            return self._evaluate_content_length(rule, product, version, pipeline_run_id)
        else:
            logger.warning(f"Unknown rule type: {rule.rule_type}")
            return []

    def _get_index_name(self, product: Product, version: int) -> Optional[str]:
        """Find the OpenSearch index name for a product version."""
        return vector_search_client.find_collection_name(
            workspace_id=str(product.workspace_id),
            product_id=str(product.id),
            version=version,
            product_name=product.name,
        )

    def _scroll_all_points(self, index_name: str) -> List[Dict[str, Any]]:
        """Scroll all points from an OpenSearch index into a list."""
        points = []
        try:
            for point in vector_search_client.scroll_points(collection_name=index_name):
                points.append(point)
        except Exception as e:
            logger.error(f"Error scrolling points from {index_name}: {e}", exc_info=True)
        return points

    def _evaluate_required_fields(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if required fields exist in chunks."""
        violations = []
        required_fields = rule.configuration.get("required_fields", [])

        if not required_fields:
            return violations

        index_name = self._get_index_name(product, version)
        if not index_name:
            logger.warning(f"No index found for product {product.id} version {version}")
            return violations

        try:
            points = self._scroll_all_points(index_name)
            total_chunks = len(points)
            chunks_with_missing_fields = 0
            missing_fields_summary = {field: 0 for field in required_fields}

            for point in points:
                has_missing = False
                for field in required_fields:
                    if field not in point or point[field] is None or point[field] == "":
                        missing_fields_summary[field] += 1
                        has_missing = True
                if has_missing:
                    chunks_with_missing_fields += 1

            if chunks_with_missing_fields > 0:
                violation = DqViolation(
                    product_id=product.id,
                    version=version,
                    pipeline_run_id=pipeline_run_id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"{chunks_with_missing_fields} of {total_chunks} chunks are missing required fields",
                    details={
                        "missing_fields_summary": missing_fields_summary,
                        "required_fields": required_fields,
                    },
                    affected_count=chunks_with_missing_fields,
                    total_count=total_chunks,
                    violation_rate=chunks_with_missing_fields / total_chunks if total_chunks > 0 else 0,
                )
                violations.append(violation)

        except Exception as e:
            logger.error(f"Error evaluating required fields rule: {e}", exc_info=True)

        return violations

    def _evaluate_duplicate_rate(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if duplicate rate exceeds threshold."""
        violations = []
        max_duplicate_rate = rule.configuration.get("max_duplicate_rate", 0.1)

        index_name = self._get_index_name(product, version)
        if not index_name:
            return violations

        try:
            points = self._scroll_all_points(index_name)
            total_chunks = len(points)

            if total_chunks == 0:
                return violations

            seen_texts = {}
            duplicate_count = 0

            for point in points:
                chunk_text = point.get("chunk_text", "") or point.get("text", "")
                if chunk_text:
                    if chunk_text in seen_texts:
                        duplicate_count += 1
                    else:
                        seen_texts[chunk_text] = True

            actual_duplicate_rate = duplicate_count / total_chunks if total_chunks > 0 else 0

            if actual_duplicate_rate > max_duplicate_rate:
                violation = DqViolation(
                    product_id=product.id,
                    version=version,
                    pipeline_run_id=pipeline_run_id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Duplicate rate {actual_duplicate_rate:.1%} exceeds threshold {max_duplicate_rate:.1%}",
                    details={
                        "actual_duplicate_rate": actual_duplicate_rate,
                        "max_duplicate_rate": max_duplicate_rate,
                        "duplicate_count": duplicate_count,
                    },
                    affected_count=duplicate_count,
                    total_count=total_chunks,
                    violation_rate=actual_duplicate_rate,
                )
                violations.append(violation)

        except Exception as e:
            logger.error(f"Error evaluating duplicate rate rule: {e}", exc_info=True)

        return violations

    def _evaluate_chunk_coverage(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if chunk coverage meets threshold."""
        violations = []
        min_chunk_coverage = rule.configuration.get("min_chunk_coverage", 0.85)

        # Get pipeline artifacts for this version
        preprocess_artifacts = (
            self.db.query(PipelineArtifact)
            .join(PipelineRun)
            .filter(
                PipelineRun.product_id == product.id,
                PipelineRun.version == version,
                PipelineArtifact.stage_name == "preprocess",
            )
            .all()
        )

        if not preprocess_artifacts:
            return violations

        for artifact in preprocess_artifacts:
            metadata = artifact.artifact_metadata or {}
            actual_coverage = metadata.get("chunk_coverage", 1.0)

            if actual_coverage < min_chunk_coverage:
                violation = DqViolation(
                    product_id=product.id,
                    version=version,
                    pipeline_run_id=pipeline_run_id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Chunk coverage {actual_coverage:.1%} below threshold {min_chunk_coverage:.1%}",
                    details={
                        "actual_coverage": actual_coverage,
                        "min_chunk_coverage": min_chunk_coverage,
                        "artifact_id": str(artifact.id),
                        "artifact_name": artifact.artifact_name,
                    },
                    affected_count=1,
                    total_count=len(preprocess_artifacts),
                    violation_rate=1 - actual_coverage,
                )
                violations.append(violation)

        return violations

    def _evaluate_bad_extensions(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check for files with bad extensions."""
        violations = []
        blocked_extensions = rule.configuration.get("blocked_extensions", [])

        if not blocked_extensions:
            return violations

        raw_files = self.db.query(RawFile).filter(RawFile.product_id == product.id).all()

        bad_files = []
        for raw_file in raw_files:
            filename_lower = raw_file.filename.lower()
            for ext in blocked_extensions:
                if filename_lower.endswith(ext.lower()):
                    bad_files.append({"filename": raw_file.filename, "extension": ext})
                    break

        if bad_files:
            violation = DqViolation(
                product_id=product.id,
                version=version,
                pipeline_run_id=pipeline_run_id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity=rule.severity,
                message=f"{len(bad_files)} files have blocked extensions",
                details={"bad_files": bad_files, "blocked_extensions": blocked_extensions},
                affected_count=len(bad_files),
                total_count=len(raw_files),
                violation_rate=len(bad_files) / len(raw_files) if len(raw_files) > 0 else 0,
            )
            violations.append(violation)

        return violations

    def _evaluate_freshness(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if data is fresh enough."""
        violations = []
        min_freshness_days = rule.configuration.get("min_freshness_days", 180)

        raw_files = self.db.query(RawFile).filter(RawFile.product_id == product.id).all()

        stale_files = []
        now = datetime.now(timezone.utc)

        for raw_file in raw_files:
            if raw_file.created_at:
                age_days = (now - raw_file.created_at).days
                if age_days > min_freshness_days:
                    stale_files.append(
                        {"filename": raw_file.filename, "age_days": age_days}
                    )

        if stale_files:
            violation = DqViolation(
                product_id=product.id,
                version=version,
                pipeline_run_id=pipeline_run_id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity=rule.severity,
                message=f"{len(stale_files)} files exceed {min_freshness_days} day freshness limit",
                details={
                    "stale_files": stale_files,
                    "min_freshness_days": min_freshness_days,
                },
                affected_count=len(stale_files),
                total_count=len(raw_files),
                violation_rate=len(stale_files) / len(raw_files) if len(raw_files) > 0 else 0,
            )
            violations.append(violation)

        return violations

    def _evaluate_file_size(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if file sizes are within limits."""
        violations = []
        max_file_size_mb = rule.configuration.get("max_file_size_mb", 100)
        min_file_size_kb = rule.configuration.get("min_file_size_kb", 1)

        max_bytes = max_file_size_mb * 1024 * 1024
        min_bytes = min_file_size_kb * 1024

        raw_files = self.db.query(RawFile).filter(RawFile.product_id == product.id).all()

        oversized_files = []
        undersized_files = []

        for raw_file in raw_files:
            if raw_file.size_bytes:
                if raw_file.size_bytes > max_bytes:
                    oversized_files.append(
                        {
                            "filename": raw_file.filename,
                            "size_mb": raw_file.size_bytes / (1024 * 1024),
                        }
                    )
                elif raw_file.size_bytes < min_bytes:
                    undersized_files.append(
                        {
                            "filename": raw_file.filename,
                            "size_kb": raw_file.size_bytes / 1024,
                        }
                    )

        if oversized_files or undersized_files:
            violation = DqViolation(
                product_id=product.id,
                version=version,
                pipeline_run_id=pipeline_run_id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity=rule.severity,
                message=f"{len(oversized_files)} files exceed {max_file_size_mb}MB, {len(undersized_files)} files below {min_file_size_kb}KB",
                details={
                    "oversized_files": oversized_files,
                    "undersized_files": undersized_files,
                    "max_file_size_mb": max_file_size_mb,
                    "min_file_size_kb": min_file_size_kb,
                },
                affected_count=len(oversized_files) + len(undersized_files),
                total_count=len(raw_files),
                violation_rate=(len(oversized_files) + len(undersized_files)) / len(raw_files)
                if len(raw_files) > 0
                else 0,
            )
            violations.append(violation)

        return violations

    def _evaluate_content_length(
        self, rule: DataQualityRule, product: Product, version: int, pipeline_run_id: UUID
    ) -> List[DqViolation]:
        """Check if content lengths are within limits."""
        violations = []
        min_content_length = rule.configuration.get("min_content_length", 50)
        max_content_length = rule.configuration.get("max_content_length", 8000)

        index_name = self._get_index_name(product, version)
        if not index_name:
            return violations

        try:
            points = self._scroll_all_points(index_name)
            total_chunks = len(points)

            if total_chunks == 0:
                return violations

            too_short = 0
            too_long = 0

            for point in points:
                chunk_text = point.get("chunk_text", "") or point.get("text", "")
                text_length = len(chunk_text)

                if text_length < min_content_length:
                    too_short += 1
                elif text_length > max_content_length:
                    too_long += 1

            if too_short > 0 or too_long > 0:
                violation = DqViolation(
                    product_id=product.id,
                    version=version,
                    pipeline_run_id=pipeline_run_id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"{too_short} chunks below {min_content_length} chars, {too_long} chunks above {max_content_length} chars",
                    details={
                        "too_short": too_short,
                        "too_long": too_long,
                        "min_content_length": min_content_length,
                        "max_content_length": max_content_length,
                    },
                    affected_count=too_short + too_long,
                    total_count=total_chunks,
                    violation_rate=(too_short + too_long) / total_chunks if total_chunks > 0 else 0,
                )
                violations.append(violation)

        except Exception as e:
            logger.error(f"Error evaluating content length rule: {e}", exc_info=True)

        return violations
