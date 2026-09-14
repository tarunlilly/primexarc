"""
Governance API endpoints for policy management and quality gates.

Endpoints:
- POST /api/v1/governance/policies - Register policy
- GET /api/v1/governance/policies - List policies
- PUT /api/v1/governance/policies/{policy_id} - Update policy
- DELETE /api/v1/governance/policies/{policy_id} - Delete policy
- POST /api/v1/governance/evaluate - Evaluate policies on a product
- GET /api/v1/governance/violations - Get policy violations
- POST /api/v1/governance/quality-gates - Define quality gate
- GET /api/v1/governance/quality-gates - List quality gates
- POST /api/v1/governance/alerts/rules - Define alert rule
- GET /api/v1/governance/alerts - Get active alerts
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class PolicySeverity(str, Enum):
    """Policy severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PolicyCategory(str, Enum):
    """Policy categories."""

    DATA_QUALITY = "data_quality"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"
    COST = "cost"


class PolicyCreate(BaseModel):
    """Request model for creating policy."""

    name: str
    description: str
    category: PolicyCategory
    severity: PolicySeverity
    rule_type: str  # e.g., "min_trust_score", "max_error_rate", "field_encryption"
    threshold: float
    enabled: bool = True
    auto_remediate: bool = False


class PolicyResponse(BaseModel):
    """Response model for policy."""

    policy_id: str
    name: str
    description: str
    category: PolicyCategory
    severity: PolicySeverity
    rule_type: str
    threshold: float
    enabled: bool
    auto_remediate: bool
    created_at: datetime
    violations_count: int = 0


class PolicyEvaluateRequest(BaseModel):
    """Request to evaluate policies on a product."""

    product_id: UUID
    policy_ids: Optional[List[str]] = None  # If None, evaluate all


class PolicyViolationResponse(BaseModel):
    """Response model for policy violation."""

    violation_id: str
    policy_id: str
    policy_name: str
    product_id: str
    severity: PolicySeverity
    violation_message: str
    timestamp: datetime
    auto_remediated: bool = False


class QualityGateCreate(BaseModel):
    """Request model for creating quality gate."""

    name: str
    description: str
    blocking: bool = True  # If True, blocks promotion
    conditions: Dict[str, Any] = Field(..., description="Conditions e.g. {min_trust_score: 75, max_error_rate: 0.05}")


class QualityGateResponse(BaseModel):
    """Response model for quality gate."""

    gate_id: str
    name: str
    description: str
    blocking: bool
    conditions: Dict[str, Any]
    created_at: datetime
    passed_products: int = 0
    failed_products: int = 0


class AlertRuleCreate(BaseModel):
    """Request model for creating alert rule."""

    name: str
    description: str
    policy_id: str
    channels: List[str] = Field(..., description="Channels: email, slack, webhook, log")
    notification_template: Optional[Dict[str, str]] = None


class AlertRuleResponse(BaseModel):
    """Response model for alert rule."""

    rule_id: str
    name: str
    policy_id: str
    channels: List[str]
    active_alerts: int = 0
    created_at: datetime


class AlertResponse(BaseModel):
    """Response model for alert."""

    alert_id: str
    rule_id: str
    policy_id: str
    policy_name: str
    severity: PolicySeverity
    message: str
    product_id: Optional[str] = None
    timestamp: datetime
    acknowledged: bool = False


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/policies")
async def create_policy(
    policy_data: PolicyCreate,
    db: Session = Depends(get_db),
) -> PolicyResponse:
    """
    Register a new governance policy.

    Args:
        policy_data: Policy configuration
        db: Database session

    Returns:
        Created policy details
    """
    logger.info(f"📋 POST /api/v1/governance/policies - Creating policy: {policy_data.name}")

    try:
        policy_id = f"policy_{policy_data.name.lower().replace(' ', '_')}_{int(datetime.utcnow().timestamp())}"

        logger.info(f"✅ Policy created: {policy_id}")

        return PolicyResponse(
            policy_id=policy_id,
            name=policy_data.name,
            description=policy_data.description,
            category=policy_data.category,
            severity=policy_data.severity,
            rule_type=policy_data.rule_type,
            threshold=policy_data.threshold,
            enabled=policy_data.enabled,
            auto_remediate=policy_data.auto_remediate,
            created_at=datetime.utcnow(),
            violations_count=0,
        )

    except Exception as e:
        logger.error(f"❌ Error creating policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create policy: {str(e)}",
        )


