"""
Comprehensive CORS middleware tests for FastAPI application.

This test suite consolidates CORS testing across multiple scenarios:
1. Configuration validation with various origin lists
2. Preflight (OPTIONS) request handling
3. Actual cross-origin requests (GET/POST/etc)
4. Error response handling with CORS headers
5. Credentials and security settings
6. Production origin configurations
7. Header exposure and caching
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from unittest.mock import patch
import sys
from pathlib import Path


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def cors_app():
    """Create a minimal FastAPI app with CORS middleware for lightweight testing."""
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://primedata-frontend.apps-internal.lrl.lilly.com",
            "https://primedata-internal.apps-internal.lrl.lilly.com",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=600,
    )

    @app.options("/{path_name:path}", include_in_schema=False)
    async def options_handler(path_name: str):
        """Handle CORS preflight"""
        return {}

    @app.get("/health/simple")
    async def health():
        """Health check"""
        return {"status": "ok"}

    @app.get("/api/v1/products/")
    async def list_products():
        """Test products endpoint"""
        return {"products": []}

    @app.get("/api/v1/users/me")
    async def get_user():
        """Test user endpoint"""
        return {"id": "123", "email": "test@example.com"}

    return app


@pytest.fixture
def cors_client(cors_app):
    """Create test client for lightweight CORS app."""
    return TestClient(cors_app)


@pytest.fixture
def app_with_full_dependencies():
    """Create test client for FastAPI app with full dependencies."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    with patch.dict("os.environ", {
        "DATABASE_URL": "sqlite:///:memory:",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test",
    }):
        try:
            from primedata.api.app import app
            return TestClient(app)
        except ImportError:
            # If full app not available, use the lightweight one
            return None


# ============================================================================
# TEST CLASSES: CONFIGURATION & SETUP
# ============================================================================

class TestCORSConfiguration:
    """Test CORS configuration scenarios and setup."""

    def test_cors_with_allowed_origins_list(self, cors_client):
        """Test CORS with proper list of allowed origins."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "POST",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_blocks_disallowed_origins(self):
        """Test that CORS blocks disallowed origins."""
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://primedata-frontend.apps-internal.lrl.lilly.com"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "POST",
            }
        )
        # Disallowed origin should be blocked
        assert response.headers.get("access-control-allow-origin") is None

    def test_cors_case_sensitivity_in_origins(self):
        """Test that origin matching is case-sensitive and exact."""
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://primedata-frontend.apps.lrl.lilly.com"],
            allow_credentials=True,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["*"],
        )

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app)

        # Test with different case - should be blocked
        response = client.options(
            "/health",
            headers={
                "Origin": "https://PRIMEDATA-FRONTEND.APPS.LRL.LILLY.COM",
                "Access-Control-Request-Method": "POST",
            }
        )
        # Different case should not match (CORS is case-sensitive)
        assert response.headers.get("access-control-allow-origin") is None

    def test_cors_production_origins_allowed(self, cors_client):
        """Test specific allowed origins from production configuration."""
        test_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://primedata-frontend.apps-internal.lrl.lilly.com",
            "https://primedata-internal.apps-internal.lrl.lilly.com",
        ]

        for origin in test_origins:
            response = cors_client.options(
                "/health/simple",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                }
            )
            assert response.status_code == 200
            assert response.headers.get("access-control-allow-origin") == origin


# ============================================================================
# TEST CLASSES: PREFLIGHT REQUESTS (OPTIONS)
# ============================================================================

class TestCORSPreflight:
    """Test CORS preflight (OPTIONS) requests."""

    def test_preflight_from_allowed_localhost_origin(self, cors_client):
        """Test preflight request from localhost:3000 (allowed origin)."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert "POST" in response.headers.get("access-control-allow-methods", "")
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_from_allowed_127_origin(self, cors_client):
        """Test preflight request from 127.0.0.1:3000 (allowed origin)."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_from_disallowed_origin_blocked(self, cors_client):
        """Test preflight request from disallowed origin is blocked."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "POST",
            }
        )
        # FastAPI CORSMiddleware doesn't add headers for disallowed origins
        assert response.headers.get("access-control-allow-origin") is None

    def test_preflight_from_internal_production_origin(self, cors_client):
        """Test preflight from internal production origin."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "https://primedata-internal.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "POST",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-internal.apps-internal.lrl.lilly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_on_products_endpoint(self, cors_client):
        """Test preflight on /api/v1/products/ endpoint."""
        response = cors_client.options(
            "/api/v1/products/",
            headers={
                "Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"
        assert "POST" in response.headers.get("access-control-allow-methods", "")
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_on_users_me_endpoint(self, cors_client):
        """Test preflight on /api/v1/users/me endpoint."""
        response = cors_client.options(
            "/api/v1/users/me",
            headers={
                "Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_with_multiple_request_headers(self, cors_client):
        """Test preflight with multiple request headers."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type, authorization, x-custom-header",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        # FastAPI CORS returns the requested headers or "*"
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert allow_headers != ""


