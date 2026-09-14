"""
Data Quality Validation Engine for PrimeData.

This module provides the core validation logic for data quality rules,
checking data against configured rules and generating violation reports.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from primedata.utils.log_utils import get_logger
from ..storage.storage_client import storage_client
from ..storage.paths import _get_base_prefix, embed_prefix, dq_rules_key
from ..core.constants import BUCKET_CONFIG, BUCKET_EMBED
from .rules_schema import (
    BadExtensionsRule,
    ContentLengthRule,
    DataQualityReport,
    DataQualityRules,
    DataQualityViolation,
    FileSizeRule,
    MaxDuplicateRateRule,
    MinChunkCoverageRule,
    MinFreshnessRule,
    RequiredFieldsRule,
    RuleSeverity,
)

logger = get_logger(__name__)


class DataQualityValidator:
    """Main data quality validation engine."""

    def __init__(self):
        self.storage_client = storage_client

    async def validate_product_data(
        self, product_id: str, version: int, pipeline_run_id: str, workspace_id: str
    ) -> DataQualityReport:
        """
        Validate product data against configured quality rules.

        Args:
            product_id: ID of the product to validate
            version: Version of the product
            pipeline_run_id: ID of the pipeline run
            workspace_id: ID of the workspace

        Returns:
            DataQualityReport with violations found
        """
        logger.info(f"✔️ Starting data quality validation for product {product_id}, version {version}")
        logger.debug(f"📋 pipeline_run_id: {pipeline_run_id}, workspace_id: {workspace_id}")

        # Load quality rules
        logger.debug("📋 Loading quality rules from storage")
        rules = await self._load_quality_rules(product_id, workspace_id)
        if not rules:
            logger.info(f"⚠️ No quality rules found for product {product_id}")
            return DataQualityReport(
                product_id=product_id,
                version=version,
                pipeline_run_id=pipeline_run_id,
                created_at=datetime.utcnow().isoformat(),
                total_items_checked=0,
                total_violations=0,
            )

        # Get data to validate
        logger.debug("📋 Retrieving data items for validation")
        data_items = await self._get_data_items(product_id, version, workspace_id)
        logger.debug(f"✓ Retrieved {len(data_items)} data items for validation")

        # Run validations
        logger.debug("✔️ Running rule validations")
        violations = []
        total_checked = len(data_items)

        enabled_rules = rules.get_enabled_rules()
        logger.debug(f"📋 Processing {len(enabled_rules)} enabled rules")
        for rule in enabled_rules:
            logger.debug(f"🔍 Validating rule: {rule.name}")
            rule_violations = await self._validate_rule(rule, data_items, product_id, version)
            violations.extend(rule_violations)
            if rule_violations:
                logger.debug(f"❌ Found {len(rule_violations)} violations for rule {rule.name}")

        # Create report
        logger.debug("💾 Creating data quality report")
        report = DataQualityReport(
            product_id=product_id,
            version=version,
            pipeline_run_id=pipeline_run_id,
            created_at=datetime.utcnow().isoformat(),
            violations=violations,
            total_items_checked=total_checked,
            total_violations=len(violations),
        )
        logger.debug(f"📋 Report: {len(violations)} violations, quality_score: {report.overall_quality_score:.2%}")

        logger.info(f"✅ Data quality validation completed: {len(violations)} violations found")
        return report

    async def _load_quality_rules(self, product_id: str, workspace_id: str) -> Optional[DataQualityRules]:
        """Load quality rules from S3/GCS storage."""
        logger.debug(f"🔧 Loading quality rules for product {product_id} in workspace {workspace_id}")
        try:
            rules_key = dq_rules_key(workspace_id, product_id)
            logger.debug(f"📋 Storage key: {rules_key}")

            # Try to get rules file
            logger.debug("📋 Retrieving rules from storage")
            rules_data = await self.storage_client.get_object(BUCKET_CONFIG, rules_key)
            if not rules_data:
                logger.warning(f"⚠️ Rules file not found at {rules_key}")
                return None

            # Parse YAML (for now, we'll use JSON format)
            logger.debug("💾 Parsing rules JSON")
            rules_dict = json.loads(rules_data)
            rules = DataQualityRules(**rules_dict)
            logger.info(f"✅ Loaded {len(rules.get_all_rules())} quality rules")
            return rules

        except Exception as e:
            logger.error(f"❌ Failed to load quality rules for product {product_id}: {e}", exc_info=True)
            return None

    async def _get_data_items(self, product_id: str, version: int, workspace_id: str) -> List[Dict[str, Any]]:
        """Get data items to validate from S3/GCS storage."""
        logger.debug(f"🔎 Retrieving data items for product {product_id} v{version}")
        try:
            # Get chunks from the embed bucket using embed_prefix helper
            chunks_key_prefix = embed_prefix(workspace_id, product_id, version)
            logger.debug(f"📋 Storage prefix: {chunks_key_prefix}")

            data_items = []
            logger.debug("📋 Listing objects from storage")
            objects = await self.storage_client.list_objects(BUCKET_EMBED, chunks_key_prefix)
            logger.debug(f"✓ Found {len(objects)} objects at prefix")

            for obj in objects:
                try:
                    # Get chunk data
                    logger.debug(f"📋 Loading chunk: {obj.name}")
                    chunk_data = await self.storage_client.get_object(BUCKET_EMBED, obj.name)
                    if chunk_data:
                        chunk_info = json.loads(chunk_data)
                        data_items.append(chunk_info)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load chunk {obj.name}: {e}")

            logger.info(f"✅ Retrieved {len(data_items)} data items")
            return data_items

        except Exception as e:
            logger.error(f"❌ Failed to get data items for validation: {e}", exc_info=True)
            return []

    async def _validate_rule(
        self, rule: Any, data_items: List[Dict[str, Any]], product_id: str, version: int
    ) -> List[DataQualityViolation]:
        """Validate a specific rule against data items."""
        logger.debug(f"🔧 Validating rule: {rule.name} (type: {rule.rule_type})")
        violations = []

        try:
            if isinstance(rule, RequiredFieldsRule):
                logger.debug("📋 Processing RequiredFieldsRule")
                violations = await self._validate_required_fields(rule, data_items)
            elif isinstance(rule, MaxDuplicateRateRule):
                logger.debug("📋 Processing MaxDuplicateRateRule")
                violations = await self._validate_duplicate_rate(rule, data_items)
            elif isinstance(rule, MinChunkCoverageRule):
                logger.debug("📋 Processing MinChunkCoverageRule")
                violations = await self._validate_chunk_coverage(rule, data_items)
            elif isinstance(rule, BadExtensionsRule):
                logger.debug("📋 Processing BadExtensionsRule")
                violations = await self._validate_bad_extensions(rule, data_items)
            elif isinstance(rule, MinFreshnessRule):
                logger.debug("📋 Processing MinFreshnessRule")
                violations = await self._validate_freshness(rule, data_items)
            elif isinstance(rule, FileSizeRule):
                logger.debug("📋 Processing FileSizeRule")
                violations = await self._validate_file_size(rule, data_items)
            elif isinstance(rule, ContentLengthRule):
                logger.debug("📋 Processing ContentLengthRule")
                violations = await self._validate_content_length(rule, data_items)
            else:
                logger.warning(f"⚠️ Unknown rule type: {type(rule)}")

            if violations:
                logger.info(f"❌ Found {len(violations)} violations for rule {rule.name}")
            else:
                logger.debug(f"✅ No violations for rule {rule.name}")

        except Exception as e:
            logger.error(f"❌ Error validating rule {rule.name}: {e}", exc_info=True)
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=RuleSeverity.ERROR,
                    message=f"Validation error: {str(e)}",
                    details={"error": str(e)},
                    affected_count=1,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_required_fields(
        self, rule: RequiredFieldsRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate required fields rule."""
        logger.debug(f"✔️ Validating required fields: {rule.required_fields}")
        violations = []
        missing_fields_count = 0

        for item in data_items:
            missing_fields = []
            for field in rule.required_fields:
                if field not in item or item[field] is None or item[field] == "":
                    missing_fields.append(field)

            if missing_fields:
                missing_fields_count += 1

        logger.debug(f"📋 Missing fields in {missing_fields_count} items")

        if missing_fields_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Missing required fields in {missing_fields_count} items",
                    details={"required_fields": rule.required_fields, "missing_count": missing_fields_count},
                    affected_count=missing_fields_count,
                    total_count=len(data_items),
                )
            )
            logger.info(f"❌ RequiredFieldsRule violation: {missing_fields_count}/{len(data_items)} items")

        return violations

    async def _validate_duplicate_rate(
        self, rule: MaxDuplicateRateRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate duplicate rate rule."""
        logger.debug(f"✔️ Validating duplicate rate (max: {rule.max_duplicate_rate:.2%})")
        violations = []

        # Count duplicates based on content hash or text
        logger.debug("📋 Computing content hashes")
        content_hashes = {}
        duplicates = 0

        for item in data_items:
            content = item.get("text", "") or item.get("content", "")
            content_hash = hash(content)

            if content_hash in content_hashes:
                duplicates += 1
            else:
                content_hashes[content_hash] = True

        duplicate_rate = duplicates / len(data_items) if data_items else 0
        logger.debug(f"💾 Duplicate rate: {duplicate_rate:.2%} ({duplicates} duplicates)")

        if duplicate_rate > rule.max_duplicate_rate:
            logger.info(f"❌ Duplicate rate violation: {duplicate_rate:.2%} > {rule.max_duplicate_rate:.2%}")
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Duplicate rate {duplicate_rate:.2%} exceeds maximum {rule.max_duplicate_rate:.2%}",
                    details={
                        "duplicate_rate": duplicate_rate,
                        "max_duplicate_rate": rule.max_duplicate_rate,
                        "duplicate_count": duplicates,
                    },
                    affected_count=duplicates,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_chunk_coverage(
        self, rule: MinChunkCoverageRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate chunk coverage rule."""
        violations = []

        # This would require original content length information
        # For now, we'll implement a simplified version
        low_coverage_count = 0

        for item in data_items:
            chunk_size = len(item.get("text", "") or item.get("content", ""))
            original_size = item.get("original_size", chunk_size)

            if original_size > 0:
                coverage = chunk_size / original_size
                if coverage < rule.min_chunk_coverage:
                    low_coverage_count += 1

        if low_coverage_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Low chunk coverage in {low_coverage_count} items",
                    details={"min_chunk_coverage": rule.min_chunk_coverage, "low_coverage_count": low_coverage_count},
                    affected_count=low_coverage_count,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_bad_extensions(
        self, rule: BadExtensionsRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate bad extensions rule."""
        violations = []
        bad_files_count = 0

        for item in data_items:
            file_path = item.get("source_path", "") or item.get("file_path", "")
            if file_path:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in rule.bad_extensions:
                    bad_files_count += 1

        if bad_files_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {bad_files_count} files with bad extensions",
                    details={"bad_extensions": rule.bad_extensions, "bad_files_count": bad_files_count},
                    affected_count=bad_files_count,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_freshness(
        self, rule: MinFreshnessRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate freshness rule."""
        violations = []
        stale_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=rule.min_freshness_days)

        for item in data_items:
            created_at = item.get("created_at") or item.get("timestamp")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        item_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        item_date = created_at

                    if item_date < cutoff_date:
                        stale_count += 1
                except Exception:
                    # If we can't parse the date, consider it stale
                    stale_count += 1

        if stale_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {stale_count} stale items (older than {rule.min_freshness_days} days)",
                    details={
                        "min_freshness_days": rule.min_freshness_days,
                        "stale_count": stale_count,
                        "cutoff_date": cutoff_date.isoformat(),
                    },
                    affected_count=stale_count,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_file_size(self, rule: FileSizeRule, data_items: List[Dict[str, Any]]) -> List[DataQualityViolation]:
        """Validate file size rule."""
        violations = []
        oversized_count = 0
        undersized_count = 0

        max_size_bytes = rule.max_file_size_mb * 1024 * 1024
        min_size_bytes = (rule.min_file_size_kb or 0) * 1024

        for item in data_items:
            file_size = item.get("file_size", 0) or item.get("size", 0)

            if file_size > max_size_bytes:
                oversized_count += 1
            elif rule.min_file_size_kb and file_size < min_size_bytes:
                undersized_count += 1

        if oversized_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {oversized_count} files exceeding size limit",
                    details={"max_file_size_mb": rule.max_file_size_mb, "oversized_count": oversized_count},
                    affected_count=oversized_count,
                    total_count=len(data_items),
                )
            )

        if undersized_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {undersized_count} files below minimum size",
                    details={"min_file_size_kb": rule.min_file_size_kb, "undersized_count": undersized_count},
                    affected_count=undersized_count,
                    total_count=len(data_items),
                )
            )

        return violations

    async def _validate_content_length(
        self, rule: ContentLengthRule, data_items: List[Dict[str, Any]]
    ) -> List[DataQualityViolation]:
        """Validate content length rule."""
        violations = []
        too_short_count = 0
        too_long_count = 0

        for item in data_items:
            content = item.get("text", "") or item.get("content", "")
            content_length = len(content)

            if rule.min_content_length and content_length < rule.min_content_length:
                too_short_count += 1
            elif rule.max_content_length and content_length > rule.max_content_length:
                too_long_count += 1

        if too_short_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {too_short_count} items below minimum content length",
                    details={"min_content_length": rule.min_content_length, "too_short_count": too_short_count},
                    affected_count=too_short_count,
                    total_count=len(data_items),
                )
            )

        if too_long_count > 0:
            violations.append(
                DataQualityViolation(
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    message=f"Found {too_long_count} items exceeding maximum content length",
                    details={"max_content_length": rule.max_content_length, "too_long_count": too_long_count},
                    affected_count=too_long_count,
                    total_count=len(data_items),
                )
            )

        return violations
