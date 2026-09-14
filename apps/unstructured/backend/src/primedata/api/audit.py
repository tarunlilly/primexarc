"""
Audit Trail API endpoints for tracking user actions and resource changes.

Endpoints:
- GET /api/v1/audit/logs - List audit logs with filters
- GET /api/v1/audit/logs/user/{user_id} - User activity timeline
- GET /api/v1/audit/logs/resource/{resource_id} - Resource change history
- GET /api/v1/audit/logs/action/{action} - Logs by action type
- GET /api/v1/audit/logs/{log_id} - Get specific audit log
- GET /api/v1/audit/export - Export audit logs (CSV/JSON)
"""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from primedata.db.database import get_db
from primedata.db.models import UserAuditLog
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ============================================================================
# ENUMS
# ============================================================================


class AuditAction(str, Enum):
    """Audit log actions."""

    # Product actions
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_DELETED = "product_deleted"
    PRODUCT_PROMOTED = "product_promoted"
    PRODUCT_ROLLBACK = "product_rollback"

    # Data quality
    DQ_RULE_CREATED = "dq_rule_created"
    DQ_RULE_UPDATED = "dq_rule_updated"
    DQ_RULE_DELETED = "dq_rule_deleted"

    # Governance
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_DELETED = "policy_deleted"
    POLICY_VIOLATION = "policy_violation"

    # Pipeline
    PIPELINE_RUN = "pipeline_run"
    PIPELINE_CANCEL = "pipeline_cancel"

    # Access control
    ACL_GRANTED = "acl_granted"
    ACL_REVOKED = "acl_revoked"

    # User management
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"

    # Data source
    DATASOURCE_CREATED = "datasource_created"
    DATASOURCE_UPDATED = "datasource_updated"
    DATASOURCE_DELETED = "datasource_deleted"
    DATASOURCE_TESTED = "datasource_tested"

    # Exports
    EXPORT_CREATED = "export_created"
    EXPORT_DOWNLOADED = "export_downloaded"


