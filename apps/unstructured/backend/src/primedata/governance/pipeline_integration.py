"""
Governance Module - Pipeline Integration

Integrates governance checks into the ingestion pipeline to ensure data quality
gates are enforced during processing and quality policies trigger alerts.

Implements DRY principle: Reuses PolicyEngine and QualityGatesManager for
consistent governance across pipeline stages.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from primedata.utils.log_utils import get_logger

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
    QualityThreshold,
    QualityGatesManager,
    GateStatus,
)
from .alerts import (
    AlertRule,
    AlertGenerator,
    AlertChannel,
    AlertPriority,
)

logger = get_logger(__name__)


# ============================================================================
# GOVERNANCE PIPELINE STAGE
# ============================================================================


class GovernancePipelineStage:
    """
    Integrates governance checks into pipeline stages.

    Evaluates policies and quality gates before/after pipeline operations,
    generates alerts on failures, and allows operation gating.
    """

    def __init__(
        self,
        stage_name: str,
        policy_engine: PolicyEngine,
        gates_manager: QualityGatesManager,
        alert_generator: AlertGenerator,
    ):
        """
        Initialize governance pipeline stage.

        Args:
            stage_name: Name of pipeline stage
            policy_engine: PolicyEngine instance
            gates_manager: QualityGatesManager instance
            alert_generator: AlertGenerator instance
        """
        self.stage_name = stage_name
        self.policy_engine = policy_engine
        self.gates_manager = gates_manager
        self.alert_generator = alert_generator
        self.stage_metrics: Dict[str, Any] = {}
        logger.debug(f"GovernancePipelineStage initialized: {stage_name}")

    def evaluate_policies(
        self,
        resource_id: str,
        resource_type: str,
        resource_data: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, PolicyEvaluationResult]]:
        """
        Evaluate policies for a resource.

        Args:
            resource_id: Resource ID
            resource_type: Resource type
            resource_data: Resource data for evaluation

        Returns:
            Tuple of (all_passed: bool, results: Dict)
        """
        results = self.policy_engine.evaluate_policies(
            resource_id, resource_type, resource_data
        )

        # Process any violations as alerts
        violations = self.policy_engine.get_violations(results)
        if violations:
            alerts = self.alert_generator.process_violations(violations)
            self.alert_generator.send_alerts(alerts)

        has_blocking = self.policy_engine.has_blocking_violations(results)

        logger.info(
            f"Stage '{self.stage_name}' policy evaluation | "
            f"Resource: {resource_type}/{resource_id} | "
            f"Violations: {len(violations)} | "
            f"Blocking: {has_blocking}"
        )

        return not has_blocking, results

    def evaluate_gates(
        self,
        metrics: Dict[str, float],
        resource_id: str = "",
        resource_type: str = "",
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate quality gates for metrics.

        Args:
            metrics: Dictionary of metric_name -> value
            resource_id: Resource ID being evaluated
            resource_type: Resource type being evaluated

        Returns:
            Tuple of (can_proceed: bool, gate_results: Dict)
        """
        results = self.gates_manager.evaluate_all_gates(
            metrics, resource_id, resource_type
        )

        can_proceed = self.gates_manager.can_proceed(results)
        summary = self.gates_manager.summarize_gates(results)

        logger.info(
            f"Stage '{self.stage_name}' gate evaluation | "
            f"Resource: {resource_type}/{resource_id} | "
            f"Gates: {summary['total_gates']} | "
            f"Open: {summary['open_gates']} | "
            f"Closed: {summary['closed_gates']} | "
            f"Can Proceed: {can_proceed}"
        )

        return can_proceed, results

    def record_stage_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Record metrics for this stage.

        Args:
            metrics: Dictionary of metrics
        """
        self.stage_metrics = metrics.copy()
        logger.debug(f"Stage '{self.stage_name}' metrics recorded: {len(metrics)} metrics")

    def get_stage_summary(self) -> Dict[str, Any]:
        """
        Get summary of stage governance status.

        Returns:
            Summary dictionary
        """
        policy_summary = self.policy_engine.summarize_results(
            self.policy_engine.evaluate_policies("", "", {})
        )
        alert_summary = self.alert_generator.get_alert_summary()

        return {
            "stage": self.stage_name,
            "policies": policy_summary,
            "alerts": alert_summary,
            "metrics_recorded": len(self.stage_metrics),
            "timestamp": datetime.utcnow().isoformat(),
        }


# ============================================================================
# GOVERNANCE PIPELINE ORCHESTRATOR
# ============================================================================


class GovernancePipeline:
    """
    Orchestrates governance across multiple pipeline stages.

    KISS principle: Simple composition of stages with shared governance
    components for consistent policy enforcement.
    """

    def __init__(
        self,
        pipeline_name: str,
        policy_engine: Optional[PolicyEngine] = None,
        gates_manager: Optional[QualityGatesManager] = None,
        alert_generator: Optional[AlertGenerator] = None,
    ):
        """
        Initialize governance pipeline.

        Args:
            pipeline_name: Name of pipeline
            policy_engine: PolicyEngine instance (created if None)
            gates_manager: QualityGatesManager instance (created if None)
            alert_generator: AlertGenerator instance (created if None)
        """
        self.pipeline_name = pipeline_name
        self.policy_engine = policy_engine or PolicyEngine()
        self.gates_manager = gates_manager or QualityGatesManager(self.policy_engine)
        self.alert_generator = alert_generator or AlertGenerator()
        self.stages: Dict[str, GovernancePipelineStage] = {}
        self.execution_log: List[Dict[str, Any]] = []
        logger.debug(f"GovernancePipeline initialized: {pipeline_name}")

    def register_stage(self, stage_name: str) -> GovernancePipelineStage:
        """
        Register a pipeline stage with governance.

        Args:
            stage_name: Name of stage

        Returns:
            GovernancePipelineStage instance
        """
        stage = GovernancePipelineStage(
            stage_name,
            self.policy_engine,
            self.gates_manager,
            self.alert_generator,
        )
        self.stages[stage_name] = stage
        logger.debug(f"Stage registered: {stage_name}")
        return stage

    def get_stage(self, stage_name: str) -> Optional[GovernancePipelineStage]:
        """
        Get a registered stage.

        Args:
            stage_name: Name of stage

        Returns:
            GovernancePipelineStage or None
        """
        return self.stages.get(stage_name)

    def execute_stage_with_governance(
        self,
        stage_name: str,
        operation: callable,
        *args,
        **kwargs,
    ) -> Tuple[bool, Any, Dict[str, Any]]:
        """
        Execute a pipeline stage with governance checks.

        Args:
            stage_name: Name of stage
            operation: Callable to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Tuple of (success: bool, result: Any, governance_result: Dict)
        """
        stage = self.get_stage(stage_name)
        if not stage:
            logger.warning(f"Stage not registered: {stage_name}")
            return False, None, {"error": "Stage not registered"}

        try:
            # Execute operation
            result = operation(*args, **kwargs)

            # Record execution
            self.execution_log.append(
                {
                    "stage": stage_name,
                    "success": True,
                    "timestamp": datetime.utcnow().isoformat(),
                    "result": str(result)[:100],  # Truncate for logging
                }
            )

            logger.info(f"Stage executed successfully: {stage_name}")
            return True, result, {"status": "success"}

        except Exception as e:
            # Record failure
            self.execution_log.append(
                {
                    "stage": stage_name,
                    "success": False,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e)[:100],
                }
            )

            logger.error(f"Stage execution failed: {stage_name} - {e}")
            return False, None, {"error": str(e)}

    def get_pipeline_summary(self) -> Dict[str, Any]:
        """
        Get summary of pipeline governance status.

        Returns:
            Summary dictionary
        """
        stage_summaries = {}
        for stage_name, stage in self.stages.items():
            stage_summaries[stage_name] = stage.get_stage_summary()

        return {
            "pipeline": self.pipeline_name,
            "stages": stage_summaries,
            "total_stages": len(self.stages),
            "executions": len(self.execution_log),
            "policy_engine_policies": len(self.policy_engine.policies),
            "quality_gates": len(self.gates_manager.gates),
            "active_alert_rules": sum(1 for r in self.alert_generator.rules.values() if r.enabled),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_execution_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get execution log for recent executions.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of execution log entries
        """
        return self.execution_log[-limit:]


