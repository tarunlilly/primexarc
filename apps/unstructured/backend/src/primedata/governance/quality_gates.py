"""
Governance Module - Quality Gates

Provides policy-based quality gates that determine if operations can proceed
based on quality metrics and thresholds.

Implements DRY principle: Reuses PolicyEngine for evaluation, extends with
quality-specific logic for pass/fail gates.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from primedata.utils.log_utils import get_logger

from .policy_engine import (
    PolicyEngine,
    PolicySeverity,
    PolicyCategory,
    PolicyStatus,
    PolicyViolation,
    PolicyEvaluationResult,
)

logger = get_logger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class GateStatus(str, Enum):
    """Quality gate status."""

    OPEN = "open"  # Gate passes, operation allowed
    CLOSED = "closed"  # Gate blocked, operation denied
    WARNING = "warning"  # Gate passes with warnings


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class QualityThreshold:
    """Represents a quality threshold for a metric."""

    metric_name: str
    min_value: Optional[float] = None  # Minimum acceptable value
    max_value: Optional[float] = None  # Maximum acceptable value
    weight: float = 1.0  # Importance weight for calculations
    enabled: bool = True  # Whether threshold is active

    def check(self, value: float) -> bool:
        """
        Check if value meets threshold.

        Args:
            value: Value to check

        Returns:
            True if value meets threshold, False otherwise
        """
        if not self.enabled:
            return True
        if self.min_value is not None and value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False
        return True


@dataclass
class QualityGate:
    """Represents a quality gate with thresholds."""

    gate_id: str
    name: str
    description: str
    category: PolicyCategory
    severity: PolicySeverity
    thresholds: List[QualityThreshold] = field(default_factory=list)
    blocking: bool = True  # Whether gate failures block operations
    enabled: bool = True  # Whether gate is active

    def add_threshold(self, threshold: QualityThreshold) -> None:
        """
        Add a threshold to the gate.

        Args:
            threshold: QualityThreshold to add
        """
        self.thresholds.append(threshold)
        logger.debug(f"Threshold added to gate {self.gate_id}: {threshold.metric_name}")

    def evaluate(self, metrics: Dict[str, float]) -> tuple[bool, List[str]]:
        """
        Evaluate metrics against thresholds.

        Args:
            metrics: Dictionary of metric_name -> value

        Returns:
            Tuple of (all_pass: bool, failed_messages: List[str])
        """
        if not self.enabled:
            return True, []

        failed_messages = []

        for threshold in self.thresholds:
            if threshold.metric_name not in metrics:
                msg = f"Metric '{threshold.metric_name}' not found in evaluation data"
                logger.warning(msg)
                failed_messages.append(msg)
                continue

            value = metrics[threshold.metric_name]
            if not threshold.check(value):
                msg = (
                    f"Metric '{threshold.metric_name}' failed: "
                    f"value {value} outside acceptable range "
                    f"[{threshold.min_value}, {threshold.max_value}]"
                )
                failed_messages.append(msg)
                logger.debug(msg)

        return len(failed_messages) == 0, failed_messages


@dataclass
class QualityGateResult:
    """Result of evaluating a quality gate."""

    gate_id: str
    gate_name: str
    status: GateStatus
    metrics_evaluated: Dict[str, float] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    resource_id: str = ""
    resource_type: str = ""
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_blocking(self) -> bool:
        """Check if gate failure blocks operations."""
        return self.status == GateStatus.CLOSED

    def __str__(self) -> str:
        return f"Gate {self.gate_name}: {self.status.value} | Failures: {len(self.failures)}"


# ============================================================================
# QUALITY GATES MANAGER
# ============================================================================


class QualityGatesManager:
    """
    Manages quality gates for operations.

    KISS principle: Simple gate evaluation with reuse of PolicyEngine for
    violation tracking.
    """

    def __init__(self, policy_engine: PolicyEngine):
        """
        Initialize quality gates manager.

        Args:
            policy_engine: PolicyEngine instance for policy evaluation
        """
        self.policy_engine = policy_engine
        self.gates: Dict[str, QualityGate] = {}
        logger.debug("QualityGatesManager initialized")

    def register_gate(self, gate: QualityGate) -> None:
        """
        Register a quality gate.

        Args:
            gate: QualityGate to register
        """
        self.gates[gate.gate_id] = gate
        logger.debug(f"Gate registered: {gate.gate_id} ({gate.name})")

    def evaluate_gate(
        self,
        gate_id: str,
        metrics: Dict[str, float],
        resource_id: str = "",
        resource_type: str = "",
    ) -> QualityGateResult:
        """
        Evaluate a single quality gate.

        Args:
            gate_id: ID of gate to evaluate
            metrics: Dictionary of metric values
            resource_id: ID of resource being evaluated
            resource_type: Type of resource being evaluated

        Returns:
            QualityGateResult
        """
        if gate_id not in self.gates:
            logger.warning(f"Gate not found: {gate_id}")
            return QualityGateResult(
                gate_id=gate_id,
                gate_name="Unknown",
                status=GateStatus.OPEN,
                resource_id=resource_id,
                resource_type=resource_type,
            )

        gate = self.gates[gate_id]
        passed, failures = gate.evaluate(metrics)

        status = GateStatus.OPEN if passed else GateStatus.CLOSED
        if passed and any(metrics.get(t.metric_name, 0) for t in gate.thresholds):
            status = GateStatus.OPEN

        result = QualityGateResult(
            gate_id=gate.gate_id,
            gate_name=gate.name,
            status=status,
            metrics_evaluated=metrics.copy(),
            failures=failures,
            resource_id=resource_id,
            resource_type=resource_type,
        )

        logger.debug(
            f"Gate evaluated: {gate.name} | Resource: {resource_type}/{resource_id} | "
            f"Status: {status.value}"
        )

        return result

    def evaluate_all_gates(
        self,
        metrics: Dict[str, float],
        resource_id: str = "",
        resource_type: str = "",
    ) -> Dict[str, QualityGateResult]:
        """
        Evaluate all registered gates.

        Args:
            metrics: Dictionary of metric values
            resource_id: ID of resource being evaluated
            resource_type: Type of resource being evaluated

        Returns:
            Dictionary mapping gate_id to QualityGateResult
        """
        results = {}

        for gate_id, gate in self.gates.items():
            if not gate.enabled:
                continue

            result = self.evaluate_gate(
                gate_id,
                metrics,
                resource_id=resource_id,
                resource_type=resource_type,
            )
            results[gate_id] = result

        return results

    def get_blocking_gates(
        self, results: Dict[str, QualityGateResult]
    ) -> List[QualityGateResult]:
        """
        Get gates that are blocking operations.

        Args:
            results: Dictionary of QualityGateResult

        Returns:
            List of blocking gate results
        """
        blocking = []
        for result in results.values():
            gate = self.gates.get(result.gate_id)
            if gate and gate.blocking and result.is_blocking:
                blocking.append(result)
        return blocking

    def can_proceed(self, results: Dict[str, QualityGateResult]) -> bool:
        """
        Check if operations can proceed based on gate results.

        Args:
            results: Dictionary of QualityGateResult

        Returns:
            True if no blocking gates are closed, False otherwise
        """
        blocking = self.get_blocking_gates(results)
        return len(blocking) == 0

    def summarize_gates(self, results: Dict[str, QualityGateResult]) -> Dict[str, Any]:
        """
        Summarize gate evaluation results.

        Args:
            results: Dictionary of QualityGateResult

        Returns:
            Summary dictionary with counts and status
        """
        blocking = self.get_blocking_gates(results)

        return {
            "total_gates": len(results),
            "open_gates": sum(1 for r in results.values() if r.status == GateStatus.OPEN),
            "closed_gates": sum(1 for r in results.values() if r.status == GateStatus.CLOSED),
            "warning_gates": sum(
                1 for r in results.values() if r.status == GateStatus.WARNING
            ),
            "blocking_gates": len(blocking),
            "can_proceed": self.can_proceed(results),
        }
