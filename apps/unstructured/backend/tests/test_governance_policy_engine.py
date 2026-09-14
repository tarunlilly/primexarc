"""
Unit Tests for Governance Policy Engine

Tests cover:
- Policy registration and management
- Policy evaluation logic
- Violation detection and severity
- Results aggregation
- Edge cases and error handling
"""

import pytest
from datetime import datetime
from uuid import uuid4

from primedata.governance.policy_engine import (
    PolicyEngine,
    PolicySeverity,
    PolicyCategory,
    PolicyStatus,
    PolicyViolation,
    PolicyEvaluationResult,
    PolicyRuleDefinition,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def policy_engine():
    """Create policy engine instance."""
    return PolicyEngine()


@pytest.fixture
def test_resource_id():
    """Test resource ID."""
    return str(uuid4())


@pytest.fixture
def test_policy_rule():
    """Create test policy rule."""
    return PolicyRuleDefinition(
        rule_id="policy-1",
        name="Test Policy",
        description="Test policy rule",
        category=PolicyCategory.QUALITY,
        severity=PolicySeverity.ERROR,
        enabled=True,
    )


@pytest.fixture
def test_quality_policy():
    """Create quality policy."""
    return PolicyRuleDefinition(
        rule_id="quality-completeness",
        name="Completeness Check",
        description="Verify data completeness",
        category=PolicyCategory.QUALITY,
        severity=PolicySeverity.ERROR,
        enabled=True,
        parameters={"min_completeness": 0.95},
    )


@pytest.fixture
def test_compliance_policy():
    """Create compliance policy."""
    return PolicyRuleDefinition(
        rule_id="compliance-gdpr",
        name="GDPR Compliance",
        description="GDPR compliance check",
        category=PolicyCategory.COMPLIANCE,
        severity=PolicySeverity.CRITICAL,
        enabled=True,
    )


@pytest.fixture
def test_resource_data():
    """Create test resource data."""
    return {
        "name": "Test Data",
        "size": 1024,
        "quality": 0.95,
        "completeness": 0.98,
    }


# ============================================================================
# ENUM TESTS
# ============================================================================


class TestPolicySeverity:
    """Test PolicySeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert PolicySeverity.INFO.value == "info"
        assert PolicySeverity.WARNING.value == "warning"
        assert PolicySeverity.ERROR.value == "error"
        assert PolicySeverity.CRITICAL.value == "critical"

    def test_severity_comparison(self):
        """Test severity comparison."""
        assert PolicySeverity.CRITICAL != PolicySeverity.INFO
        assert PolicySeverity.ERROR != PolicySeverity.WARNING


class TestPolicyCategory:
    """Test PolicyCategory enum."""

    def test_category_values(self):
        """Test category enum values."""
        assert PolicyCategory.QUALITY.value == "quality"
        assert PolicyCategory.COMPLIANCE.value == "compliance"
        assert PolicyCategory.SECURITY.value == "security"
        assert PolicyCategory.PERFORMANCE.value == "performance"
        assert PolicyCategory.LINEAGE.value == "lineage"


class TestPolicyStatus:
    """Test PolicyStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert PolicyStatus.PASSED.value == "passed"
        assert PolicyStatus.FAILED.value == "failed"
        assert PolicyStatus.WARNINGS.value == "warnings"
        assert PolicyStatus.UNKNOWN.value == "unknown"


# ============================================================================
# VIOLATION TESTS
# ============================================================================


class TestPolicyViolation:
    """Test PolicyViolation data class."""

    def test_violation_creation(self):
        """Test creating a violation."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test Policy",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test violation",
            resource_id="r1",
            resource_type="DOCUMENT",
        )

        assert violation.policy_id == "p1"
        assert violation.policy_name == "Test Policy"
        assert violation.severity == PolicySeverity.ERROR
        assert violation.is_blocking() is True

    def test_violation_is_blocking_error(self):
        """Test violation blocking for ERROR severity."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Error",
            resource_id="r1",
            resource_type="DOC",
        )

        assert violation.is_blocking() is True

    def test_violation_is_blocking_critical(self):
        """Test violation blocking for CRITICAL severity."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.COMPLIANCE,
            message="Critical",
            resource_id="r1",
            resource_type="DOC",
        )

        assert violation.is_blocking() is True

    def test_violation_not_blocking_warning(self):
        """Test violation not blocking for WARNING severity."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.QUALITY,
            message="Warning",
            resource_id="r1",
            resource_type="DOC",
        )

        assert violation.is_blocking() is False

    def test_violation_not_blocking_info(self):
        """Test violation not blocking for INFO severity."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.QUALITY,
            message="Info",
            resource_id="r1",
            resource_type="DOC",
        )

        assert violation.is_blocking() is False

    def test_violation_with_details(self):
        """Test violation with additional details."""
        details = {"expected": 100, "actual": 95}
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test",
            resource_id="r1",
            resource_type="DOC",
            details=details,
        )

        assert violation.details == details


# ============================================================================
# EVALUATION RESULT TESTS
# ============================================================================


class TestPolicyEvaluationResult:
    """Test PolicyEvaluationResult data class."""

    def test_result_creation(self):
        """Test creating evaluation result."""
        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test Policy",
            resource_id="r1",
            status=PolicyStatus.PASSED,
        )

        assert result.policy_id == "p1"
        assert result.status == PolicyStatus.PASSED
        assert result.is_blocking is False
        assert result.violation_count == 0

    def test_result_with_violations(self):
        """Test result with violations."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Violation",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation],
        )

        assert result.violation_count == 1
        assert result.is_blocking is True

    def test_result_with_warnings(self):
        """Test result with warnings."""
        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.WARNINGS,
            warnings=["Warning 1", "Warning 2"],
        )

        assert result.warning_count == 2
        assert result.is_blocking is False

    def test_result_blocking_mixed_violations(self):
        """Test blocking with mixed violation severities."""
        blocking_violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Error",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[blocking_violation],
        )

        assert result.is_blocking is True


