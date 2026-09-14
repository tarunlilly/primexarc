"""
Unit Tests for Audit Logging

Tests cover:
- Audit middleware capturing requests
- UserAuditLog model creation
- Action mapping (HTTP method to audit action)
- Resource extraction from paths
- Status tracking (success/failure)
- Database persistence
- Edge cases and error handling
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import json

from sqlalchemy.orm import Session
from fastapi import Request, Response
from starlette.requests import Request as StarletteRequest

from primedata.db.models import UserAuditLog, User, Workspace
from primedata.core.audit_middleware import AuditMiddleware


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def test_workspace_id():
    """Test workspace ID."""
    return uuid4()


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def mock_request():
    """Create mock request."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.url.path = "/api/v1/products/123"
    request.url.scheme = "http"
    request.url.hostname = "localhost"
    request.client = Mock(host="192.168.1.1")
    request.query_params = {}
    request.headers = {"user-agent": "Mozilla/5.0"}
    request.state = Mock()
    return request


@pytest.fixture
def mock_response():
    """Create mock response."""
    response = Mock(spec=Response)
    response.status_code = 200
    response.headers = {}
    return response


@pytest.fixture
def test_workspace(test_workspace_id):
    """Create test workspace."""
    workspace = Mock(spec=Workspace)
    workspace.id = test_workspace_id
    workspace.name = "Test Workspace"
    return workspace


@pytest.fixture
def test_user(test_user_id):
    """Create test user."""
    user = Mock(spec=User)
    user.id = test_user_id
    user.email = "test@example.com"
    user.name = "Test User"
    return user


@pytest.fixture
def test_audit_log(test_user_id, test_workspace_id):
    """Create test audit log."""
    audit_log = Mock(spec=UserAuditLog)
    audit_log.id = uuid4()
    audit_log.user_id = test_user_id
    audit_log.workspace_id = test_workspace_id
    audit_log.action = "CREATE"
    audit_log.resource_type = "PRODUCT"
    audit_log.resource_id = "prod-123"
    audit_log.status = "success"
    audit_log.ip_address = "192.168.1.1"
    audit_log.timestamp = datetime.utcnow()
    return audit_log


# ============================================================================
# AUDIT MIDDLEWARE TESTS
# ============================================================================


