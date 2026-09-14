"""
Data Quality API endpoints for PrimeData.

This module provides REST API endpoints for managing data quality rules
and viewing quality violations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.security import get_current_user
from ..core.user_utils import get_user_id
from ..db.database import get_db
from ..db.models import DqViolation, Product
from ..dq.rules_schema import DataQualityRules, DataQualityViolation
from ..storage.storage_client import storage_client
from ..storage.paths import dq_rules_key
from ..core.constants import BUCKET_CONFIG

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(tags=["data-quality"])


class DataQualityRulesRequest(BaseModel):
    """Request model for creating/updating data quality rules."""

    rules: Dict[str, Any]  # JSON representation of DataQualityRules


class DataQualityRulesResponse(BaseModel):
    """Response model for data quality rules."""

    product_id: str
    version: int
    created_at: str
    updated_at: str
    rules: Dict[str, Any]


class DataQualityViolationResponse(BaseModel):
    """Response model for data quality violations."""

    id: str
    rule_name: str
    rule_type: str
    severity: str
    message: str
    details: Dict[str, Any]
    affected_count: int
    total_count: int
    violation_rate: float
    created_at: str


class DataQualityReportResponse(BaseModel):
    """Response model for data quality report."""

    product_id: str
    version: int
    pipeline_run_id: str
    created_at: str
    violations: List[DataQualityViolationResponse]
    total_items_checked: int
    total_violations: int
    has_violations: bool
    has_errors: bool
    has_warnings: bool
    overall_quality_score: float


@router.get("/products/{product_id}/rules", response_model=DataQualityRulesResponse)
async def get_data_quality_rules(
    product_id: str, request: Request, db: Session = Depends(get_db)
):
    """Get data quality rules for a product."""
    logger.info(f"✔️ Fetching data quality rules | product_id={product_id}")

    try:
        from uuid import UUID
        from ..db.models_enterprise import DataQualityRule

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))
        logger.info(f"📋 Product access verified | product_id={product_id}")

        # Get rules from database
        rules = (
            db.query(DataQualityRule)
            .filter(DataQualityRule.product_id == product_id, DataQualityRule.is_current == True)
            .all()
        )
        logger.info(f"💾 Rules retrieved from database | count={len(rules)}")

        if rules:
            # Convert to the expected format
            def rule_to_dict(rule):
                base_rule = {
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "severity": str(rule.severity),
                    "enabled": rule.enabled,
                }

                # Map configuration fields to the expected frontend format
                if rule.rule_type == "required_fields":
                    base_rule["required_fields"] = rule.configuration.get("required_fields", [])
                elif rule.rule_type == "max_duplicate_rate":
                    base_rule["max_duplicate_rate"] = rule.configuration.get("max_duplicate_rate", 0.1)
                elif rule.rule_type == "min_chunk_coverage":
                    base_rule["min_chunk_coverage"] = rule.configuration.get("min_chunk_coverage", 0.8)
                elif rule.rule_type == "bad_extensions":
                    base_rule["bad_extensions"] = rule.configuration.get("blocked_extensions", [])
                elif rule.rule_type == "min_freshness":
                    base_rule["min_freshness_days"] = rule.configuration.get("min_freshness_days", 30)
                elif rule.rule_type == "file_size":
                    base_rule["max_file_size_mb"] = rule.configuration.get("max_file_size_mb", 10)
                    base_rule["min_file_size_kb"] = rule.configuration.get("min_file_size_kb", 1)
                elif rule.rule_type == "content_length":
                    base_rule["min_content_length"] = rule.configuration.get("min_content_length", 100)
                    base_rule["max_content_length"] = rule.configuration.get("max_content_length", 10000)

                return base_rule

            rules_dict = {
                "product_id": product_id,
                "version": max(rule.version for rule in rules) if rules else 1,
                "created_at": min(rule.created_at for rule in rules).isoformat() if rules else "",
                "updated_at": max(rule.updated_at for rule in rules).isoformat() if rules else "",
                "rules": {
                    "required_fields_rules": [rule_to_dict(rule) for rule in rules if rule.rule_type == "required_fields"],
                    "max_duplicate_rate_rules": [
                        rule_to_dict(rule) for rule in rules if rule.rule_type == "max_duplicate_rate"
                    ],
                    "min_chunk_coverage_rules": [
                        rule_to_dict(rule) for rule in rules if rule.rule_type == "min_chunk_coverage"
                    ],
                    "bad_extensions_rules": [rule_to_dict(rule) for rule in rules if rule.rule_type == "bad_extensions"],
                    "min_freshness_rules": [rule_to_dict(rule) for rule in rules if rule.rule_type == "min_freshness"],
                    "file_size_rules": [rule_to_dict(rule) for rule in rules if rule.rule_type == "file_size"],
                    "content_length_rules": [rule_to_dict(rule) for rule in rules if rule.rule_type == "content_length"],
                },
            }
            logger.info(f"✅ Rules formatted successfully | product_id={product_id}")
            return DataQualityRulesResponse(**rules_dict)

        # Return empty rules if none found
        logger.info(f"⚠️ No rules found, returning empty | product_id={product_id}")
        return DataQualityRulesResponse(product_id=product_id, version=1, created_at="", updated_at="", rules={})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get data quality rules | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get data quality rules: {str(e)}")


@router.put("/products/{product_id}/rules", response_model=DataQualityRulesResponse)
async def update_data_quality_rules(
    product_id: str,
    request_body: DataQualityRulesRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update data quality rules for a product."""
    logger.info(f"✔️ Updating data quality rules | product_id={product_id}")

    try:
        from uuid import UUID
        from ..db.models_enterprise import DataQualityRule, DataQualityRuleAudit, AuditAction, RuleSeverity

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))
        logger.info(f"📋 Product access verified | product_id={product_id}")

        # Validate rules
        try:
            rules = DataQualityRules(**request_body.rules)
            logger.info(f"📋 Rules validated successfully")
        except Exception as e:
            logger.warning(f"✔️ Rules validation failed | error={str(e)}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid rules format: {str(e)}")

        # Mark existing rules as not current
        logger.info(f"📋 Marking old rules as not current")
        existing_rules = (
            db.query(DataQualityRule)
            .filter(DataQualityRule.product_id == product_id, DataQualityRule.is_current == True)
            .all()
        )

        for rule in existing_rules:
            rule.is_current = False

        # Create new rules in database
        new_rules = []
        for rule_type, rule_list in request_body.rules.items():
            if rule_type.endswith("_rules") and isinstance(rule_list, list):
                for rule_data in rule_list:
                    # Map frontend fields to configuration object
                    configuration = {}
                    rule_type_clean = rule_data.get("rule_type", rule_type.replace("_rules", ""))

                    if rule_type_clean == "required_fields":
                        configuration["required_fields"] = rule_data.get("required_fields", [])
                    elif rule_type_clean == "max_duplicate_rate":
                        configuration["max_duplicate_rate"] = rule_data.get("max_duplicate_rate", 0.1)
                    elif rule_type_clean == "min_chunk_coverage":
                        configuration["min_chunk_coverage"] = rule_data.get("min_chunk_coverage", 0.8)
                    elif rule_type_clean == "bad_extensions":
                        configuration["blocked_extensions"] = rule_data.get("bad_extensions", [])
                    elif rule_type_clean == "min_freshness":
                        configuration["min_freshness_days"] = rule_data.get("min_freshness_days", 30)
                    elif rule_type_clean == "file_size":
                        configuration["max_file_size_mb"] = rule_data.get("max_file_size_mb", 10)
                        configuration["min_file_size_kb"] = rule_data.get("min_file_size_kb", 1)
                    elif rule_type_clean == "content_length":
                        configuration["min_content_length"] = rule_data.get("min_content_length", 100)
                        configuration["max_content_length"] = rule_data.get("max_content_length", 10000)

                    new_rule = DataQualityRule(
                        product_id=product_id,
                        workspace_id=product.workspace_id,
                        name=rule_data.get("name", ""),
                        description=rule_data.get("description", ""),
                        rule_type=rule_type_clean,
                        severity=RuleSeverity(rule_data.get("severity", "error")),
                        configuration=configuration,
                        enabled=rule_data.get("enabled", True),
                        created_by=None,
                        updated_by=None,
                    )
                    db.add(new_rule)
                    new_rules.append(new_rule)

        # Flush to get the IDs
        db.flush()
        logger.info(f"📋 New rules created | count={len(new_rules)}")

        # Create audit logs
        for rule in new_rules:
            # Serialize rule data properly for JSON storage
            rule_data = {
                "id": str(rule.id),
                "product_id": str(rule.product_id),
                "workspace_id": str(rule.workspace_id),
                "name": rule.name,
                "description": rule.description,
                "rule_type": rule.rule_type,
                "severity": str(rule.severity),
                "status": str(rule.status),
                "configuration": rule.configuration,
                "version": rule.version,
                "is_current": rule.is_current,
                "enabled": rule.enabled,
                "created_by": str(rule.created_by),
                "updated_by": str(rule.updated_by) if rule.updated_by else None,
                "compliance_tags": rule.compliance_tags,
                "business_owner": rule.business_owner,
                "technical_owner": rule.technical_owner,
            }

            audit_log = DataQualityRuleAudit(
                rule_id=rule.id, action=AuditAction.CREATE, changed_by=None, new_values=rule_data
            )
            db.add(audit_log)

        db.commit()
        logger.info(f"✅ Rules updated successfully | product_id={product_id}")

        # Return the updated rules
        return DataQualityRulesResponse(
            product_id=product_id,
            version=1,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            rules=request_body.rules,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to update data quality rules | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update data quality rules: {str(e)}")


@router.get("/products/{product_id}/violations", response_model=List[DataQualityViolationResponse])
async def get_data_quality_violations(
    product_id: str,
    request: Request,
    version: Optional[int] = Query(None, description="Specific version to get violations for"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of violations to return"),
    db: Session = Depends(get_db)
):
    """Get data quality violations for a product."""
    logger.info(f"✔️ Fetching violations | product_id={product_id}, version={version}, severity={severity}, limit={limit}")

    try:
        from uuid import UUID

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))
        logger.info(f"📋 Product access verified")

        # Build query
        query = db.query(DqViolation).filter(DqViolation.product_id == product_id)

        if version is not None:
            query = query.filter(DqViolation.version == version)
        else:
            # Get latest version if not specified
            latest_version = (
                db.query(DqViolation.version)
                .filter(DqViolation.product_id == product_id)
                .order_by(DqViolation.version.desc())
                .first()
            )

            if latest_version:
                query = query.filter(DqViolation.version == latest_version[0])

        if severity:
            query = query.filter(DqViolation.severity == severity)

        # Order by creation time and limit
        violations = query.order_by(DqViolation.created_at.desc()).limit(limit).all()
        logger.info(f"💾 Violations retrieved | count={len(violations)}")

        # Convert to response format
        result = [
            DataQualityViolationResponse(
                id=str(violation.id),
                rule_name=violation.rule_name,
                rule_type=violation.rule_type,
                severity=violation.severity.value,
                message=violation.message,
                details=violation.details or {},
                affected_count=violation.affected_count,
                total_count=violation.total_count,
                violation_rate=violation.violation_rate,
                created_at=violation.created_at.isoformat(),
            )
            for violation in violations
        ]
        logger.info(f"✅ Violations formatted | count={len(result)}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get data quality violations | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get data quality violations: {str(e)}")


