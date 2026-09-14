"""
Comprehensive tests for governance quality gates and alerts.

Tests cover:
- Quality threshold checking
- Quality gate evaluation
- Quality gates manager
- Alert rule triggering
- Alert generation
- Alert sending and history
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from primedata.governance.quality_gates import (
    QualityThreshold,
    QualityGate,
    QualityGateResult,
    QualityGatesManager,
    GateStatus,
)
from primedata.governance.alerts import (
    AlertRule,
    Alert,
    AlertGenerator,
    AlertChannel,
    AlertPriority,
    default_log_handler,
)
from primedata.governance.policy_engine import (
    PolicyEngine,
    PolicySeverity,
    PolicyCategory,
    PolicyViolation,
    PolicyStatus,
)


# ============================================================================
# QUALITY THRESHOLD TESTS
# ============================================================================


class TestQualityThreshold:
    """Tests for QualityThreshold."""

    def test_threshold_creation(self):
        """Test creating a quality threshold."""
        threshold = QualityThreshold(
            metric_name="confidence",
            min_value=0.8,
            max_value=1.0,
            weight=1.5,
        )
        assert threshold.metric_name == "confidence"
        assert threshold.min_value == 0.8
        assert threshold.max_value == 1.0
        assert threshold.weight == 1.5
        assert threshold.enabled is True

    def test_threshold_check_within_range(self):
        """Test threshold check for value within range."""
        threshold = QualityThreshold(metric_name="confidence", min_value=0.8, max_value=1.0)
        assert threshold.check(0.9) is True
        assert threshold.check(0.8) is True
        assert threshold.check(1.0) is True

    def test_threshold_check_below_min(self):
        """Test threshold check for value below minimum."""
        threshold = QualityThreshold(metric_name="confidence", min_value=0.8)
        assert threshold.check(0.7) is False

    def test_threshold_check_above_max(self):
        """Test threshold check for value above maximum."""
        threshold = QualityThreshold(metric_name="confidence", max_value=1.0)
        assert threshold.check(1.1) is False

    def test_threshold_check_disabled(self):
        """Test threshold check when disabled."""
        threshold = QualityThreshold(
            metric_name="confidence",
            min_value=0.8,
            max_value=1.0,
            enabled=False,
        )
        # Should pass even if outside range
        assert threshold.check(0.5) is True

    def test_threshold_with_only_min(self):
        """Test threshold with only minimum value."""
        threshold = QualityThreshold(metric_name="confidence", min_value=0.7)
        assert threshold.check(0.7) is True
        assert threshold.check(0.8) is True
        assert threshold.check(0.6) is False

    def test_threshold_with_only_max(self):
        """Test threshold with only maximum value."""
        threshold = QualityThreshold(metric_name="noise", max_value=0.3)
        assert threshold.check(0.3) is True
        assert threshold.check(0.2) is True
        assert threshold.check(0.4) is False


# ============================================================================
# QUALITY GATE TESTS
# ============================================================================


class TestQualityGate:
    """Tests for QualityGate."""

    def test_gate_creation(self):
        """Test creating a quality gate."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Min Confidence Gate",
            description="Ensures minimum confidence",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        assert gate.gate_id == "gate_1"
        assert gate.name == "Min Confidence Gate"
        assert gate.blocking is True
        assert gate.enabled is True

    def test_gate_add_threshold(self):
        """Test adding thresholds to gate."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        threshold = QualityThreshold(metric_name="confidence", min_value=0.8)
        gate.add_threshold(threshold)
        assert len(gate.thresholds) == 1
        assert gate.thresholds[0].metric_name == "confidence"

    def test_gate_evaluate_all_pass(self):
        """Test evaluating gate when all thresholds pass."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))
        gate.add_threshold(QualityThreshold(metric_name="coherence", min_value=0.7))

        metrics = {"confidence": 0.9, "coherence": 0.85}
        passed, failures = gate.evaluate(metrics)
        assert passed is True
        assert len(failures) == 0

    def test_gate_evaluate_some_fail(self):
        """Test evaluating gate when some thresholds fail."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))
        gate.add_threshold(QualityThreshold(metric_name="coherence", min_value=0.7))

        metrics = {"confidence": 0.9, "coherence": 0.5}
        passed, failures = gate.evaluate(metrics)
        assert passed is False
        assert len(failures) == 1
        assert "coherence" in failures[0]

    def test_gate_evaluate_missing_metric(self):
        """Test evaluating gate with missing metric."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))

        metrics = {"coherence": 0.85}  # Missing confidence
        passed, failures = gate.evaluate(metrics)
        assert passed is False
        assert any("not found" in f for f in failures)

    def test_gate_evaluate_disabled(self):
        """Test evaluating disabled gate."""
        gate = QualityGate(
            gate_id="gate_1",
            name="Test Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
            enabled=False,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))

        metrics = {"confidence": 0.5}  # Below threshold
        passed, failures = gate.evaluate(metrics)
        assert passed is True  # Should pass when disabled
        assert len(failures) == 0


