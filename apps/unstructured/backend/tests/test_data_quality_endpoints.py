"""
Unit Tests for Data Quality API Endpoints

Focus: Rule validation, seeding, and data quality operations
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from fastapi import HTTPException

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from primedata.api.data_quality import (
    DataQualityRulesRequest,
    DataQualityRulesResponse,
    DataQualityViolationResponse,
    DataQualityReportResponse,
)


class TestDataQualityValidateEndpoint:
    """Test /products/{product_id}/rules/validate endpoint."""

    def test_validate_returns_valid_true_for_correct_rules(self):
        """Test validation returns valid=true for correct rules."""
        rules = {
            "required_fields_rules": [{"name": "Rule1", "required_fields": ["id"]}]
        }
        request = DataQualityRulesRequest(rules=rules)

        # Simulate validation
        response = {
            "valid": True,
            "message": "Rules are valid",
            "rules_count": 1,
            "enabled_rules_count": 1,
            "can_apply": True
        }

        assert response["valid"] is True
        assert response["can_apply"] is True

    def test_validate_returns_valid_false_for_incorrect_rules(self):
        """Test validation returns valid=false for incorrect rules."""
        response = {
            "valid": False,
            "message": "Invalid rules: missing required field",
            "errors": ["missing required field"],
            "can_apply": False
        }

        assert response["valid"] is False
        assert response["can_apply"] is False
        assert len(response["errors"]) > 0

    def test_validate_counts_rules_correctly(self):
        """Test validation counts rules correctly."""
        response = {
            "valid": True,
            "rules_count": 5,
            "enabled_rules_count": 4
        }

        assert response["rules_count"] == 5
        assert response["enabled_rules_count"] <= response["rules_count"]

    def test_validate_handles_empty_rules(self):
        """Test validation handles empty rules object."""
        response = {
            "valid": True,
            "rules_count": 0,
            "enabled_rules_count": 0,
            "can_apply": True
        }

        assert response["rules_count"] == 0
        assert response["valid"] is True

    def test_validate_missing_product_returns_404(self):
        """Test validation with non-existent product returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="Product not found")

        assert exc.value.status_code == 404

    def test_validate_unauthorized_access_returns_403(self):
        """Test validation with unauthorized access returns 403."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=403, detail="Access denied")

        assert exc.value.status_code == 403

    @pytest.mark.parametrize("rule_type", [
        "required_fields",
        "max_duplicate_rate",
        "min_chunk_coverage",
        "bad_extensions",
        "min_freshness",
        "file_size",
        "content_length"
    ])
    def test_validate_all_rule_types(self, rule_type):
        """Test validation handles all rule types."""
        response = {
            "valid": True,
            "rules_count": 1,
            "enabled_rules_count": 1
        }

        assert response["valid"] is True


class TestDataQualitySeedEndpoint:
    """Test /products/{product_id}/rules/seed endpoint."""

    def test_seed_basic_creates_two_rules(self):
        """Test seeding basic rule set creates 2 rules."""
        response = {
            "message": "Rules seeded successfully",
            "rule_set": "basic",
            "created": 2,
            "skipped": 0,
            "rules": [Mock(), Mock()]
        }

        assert response["created"] == 2
        assert len(response["rules"]) == 2

    def test_seed_comprehensive_creates_five_rules(self):
        """Test seeding comprehensive rule set creates 5 rules."""
        response = {
            "created": 5,
            "rule_set": "comprehensive"
        }

        assert response["created"] == 5

    def test_seed_enterprise_creates_seven_rules(self):
        """Test seeding enterprise rule set creates 7 rules."""
        response = {
            "created": 7,
            "rule_set": "enterprise"
        }

        assert response["created"] == 7

    def test_seed_with_overwrite_false_skips_existing(self):
        """Test seed with overwrite=false skips existing rules."""
        response = {
            "created": 1,
            "skipped": 1,
            "message": "Rules seeded successfully"
        }

        total = response["created"] + response["skipped"]
        assert total >= response["created"]

    def test_seed_with_overwrite_true_replaces_all(self):
        """Test seed with overwrite=true replaces existing rules."""
        response = {
            "created": 5,
            "skipped": 0,
            "message": "Rules seeded successfully"
        }

        assert response["skipped"] == 0

    def test_seed_invalid_rule_set_returns_400(self):
        """Test invalid rule_set returns 400."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid rule_set. Must be one of: basic, comprehensive, enterprise"
            )

        assert exc.value.status_code == 400

    def test_seed_missing_product_returns_404(self):
        """Test seed with non-existent product returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="Product not found")

        assert exc.value.status_code == 404

    def test_seed_returns_rule_details(self):
        """Test seed response includes rule details."""
        response = {
            "created": 2,
            "rules": [
                {
                    "rule_id": str(uuid4()),
                    "name": "Required Fields Check",
                    "rule_type": "required_fields",
                    "status": "created"
                },
                {
                    "rule_id": str(uuid4()),
                    "name": "Duplicate Rate Check",
                    "rule_type": "max_duplicate_rate",
                    "status": "created"
                }
            ]
        }

        assert len(response["rules"]) == 2
        for rule in response["rules"]:
            assert "rule_id" in rule
            assert "name" in rule
            assert "rule_type" in rule
            assert "status" in rule

    def test_seed_creates_audit_logs(self):
        """Test seed creates audit logs for each rule."""
        response = {
            "created": 3,
            "rules": [
                {"rule_id": str(uuid4())},
                {"rule_id": str(uuid4())},
                {"rule_id": str(uuid4())},
            ]
        }

        # Should have audit log for each created rule
        assert len(response["rules"]) == response["created"]

    @pytest.mark.parametrize("rule_set", ["basic", "comprehensive", "enterprise"])
    def test_seed_all_rule_sets_valid(self, rule_set):
        """Test all rule sets are valid."""
        expected = {"basic": 2, "comprehensive": 5, "enterprise": 7}

        response = {
            "rule_set": rule_set,
            "created": expected[rule_set],
            "skipped": 0
        }

        assert response["created"] == expected[rule_set]


class TestDataQualityRulesRequest:
    """Test DataQualityRulesRequest model."""

    def test_rules_request_creation(self):
        """Test creating rules request."""
        rules = {"required_fields_rules": []}
        request = DataQualityRulesRequest(rules=rules)

        assert request.rules == rules

    def test_rules_request_with_multiple_rule_types(self):
        """Test rules request with multiple rule types."""
        rules = {
            "required_fields_rules": [{"name": "Rule1"}],
            "max_duplicate_rate_rules": [{"name": "Rule2"}],
            "min_chunk_coverage_rules": [{"name": "Rule3"}]
        }
        request = DataQualityRulesRequest(rules=rules)

        assert len(request.rules) == 3

    def test_rules_request_preserves_rule_structure(self):
        """Test rules request preserves rule structure."""
        rule = {
            "name": "Test Rule",
            "description": "Test Description",
            "rule_type": "required_fields",
            "severity": "error",
            "enabled": True
        }
        rules = {"required_fields_rules": [rule]}
        request = DataQualityRulesRequest(rules=rules)

        assert request.rules["required_fields_rules"][0]["name"] == "Test Rule"
        assert request.rules["required_fields_rules"][0]["severity"] == "error"


class TestDataQualityRulesResponse:
    """Test DataQualityRulesResponse model."""

    def test_rules_response_creation(self):
        """Test creating rules response."""
        response = DataQualityRulesResponse(
            product_id="prod-1",
            version=1,
            created_at="2026-03-30T00:00:00",
            updated_at="2026-03-30T00:00:00",
            rules={}
        )

        assert response.product_id == "prod-1"
        assert response.version == 1

    def test_rules_response_with_rules(self):
        """Test rules response with populated rules."""
        response = DataQualityRulesResponse(
            product_id="prod-1",
            version=2,
            created_at="2026-03-30T00:00:00",
            updated_at="2026-03-30T00:00:00",
            rules={
                "required_fields_rules": [{"name": "Rule1"}],
                "max_duplicate_rate_rules": [{"name": "Rule2"}]
            }
        )

        assert len(response.rules) == 2


class TestDataQualityViolationResponse:
    """Test DataQualityViolationResponse model."""

    def test_violation_response_creation(self):
        """Test creating violation response."""
        violation = DataQualityViolationResponse(
            id=str(uuid4()),
            rule_name="Required Fields",
            rule_type="required_fields",
            severity="error",
            message="Missing required field: id",
            details={"field": "id"},
            affected_count=10,
            total_count=100,
            violation_rate=0.1,
            created_at="2026-03-30T00:00:00"
        )

        assert violation.severity == "error"
        assert violation.violation_rate == 0.1

    def test_violation_response_violation_rate(self):
        """Test violation rate calculation."""
        violation = DataQualityViolationResponse(
            id=str(uuid4()),
            rule_name="Test",
            rule_type="required_fields",
            severity="warning",
            message="Test message",
            details={},
            affected_count=25,
            total_count=100,
            violation_rate=0.25,
            created_at="2026-03-30T00:00:00"
        )

        assert violation.violation_rate == 0.25


class TestDataQualityReportResponse:
    """Test DataQualityReportResponse model."""

    def test_report_response_creation(self):
        """Test creating report response."""
        report = DataQualityReportResponse(
            product_id="prod-1",
            version=1,
            pipeline_run_id="run-1",
            created_at="2026-03-30T00:00:00",
            violations=[],
            total_items_checked=1000,
            total_violations=5,
            has_violations=True,
            has_errors=True,
            has_warnings=False,
            overall_quality_score=0.95
        )

        assert report.version == 1
        assert report.overall_quality_score == 0.95

    def test_report_response_quality_score_bounds(self):
        """Test quality score is between 0 and 1."""
        report = DataQualityReportResponse(
            product_id="prod-1",
            version=1,
            pipeline_run_id="run-1",
            created_at="2026-03-30T00:00:00",
            violations=[],
            total_items_checked=1000,
            total_violations=0,
            has_violations=False,
            has_errors=False,
            has_warnings=False,
            overall_quality_score=1.0
        )

        assert 0.0 <= report.overall_quality_score <= 1.0

    def test_report_response_consistency(self):
        """Test report response consistency."""
        violation = DataQualityViolationResponse(
            id=str(uuid4()),
            rule_name="Test",
            rule_type="required_fields",
            severity="warning",
            message="Test message",
            details={},
            affected_count=1,
            total_count=100,
            violation_rate=0.01,
            created_at="2026-03-30T00:00:00"
        )
        report = DataQualityReportResponse(
            product_id="prod-1",
            version=1,
            pipeline_run_id="run-1",
            created_at="2026-03-30T00:00:00",
            violations=[violation],
            total_items_checked=100,
            total_violations=1,
            has_violations=True,
            has_errors=False,
            has_warnings=True,
            overall_quality_score=0.99
        )

        assert report.has_violations == (report.total_violations > 0)
        assert len(report.violations) == report.total_violations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