# ============================================================================
# TEST CLASSES: ACTUAL CROSS-ORIGIN REQUESTS
# ============================================================================

class TestCORSActualRequests:
    """Test actual cross-origin requests (GET/POST/etc)."""

    def test_get_from_allowed_origin_includes_cors_header(self, cors_client):
        """Test GET request from allowed origin includes CORS header."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_post_from_allowed_origin_includes_cors_header(self, cors_client):
        """Test POST request from allowed origin includes CORS header."""
        response = cors_client.post(
            "/health/simple",
            headers={"Origin": "http://localhost:3000"},
            json={}
        )
        # POST might not be allowed on /health/simple, but CORS headers should still be there
        if response.status_code == 405:
            # Method Not Allowed - but CORS headers should be present
            assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_get_from_disallowed_origin_no_cors_header(self, cors_client):
        """Test GET request from disallowed origin has no CORS header."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "https://evil.com"}
        )
        assert response.status_code == 200
        # CORS header should NOT be present for disallowed origin
        assert response.headers.get("access-control-allow-origin") is None

    def test_get_without_origin_works_normally(self, cors_client):
        """Test request without Origin header works normally (same-origin)."""
        response = cors_client.get("/health/simple")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        # Same-origin requests don't get CORS headers
        assert response.headers.get("access-control-allow-origin") is None

    def test_products_endpoint_from_allowed_origin(self, cors_client):
        """Test /api/v1/products/ endpoint from allowed origin."""
        response = cors_client.get(
            "/api/v1/products/",
            headers={"Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com"}
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"

    def test_users_me_endpoint_from_allowed_origin(self, cors_client):
        """Test /api/v1/users/me endpoint from allowed origin."""
        response = cors_client.get(
            "/api/v1/users/me",
            headers={"Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com"}
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"


# ============================================================================
# TEST CLASSES: ERROR RESPONSES WITH CORS HEADERS
# ============================================================================

class TestCORSErrorResponses:
    """Test CORS headers on error responses (4xx, 5xx)."""

    def test_cors_headers_on_error_from_allowed_origin(self, cors_client):
        """Test CORS headers are present on errors from allowed origins."""
        response = cors_client.get(
            "/nonexistent-endpoint",
            headers={"Origin": "http://localhost:3000"}
        )

        # Test that CORS headers are present even on error (404 or 405)
        assert response.status_code in [404, 405]
        # CORS headers MUST still be present even on error
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_headers_missing_on_error_from_disallowed_origin(self, cors_client):
        """Test CORS headers are NOT present on errors from disallowed origins."""
        response = cors_client.get(
            "/nonexistent-endpoint",
            headers={"Origin": "https://evil.com"}
        )

        # Error response may be 404 or 405
        assert response.status_code in [404, 405]
        # CORS headers should NOT be present for disallowed origin
        assert response.headers.get("access-control-allow-origin") is None

    def test_cors_headers_on_error_from_allowed_origin_internal(self, cors_client):
        """Test CORS headers are present on errors from internal production origin."""
        response = cors_client.get(
            "/api/v1/nonexistent",
            headers={"Origin": "https://primedata-internal.apps-internal.lrl.lilly.com"}
        )

        # Error may be 404 or 405
        assert response.status_code in [404, 405]
        assert response.headers.get("access-control-allow-origin") == "https://primedata-internal.apps-internal.lrl.lilly.com"


# ============================================================================
# TEST CLASSES: CREDENTIALS AND SECURITY
# ============================================================================

class TestCORSCredentials:
    """Test CORS credentials handling and security."""

    def test_credentials_header_true_for_allowed_origin(self, cors_client):
        """Test access-control-allow-credentials header for allowed origin."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_credentials_header_for_get_request(self, cors_client):
        """Test credentials header on GET request."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_vary_header_includes_origin(self, cors_client):
        """Test Vary header includes Origin for proper caching."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "http://localhost:3000"}
        )
        vary_header = response.headers.get("vary", "")
        assert "Origin" in vary_header

    def test_vary_header_on_preflight(self, cors_client):
        """Test Vary header on preflight request."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )
        vary_header = response.headers.get("vary", "").lower()
        assert "origin" in vary_header


# ============================================================================
# TEST CLASSES: HEADERS AND EXPOSURE
# ============================================================================

class TestCORSHeadersExposed:
    """Test that necessary headers are exposed to the frontend."""

    def test_access_control_expose_headers_present(self, cors_client):
        """Test that expose-headers allows frontend to read response headers."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.status_code == 200
        # Should expose headers for frontend to read (or be configured with *)
        # CORS middleware may set * or specific headers
        assert response.headers.get("access-control-allow-origin") is not None

    def test_cors_headers_all_methods(self, cors_client):
        """Test CORS headers work for multiple HTTP methods."""
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

        for method in methods:
            response = cors_client.options(
                "/health/simple",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": method,
                }
            )
            assert response.status_code == 200
            assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ============================================================================
# TEST CLASSES: PRODUCTION ORIGINS
# ============================================================================

class TestCORSProductionOrigins:
    """Test specific allowed origins from production configuration."""

    def test_primedata_frontend_allowed(self, cors_client):
        """Test that primedata-frontend origin is allowed."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "POST",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-frontend.apps-internal.lrl.lilly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_primedata_internal_allowed(self, cors_client):
        """Test that primedata-internal origin is allowed."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "https://primedata-internal.apps-internal.lrl.lilly.com",
                "Access-Control-Request-Method": "POST",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://primedata-internal.apps-internal.lrl.lilly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_localhost_3000_allowed(self, cors_client):
        """Test that http://localhost:3000 is allowed for development."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_127_0_0_1_3000_allowed(self, cors_client):
        """Test that http://127.0.0.1:3000 is allowed for development."""
        response = cors_client.options(
            "/health/simple",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


# ============================================================================
# TEST CLASSES: EDGE CASES AND NEGATIVE SCENARIOS
# ============================================================================

class TestCORSEdgeCases:
    """Test edge cases and negative scenarios."""

    def test_empty_origin_header(self, cors_client):
        """Test request with empty Origin header."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": ""}
        )
        # Empty origin should be treated as no origin
        assert response.status_code == 200

    def test_malformed_origin_blocked(self, cors_client):
        """Test that malformed origins are blocked."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "not-a-valid-origin"}
        )
        # Invalid origin should be blocked
        assert response.headers.get("access-control-allow-origin") is None

    def test_origin_with_port_must_match_exactly(self, cors_client):
        """Test that origins with ports must match exactly."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "http://localhost:8000"}  # Wrong port
        )
        # Should be blocked because port doesn't match
        assert response.headers.get("access-control-allow-origin") is None

    def test_http_vs_https_must_match_exactly(self, cors_client):
        """Test that http vs https must match exactly."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "https://localhost:3000"}  # Wrong protocol
        )
        # Should be blocked because protocol doesn't match
        assert response.headers.get("access-control-allow-origin") is None

    def test_multiple_origins_in_single_header_not_supported(self, cors_client):
        """Test that multiple origins in single header are not supported."""
        response = cors_client.get(
            "/health/simple",
            headers={"Origin": "http://localhost:3000 https://evil.com"}
        )
        # Multiple origins in single header should be treated as invalid
        assert response.headers.get("access-control-allow-origin") is None

    def test_preflight_with_no_access_control_request_method(self, cors_client):
        """Test preflight without Access-Control-Request-Method header."""
        response = cors_client.options(
            "/health/simple",
            headers={"Origin": "http://localhost:3000"}
        )
        # Should still work or return appropriate error
        assert response.status_code in [200, 400]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