# ============================================================================
# QUALITY GATE RESULT TESTS
# ============================================================================


class TestQualityGateResult:
    """Tests for QualityGateResult."""

    def test_result_creation(self):
        """Test creating a gate result."""
        result = QualityGateResult(
            gate_id="gate_1",
            gate_name="Test Gate",
            status=GateStatus.OPEN,
            resource_id="resource_1",
            resource_type="dataset",
        )
        assert result.gate_id == "gate_1"
        assert result.status == GateStatus.OPEN
        assert result.is_blocking is False

    def test_result_is_blocking(self):
        """Test blocking property."""
        result_open = QualityGateResult(
            gate_id="gate_1",
            gate_name="Test Gate",
            status=GateStatus.OPEN,
        )
        assert result_open.is_blocking is False

        result_closed = QualityGateResult(
            gate_id="gate_1",
            gate_name="Test Gate",
            status=GateStatus.CLOSED,
        )
        assert result_closed.is_blocking is True

    def test_result_with_failures(self):
        """Test gate result with failures."""
        result = QualityGateResult(
            gate_id="gate_1",
            gate_name="Test Gate",
            status=GateStatus.CLOSED,
            failures=["confidence too low", "coherence too low"],
        )
        assert len(result.failures) == 2
        assert result.is_blocking is True


# ============================================================================
# QUALITY GATES MANAGER TESTS
# ============================================================================