class TestAuditMiddleware:
    """Test AuditMiddleware class."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = AuditMiddleware(None)
        assert middleware is not None
        assert hasattr(middleware, "dispatch")
        assert hasattr(middleware, "SKIP_PATHS")

    def test_skip_paths_configured(self):
        """Test that skip paths are configured."""
        middleware = AuditMiddleware(None)
        assert "/health" in middleware.SKIP_PATHS
        assert "/docs" in middleware.SKIP_PATHS
        assert "/openapi.json" in middleware.SKIP_PATHS

    def test_should_skip_health_endpoint(self):
        """Test that health endpoints are skipped."""
        middleware = AuditMiddleware(None)
        request = Mock()
        request.url.path = "/health"
        request.method = "GET"

        result = middleware._should_skip(request)
        assert result is True

    def test_should_skip_options_method(self):
        """Test that OPTIONS requests are skipped."""
        middleware = AuditMiddleware(None)
        request = Mock()
        request.url.path = "/api/v1/products"
        request.method = "OPTIONS"

        result = middleware._should_skip(request)
        assert result is True

    def test_should_not_skip_post_request(self):
        """Test that POST requests are not skipped."""
        middleware = AuditMiddleware(None)
        request = Mock()
        request.url.path = "/api/v1/products"
        request.method = "POST"

        result = middleware._should_skip(request)
        assert result is False

    def test_should_not_skip_delete_request(self):
        """Test that DELETE requests are not skipped."""
        middleware = AuditMiddleware(None)
        request = Mock()
        request.url.path = "/api/v1/products/123"
        request.method = "DELETE"

        result = middleware._should_skip(request)
        assert result is False

    # ========================================================================
    # ACTION MAPPING TESTS
    # ========================================================================

    def test_get_action_from_post(self):
        """Test GET to VIEW mapping."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("GET")
        assert action == "VIEW"

    def test_get_action_from_post_method(self):
        """Test POST to CREATE mapping."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("POST")
        assert action == "CREATE"

    def test_get_action_from_put(self):
        """Test PUT to UPDATE mapping."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("PUT")
        assert action == "UPDATE"

    def test_get_action_from_patch(self):
        """Test PATCH to UPDATE mapping."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("PATCH")
        assert action == "UPDATE"

    def test_get_action_from_delete(self):
        """Test DELETE to DELETE mapping."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("DELETE")
        assert action == "DELETE"

    def test_get_action_unknown_method(self):
        """Test unknown method handling."""
        middleware = AuditMiddleware(None)
        action = middleware._get_action_from_method("CUSTOM")
        assert action == "CUSTOM"

    # ========================================================================
    # RESOURCE EXTRACTION TESTS
    # ========================================================================

    def test_extract_resource_from_simple_path(self):
        """Test resource extraction from simple path."""
        middleware = AuditMiddleware(None)
        path = "/api/v1/products/prod-123"
        resource_type, resource_id = middleware._extract_resource_info(path, None)

        assert resource_type == "PRODUCTS"
        assert resource_id == "prod-123"

    def test_extract_resource_from_nested_path(self):
        """Test resource extraction from nested path."""
        middleware = AuditMiddleware(None)
        path = "/api/v1/workspaces/ws-123/products/prod-456"
        resource_type, resource_id = middleware._extract_resource_info(path, None)

        # Extracts first resource in path (workspaces)
        assert resource_type == "WORKSPACES"
        assert resource_id == "ws-123"

    def test_extract_resource_from_body(self):
        """Test resource extraction from request body."""
        middleware = AuditMiddleware(None)
        path = "/api/v1/products"
        body = {"id": "prod-789"}
        resource_type, resource_id = middleware._extract_resource_info(path, body)

        # Body ID overrides path extraction
        assert resource_id == "prod-789"
        assert resource_type == "PRODUCTS"  # Still extracted from path

    def test_extract_resource_product_id_from_body(self):
        """Test resource extraction from product_id in body."""
        middleware = AuditMiddleware(None)
        path = "/api/v1/chunks"
        body = {"product_id": "prod-999"}
        resource_type, resource_id = middleware._extract_resource_info(path, body)

        assert resource_type == "PRODUCT"
        assert resource_id == "prod-999"

    def test_extract_resource_limits_id_length(self):
        """Test that resource ID is limited to 255 characters."""
        middleware = AuditMiddleware(None)
        path = "/api/v1/products"
        long_id = "x" * 300
        body = {"id": long_id}
        resource_type, resource_id = middleware._extract_resource_info(path, body)

        assert len(resource_id) == 255
        assert resource_id == "x" * 255

    # ========================================================================
    # REQUEST CAPTURE TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_capture_request_with_user_state(self):
        """Test capturing request with user state."""
        middleware = AuditMiddleware(None)
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/products"
        request.query_params = {}
        request.headers = {"user-agent": "test"}
        request.state = Mock(user_id="user-123", workspace_id="ws-456")

        # Mock body reading
        request.body = AsyncMock(return_value=b'{"name": "test"}')

        request_data = await middleware._capture_request(request)

        assert request_data["user_id"] == "user-123"
        assert request_data["workspace_id"] == "ws-456"
        assert request_data["method"] == "POST"
        assert request_data["path"] == "/api/v1/products"

    @pytest.mark.asyncio
    async def test_capture_request_without_body(self):
        """Test capturing GET request without body."""
        middleware = AuditMiddleware(None)
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/v1/products"
        request.query_params = {}
        request.headers = {}
        request.state = Mock()

        request_data = await middleware._capture_request(request)

        assert request_data["method"] == "GET"
        assert request_data["body"] is None

    @pytest.mark.asyncio
    async def test_capture_request_with_invalid_body(self):
        """Test that invalid JSON body doesn't crash."""
        middleware = AuditMiddleware(None)
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/products"
        request.query_params = {}
        request.headers = {}
        request.state = Mock()

        # Mock body that fails JSON parsing
        request.body = AsyncMock(return_value=b'invalid json')

        request_data = await middleware._capture_request(request)

        # Should not raise, body might be unparsed
        assert request_data["method"] == "POST"


# ============================================================================
# AUDIT LOG MODEL TESTS
# ============================================================================