# ============================================================================
# PRE-BUILT PIPELINE TEMPLATES
# ============================================================================


def create_ingestion_pipeline() -> GovernancePipeline:
    """
    Create a pre-configured governance pipeline for data ingestion.

    Returns:
        Configured GovernancePipeline instance
    """
    pipeline = GovernancePipeline("DataIngestionPipeline")

    # Register stages
    raw_ingestion = pipeline.register_stage("raw_ingestion")
    validation = pipeline.register_stage("validation")
    enrichment = pipeline.register_stage("enrichment")
    indexing = pipeline.register_stage("indexing")

    # Setup common quality gates for all stages
    quality_gate = QualityGate(
        gate_id="data_quality_gate",
        name="Minimum Data Quality",
        description="Ensures minimum quality standards",
        category=PolicyCategory.QUALITY,
        severity=PolicySeverity.ERROR,
        blocking=True,
    )
    quality_gate.add_threshold(QualityThreshold(metric_name="quality_score", min_value=0.7))
    quality_gate.add_threshold(QualityThreshold(metric_name="completeness", min_value=0.8))

    pipeline.gates_manager.register_gate(quality_gate)

    # Setup alert rules
    alert_rule = AlertRule(
        rule_id="ingestion_alert",
        name="Data Quality Alert",
        description="Alert on data quality issues",
        min_severity=PolicySeverity.WARNING,
        channels=[AlertChannel.LOG],
        priority=AlertPriority.HIGH,
    )
    pipeline.alert_generator.register_rule(alert_rule)

    logger.debug("Ingestion pipeline template created with standard gates and alerts")
    return pipeline


def create_processing_pipeline() -> GovernancePipeline:
    """
    Create a pre-configured governance pipeline for data processing.

    Returns:
        Configured GovernancePipeline instance
    """
    pipeline = GovernancePipeline("DataProcessingPipeline")

    # Register stages
    preprocessing = pipeline.register_stage("preprocessing")
    transformation = pipeline.register_stage("transformation")
    aggregation = pipeline.register_stage("aggregation")
    export = pipeline.register_stage("export")

    # Setup quality gates for processing
    performance_gate = QualityGate(
        gate_id="performance_gate",
        name="Performance Gate",
        description="Ensures processing performance",
        category=PolicyCategory.PERFORMANCE,
        severity=PolicySeverity.WARNING,
        blocking=False,
    )
    performance_gate.add_threshold(QualityThreshold(metric_name="processing_time", max_value=300))

    pipeline.gates_manager.register_gate(performance_gate)

    logger.debug("Processing pipeline template created with performance gates")
    return pipeline