class TestQualityGatesManager:
    """Tests for QualityGatesManager."""

    @pytest.fixture
    def manager(self):
        """Create a quality gates manager."""
        engine = PolicyEngine()
        return QualityGatesManager(engine)

    @pytest.fixture
    def confidence_gate(self):
        """Create a confidence gate."""
        gate = QualityGate(
            gate_id="confidence_gate",
            name="Minimum Confidence Gate",
            description="Ensures minimum confidence score",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))
        return gate

    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert len(manager.gates) == 0
        assert manager.policy_engine is not None

    def test_register_gate(self, manager, confidence_gate):
        """Test registering a gate."""
        manager.register_gate(confidence_gate)
        assert len(manager.gates) == 1
        assert "confidence_gate" in manager.gates

    def test_evaluate_single_gate(self, manager, confidence_gate):
        """Test evaluating a single gate."""
        manager.register_gate(confidence_gate)

        metrics = {"confidence": 0.9}
        result = manager.evaluate_gate("confidence_gate", metrics, "resource_1", "dataset")

        assert result.gate_id == "confidence_gate"
        assert result.status == GateStatus.OPEN
        assert result.is_blocking is False

    def test_evaluate_gate_failure(self, manager, confidence_gate):
        """Test evaluating a gate that fails."""
        manager.register_gate(confidence_gate)

        metrics = {"confidence": 0.7}
        result = manager.evaluate_gate("confidence_gate", metrics, "resource_1", "dataset")

        assert result.status == GateStatus.CLOSED
        assert result.is_blocking is True
        assert len(result.failures) > 0

    def test_evaluate_all_gates(self, manager):
        """Test evaluating all gates."""
        gate1 = QualityGate(
            gate_id="gate_1",
            name="Gate 1",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        gate1.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))

        gate2 = QualityGate(
            gate_id="gate_2",
            name="Gate 2",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        gate2.add_threshold(QualityThreshold(metric_name="coherence", min_value=0.7))

        manager.register_gate(gate1)
        manager.register_gate(gate2)

        metrics = {"confidence": 0.9, "coherence": 0.85}
        results = manager.evaluate_all_gates(metrics, "resource_1", "dataset")

        assert len(results) == 2
        assert all(r.status == GateStatus.OPEN for r in results.values())

    def test_get_blocking_gates(self, manager):
        """Test getting blocking gates."""
        gate1 = QualityGate(
            gate_id="gate_1",
            name="Gate 1",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            blocking=True,
        )
        gate1.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))

        manager.register_gate(gate1)

        metrics = {"confidence": 0.7}  # Will fail
        results = manager.evaluate_all_gates(metrics)
        blocking = manager.get_blocking_gates(results)

        assert len(blocking) == 1
        assert blocking[0].gate_id == "gate_1"

    def test_can_proceed_with_no_blocking(self, manager, confidence_gate):
        """Test can_proceed when no gates are blocking."""
        manager.register_gate(confidence_gate)

        metrics = {"confidence": 0.9}
        results = manager.evaluate_all_gates(metrics)
        assert manager.can_proceed(results) is True

    def test_can_proceed_with_blocking(self, manager, confidence_gate):
        """Test can_proceed when gates are blocking."""
        manager.register_gate(confidence_gate)

        metrics = {"confidence": 0.7}
        results = manager.evaluate_all_gates(metrics)
        assert manager.can_proceed(results) is False

    def test_summarize_gates(self, manager):
        """Test summarizing gate results."""
        gate1 = QualityGate(
            gate_id="gate_1",
            name="Gate 1",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )
        gate1.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))

        gate2 = QualityGate(
            gate_id="gate_2",
            name="Gate 2",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        gate2.add_threshold(QualityThreshold(metric_name="coherence", min_value=0.7))

        manager.register_gate(gate1)
        manager.register_gate(gate2)

        metrics = {"confidence": 0.9, "coherence": 0.5}
        results = manager.evaluate_all_gates(metrics)
        summary = manager.summarize_gates(results)

        assert summary["total_gates"] == 2
        assert summary["open_gates"] == 1
        assert summary["closed_gates"] == 1
        assert summary["can_proceed"] is False


# ============================================================================
# ALERT RULE TESTS
# ============================================================================


class TestAlertRule:
    """Tests for AlertRule."""

    def test_rule_creation(self):
        """Test creating an alert rule."""
        rule = AlertRule(
            rule_id="rule_1",
            name="High Severity Alerts",
            description="Alert on high severity violations",
            min_severity=PolicySeverity.ERROR,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL],
        )
        assert rule.rule_id == "rule_1"
        assert rule.min_severity == PolicySeverity.ERROR
        assert len(rule.channels) == 2

    def test_rule_should_alert_matching_policy(self):
        """Test rule should_alert with matching policy."""
        rule = AlertRule(
            rule_id="rule_1",
            name="Test Rule",
            description="Test",
            policy_id="policy_1",
            min_severity=PolicySeverity.WARNING,
        )
        violation = PolicyViolation(
            policy_id="policy_1",
            policy_name="Test Policy",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="res_1",
            resource_type="dataset",
        )
        assert rule.should_alert(violation) is True

    def test_rule_should_alert_non_matching_policy(self):
        """Test rule should_alert with non-matching policy."""
        rule = AlertRule(
            rule_id="rule_1",
            name="Test Rule",
            description="Test",
            policy_id="policy_1",
            min_severity=PolicySeverity.WARNING,
        )
        violation = PolicyViolation(
            policy_id="policy_2",
            policy_name="Other Policy",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="res_1",
            resource_type="dataset",
        )
        assert rule.should_alert(violation) is False

    def test_rule_should_alert_severity_too_low(self):
        """Test rule should_alert with severity too low."""
        rule = AlertRule(
            rule_id="rule_1",
            name="Test Rule",
            description="Test",
            min_severity=PolicySeverity.ERROR,
        )
        violation = PolicyViolation(
            policy_id="policy_1",
            policy_name="Test Policy",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="res_1",
            resource_type="dataset",
        )
        assert rule.should_alert(violation) is False

    def test_rule_should_alert_disabled(self):
        """Test rule should_alert when disabled."""
        rule = AlertRule(
            rule_id="rule_1",
            name="Test Rule",
            description="Test",
            min_severity=PolicySeverity.WARNING,
            enabled=False,
        )
        violation = PolicyViolation(
            policy_id="policy_1",
            policy_name="Test Policy",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="res_1",
            resource_type="dataset",
        )
        assert rule.should_alert(violation) is False


# ============================================================================
# ALERT GENERATOR TESTS
# ============================================================================