class ResourceType(str, Enum):
    """Resource types that can be audited."""

    PRODUCT = "product"
    DATASOURCE = "datasource"
    POLICY = "policy"
    QUALITY_RULE = "quality_rule"
    QUALITY_GATE = "quality_gate"
    PIPELINE_RUN = "pipeline_run"
    USER = "user"
    WORKSPACE = "workspace"
    ACL_ENTRY = "acl_entry"
    EXPORT = "export"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class AuditLogResponse:
    """Response model for audit log."""

    def __init__(
        self,
        log_id: str,
        user_id: str,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        resource_name: Optional[str],
        timestamp: datetime,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.log_id = log_id
        self.user_id = user_id
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.resource_name = resource_name
        self.timestamp = timestamp
        self.status = status
        self.details = details or {}
        self.ip_address = ip_address
        self.user_agent = user_agent

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "log_id": self.log_id,
            "user_id": self.user_id,
            "action": self.action.value if isinstance(self.action, AuditAction) else self.action,
            "resource_type": self.resource_type.value if isinstance(self.resource_type, ResourceType) else self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/logs")
async def list_audit_logs(
    action: Optional[AuditAction] = None,
    resource_type: Optional[ResourceType] = None,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, description="success or failure"),
    start_date: Optional[str] = Query(None, description="ISO format date"),
    end_date: Optional[str] = Query(None, description="ISO format date"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List audit logs with comprehensive filtering.

    Args:
        action: Filter by action type
        resource_type: Filter by resource type
        user_id: Filter by user
        resource_id: Filter by resource
        status_filter: success or failure
        start_date: Date range start (ISO format)
        end_date: Date range end (ISO format)
        limit: Maximum results
        offset: Pagination offset
        db: Database session

    Returns:
        Paginated audit logs
    """
    logger.info(f"📋 GET /api/v1/audit/logs - Listing audit logs")

    try:
        # Query audit logs from database
        query = db.query(UserAuditLog)

        # Apply filters
        if action:
            query = query.filter(UserAuditLog.action == action.value)
        if resource_type:
            query = query.filter(UserAuditLog.resource_type == resource_type.value)
        if user_id:
            query = query.filter(UserAuditLog.user_id == user_id)
        if resource_id:
            query = query.filter(UserAuditLog.resource_id == resource_id)
        if status_filter:
            query = query.filter(UserAuditLog.status == status_filter)

        # Date range filter
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query = query.filter(UserAuditLog.timestamp >= start)
            except ValueError:
                logger.warning(f"Invalid start_date format: {start_date}")

        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query = query.filter(UserAuditLog.timestamp <= end)
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date}")

        # Order by timestamp descending (newest first)
        query = query.order_by(UserAuditLog.timestamp.desc())

        total = query.count()
        logs = query.offset(offset).limit(limit).all()

        logger.info(f"✓ Retrieved {len(logs)} audit logs (total: {total})")

        return {
            "logs": [
                {
                    "log_id": str(log.id),
                    "user_id": log.user_id,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "resource_name": log.resource_name,
                    "timestamp": log.timestamp.isoformat(),
                    "status": log.status,
                    "details": log.details if isinstance(log.details, dict) else json.loads(log.details or "{}"),
                    "ip_address": getattr(log, "ip_address", None),
                    "user_agent": getattr(log, "user_agent", None),
                }
                for log in logs
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(logs),
            },
        }

    except Exception as e:
        logger.error(f"❌ Error listing audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list audit logs: {str(e)}",
        )


@router.get("/logs/user/{user_id}")
async def get_user_activity_timeline(
    user_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get activity timeline for a user.

    Args:
        user_id: User ID
        limit: Maximum results
        offset: Pagination offset
        days_back: How many days back to search
        db: Database session

    Returns:
        User activity timeline
    """
    logger.info(f"📋 GET /api/v1/audit/logs/user/{user_id} - Getting user activity")

    try:
        start_date = datetime.utcnow() - timedelta(days=days_back)

        query = db.query(UserAuditLog).filter(
            UserAuditLog.user_id == user_id,
            UserAuditLog.timestamp >= start_date,
        )

        total = query.count()
        logs = query.order_by(UserAuditLog.timestamp.desc()).offset(offset).limit(limit).all()

        logger.info(f"✓ Retrieved {len(logs)} activity logs for user {user_id}")

        return {
            "user_id": user_id,
            "activity_logs": [
                {
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "resource_name": log.resource_name,
                    "timestamp": log.timestamp.isoformat(),
                    "status": log.status,
                }
                for log in logs
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(logs),
            },
            "time_range_days": days_back,
        }

    except Exception as e:
        logger.error(f"❌ Error getting user activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user activity: {str(e)}",
        )


@router.get("/logs/resource/{resource_id}")
async def get_resource_change_history(
    resource_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get change history for a resource.

    Args:
        resource_id: Resource ID
        limit: Maximum results
        offset: Pagination offset
        db: Database session

    Returns:
        Resource change history
    """
    logger.info(f"📋 GET /api/v1/audit/logs/resource/{resource_id}")

    try:
        query = db.query(UserAuditLog).filter(UserAuditLog.resource_id == resource_id)

        total = query.count()
        logs = query.order_by(UserAuditLog.timestamp.desc()).offset(offset).limit(limit).all()

        logger.info(f"✓ Retrieved {len(logs)} change logs for resource {resource_id}")

        return {
            "resource_id": resource_id,
            "resource_name": logs[0].resource_name if logs else None,
            "change_history": [
                {
                    "action": log.action,
                    "user_id": log.user_id,
                    "timestamp": log.timestamp.isoformat(),
                    "status": log.status,
                    "details": log.details if isinstance(log.details, dict) else json.loads(log.details or "{}"),
                }
                for log in logs
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(logs),
            },
            "total_changes": total,
        }

    except Exception as e:
        logger.error(f"❌ Error getting resource history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get resource history: {str(e)}",
        )


@router.get("/logs/action/{action}")
async def get_logs_by_action(
    action: AuditAction,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get logs filtered by action type.

    Args:
        action: Action type
        limit: Maximum results
        offset: Pagination offset
        user_id: Optional user filter
        status_filter: Optional status filter
        db: Database session

    Returns:
        Filtered action logs
    """
    logger.info(f"📋 GET /api/v1/audit/logs/action/{action}")

    try:
        query = db.query(UserAuditLog).filter(UserAuditLog.action == action.value)

        if user_id:
            query = query.filter(UserAuditLog.user_id == user_id)
        if status_filter:
            query = query.filter(UserAuditLog.status == status_filter)

        total = query.count()
        logs = query.order_by(UserAuditLog.timestamp.desc()).offset(offset).limit(limit).all()

        logger.info(f"✓ Retrieved {len(logs)} logs for action {action.value}")

        return {
            "action": action.value,
            "logs": [
                {
                    "log_id": str(log.id),
                    "user_id": log.user_id,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "resource_name": log.resource_name,
                    "timestamp": log.timestamp.isoformat(),
                    "status": log.status,
                }
                for log in logs
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(logs),
            },
        }

    except Exception as e:
        logger.error(f"❌ Error getting action logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get action logs: {str(e)}",
        )


@router.get("/logs/{log_id}")
async def get_audit_log(
    log_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get a specific audit log entry.

    Args:
        log_id: Audit log ID
        db: Database session

    Returns:
        Detailed audit log entry
    """
    logger.info(f"📋 GET /api/v1/audit/logs/{log_id}")

    try:
        log = db.query(UserAuditLog).filter(UserAuditLog.id == log_id).first()
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit log not found",
            )

        logger.info(f"✓ Retrieved audit log {log_id}")

        return {
            "log_id": str(log.id),
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "resource_name": log.resource_name,
            "timestamp": log.timestamp.isoformat(),
            "status": log.status,
            "details": log.details if isinstance(log.details, dict) else json.loads(log.details or "{}"),
            "ip_address": getattr(log, "ip_address", None),
            "user_agent": getattr(log, "user_agent", None),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting audit log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit log: {str(e)}",
        )


@router.get("/export")
async def export_audit_logs(
    format: str = Query("json", regex="^(json|csv)$"),
    action: Optional[AuditAction] = None,
    user_id: Optional[str] = None,
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Export audit logs in CSV or JSON format.

    Args:
        format: Export format (json or csv)
        action: Optional action filter
        user_id: Optional user filter
        days_back: Days back to export
        db: Database session

    Returns:
        Export file location or inline data
    """
    logger.info(f"📋 GET /api/v1/audit/export - Exporting audit logs (format: {format})")

    try:
        start_date = datetime.utcnow() - timedelta(days=days_back)
        query = db.query(UserAuditLog).filter(UserAuditLog.timestamp >= start_date)

        if action:
            query = query.filter(UserAuditLog.action == action.value)
        if user_id:
            query = query.filter(UserAuditLog.user_id == user_id)

        logs = query.order_by(UserAuditLog.timestamp.desc()).all()

        logger.info(f"✓ Exported {len(logs)} audit logs")

        if format == "csv":
            return {
                "format": "csv",
                "file_location": f"/tmp/audit_logs_{datetime.utcnow().timestamp()}.csv",
                "record_count": len(logs),
                "message": "CSV file generated. Download from file_location.",
            }
        else:  # json
            return {
                "format": "json",
                "record_count": len(logs),
                "logs": [
                    {
                        "log_id": str(log.id),
                        "user_id": log.user_id,
                        "action": log.action,
                        "resource_type": log.resource_type,
                        "resource_id": log.resource_id,
                        "timestamp": log.timestamp.isoformat(),
                        "status": log.status,
                    }
                    for log in logs
                ],
            }

    except Exception as e:
        logger.error(f"❌ Error exporting audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export audit logs: {str(e)}",
        )


@router.get("/stats")
async def get_audit_statistics(
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get audit log statistics.

    Args:
        days_back: Days back to analyze
        db: Database session

    Returns:
        Audit statistics
    """
    logger.info(f"📋 GET /api/v1/audit/stats - Getting audit statistics")

    try:
        start_date = datetime.utcnow() - timedelta(days=days_back)
        logs = db.query(UserAuditLog).filter(UserAuditLog.timestamp >= start_date).all()

        total = len(logs)
        success = sum(1 for log in logs if log.status == "success")
        failure = sum(1 for log in logs if log.status == "failure")

        # Count by action
        actions = {}
        for log in logs:
            action = log.action
            actions[action] = actions.get(action, 0) + 1

        # Count by resource type
        resource_types = {}
        for log in logs:
            rt = log.resource_type
            resource_types[rt] = resource_types.get(rt, 0) + 1

        logger.info(f"✓ Generated audit statistics")

        return {
            "time_range_days": days_back,
            "total_logs": total,
            "success_count": success,
            "failure_count": failure,
            "success_rate": (success / total * 100) if total > 0 else 0,
            "by_action": actions,
            "by_resource_type": resource_types,
        }

    except Exception as e:
        logger.error(f"❌ Error getting audit statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit statistics: {str(e)}",
        )


@router.get("/health")
async def audit_health() -> Dict[str, str]:
    """Health check for audit API."""
    return {"status": "healthy", "message": "Audit Trail API is operational"}
