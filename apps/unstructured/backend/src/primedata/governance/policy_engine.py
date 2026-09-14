"""
Governance Module - Policy Engine Core

Provides the foundation for policy-based governance with enums, data classes,
and the core PolicyEngine orchestrator for evaluating data quality rules.

Follows DRY and KISS principles: minimal, focused implementations reused across module.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class PolicySeverity(str, Enum):
    """Policy violation severity levels."""

    INFO = "info"  # Informational
    WARNING = "warning"  # Non-blocking warning
    ERROR = "error"  # Blocking error
    CRITICAL = "critical"  # Critical blocking error


class PolicyCategory(str, Enum):
    """Policy categories for organization and filtering."""

    QUALITY = "quality"  # Data quality policies
    COMPLIANCE = "compliance"  # Compliance policies
    SECURITY = "security"  # Security policies
    PERFORMANCE = "performance"  # Performance policies
    LINEAGE = "lineage"  # Data lineage policies


class PolicyStatus(str, Enum):
    """Policy evaluation status."""

    PASSED = "passed"  # Policy passed
    FAILED = "failed"  # Policy failed
    WARNINGS = "warnings"  # Policy passed with warnings
    UNKNOWN = "unknown"  # Policy status unknown


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class PolicyViolation:
    """Represents a single policy violation."""

    policy_id: str
    policy_name: str
    severity: PolicySeverity
    category: PolicyCategory
    message: str
    resource_id: str
    resource_type: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)

    def is_blocking(self) -> bool:
        """Check if violation is blocking (ERROR or CRITICAL)."""
        return self.severity in (PolicySeverity.ERROR, PolicySeverity.CRITICAL)

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.policy_name}: {self.message}"


@dataclass
class PolicyEvaluationResult:
    """Result of evaluating a policy against a resource."""

    policy_id: str
    policy_name: str
    resource_id: str
    status: PolicyStatus
    violations: List[PolicyViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_blocking(self) -> bool:
        """Check if any violation is blocking."""
        return any(v.is_blocking() for v in self.violations)

    @property
    def violation_count(self) -> int:
        """Get count of violations."""
        return len(self.violations)

    @property
    def warning_count(self) -> int:
        """Get count of warnings."""
        return len(self.warnings)

    def __str__(self) -> str:
        status_str = f"Status: {self.status.value}"
        if self.violations:
            status_str += f" | Violations: {len(self.violations)}"
        if self.warnings:
            status_str += f" | Warnings: {len(self.warnings)}"
        return status_str


@dataclass
class PolicyRuleDefinition:
    """Definition of a policy rule."""

    rule_id: str
    name: str
    description: str
    category: PolicyCategory
    severity: PolicySeverity
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# POLICY ENGINE
# ============================================================================


class PolicyEngine:
    """
    Evaluates policies against resources and collects violations.

    KISS principle: Single responsibility - evaluate policies, collect results.
    """

    def __init__(self):
        """Initialize policy engine."""
        self.policies: Dict[str, PolicyRuleDefinition] = {}
        logger.debug("PolicyEngine initialized")

    def register_policy(self, policy: PolicyRuleDefinition) -> None:
        """
        Register a policy rule.

        Args:
            policy: PolicyRuleDefinition to register
        """
        self.policies[policy.rule_id] = policy
        logger.debug(f"Policy registered: {policy.rule_id} ({policy.name})")

    def evaluate_policies(
        self, resource_id: str, resource_type: str, resource_data: Dict[str, Any]
    ) -> Dict[str, PolicyEvaluationResult]:
        """
        Evaluate all registered policies against a resource.

        DRY principle: Reuses _evaluate_policy for each policy.

        Args:
            resource_id: ID of resource to evaluate
            resource_type: Type of resource
            resource_data: Resource data for evaluation

        Returns:
            Dictionary mapping policy_id to PolicyEvaluationResult
        """
        results = {}

        for policy_id, policy in self.policies.items():
            if not policy.enabled:
                continue

            result = self._evaluate_policy(
                policy, resource_id, resource_type, resource_data
            )
            results[policy_id] = result

            logger.debug(
                f"Policy evaluated: {policy.name} | "
                f"Resource: {resource_type}/{resource_id} | "
                f"Status: {result.status.value}"
            )

        return results

    def _evaluate_policy(
        self,
        policy: PolicyRuleDefinition,
        resource_id: str,
        resource_type: str,
        resource_data: Dict[str, Any],
    ) -> PolicyEvaluationResult:
        """
        Evaluate a single policy.

        Override in subclasses or use custom evaluators.

        Args:
            policy: Policy rule to evaluate
            resource_id: Resource ID
            resource_type: Resource type
            resource_data: Resource data

        Returns:
            PolicyEvaluationResult
        """
        # Default: pass all policies (override in subclasses)
        return PolicyEvaluationResult(
            policy_id=policy.rule_id,
            policy_name=policy.name,
            resource_id=resource_id,
            status=PolicyStatus.PASSED,
        )

    def get_violations(
        self, results: Dict[str, PolicyEvaluationResult]
    ) -> List[PolicyViolation]:
        """
        Extract all violations from evaluation results.

        Args:
            results: Dictionary of PolicyEvaluationResult

        Returns:
            List of all PolicyViolation objects
        """
        violations = []
        for result in results.values():
            violations.extend(result.violations)
        return violations

    def has_blocking_violations(
        self, results: Dict[str, PolicyEvaluationResult]
    ) -> bool:
        """
        Check if any blocking violations exist.

        Args:
            results: Dictionary of PolicyEvaluationResult

        Returns:
            True if any policy result has blocking violations
        """
        return any(result.is_blocking for result in results.values())

    def summarize_results(
        self, results: Dict[str, PolicyEvaluationResult]
    ) -> Dict[str, Any]:
        """
        Summarize evaluation results.

        Args:
            results: Dictionary of PolicyEvaluationResult

        Returns:
            Summary dictionary with counts and status
        """
        violations = self.get_violations(results)
        has_blocking = self.has_blocking_violations(results)

        return {
            "total_policies": len(results),
            "passed_policies": sum(
                1 for r in results.values() if r.status == PolicyStatus.PASSED
            ),
            "failed_policies": sum(
                1 for r in results.values() if r.status == PolicyStatus.FAILED
            ),
            "total_violations": len(violations),
            "blocking_violations": sum(1 for v in violations if v.is_blocking()),
            "blocking_detected": has_blocking,
        }