class TestAlertGenerator:
    """Tests for AlertGenerator."""

    @pytest.fixture
    def generator(self):
        """Create an alert generator."""
        return AlertGenerator()

    @pytest.fixture
    def test_rule(self):
        """Create a test alert rule."""
        return AlertRule(
            rule_id="rule_1",
            name="Test Rule",
            description="Test alert rule",
            min_severity=PolicySeverity.WARNING,
            channels=[AlertChannel.LOG],
        )

    @pytest.fixture
    def test_violation(self):
        """Create a test violation."""
        return PolicyViolation(
            policy_id="policy_1",
            policy_name="Test Policy",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test message",
            resource_id="resource_1",
            resource_type="dataset",
        )

    def test_generator_initialization(self, generator):
        """Test generator initialization."""
        assert len(generator.rules) == 0
        assert len(generator.alert_handlers) == 0
        assert len(generator.alert_history) == 0

    def test_register_rule(self, generator, test_rule):
        """Test registering a rule."""
        generator.register_rule(test_rule)
        assert len(generator.rules) == 1
        assert "rule_1" in generator.rules

    def test_register_handler(self, generator):
        """Test registering a handler."""
        handler = Mock(return_value=True)
        generator.register_handler(AlertChannel.LOG, handler)
        assert AlertChannel.LOG in generator.alert_handlers

    def test_generate_alert(self, generator, test_rule, test_violation):
        """Test generating an alert."""
        alert = generator.generate_alert(test_rule, test_violation)

        assert alert is not None
        assert alert.rule_id == "rule_1"
        assert alert.severity == PolicySeverity.ERROR
        assert "Test Policy" in alert.message

    def test_generate_alert_cooldown(self, generator, test_rule, test_violation):
        """Test alert generation with cooldown."""
        test_rule.cooldown_minutes = 60

        # First alert should be generated
        alert1 = generator.generate_alert(test_rule, test_violation)
        assert alert1 is not None

        # Second alert should be suppressed (within cooldown)
        alert2 = generator.generate_alert(test_rule, test_violation)
        assert alert2 is None

    def test_process_violations(self, generator, test_rule, test_violation):
        """Test processing violations."""
        generator.register_rule(test_rule)

        alerts = generator.process_violations([test_violation])
        assert len(alerts) == 1
        assert alerts[0].severity == PolicySeverity.ERROR

    def test_send_alert(self, generator, test_rule, test_violation):
        """Test sending an alert."""
        handler = Mock(return_value=True)
        generator.register_handler(AlertChannel.LOG, handler)

        alert = Alert(
            alert_id="alert_1",
            rule_id="rule_1",
            title="Test Alert",
            message="Test message",
            severity=PolicySeverity.ERROR,
            priority=AlertPriority.HIGH,
            violation=test_violation,
            channels=[AlertChannel.LOG],
        )

        results = generator.send_alert(alert)
        assert AlertChannel.LOG in results
        assert results[AlertChannel.LOG] is True
        handler.assert_called_once()

    def test_send_alerts(self, generator, test_violation):
        """Test sending multiple alerts."""
        handler = Mock(return_value=True)
        generator.register_handler(AlertChannel.LOG, handler)

        alerts = [
            Alert(
                alert_id=f"alert_{i}",
                rule_id="rule_1",
                title=f"Alert {i}",
                message="Test message",
                severity=PolicySeverity.ERROR,
                priority=AlertPriority.HIGH,
                violation=test_violation,
                channels=[AlertChannel.LOG],
            )
            for i in range(3)
        ]

        results = generator.send_alerts(alerts)
        assert len(results) == 3

    def test_get_recent_alerts(self, generator, test_violation):
        """Test getting recent alerts."""
        alert1 = Alert(
            alert_id="alert_1",
            rule_id="rule_1",
            title="Alert 1",
            message="Test",
            severity=PolicySeverity.ERROR,
            priority=AlertPriority.HIGH,
            violation=test_violation,
            created_at=datetime.utcnow(),
        )

        alert2 = Alert(
            alert_id="alert_2",
            rule_id="rule_2",
            title="Alert 2",
            message="Test",
            severity=PolicySeverity.WARNING,
            priority=AlertPriority.MEDIUM,
            violation=test_violation,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )

        generator.alert_history = [alert1, alert2]

        # Get alerts from last hour (should get only alert1)
        recent = generator.get_recent_alerts(minutes=60)
        assert len(recent) == 1
        assert recent[0].alert_id == "alert_1"

    def test_get_recent_alerts_by_severity(self, generator, test_violation):
        """Test getting recent alerts filtered by severity."""
        alert1 = Alert(
            alert_id="alert_1",
            rule_id="rule_1",
            title="Alert 1",
            message="Test",
            severity=PolicySeverity.ERROR,
            priority=AlertPriority.HIGH,
            violation=test_violation,
        )

        alert2 = Alert(
            alert_id="alert_2",
            rule_id="rule_2",
            title="Alert 2",
            message="Test",
            severity=PolicySeverity.WARNING,
            priority=AlertPriority.MEDIUM,
            violation=test_violation,
        )

        generator.alert_history = [alert1, alert2]

        critical = generator.get_recent_alerts(severity=PolicySeverity.ERROR)
        assert len(critical) == 1
        assert critical[0].severity == PolicySeverity.ERROR

    def test_get_alert_summary(self, generator, test_violation):
        """Test getting alert summary."""
        alerts = [
            Alert(
                alert_id=f"alert_{i}",
                rule_id="rule_1",
                title=f"Alert {i}",
                message="Test",
                severity=PolicySeverity.ERROR if i % 2 == 0 else PolicySeverity.WARNING,
                priority=AlertPriority.HIGH,
                violation=test_violation,
                channels=[AlertChannel.LOG],
            )
            for i in range(5)
        ]

        generator.alert_history = alerts
        generator.register_rule(
            AlertRule(
                rule_id="rule_1",
                name="Test Rule",
                description="Test",
                enabled=True,
            )
        )

        summary = generator.get_alert_summary()
        assert summary["total_alerts"] == 5
        assert summary["by_severity"]["error"] == 3  # alerts 0, 2, 4
        assert summary["by_severity"]["warning"] == 2  # alerts 1, 3
        assert summary["active_rules"] == 1