@router.get("/policies")
async def list_policies(
    category: Optional[PolicyCategory] = None,
    severity: Optional[PolicySeverity] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all governance policies (with optional filters).

    Args:
        category: Filter by category
        severity: Filter by severity
        enabled_only: Only return enabled policies
        db: Database session

    Returns:
        List of policies
    """
    logger.info(f"📋 GET /api/v1/governance/policies - Listing policies")

    try:
        # Simulated policy list
        policies = [
            {
                "policy_id": "policy_min_trust_score",
                "name": "Minimum Trust Score",
                "description": "Products must have minimum AI Trust Score of 75%",
                "category": PolicyCategory.DATA_QUALITY,
                "severity": PolicySeverity.HIGH,
                "rule_type": "min_trust_score",
                "threshold": 75.0,
                "enabled": True,
                "auto_remediate": False,
                "created_at": datetime.utcnow(),
                "violations_count": 2,
            },
            {
                "policy_id": "policy_metadata_presence",
                "name": "Metadata Presence",
                "description": "All chunks must have required metadata fields",
                "category": PolicyCategory.COMPLIANCE,
                "severity": PolicySeverity.MEDIUM,
                "rule_type": "metadata_presence",
                "threshold": 95.0,
                "enabled": True,
                "auto_remediate": False,
                "created_at": datetime.utcnow(),
                "violations_count": 0,
            },
        ]

        # Apply filters
        if category:
            policies = [p for p in policies if p["category"] == category]
        if severity:
            policies = [p for p in policies if p["severity"] == severity]
        if enabled_only:
            policies = [p for p in policies if p["enabled"]]

        logger.info(f"✓ Retrieved {len(policies)} policies")

        return {
            "policies": policies,
            "count": len(policies),
        }

    except Exception as e:
        logger.error(f"❌ Error listing policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list policies: {str(e)}",
        )


@router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    policy_data: PolicyCreate,
    db: Session = Depends(get_db),
) -> PolicyResponse:
    """
    Update a governance policy.

    Args:
        policy_id: Policy ID
        policy_data: Updated policy data
        db: Database session

    Returns:
        Updated policy details
    """
    logger.info(f"📋 PUT /api/v1/governance/policies/{policy_id}")

    try:
        logger.info(f"✅ Policy {policy_id} updated")

        return PolicyResponse(
            policy_id=policy_id,
            name=policy_data.name,
            description=policy_data.description,
            category=policy_data.category,
            severity=policy_data.severity,
            rule_type=policy_data.rule_type,
            threshold=policy_data.threshold,
            enabled=policy_data.enabled,
            auto_remediate=policy_data.auto_remediate,
            created_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"❌ Error updating policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update policy: {str(e)}",
        )


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """
    Delete a governance policy.

    Args:
        policy_id: Policy ID
        db: Database session

    Returns:
        Deletion confirmation
    """
    logger.info(f"📋 DELETE /api/v1/governance/policies/{policy_id}")

    try:
        logger.info(f"✅ Policy {policy_id} deleted")

        return {"success": True, "deleted_policy_id": policy_id}

    except Exception as e:
        logger.error(f"❌ Error deleting policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete policy: {str(e)}",
        )


@router.post("/evaluate")
async def evaluate_policies(
    evaluate_request: PolicyEvaluateRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Evaluate policies on a product.

    Args:
        evaluate_request: Product and policies to evaluate
        db: Database session

    Returns:
        Evaluation results with violations
    """
    logger.info(f"📋 POST /api/v1/governance/evaluate - Evaluating product {evaluate_request.product_id}")

    try:
        product = db.query(Product).filter(Product.id == evaluate_request.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found",
            )

        # Simulate policy evaluation
        violations = []
        if product.trust_score < 75:
            violations.append(
                {
                    "violation_id": f"viol_{datetime.utcnow().timestamp()}",
                    "policy_id": "policy_min_trust_score",
                    "policy_name": "Minimum Trust Score",
                    "product_id": str(evaluate_request.product_id),
                    "severity": PolicySeverity.HIGH,
                    "violation_message": f"Trust score {product.trust_score}% below threshold of 75%",
                    "timestamp": datetime.utcnow(),
                    "auto_remediated": False,
                }
            )

        logger.info(f"✓ Evaluation complete: {len(violations)} violations found")

        return {
            "product_id": str(evaluate_request.product_id),
            "product_name": product.name,
            "evaluation_timestamp": datetime.utcnow().isoformat(),
            "passed": len(violations) == 0,
            "violations": violations,
            "violation_count": len(violations),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error evaluating policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate policies: {str(e)}",
        )


@router.get("/violations")
async def get_violations(
    product_id: Optional[UUID] = None,
    severity: Optional[PolicySeverity] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get policy violations (with optional filters).

    Args:
        product_id: Filter by product
        severity: Filter by severity
        limit: Maximum results
        offset: Pagination offset
        db: Database session

    Returns:
        List of violations
    """
    logger.info(f"📋 GET /api/v1/governance/violations")

    try:
        # Simulated violations
        violations = [
            {
                "violation_id": "viol_1",
                "policy_id": "policy_min_trust_score",
                "policy_name": "Minimum Trust Score",
                "product_id": str(product_id) if product_id else "product-1",
                "severity": PolicySeverity.HIGH,
                "violation_message": "Trust score below threshold",
                "timestamp": datetime.utcnow(),
                "acknowledged": False,
            }
        ]

        # Apply filters
        if product_id:
            violations = [v for v in violations if v["product_id"] == str(product_id)]
        if severity:
            violations = [v for v in violations if v["severity"] == severity]

        total = len(violations)
        violations = violations[offset : offset + limit]

        logger.info(f"✓ Retrieved {len(violations)} violations")

        return {
            "violations": violations,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(violations),
            },
        }

    except Exception as e:
        logger.error(f"❌ Error getting violations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get violations: {str(e)}",
        )


@router.post("/quality-gates")
async def create_quality_gate(
    gate_data: QualityGateCreate,
    db: Session = Depends(get_db),
) -> QualityGateResponse:
    """
    Define a quality gate for product promotion.

    Args:
        gate_data: Quality gate configuration
        db: Database session

    Returns:
        Created quality gate details
    """
    logger.info(f"📋 POST /api/v1/governance/quality-gates - Creating gate: {gate_data.name}")

    try:
        gate_id = f"gate_{gate_data.name.lower().replace(' ', '_')}"

        logger.info(f"✅ Quality gate created: {gate_id}")

        return QualityGateResponse(
            gate_id=gate_id,
            name=gate_data.name,
            description=gate_data.description,
            blocking=gate_data.blocking,
            conditions=gate_data.conditions,
            created_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"❌ Error creating quality gate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create quality gate: {str(e)}",
        )


@router.get("/quality-gates")
async def list_quality_gates(
    blocking_only: bool = False,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all quality gates.

    Args:
        blocking_only: Only return blocking gates
        db: Database session

    Returns:
        List of quality gates
    """
    logger.info(f"📋 GET /api/v1/governance/quality-gates")

    try:
        gates = [
            {
                "gate_id": "gate_min_trust",
                "name": "Minimum Trust Score Gate",
                "description": "Blocks promotion if trust score < 75%",
                "blocking": True,
                "conditions": {"min_trust_score": 75},
                "created_at": datetime.utcnow(),
                "passed_products": 8,
                "failed_products": 2,
            }
        ]

        if blocking_only:
            gates = [g for g in gates if g["blocking"]]

        logger.info(f"✓ Retrieved {len(gates)} quality gates")

        return {"gates": gates, "count": len(gates)}

    except Exception as e:
        logger.error(f"❌ Error listing quality gates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list quality gates: {str(e)}",
        )


@router.post("/alerts/rules")
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    db: Session = Depends(get_db),
) -> AlertRuleResponse:
    """
    Define an alert rule for policy violations.

    Args:
        rule_data: Alert rule configuration
        db: Database session

    Returns:
        Created alert rule details
    """
    logger.info(f"📋 POST /api/v1/governance/alerts/rules - Creating alert: {rule_data.name}")

    try:
        rule_id = f"alert_rule_{int(datetime.utcnow().timestamp())}"

        logger.info(f"✅ Alert rule created: {rule_id}")

        return AlertRuleResponse(
            rule_id=rule_id,
            name=rule_data.name,
            policy_id=rule_data.policy_id,
            channels=rule_data.channels,
            created_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"❌ Error creating alert rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create alert rule: {str(e)}",
        )


@router.get("/alerts")
async def get_alerts(
    severity: Optional[PolicySeverity] = None,
    acknowledged: bool = False,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get active alerts (with optional filters).

    Args:
        severity: Filter by severity
        acknowledged: Filter acknowledged alerts
        limit: Maximum results
        db: Database session

    Returns:
        List of active alerts
    """
    logger.info(f"📋 GET /api/v1/governance/alerts")

    try:
        alerts = [
            {
                "alert_id": "alert_1",
                "rule_id": "alert_rule_1",
                "policy_id": "policy_min_trust_score",
                "policy_name": "Minimum Trust Score",
                "severity": PolicySeverity.HIGH,
                "message": "Product 'data-product-1' violated minimum trust score policy",
                "product_id": "product-1",
                "timestamp": datetime.utcnow(),
                "acknowledged": False,
            }
        ]

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        alerts = alerts[:limit]

        logger.info(f"✓ Retrieved {len(alerts)} alerts")

        return {
            "alerts": alerts,
            "count": len(alerts),
            "unacknowledged": sum(1 for a in alerts if not a["acknowledged"]),
        }

    except Exception as e:
        logger.error(f"❌ Error getting alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alerts: {str(e)}",
        )


@router.get("/health")
async def governance_health() -> Dict[str, str]:
    """Health check for governance API."""
    return {"status": "healthy", "message": "Governance API is operational"}