# ============================================================================
# POLICY RULE TESTS
# ============================================================================


class TestPolicyRuleDefinition:
    """Test PolicyRuleDefinition data class."""

    def test_rule_creation(self):
        """Test creating policy rule."""
        rule = PolicyRuleDefinition(
            rule_id="rule-1",
            name="Test Rule",
            description="Test rule description",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )

        assert rule.rule_id == "rule-1"
        assert rule.name == "Test Rule"
        assert rule.enabled is True

    def test_rule_with_parameters(self):
        """Test rule with parameters."""
        params = {"min_score": 0.8, "max_threshold": 100}
        rule = PolicyRuleDefinition(
            rule_id="rule-1",
            name="Test",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            parameters=params,
        )

        assert rule.parameters == params

    def test_rule_disabled(self):
        """Test disabled rule."""
        rule = PolicyRuleDefinition(
            rule_id="rule-1",
            name="Test",
            description="Test",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            enabled=False,
        )

        assert rule.enabled is False


# ============================================================================
# POLICY ENGINE TESTS
# ============================================================================


class TestPolicyEngineBasics:
    """Test PolicyEngine basic functionality."""

    def test_engine_initialization(self, policy_engine):
        """Test engine initialization."""
        assert policy_engine is not None
        assert len(policy_engine.policies) == 0

    def test_register_single_policy(self, policy_engine, test_policy_rule):
        """Test registering a single policy."""
        policy_engine.register_policy(test_policy_rule)

        assert len(policy_engine.policies) == 1
        assert test_policy_rule.rule_id in policy_engine.policies

    def test_register_multiple_policies(self, policy_engine, test_quality_policy, test_compliance_policy):
        """Test registering multiple policies."""
        policy_engine.register_policy(test_quality_policy)
        policy_engine.register_policy(test_compliance_policy)

        assert len(policy_engine.policies) == 2
        assert test_quality_policy.rule_id in policy_engine.policies
        assert test_compliance_policy.rule_id in policy_engine.policies

    def test_register_policy_overwrites(self, policy_engine):
        """Test that registering same policy ID overwrites."""
        rule1 = PolicyRuleDefinition(
            rule_id="p1",
            name="Rule 1",
            description="",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
        )
        rule2 = PolicyRuleDefinition(
            rule_id="p1",
            name="Rule 2",
            description="",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.WARNING,
        )

        policy_engine.register_policy(rule1)
        policy_engine.register_policy(rule2)

        assert len(policy_engine.policies) == 1
        assert policy_engine.policies["p1"].name == "Rule 2"


class TestPolicyEvaluation:
    """Test policy evaluation."""

    def test_evaluate_policies_empty(self, policy_engine, test_resource_id, test_resource_data):
        """Test evaluating with no registered policies."""
        results = policy_engine.evaluate_policies(
            test_resource_id, "DOCUMENT", test_resource_data
        )

        assert len(results) == 0

    def test_evaluate_single_policy(
        self, policy_engine, test_policy_rule, test_resource_id, test_resource_data
    ):
        """Test evaluating single policy."""
        policy_engine.register_policy(test_policy_rule)

        results = policy_engine.evaluate_policies(
            test_resource_id, "DOCUMENT", test_resource_data
        )

        assert len(results) == 1
        assert test_policy_rule.rule_id in results

    def test_evaluate_multiple_policies(
        self,
        policy_engine,
        test_quality_policy,
        test_compliance_policy,
        test_resource_id,
        test_resource_data,
    ):
        """Test evaluating multiple policies."""
        policy_engine.register_policy(test_quality_policy)
        policy_engine.register_policy(test_compliance_policy)

        results = policy_engine.evaluate_policies(
            test_resource_id, "DOCUMENT", test_resource_data
        )

        assert len(results) == 2

    def test_evaluate_skips_disabled_policies(
        self, policy_engine, test_resource_id, test_resource_data
    ):
        """Test that disabled policies are skipped."""
        disabled_policy = PolicyRuleDefinition(
            rule_id="disabled",
            name="Disabled",
            description="",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            enabled=False,
        )

        enabled_policy = PolicyRuleDefinition(
            rule_id="enabled",
            name="Enabled",
            description="",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            enabled=True,
        )

        policy_engine.register_policy(disabled_policy)
        policy_engine.register_policy(enabled_policy)

        results = policy_engine.evaluate_policies(
            test_resource_id, "DOCUMENT", test_resource_data
        )

        # Only enabled policy should be evaluated
        assert len(results) == 1
        assert "enabled" in results