# ============================================================================
# EDGE CASES AND INTEGRATION TESTS
# ============================================================================


class TestGovernanceIntegration:
    """Integration tests for governance module."""

    def test_quality_gate_and_alerts_workflow(self):
        """Test complete workflow with gates and alerts."""
        # Setup
        engine = PolicyEngine()
        manager = QualityGatesManager(engine)
        generator = AlertGenerator()

        # Create gate
        gate = QualityGate(
            gate_id="confidence_gate",
            name="Confidence Gate",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            blocking=True,
        )
        gate.add_threshold(QualityThreshold(metric_name="confidence", min_value=0.8))
        manager.register_gate(gate)

        # Create alert rule
        rule = AlertRule(
            rule_id="rule_1",
            name="Gate Failure Alert",
            description="Alert on gate failure",
            min_severity=PolicySeverity.ERROR,
            channels=[AlertChannel.LOG],
        )
        generator.register_rule(rule)

        # Register handler
        handler = Mock(return_value=True)
        generator.register_handler(AlertChannel.LOG, handler)

        # Evaluate with failing metrics
        metrics = {"confidence": 0.7}
        results = manager.evaluate_all_gates(metrics, "resource_1", "dataset")

        # Check gate result
        assert not manager.can_proceed(results)
        blocking_gates = manager.get_blocking_gates(results)
        assert len(blocking_gates) == 1

        # Generate alert from violation
        violation = PolicyViolation(
            policy_id="gate_confidence_gate",
            policy_name="Confidence Gate",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Confidence too low",
            resource_id="resource_1",
            resource_type="dataset",
        )

        alerts = generator.process_violations([violation])
        assert len(alerts) == 1

        # Send alert
        results_sent = generator.send_alerts(alerts)
        assert len(results_sent) == 1

    def test_multiple_gates_and_rules(self):
        """Test with multiple gates and rules."""
        engine = PolicyEngine()
        manager = QualityGatesManager(engine)
        generator = AlertGenerator()

        # Create multiple gates
        for i in range(3):
            gate = QualityGate(
                gate_id=f"gate_{i}",
                name=f"Gate {i}",
                description="Test",
                category=PolicyCategory.QUALITY,
                severity=PolicySeverity.WARNING,
            )
            gate.add_threshold(
                QualityThreshold(metric_name=f"metric_{i}", min_value=0.5)
            )
            manager.register_gate(gate)

        # Create multiple rules
        for i in range(3):
            rule = AlertRule(
                rule_id=f"rule_{i}",
                name=f"Rule {i}",
                description="Test",
                min_severity=PolicySeverity.WARNING,
                channels=[AlertChannel.LOG],
            )
            generator.register_rule(rule)

        # Evaluate all gates
        metrics = {f"metric_{i}": 0.6 + i * 0.1 for i in range(3)}
        results = manager.evaluate_all_gates(metrics)

        assert len(results) == 3
        assert all(r.status == GateStatus.OPEN for r in results.values())
        assert manager.can_proceed(results)

        # Summary
        summary = manager.summarize_gates(results)
        assert summary["total_gates"] == 3
        assert summary["open_gates"] == 3
        assert summary["can_proceed"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