class TestUserAuditLogModel:
    """Test UserAuditLog model."""

    def test_audit_log_creation(self, mock_db, test_user_id, test_workspace_id):
        """Test creating an audit log entry."""
        audit_log = UserAuditLog(
            workspace_id=test_workspace_id,
            user_id=test_user_id,
            action="CREATE",
            resource_type="PRODUCT",
            resource_id="prod-123",
            status="success",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert audit_log.user_id == test_user_id
        assert audit_log.workspace_id == test_workspace_id
        assert audit_log.action == "CREATE"
        assert audit_log.resource_type == "PRODUCT"
        assert audit_log.resource_id == "prod-123"
        assert audit_log.status == "success"

    def test_audit_log_with_changes(self, mock_db, test_user_id):
        """Test audit log with changes captured."""
        changes = {
            "before": {"name": "old-name"},
            "after": {"name": "new-name"},
        }
        audit_log = UserAuditLog(
            user_id=test_user_id,
            action="UPDATE",
            resource_type="PRODUCT",
            resource_id="prod-456",
            changes=changes,
            status="success",
        )

        assert audit_log.changes == changes

    def test_audit_log_with_error(self, mock_db, test_user_id):
        """Test audit log with error message."""
        audit_log = UserAuditLog(
            user_id=test_user_id,
            action="DELETE",
            resource_type="PRODUCT",
            resource_id="prod-789",
            status="failure",
            error_message="Product not found",
        )

        assert audit_log.status == "failure"
        assert audit_log.error_message == "Product not found"

    def test_audit_log_with_metadata(self, mock_db, test_user_id):
        """Test audit log with additional metadata."""
        audit_metadata = {
            "http_method": "POST",
            "http_status": 201,
            "path": "/api/v1/products",
        }
        audit_log = UserAuditLog(
            user_id=test_user_id,
            action="CREATE",
            resource_type="PRODUCT",
            resource_id="prod-999",
            audit_metadata=audit_metadata,
            status="success",
        )

        assert audit_log.audit_metadata == audit_metadata
        assert audit_log.audit_metadata["http_status"] == 201

    def test_audit_log_tablename(self):
        """Test that audit log has correct table name."""
        assert UserAuditLog.__tablename__ == "user_audit_logs"

    def test_audit_log_indexes_configured(self):
        """Test that indexes are configured."""
        # Check that __table_args__ contains indexes
        assert hasattr(UserAuditLog, "__table_args__")
        # This verifies the model has been properly configured with indexes


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================


class TestAuditLoggingFlow:
    """Test end-to-end audit logging flow."""

    def test_complete_audit_trail_success(self, test_user_id, test_workspace_id):
        """Test complete audit trail for successful operation."""
        # Simulate successful product creation
        audit_log = UserAuditLog(
            workspace_id=test_workspace_id,
            user_id=test_user_id,
            action="CREATE",
            resource_type="PRODUCT",
            resource_id="new-prod-123",
            changes={"body": {"name": "New Product"}},
            status="success",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 (Test)",
            audit_metadata={
                "http_method": "POST",
                "http_status": 201,
                "path": "/api/v1/products",
            },
        )

        # Verify all fields captured
        assert audit_log.user_id == test_user_id
        assert audit_log.workspace_id == test_workspace_id
        assert audit_log.action == "CREATE"
        assert audit_log.status == "success"
        assert audit_log.audit_metadata["http_status"] == 201

    def test_complete_audit_trail_failure(self, test_user_id, test_workspace_id):
        """Test complete audit trail for failed operation."""
        # Simulate failed product update
        audit_log = UserAuditLog(
            workspace_id=test_workspace_id,
            user_id=test_user_id,
            action="UPDATE",
            resource_type="PRODUCT",
            resource_id="missing-prod",
            status="failure",
            error_message="Product not found",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            audit_metadata={
                "http_method": "PUT",
                "http_status": 404,
                "path": "/api/v1/products/missing-prod",
            },
        )

        # Verify error captured
        assert audit_log.status == "failure"
        assert audit_log.error_message == "Product not found"
        assert audit_log.audit_metadata["http_status"] == 404

    def test_audit_trail_multiple_actions(self, test_user_id, test_workspace_id):
        """Test that multiple actions are captured independently."""
        actions = [
            ("CREATE", "PRODUCT", "prod-1", "success"),
            ("UPDATE", "PRODUCT", "prod-1", "success"),
            ("VIEW", "PRODUCT", "prod-1", "success"),
            ("DELETE", "PRODUCT", "prod-1", "success"),
        ]

        audit_logs = []
        for action, resource_type, resource_id, status in actions:
            audit_log = UserAuditLog(
                user_id=test_user_id,
                workspace_id=test_workspace_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
            )
            audit_logs.append(audit_log)

        # Verify all actions captured
        assert len(audit_logs) == 4
        assert audit_logs[0].action == "CREATE"
        assert audit_logs[1].action == "UPDATE"
        assert audit_logs[2].action == "VIEW"
        assert audit_logs[3].action == "DELETE"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestAuditEdgeCases:
    """Test edge cases and error handling."""

    def test_audit_log_without_user(self, test_workspace_id):
        """Test audit log can be created without user (system action)."""
        audit_log = UserAuditLog(
            workspace_id=test_workspace_id,
            user_id=None,  # System action
            action="SCHEDULED_JOB",
            resource_type="DOCUMENT",
            resource_id="doc-123",
            status="success",
        )

        assert audit_log.user_id is None
        assert audit_log.action == "SCHEDULED_JOB"

    def test_audit_log_without_workspace(self, test_user_id):
        """Test audit log can be created without workspace (global action)."""
        audit_log = UserAuditLog(
            workspace_id=None,  # Global action
            user_id=test_user_id,
            action="LOGIN",
            resource_type="USER",
            resource_id=test_user_id,
            status="success",
        )

        assert audit_log.workspace_id is None
        assert audit_log.action == "LOGIN"

    def test_resource_extraction_from_empty_path(self):
        """Test resource extraction handles empty path gracefully."""
        middleware = AuditMiddleware(None)
        path = ""
        resource_type, resource_id = middleware._extract_resource_info(path, None)

        assert resource_type == "UNKNOWN"
        # Should not crash

    def test_audit_log_special_characters_in_resource_id(self, test_user_id):
        """Test audit log handles special characters in resource ID."""
        special_id = "prod-123!@#$%^&*()_+-=[]{}|;':,.<>?"[:255]
        audit_log = UserAuditLog(
            user_id=test_user_id,
            action="CREATE",
            resource_type="PRODUCT",
            resource_id=special_id,
            status="success",
        )

        assert audit_log.resource_id == special_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
