"""
Plan limits configuration - single source of truth.

This module contains all billing plan limits in one place to avoid duplication
and ensure consistency across the application.
"""

from typing import Dict, Any
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

# Plan limits configuration
# -1 means unlimited
PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_products": 3,
        "max_data_sources_per_product": 5,
        "max_pipeline_runs_per_month": 10,
        "max_raw_files_size_mb": 100,  # 100 MB total for all raw files across all data sources
        "schedule_frequency": "manual",
    },
    "pro": {
        "max_products": 25,
        "max_data_sources_per_product": 50,
        "max_pipeline_runs_per_month": 1000,
        "max_raw_files_size_mb": -1,  # Unlimited
        "schedule_frequency": "hourly",
    },
    "enterprise": {
        "max_products": -1,  # Unlimited
        "max_data_sources_per_product": -1,  # Unlimited
        "max_pipeline_runs_per_month": -1,  # Unlimited
        "max_raw_files_size_mb": -1,  # Unlimited
        "schedule_frequency": "realtime",
    },
}


def get_plan_limits(plan_name: str) -> Dict[str, Any]:
    """
    Get all limits for a plan.

    Args:
        plan_name: Plan name (free, pro, enterprise)

    Returns:
        Dictionary of plan limits
    """
    logger.debug(f"⚠️ get_plan_limits(plan_name={plan_name})")
    normalized_plan = plan_name.lower()
    limits = PLAN_LIMITS.get(normalized_plan, PLAN_LIMITS["free"])
    logger.info(f"⚠️ ✅ Retrieved plan limits: plan={normalized_plan}, limit_keys={list(limits.keys())}")
    logger.debug(f"📋 Plan limits details: {limits}")
    return limits


def get_plan_limit(plan_name: str, limit_type: str) -> Any:
    """
    Get a specific limit for a plan.

    Args:
        plan_name: Plan name (free, pro, enterprise)
        limit_type: Type of limit (e.g., "max_products", "max_raw_files_size_mb")

    Returns:
        Limit value (-1 for unlimited, or number)
    """
    logger.debug(f"⚠️ get_plan_limit(plan_name={plan_name}, limit_type={limit_type})")
    limits = get_plan_limits(plan_name)
    limit_value = limits.get(limit_type, -1)  # Default to unlimited if not found
    if limit_value == -1:
        logger.info(f"⚠️ ✅ Plan limit: {plan_name}.{limit_type} = UNLIMITED")
    else:
        logger.info(f"⚠️ ✅ Plan limit: {plan_name}.{limit_type} = {limit_value}")
    return limit_value