class TestViolationAggregation:
    """Test violation aggregation."""

    def test_get_violations_empty(self, policy_engine):
        """Test getting violations from empty results."""
        violations = policy_engine.get_violations({})

        assert len(violations) == 0

    def test_get_violations_single(self):
        """Test getting single violation."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Violation",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation],
        )

        engine = PolicyEngine()
        violations = engine.get_violations({"p1": result})

        assert len(violations) == 1
        assert violations[0] == violation

    def test_get_violations_multiple_policies(self):
        """Test getting violations from multiple policies."""
        violation1 = PolicyViolation(
            policy_id="p1",
            policy_name="Test1",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="V1",
            resource_id="r1",
            resource_type="DOC",
        )

        violation2 = PolicyViolation(
            policy_id="p2",
            policy_name="Test2",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.COMPLIANCE,
            message="V2",
            resource_id="r1",
            resource_type="DOC",
        )

        result1 = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test1",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation1],
        )

        result2 = PolicyEvaluationResult(
            policy_id="p2",
            policy_name="Test2",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation2],
        )

        engine = PolicyEngine()
        violations = engine.get_violations({"p1": result1, "p2": result2})

        assert len(violations) == 2


class TestBlockingViolationDetection:
    """Test blocking violation detection."""

    def test_has_blocking_violations_false(self):
        """Test no blocking violations."""
        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.PASSED,
        )

        engine = PolicyEngine()
        has_blocking = engine.has_blocking_violations({"p1": result})

        assert has_blocking is False

    def test_has_blocking_violations_true(self):
        """Test with blocking violations."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Error",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation],
        )

        engine = PolicyEngine()
        has_blocking = engine.has_blocking_violations({"p1": result})

        assert has_blocking is True


class TestResultsSummary:
    """Test results summarization."""

    def test_summarize_empty_results(self, policy_engine):
        """Test summarizing empty results."""
        summary = policy_engine.summarize_results({})

        assert summary["total_policies"] == 0
        assert summary["blocking_detected"] is False

    def test_summarize_passed_policies(self):
        """Test summary with passed policies."""
        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.PASSED,
        )

        engine = PolicyEngine()
        summary = engine.summarize_results({"p1": result})

        assert summary["total_policies"] == 1
        assert summary["passed_policies"] == 1
        assert summary["failed_policies"] == 0
        assert summary["blocking_detected"] is False

    def test_summarize_failed_policies(self):
        """Test summary with failed policies."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Error",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[violation],
        )

        engine = PolicyEngine()
        summary = engine.summarize_results({"p1": result})

        assert summary["failed_policies"] == 1
        assert summary["total_violations"] == 1
        assert summary["blocking_violations"] == 1
        assert summary["blocking_detected"] is True


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestGovernanceEdgeCases:
    """Test edge cases."""

    def test_multiple_violations_per_policy(self):
        """Test policy with multiple violations."""
        v1 = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="V1",
            resource_id="r1",
            resource_type="DOC",
        )

        v2 = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.QUALITY,
            message="V2",
            resource_id="r1",
            resource_type="DOC",
        )

        result = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="Test",
            resource_id="r1",
            status=PolicyStatus.FAILED,
            violations=[v1, v2],
        )

        engine = PolicyEngine()
        summary = engine.summarize_results({"p1": result})

        assert summary["total_violations"] == 2
        assert summary["blocking_violations"] == 1

    def test_policy_with_complex_parameters(self):
        """Test policy with complex parameters."""
        params = {
            "thresholds": {"min": 0.7, "max": 0.95},
            "rules": ["rule1", "rule2"],
            "metadata": {"version": 1},
        }

        rule = PolicyRuleDefinition(
            rule_id="p1",
            name="Complex",
            description="",
            category=PolicyCategory.QUALITY,
            severity=PolicySeverity.ERROR,
            parameters=params,
        )

        assert rule.parameters == params

    def test_timestamp_generation(self):
        """Test that timestamps are generated."""
        violation = PolicyViolation(
            policy_id="p1",
            policy_name="Test",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.QUALITY,
            message="Test",
            resource_id="r1",
            resource_type="DOC",
        )

        assert isinstance(violation.timestamp, datetime)
        assert violation.timestamp <= datetime.utcnow()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