@router.get("/products/{product_id}/report", response_model=DataQualityReportResponse)
async def get_data_quality_report(
    product_id: str,
    request: Request,
    version: Optional[int] = Query(None, description="Specific version to get report for"),
    db: Session = Depends(get_db)
):
    """Get comprehensive data quality report for a product."""
    try:
        from uuid import UUID
        from ..db.models_enterprise import RuleSeverity

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))

        # Get violations
        query = db.query(DqViolation).filter(DqViolation.product_id == product_id)

        if version is not None:
            query = query.filter(DqViolation.version == version)
        else:
            # Get latest version if not specified
            latest_version = (
                db.query(DqViolation.version)
                .filter(DqViolation.product_id == product_id)
                .order_by(DqViolation.version.desc())
                .first()
            )

            if latest_version:
                query = query.filter(DqViolation.version == latest_version[0])

        violations = query.all()

        # Calculate statistics
        total_items_checked = max((v.total_count for v in violations), default=0)
        total_violations = len(violations)
        has_violations = total_violations > 0
        has_errors = any(v.severity == RuleSeverity.ERROR for v in violations)
        has_warnings = any(v.severity == RuleSeverity.WARNING for v in violations)

        # Calculate quality score
        if total_items_checked == 0:
            overall_quality_score = 1.0
        else:
            error_violations = sum(v.affected_count for v in violations if v.severity == RuleSeverity.ERROR)
            warning_violations = sum(v.affected_count for v in violations if v.severity == RuleSeverity.WARNING)
            total_penalty = (error_violations * 2) + warning_violations
            max_possible_penalty = total_items_checked * 2
            overall_quality_score = max(0.0, 1.0 - (total_penalty / max_possible_penalty))

        # Convert violations to response format
        violation_responses = [
            DataQualityViolationResponse(
                id=str(violation.id),
                rule_name=violation.rule_name,
                rule_type=violation.rule_type,
                severity=violation.severity.value,
                message=violation.message,
                details=violation.details or {},
                affected_count=violation.affected_count,
                total_count=violation.total_count,
                violation_rate=violation.violation_rate,
                created_at=violation.created_at.isoformat(),
            )
            for violation in violations
        ]

        return DataQualityReportResponse(
            product_id=product_id,
            version=version or (latest_version[0] if latest_version else 0),
            pipeline_run_id="",  # Would need to get from violations
            created_at=violations[0].created_at.isoformat() if violations else "",
            violations=violation_responses,
            total_items_checked=total_items_checked,
            total_violations=total_violations,
            has_violations=has_violations,
            has_errors=has_errors,
            has_warnings=has_warnings,
            overall_quality_score=overall_quality_score,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get data quality report: {str(e)}")


@router.delete("/products/{product_id}/rules")
async def delete_data_quality_rules(
    product_id: str, request: Request, db: Session = Depends(get_db)
):
    """Delete data quality rules for a product."""
    try:
        from uuid import UUID

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))

        # Delete rules from storage
        rules_key = dq_rules_key(product.workspace_id, product_id)

        try:
            await storage_client.delete_object(BUCKET_CONFIG, rules_key)
        except Exception:
            pass  # Rules might not exist

        return {"message": "Data quality rules deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete data quality rules: {str(e)}")


@router.post("/products/{product_id}/rules/validate")
async def validate_data_quality_rules(
    product_id: str,
    rules: DataQualityRulesRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Validate data quality rules without saving them."""
    logger.info(f"✔️ Validating data quality rules | product_id={product_id}")

    try:
        from uuid import UUID

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))
        logger.info(f"📋 Product access verified | product_id={product_id}")

        # Validate rules
        try:
            validated_rules = DataQualityRules(**rules.rules)
            logger.info(f"✅ Rules validated successfully | count={len(validated_rules.get_all_rules())}")
            return {
                "valid": True,
                "message": "Rules are valid",
                "rules_count": len(validated_rules.get_all_rules()),
                "enabled_rules_count": len(validated_rules.get_enabled_rules()),
                "can_apply": True,
            }
        except Exception as e:
            logger.warning(f"⚠️ Rules validation failed | error={str(e)}")
            return {"valid": False, "message": f"Invalid rules: {str(e)}", "errors": [str(e)], "can_apply": False}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to validate data quality rules | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to validate data quality rules: {str(e)}")

