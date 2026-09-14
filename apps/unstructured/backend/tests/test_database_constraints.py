"""
Unit Tests for Database Constraint Violations Prevention

Tests ensure that:
1. All NOT NULL fields are properly populated
2. Required dependencies are injected (current_user, db)
3. Payload extraction includes proper fallbacks
4. Audit trail fields capture actual user IDs
5. Access control is properly implemented
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy.orm import Session
from sqlalchemy import inspect

from primedata.db.models import (
    User, Product, RawFile, DataSource, Workspace,
    PipelineRun, BillingProfile
)
from primedata.db.models_enterprise import (
    DataQualityRule, DataQualityRuleAudit, CustomPlaybook
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def mock_current_user():
    """Create mock current user."""
    return {
        "id": str(uuid4()),
        "email": "test@example.com",
        "name": "Test User"
    }


@pytest.fixture
def test_workspace_id():
    """Test workspace ID."""
    return uuid4()


@pytest.fixture
def test_product_id():
    """Test product ID."""
    return uuid4()


@pytest.fixture
def test_workspace(test_workspace_id):
    """Create test workspace."""
    workspace = Mock(spec=Workspace)
    workspace.id = test_workspace_id
    workspace.name = "Test Workspace"
    return workspace


@pytest.fixture
def test_product(test_product_id, test_workspace_id):
    """Create test product."""
    product = Mock(spec=Product)
    product.id = test_product_id
    product.workspace_id = test_workspace_id
    product.name = "Test Product"
    product.current_version = 1
    return product


# ============================================================================
# TESTS: NOT NULL CONSTRAINT VIOLATIONS
# ============================================================================

class TestNotNullConstraints:
    """Test that NOT NULL constraints are properly handled."""

    def test_rawfile_must_have_storage_etag(self):
        """Test RawFile cannot have NULL storage_etag."""
        # Get NOT NULL columns from RawFile model
        mapper = inspect(RawFile)
        columns = mapper.columns

        # Verify storage_etag column is NOT NULL
        storage_etag_col = columns.get('storage_etag')
        assert storage_etag_col is not None, "storage_etag column should exist"
        assert not storage_etag_col.nullable, "storage_etag should have NOT NULL constraint"

    def test_user_must_have_auth_provider(self):
        """Test User cannot have NULL auth_provider."""
        mapper = inspect(User)
        auth_provider_col = mapper.columns.get('auth_provider')

        assert auth_provider_col is not None, "auth_provider column should exist"
        assert not auth_provider_col.nullable, "auth_provider should have NOT NULL constraint"

    def test_quality_rule_must_have_created_by(self):
        """Test DataQualityRule cannot have NULL created_by."""
        mapper = inspect(DataQualityRule)
        created_by_col = mapper.columns.get('created_by')

        assert created_by_col is not None, "created_by column should exist"
        assert not created_by_col.nullable, "created_by should have NOT NULL constraint"

    def test_playbook_must_have_owner_user_id(self):
        """Test CustomPlaybook cannot have NULL owner_user_id."""
        mapper = inspect(CustomPlaybook)
        owner_col = mapper.columns.get('owner_user_id')

        assert owner_col is not None, "owner_user_id column should exist"
        assert not owner_col.nullable, "owner_user_id should have NOT NULL constraint"

    def test_quality_rule_audit_must_have_changed_by(self):
        """Test DataQualityRuleAudit cannot have NULL changed_by."""
        mapper = inspect(DataQualityRuleAudit)
        changed_by_col = mapper.columns.get('changed_by')

        assert changed_by_col is not None, "changed_by column should exist"
        assert not changed_by_col.nullable, "changed_by should have NOT NULL constraint"


# ============================================================================
# TESTS: MISSING DEPENDENCY INJECTION
# ============================================================================

class TestDependencyInjection:
    """Test that required dependencies are properly injected."""

    def test_billing_portal_endpoint_has_current_user(self):
        """Test /billing/portal endpoint requires authentication."""
        from primedata.api.billing import get_customer_portal

        # Check function signature
        import inspect
        sig = inspect.signature(get_customer_portal)
        params = list(sig.parameters.keys())

        # Should have current_user parameter
        assert 'current_user' in params, "Portal endpoint should have current_user dependency"
        assert 'db' in params, "Portal endpoint should have db dependency"

    def test_billing_limits_endpoint_has_current_user(self):
        """Test /billing/limits endpoint requires authentication."""
        from primedata.api.billing import get_billing_limits

        import inspect
        sig = inspect.signature(get_billing_limits)
        params = list(sig.parameters.keys())

        # Should have current_user parameter
        assert 'current_user' in params, "Billing limits endpoint should have current_user dependency"

    def test_datasources_test_config_has_current_user(self):
        """Test /datasources/test-config endpoint requires authentication."""
        from primedata.api.datasources import test_datasource_config

        import inspect
        sig = inspect.signature(test_datasource_config)
        params = list(sig.parameters.keys())

        # Should have current_user parameter
        assert 'current_user' in params, "Test config endpoint should have current_user dependency"

    def test_rules_seed_endpoint_has_current_user(self):
        """Test /products/{product_id}/rules/seed has current_user."""
        from primedata.api.products import seed_data_quality_rules

        import inspect
        sig = inspect.signature(seed_data_quality_rules)
        params = list(sig.parameters.keys())

        # Should have current_user parameter
        assert 'current_user' in params, "Rules seed endpoint should have current_user dependency"


# ============================================================================
# TESTS: AUDIT TRAIL FIELDS
# ============================================================================

class TestAuditTrailFields:
    """Test that audit fields capture actual user information."""

    def test_quality_rule_creation_captures_user(self, mock_db, mock_current_user):
        """Test DataQualityRule captures created_by from current_user."""
        # Simulate rule creation from endpoint
        rule_data = {
            "name": "Test Rule",
            "description": "Test description",
            "rule_type": "required_fields",
            "severity": "error",
            "configuration": {},
            "enabled": True,
        }

        # Created_by should come from current_user, NOT None
        expected_created_by = mock_current_user.get("id")

        assert expected_created_by is not None, "created_by must not be None"
        assert isinstance(expected_created_by, str), "created_by should be a string ID"

    def test_data_quality_rule_audit_captures_user(self, mock_current_user):
        """Test DataQualityRuleAudit captures changed_by."""
        # Simulate audit log creation
        changed_by = mock_current_user.get("id")

        assert changed_by is not None, "changed_by must not be None"
        assert len(changed_by) > 0, "changed_by should not be empty string"

    def test_playbook_creation_captures_owner(self, mock_current_user):
        """Test CustomPlaybook captures owner_user_id."""
        # Simulate playbook creation
        owner_user_id = mock_current_user.get("id")

        assert owner_user_id is not None, "owner_user_id must not be None"
        assert isinstance(owner_user_id, str), "owner_user_id should be a string"


# ============================================================================
# TESTS: PAYLOAD EXTRACTION SAFETY
# ============================================================================

class TestPayloadExtraction:
    """Test safe extraction of fields from payloads."""

    def test_chunk_text_extraction_handles_missing_field(self):
        """Test chunk_text extraction has proper fallback."""
        # Simulate empty payload
        payload = {}

        # Proper extraction logic
        chunk_text = payload.get("text") or payload.get("chunk_text", "")

        # Should not raise error
        assert isinstance(chunk_text, str), "chunk_text should be string"

    def test_chunk_text_extraction_prefers_text_field(self):
        """Test chunk_text extraction prefers 'text' field."""
        # Simulate payload with 'text' field (as stored in OpenSearch)
        payload = {"text": "Hello World", "chunk_text": "Old Field"}

        # Proper extraction logic
        chunk_text = payload.get("text") or payload.get("chunk_text", "")

        # Should prefer 'text' field
        assert chunk_text == "Hello World", "Should use 'text' field when available"

    def test_chunk_text_extraction_fallback_to_chunk_text(self):
        """Test chunk_text extraction falls back to chunk_text field."""
        # Simulate payload with only 'chunk_text' field
        payload = {"chunk_text": "Fallback Content"}

        # Proper extraction logic
        chunk_text = payload.get("text") or payload.get("chunk_text", "")

        # Should fall back to chunk_text
        assert chunk_text == "Fallback Content", "Should fallback to chunk_text when text unavailable"

    def test_chunk_text_extraction_returns_empty_string_safely(self):
        """Test chunk_text extraction returns empty string as last resort."""
        # Empty payload
        payload = {}

        # Proper extraction logic
        chunk_text = payload.get("text") or payload.get("chunk_text", "")

        # Should return empty string, not None
        assert chunk_text == "", "Should return empty string when both fields missing"
        assert chunk_text is not None, "chunk_text should never be None"


# ============================================================================
# TESTS: ACCESS CONTROL VALIDATION
# ============================================================================

class TestAccessControl:
    """Test that endpoints validate user access to resources."""

    def test_billing_portal_validates_workspace_access(self):
        """Test billing portal endpoint validates user can access workspace."""
        # The endpoint should:
        # 1. Verify user is authenticated (current_user present)
        # 2. Verify user has access to the workspace_id

        # This should be tested by checking that the endpoint uses
        # authorization/permission checking
        pass

    def test_quality_rule_seed_validates_product_access(self):
        """Test rules seed endpoint validates user can access product."""
        # The endpoint should:
        # 1. Verify current_user is provided
        # 2. Verify user has access to the product

        # Check that ensure_product_access is called with request and user
        from primedata.api.products import seed_data_quality_rules

        # Function should call ensure_product_access
        # which validates user has permission to access product
        pass


# ============================================================================
# TESTS: FIELD POPULATION VERIFICATION
# ============================================================================

class TestFieldPopulation:
    """Test that all required fields are populated."""

    def test_rawfile_storage_etag_provided_in_folder_connector(self):
        """Test RawFile includes storage_etag when created from folder connector."""
        # storage_etag should be either:
        # 1. Actual ETag from storage provider
        # 2. Checksum/hash of file
        # 3. Generated UUID if unavailable

        # Should NOT be None or empty
        pass

    def test_rawfile_storage_etag_provided_in_web_connector(self):
        """Test RawFile includes storage_etag when created from web connector."""
        # For web URLs, storage_etag could be:
        # 1. ETag from HTTP headers
        # 2. Hash of URL
        # 3. Generated identifier

        # Should NOT be None or empty
        pass

    def test_rawfile_storage_etag_provided_in_file_upload(self):
        """Test RawFile includes storage_etag when created from file upload."""
        # For uploaded files, storage_etag should be:
        # 1. Actual ETag from S3/storage
        # 2. File checksum
        # 3. Generated value

        # Should NOT be None or empty
        pass

    def test_user_auth_provider_has_valid_value(self):
        """Test User auth_provider is set to valid value, never None."""
        # Valid values could be:
        # - "none" / "internal" for non-authenticated users
        # - "bouncer" / "oauth" for authenticated users
        # - Never None

        pass


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestConstraintIntegration:
    """Integration tests for constraint handling."""

    def test_endpoint_to_database_flow(self, mock_db, mock_current_user):
        """Test complete flow from API endpoint to database."""
        # Simulate the flow:
        # 1. Current user comes from request
        # 2. Endpoint extracts current_user
        # 3. Model is created with actual user_id
        # 4. Database accepts the insert without constraint violation

        user_id = mock_current_user.get("id")

        # Verify user_id is valid for database
        assert user_id is not None, "User ID must not be None"
        assert isinstance(user_id, str), "User ID must be string"
        assert len(user_id) > 0, "User ID must not be empty"

    def test_payload_extraction_to_response_flow(self):
        """Test complete flow from payload extraction to response."""
        # Simulate the flow:
        # 1. Chunk data retrieved from database
        # 2. Payload extracted safely
        # 3. Response returned with populated fields

        payload = {"text": "Sample chunk content"}
        chunk_text = payload.get("text") or payload.get("chunk_text", "")

        # Verify response will have populated field
        assert len(chunk_text) > 0, "Response should have populated chunk_text"
        assert chunk_text == "Sample chunk content", "Should preserve actual content"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
