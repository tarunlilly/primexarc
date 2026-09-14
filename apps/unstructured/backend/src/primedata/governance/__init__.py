"""
Governance Module

Provides comprehensive policy-based governance for data quality, compliance, and security.

Components:
- policy_engine: Core policy evaluation engine
- quality_gates: Quality-based policy gates
- alerts: Alert generation and notification
"""

from .policy_engine import (
    PolicyEngine,
    PolicySeverity,
    PolicyCategory,
    PolicyStatus,
    PolicyViolation,
    PolicyEvaluationResult,
    PolicyRuleDefinition,
)
from .quality_gates import (
    QualityGate,
    QualityGateResult,
    QualityThreshold,
    QualityGatesManager,
    GateStatus,
)
from .alerts import (
    Alert,
    AlertRule,
    AlertGenerator,
    AlertChannel,
    AlertPriority,
    default_log_handler,
    default_email_handler,
    default_webhook_handler,
    default_slack_handler,
)
from .pipeline_integration import (
    GovernancePipelineStage,
    GovernancePipeline,
    create_ingestion_pipeline,
    create_processing_pipeline,
)

__all__ = [
    # Policy Engine
    "PolicyEngine",
    "PolicySeverity",
    "PolicyCategory",
    "PolicyStatus",
    "PolicyViolation",
    "PolicyEvaluationResult",
    "PolicyRuleDefinition",
    # Quality Gates
    "QualityGate",
    "QualityGateResult",
    "QualityThreshold",
    "QualityGatesManager",
    "GateStatus",
    # Alerts
    "Alert",
    "AlertRule",
    "AlertGenerator",
    "AlertChannel",
    "AlertPriority",
    "default_log_handler",
    "default_email_handler",
    "default_webhook_handler",
    "default_slack_handler",
    # Pipeline Integration
    "GovernancePipelineStage",
    "GovernancePipeline",
    "create_ingestion_pipeline",
    "create_processing_pipeline",
]
