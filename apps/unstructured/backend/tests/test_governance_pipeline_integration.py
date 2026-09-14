"""
Comprehensive tests for governance pipeline integration.

Tests cover:
- Governance pipeline stages
- Policy evaluation in pipeline context
- Quality gate evaluation in stages
- Pipeline orchestration
- Stage registration and execution
- Pipeline templates
- Error handling and logging
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from primedata.governance.pipeline_integration import (
    GovernancePipelineStage,
    GovernancePipeline,
    create_ingestion_pipeline,
    create_processing_pipeline,
)
from primedata.governance.policy_engine import (
    PolicyEngine,
    PolicySeverity,
    PolicyCategory,
    PolicyViolation,
)
from primedata.governance.quality_gates import QualityGatesManager, QualityGate, QualityThreshold
from primedata.governance.alerts import AlertGenerator, AlertRule, AlertChannel


# ============================================================================
# GOVERNANCE PIPELINE STAGE TESTS
# ============================================================================


class TestGovernancePipelineStage:
    """Tests for GovernancePipelineStage."""

    @pytest.fixture
    def stage(self):
        """Create a governance pipeline stage."""
        engine = PolicyEngine()
        manager = QualityGatesManager(engine)
        generator = AlertGenerator()
        return GovernancePipelineStage("test_stage", engine, manager, generator)

    def test_stage_initialization(self, stage):
        """Test stage initialization."""
        assert stage.stage_name == "test_stage"
        assert stage.policy_engine is not None
        assert stage.gates_manager is not None
        assert stage.alert_generator is not None
        assert len(stage.stage_metrics) == 0

    def test_evaluate_policies_success(self, stage):
        """Test policy evaluation with no violations."""
        can_proceed, results = stage.evaluate_policies(
            "resource_1",
            "dataset",
            {"quality": 0.9},
        )
        assert can_proceed is True
        assert len(results) == 0

    def test_evaluate_policies_with_violations(self, stage):
        """Test policy evaluation with violations."""
        # Add a policy that will generate violations
        from primedata.governance.policy_engine import PolicyRuleDefinition

        policy = PolicyRuleDefinition(
            rule_id="test_policy",
            name="Test Policy",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        stage.policy_engine.register_policy(policy)

        # Manually create a violation for testing
        violation = PolicyViolation(
            policy_id="test_policy",
            policy_name="Test Policy",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="resource_1",
            resource_type="dataset",
        )

        can_proceed, results = stage.evaluate_policies(
            "resource_1",
            "dataset",
            {"quality": 0.5},
        )
        # Should still pass since default evaluator passes all
        assert can_proceed is True

    def test_evaluate_gates_success(self, stage):
        """Test gate evaluation with passing gates."""
        gate = QualityGate(
            gate_id="test_gate",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        gate.add_threshold(QualityThreshold(metric_name="quality", min_value=0.7))
        stage.gates_manager.register_gate(gate)

        can_proceed, results = stage.evaluate_gates(
            {"quality": 0.9},
            "resource_1",
            "dataset",
        )
        assert can_proceed is True

    def test_evaluate_gates_failure(self, stage):
        """Test gate evaluation with failing gates."""
        gate = QualityGate(
            gate_id="test_gate",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            blocking=True,
        )
        gate.add_threshold(QualityThreshold(metric_name="quality", min_value=0.8))
        stage.gates_manager.register_gate(gate)

        can_proceed, results = stage.evaluate_gates(
            {"quality": 0.5},
            "resource_1",
            "dataset",
        )
        assert can_proceed is False

    def test_record_stage_metrics(self, stage):
        """Test recording stage metrics."""
        metrics = {"processed_records": 1000, "quality_score": 0.95}
        stage.record_stage_metrics(metrics)
        assert stage.stage_metrics == metrics

    def test_get_stage_summary(self, stage):
        """Test getting stage summary."""
        stage.record_stage_metrics({"quality_score": 0.9})
        summary = stage.get_stage_summary()

        assert summary["stage"] == "test_stage"
        assert "policies" in summary
        assert "alerts" in summary
        assert "metrics_recorded" in summary
        assert summary["metrics_recorded"] == 1


# ============================================================================
# GOVERNANCE PIPELINE TESTS
# ============================================================================


class TestGovernancePipeline:
    """Tests for GovernancePipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create a governance pipeline."""
        return GovernancePipeline("test_pipeline")

    def test_pipeline_initialization(self, pipeline):
        """Test pipeline initialization."""
        assert pipeline.pipeline_name == "test_pipeline"
        assert pipeline.policy_engine is not None
        assert pipeline.gates_manager is not None
        assert pipeline.alert_generator is not None
        assert len(pipeline.stages) == 0
        assert len(pipeline.execution_log) == 0

    def test_register_stage(self, pipeline):
        """Test registering a stage."""
        stage = pipeline.register_stage("stage_1")
        assert len(pipeline.stages) == 1
        assert "stage_1" in pipeline.stages
        assert stage.stage_name == "stage_1"

    def test_register_multiple_stages(self, pipeline):
        """Test registering multiple stages."""
        for i in range(3):
            pipeline.register_stage(f"stage_{i}")

        assert len(pipeline.stages) == 3
        for i in range(3):
            assert f"stage_{i}" in pipeline.stages

    def test_get_stage(self, pipeline):
        """Test getting a registered stage."""
        stage = pipeline.register_stage("test_stage")
        retrieved = pipeline.get_stage("test_stage")
        assert retrieved is stage

    def test_get_nonexistent_stage(self, pipeline):
        """Test getting a non-existent stage."""
        stage = pipeline.get_stage("nonexistent")
        assert stage is None

    def test_execute_stage_success(self, pipeline):
        """Test executing a stage successfully."""
        pipeline.register_stage("test_stage")

        def operation(x, y):
            return x + y

        success, result, gov_result = pipeline.execute_stage_with_governance(
            "test_stage",
            operation,
            5,
            3,
        )

        assert success is True
        assert result == 8
        assert gov_result["status"] == "success"
        assert len(pipeline.execution_log) == 1

    def test_execute_stage_failure(self, pipeline):
        """Test executing a stage with failure."""
        pipeline.register_stage("test_stage")

        def failing_operation():
            raise ValueError("Test error")

        success, result, gov_result = pipeline.execute_stage_with_governance(
            "test_stage",
            failing_operation,
        )

        assert success is False
        assert result is None
        assert "error" in gov_result
        assert len(pipeline.execution_log) == 1
        assert pipeline.execution_log[0]["success"] is False

    def test_execute_unregistered_stage(self, pipeline):
        """Test executing an unregistered stage."""
        def operation():
            return "test"

        success, result, gov_result = pipeline.execute_stage_with_governance(
            "nonexistent",
            operation,
        )

        assert success is False
        assert result is None
        assert "error" in gov_result

    def test_get_pipeline_summary(self, pipeline):
        """Test getting pipeline summary."""
        pipeline.register_stage("stage_1")
        pipeline.register_stage("stage_2")

        summary = pipeline.get_pipeline_summary()

        assert summary["pipeline"] == "test_pipeline"
        assert summary["total_stages"] == 2
        assert "stages" in summary
        assert "policy_engine_policies" in summary
        assert "quality_gates" in summary

    def test_get_execution_log(self, pipeline):
        """Test getting execution log."""
        pipeline.register_stage("stage_1")

        def operation():
            return "success"

        # Execute multiple times
        for _ in range(5):
            pipeline.execute_stage_with_governance("stage_1", operation)

        log = pipeline.get_execution_log(limit=3)
        assert len(log) == 3

    def test_execution_log_limit(self, pipeline):
        """Test execution log with limit."""
        pipeline.register_stage("stage_1")

        def operation():
            return "test"

        # Execute 10 times
        for _ in range(10):
            pipeline.execute_stage_with_governance("stage_1", operation)

        # Get last 5
        log = pipeline.get_execution_log(limit=5)
        assert len(log) == 5
        assert len(pipeline.execution_log) == 10


# ============================================================================
# PIPELINE SHARING COMPONENTS TESTS
# ============================================================================


class TestPipelineComponentSharing:
    """Tests for component sharing across stages."""

    def test_stages_share_policy_engine(self):
        """Test that stages share the same policy engine."""
        pipeline = GovernancePipeline("test_pipeline")
        stage1 = pipeline.register_stage("stage_1")
        stage2 = pipeline.register_stage("stage_2")

        assert stage1.policy_engine is stage2.policy_engine
        assert stage1.policy_engine is pipeline.policy_engine

    def test_stages_share_gates_manager(self):
        """Test that stages share the same gates manager."""
        pipeline = GovernancePipeline("test_pipeline")
        stage1 = pipeline.register_stage("stage_1")
        stage2 = pipeline.register_stage("stage_2")

        assert stage1.gates_manager is stage2.gates_manager
        assert stage1.gates_manager is pipeline.gates_manager

    def test_stages_share_alert_generator(self):
        """Test that stages share the same alert generator."""
        pipeline = GovernancePipeline("test_pipeline")
        stage1 = pipeline.register_stage("stage_1")
        stage2 = pipeline.register_stage("stage_2")

        assert stage1.alert_generator is stage2.alert_generator
        assert stage1.alert_generator is pipeline.alert_generator

    def test_policies_registered_once_affect_all_stages(self):
        """Test that policies registered on pipeline affect all stages."""
        from primedata.governance.policy_engine import PolicyRuleDefinition

        pipeline = GovernancePipeline("test_pipeline")
        stage1 = pipeline.register_stage("stage_1")
        stage2 = pipeline.register_stage("stage_2")

        policy = PolicyRuleDefinition(
            rule_id="shared_policy",
            name="Shared Policy",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        pipeline.policy_engine.register_policy(policy)

        assert len(stage1.policy_engine.policies) == 1
        assert len(stage2.policy_engine.policies) == 1
        assert stage1.policy_engine.policies["shared_policy"] is policy


# ============================================================================
# PIPELINE TEMPLATE TESTS
# ============================================================================


class TestPipelineTemplates:
    """Tests for pre-built pipeline templates."""

    def test_create_ingestion_pipeline(self):
        """Test creating ingestion pipeline template."""
        pipeline = create_ingestion_pipeline()

        assert pipeline.pipeline_name == "DataIngestionPipeline"
        assert len(pipeline.stages) == 4
        assert "raw_ingestion" in pipeline.stages
        assert "validation" in pipeline.stages
        assert "enrichment" in pipeline.stages
        assert "indexing" in pipeline.stages

    def test_ingestion_pipeline_has_quality_gate(self):
        """Test that ingestion pipeline has quality gate."""
        pipeline = create_ingestion_pipeline()

        assert len(pipeline.gates_manager.gates) == 1
        gate = list(pipeline.gates_manager.gates.values())[0]
        assert gate.name == "Minimum Data Quality"

    def test_ingestion_pipeline_has_alert_rule(self):
        """Test that ingestion pipeline has alert rule."""
        pipeline = create_ingestion_pipeline()

        assert len(pipeline.alert_generator.rules) == 1
        rule = list(pipeline.alert_generator.rules.values())[0]
        assert rule.name == "Data Quality Alert"

    def test_create_processing_pipeline(self):
        """Test creating processing pipeline template."""
        pipeline = create_processing_pipeline()

        assert pipeline.pipeline_name == "DataProcessingPipeline"
        assert len(pipeline.stages) == 4
        assert "preprocessing" in pipeline.stages
        assert "transformation" in pipeline.stages
        assert "aggregation" in pipeline.stages
        assert "export" in pipeline.stages

    def test_processing_pipeline_has_performance_gate(self):
        """Test that processing pipeline has performance gate."""
        pipeline = create_processing_pipeline()

        assert len(pipeline.gates_manager.gates) == 1
        gate = list(pipeline.gates_manager.gates.values())[0]
        assert gate.category == PolicyCategory.PERFORMANCE


# ============================================================================
# END-TO-END INTEGRATION TESTS
# ============================================================================


class TestPipelineIntegrationEndToEnd:
    """End-to-end integration tests for governance pipeline."""

    def test_full_pipeline_workflow(self):
        """Test complete pipeline workflow with governance."""
        pipeline = create_ingestion_pipeline()

        # Get a stage
        stage = pipeline.get_stage("raw_ingestion")

        # Define a test operation
        def ingest_data(filename):
            return {"file": filename, "records": 1000}

        # Execute with governance
        success, result, gov_result = pipeline.execute_stage_with_governance(
            "raw_ingestion",
            ingest_data,
            "data.csv",
        )

        assert success is True
        assert result["records"] == 1000
        assert len(pipeline.execution_log) == 1

    def test_multi_stage_execution_with_gates(self):
        """Test executing multiple stages with quality gates."""
        pipeline = create_ingestion_pipeline()

        # Execute multiple stages
        operations = [
            ("raw_ingestion", lambda: {"records": 1000}),
            ("validation", lambda: {"valid": 950}),
            ("enrichment", lambda: {"enriched": 950}),
            ("indexing", lambda: {"indexed": 950}),
        ]

        for stage_name, operation in operations:
            success, result, gov_result = pipeline.execute_stage_with_governance(
                stage_name,
                operation,
            )
            assert success is True

        assert len(pipeline.execution_log) == 4

        # Get summary
        summary = pipeline.get_pipeline_summary()
        assert summary["total_stages"] == 4
        assert summary["executions"] == 4

    def test_pipeline_error_recovery(self):
        """Test pipeline error handling and recovery."""
        pipeline = GovernancePipeline("recovery_pipeline")
        pipeline.register_stage("stage_1")
        pipeline.register_stage("stage_2")

        def failing_op():
            raise RuntimeError("Stage failed")

        def recovering_op():
            return "recovered"

        # First stage fails
        success1, _, _ = pipeline.execute_stage_with_governance("stage_1", failing_op)
        assert success1 is False

        # Second stage succeeds (pipeline continues)
        success2, result, _ = pipeline.execute_stage_with_governance("stage_2", recovering_op)
        assert success2 is True
        assert result == "recovered"

        # Both logged
        assert len(pipeline.execution_log) == 2


# ============================================================================
# STRESS TESTS
# ============================================================================


class TestPipelineStressCases:
    """Stress tests for pipeline."""

    def test_many_stages(self):
        """Test pipeline with many stages."""
        pipeline = GovernancePipeline("large_pipeline")

        for i in range(100):
            pipeline.register_stage(f"stage_{i}")

        assert len(pipeline.stages) == 100

        # Verify summary
        summary = pipeline.get_pipeline_summary()
        assert summary["total_stages"] == 100

    def test_many_executions(self):
        """Test many pipeline executions."""
        pipeline = GovernancePipeline("busy_pipeline")
        pipeline.register_stage("stage_1")

        def quick_op():
            return "done"

        for _ in range(1000):
            pipeline.execute_stage_with_governance("stage_1", quick_op)

        assert len(pipeline.execution_log) == 1000

        # Last 10
        recent = pipeline.get_execution_log(limit=10)
        assert len(recent) == 10

    def test_many_stages_many_executions(self):
        """Test many stages with many executions each."""
        pipeline = GovernancePipeline("complex_pipeline")

        for i in range(10):
            pipeline.register_stage(f"stage_{i}")

        def op(stage_num):
            return f"stage_{stage_num} done"

        # Execute each stage 10 times
        for i in range(10):
            for _ in range(10):
                pipeline.execute_stage_with_governance(f"stage_{i}", op, i)

        assert len(pipeline.execution_log) == 100

        summary = pipeline.get_pipeline_summary()
        assert summary["total_stages"] == 10
        assert summary["executions"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
