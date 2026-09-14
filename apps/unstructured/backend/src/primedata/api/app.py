"""
FastAPI application for PrimeData API.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from primedata.api.auth import router as auth_router
from primedata.api.acl import router as acl_router
from primedata.api.ai_readiness import router as ai_readiness_router
from primedata.api.analytics import router as analytics_router
from primedata.api.artifacts import router as artifacts_router
from primedata.api.audit import router as audit_router
from primedata.api.billing import router as billing_router
from primedata.api.chunk_quality import router as chunk_quality_router
from primedata.api.chunks import router as chunks_router
from primedata.api.config import router as config_router
from primedata.api.contact import router as contact_router
from primedata.api.data_quality import router as data_quality_router
from primedata.api.data_quality_enterprise import router as data_quality_enterprise_router
from primedata.api.datasources import router as datasources_router
from primedata.api.embedding_models import router as embedding_models_router
from primedata.api.exports import router as exports_router
from primedata.api.governance import router as governance_router
from primedata.api.lineage import router as lineage_router
from primedata.api.pipeline import router as pipeline_router
from primedata.api.playbooks import router as playbooks_router  # M1
from primedata.api.playground import router as playground_router
from primedata.api.products import router as products_router
from primedata.api.quality_improvement import router as quality_improvement_router
from primedata.api.rag_evaluation import router as rag_evaluation_router
from primedata.api.settings import router as settings_router
from primedata.api.team import router as team_router
from primedata.api.versions import router as versions_router
from primedata.core.jwt_keys import get_public_jwks
from primedata.core.settings import get_settings
from primedata.core.exceptions import PrimeDataException
from primedata.core.error_handlers import primedata_exception_handler
from primedata.db.database import engine
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from primedata.utils.logger import configure_logging, get_logger
# Get settings
settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Startup: Ensure S3 parent folder (S3_METADATA_PATH) exists, create if needed.
    Shutdown: Cleanup (none currently needed).
    """
    # Startup events
    logger.info("🚀 Starting PrimeData API...")

    # Ensure S3 storage folder structure is ready
    try:
        from primedata.storage.storage_client import storage_client
        storage_client.ensure_metadata_path_exists()
        logger.info("✅ S3 storage initialization complete")
    except Exception as e:
        logger.error(f"❌ Failed to initialize S3 storage: {e}", exc_info=True)
        raise

    yield

    # Shutdown events
    logger.info("🛑 Shutting down PrimeData API...")


# Create FastAPI app
app = FastAPI(
    title="PrimeData API",
    description="AI-ready data from any source",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,  # Disable automatic trailing slash redirects to prevent 307 errors
    lifespan=lifespan,
)


# =============================================================================
# MIDDLEWARE STACK CONFIGURATION
# =============================================================================
#
# IMPORTANT: Middleware execution order in Starlette/FastAPI:
# - add_middleware() calls are applied in REVERSE order
# - Last add_middleware() call = OUTERMOST middleware (executes first on request, last on response)
# - This ensures CORSMiddleware wraps all responses and adds CORS headers
#
# Execution order (request → response):
# 1. CORSMiddleware (outermost) - adds Access-Control-Allow-Origin header
# 2. RequestLoggingMiddleware (inner) - logs CORS-related request/response info
# 3. Route handlers + exception handlers (innermost)
#
# The CORSMiddleware MUST be outermost to guarantee that ALL responses receive
# Access-Control-Allow-Origin headers, including error responses (401, 403, 404, 5xx)
# =============================================================================

# Create RequestLoggingMiddleware class to ensure proper middleware ordering
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log CORS requests and responses without interfering with CORS headers.

    Uses BaseHTTPMiddleware to ensure proper execution within middleware stack.
    CORS headers are added by CORSMiddleware which wraps this middleware.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and log CORS information."""
        origin = request.headers.get("origin")
        method = request.method
        path = request.url.path

        # Check if origin is allowed (check against settings CORS origins)
        allowed_origins = settings.CORS_ORIGINS
        if isinstance(allowed_origins, str):
            allowed_origins = [allowed_origins]

        is_origin_allowed = origin in allowed_origins if origin else False

        # Determine the CORS reason
        if not origin:
            cors_reason = "No origin header (same-origin or local)"
        elif is_origin_allowed:
            cors_reason = "✅ Origin allowed"
        else:
            cors_reason = f"❌ CORS BLOCKED: Origin '{origin}' not in allowed list"

        # Log preflight requests with details
        if method == "OPTIONS":
            logger.warning(
                f"CORS Preflight: {cors_reason}",
                extra={
                    "origin": origin,
                    "method": method,
                    "path": path,
                    "request_method": request.headers.get("access-control-request-method"),
                },
            )
        elif origin:
            # Log cross-origin requests
            logger.info(
                f"Cross-origin request: {cors_reason}",
                extra={
                    "origin": origin,
                    "method": method,
                    "path": path,
                },
            )

        # Call next middleware/handler
        response = await call_next(request)

        # Log response with CORS headers info (after CORSMiddleware has added them)
        has_cors_origin = bool(response.headers.get("access-control-allow-origin"))
        cors_origin_value = response.headers.get("access-control-allow-origin", "MISSING")

        if origin and response.status_code >= 400:
            log_level = "error" if not has_cors_origin else "warning"
            logger_func = logger.error if log_level == "error" else logger.warning
            logger_func(
                f"Error response from cross-origin request",
                extra={
                    "origin": origin,
                    "path": path,
                    "status": response.status_code,
                    "has_cors_header": has_cors_origin,
                    "cors_origin_value": cors_origin_value,
                },
            )
        elif origin and method == "OPTIONS":
            # Log successful preflight responses
            logger.info(
                f"CORS Preflight Response",
                extra={
                    "origin": origin,
                    "status": response.status_code,
                    "has_cors_header": has_cors_origin,
                    "cors_origin_value": cors_origin_value,
                    "cors_methods": response.headers.get("access-control-allow-methods", "MISSING"),
                    "cors_headers": response.headers.get("access-control-allow-headers", "MISSING"),
                },
            )

        return response


# Load CORS origins from settings (single source of truth)
# The settings module loads from environment variable or .env file
cors_origins = settings.CORS_ORIGINS
if isinstance(cors_origins, str):
    # Handle case where CORS_ORIGINS is a single string
    cors_origins = [cors_origins]

# Log CORS configuration for debugging
logger.info(f"CORS origins configured: {cors_origins}")

# Add CORSMiddleware FIRST (before any other middleware)
# It must be outermost to wrap all responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,  # Use configured origins from settings
    allow_credentials=True,       # Allow cookies and Authorization headers
    allow_methods=["*"],          # Allow all HTTP methods including OPTIONS
    allow_headers=["*"],          # Allow all request headers
    expose_headers=["*"],         # Allow frontend to access all response headers
    max_age=600               # Cache preflight responses for 10 minutes
)

# NOTE: RequestLoggingMiddleware temporarily disabled due to CORS header interference
# BaseHTTPMiddleware can sometimes strip headers when used with CORSMiddleware
# If you need request logging, implement as pure ASGI middleware instead
# app.add_middleware(RequestLoggingMiddleware)

# Register exception handlers for centralized error handling
app.add_exception_handler(PrimeDataException, primedata_exception_handler)

# Include routers
app.include_router(auth_router)
app.include_router(acl_router)  # ACL management
app.include_router(products_router)
app.include_router(datasources_router)
app.include_router(artifacts_router)
app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(pipeline_router)
app.include_router(chunks_router)
app.include_router(chunk_quality_router)  # Chunk quality analysis
app.include_router(playground_router)
app.include_router(ai_readiness_router)
app.include_router(embedding_models_router)
app.include_router(data_quality_router, prefix="/api/v1/data-quality", tags=["data-quality"])
app.include_router(data_quality_enterprise_router)  # Enterprise-grade DQ rules
app.include_router(quality_improvement_router)  # Quality improvement recommendations
app.include_router(exports_router, prefix="/api/v1/exports", tags=["exports"])
app.include_router(billing_router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(playbooks_router)  # M1
app.include_router(settings_router)
app.include_router(team_router)  # Team management
app.include_router(versions_router, prefix="/api/v1/versions", tags=["versions"])
app.include_router(governance_router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(lineage_router, prefix="/api/v1/lineage", tags=["lineage"])
app.include_router(config_router, prefix="/api/v1/config", tags=["config"])
app.include_router(rag_evaluation_router)  # RAG Evaluation (AI-Ready metrics)
app.include_router(contact_router)  # Contact form (public endpoint)


@app.post("/api/v1/test/cortex")
async def test_cortex_call():
    """Test endpoint to verify Cortex API connectivity."""
    from primedata.services.cortex_client import call_cortex_model

    result = call_cortex_model(prompt="Hello, Test", model_context="")
    return {"status": "ok" if result else "failed", "response": result}


async def check_database() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Database connection failed: {str(e)}"}


async def check_elasticsearch() -> Dict[str, Any]:
    """Check Elasticsearch connectivity."""
    try:
        import os

        import httpx

        # Use Docker service name or localhost for local dev
        elasticsearch_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{elasticsearch_url}/_cluster/health", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "message": "Elasticsearch is accessible"}
            else:
                return {"status": "unhealthy", "message": f"Elasticsearch returned status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Elasticsearch connection failed: {str(e)}"}


async def check_storage() -> Dict[str, Any]:
    """Check S3 storage connectivity."""
    try:
        import os
        import httpx

        s3_endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
        s3_health_url = f"{s3_endpoint}/health"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(s3_health_url, timeout=5.0)
                if response.status_code == 200:
                    return {"status": "healthy", "message": "S3 storage is accessible"}
                else:
                    return {"status": "unhealthy", "message": f"S3 storage returned status {response.status_code}"}
            except Exception as e:
                # Fallback check by trying to access S3 client directly
                from primedata.storage.storage_client import storage_client
                if hasattr(storage_client, "s3_client") and storage_client.s3_client:
                    return {"status": "healthy", "message": "S3 storage client is initialized"}
                raise
    except Exception as e:
        return {"status": "unhealthy", "message": f"Storage connection failed: {str(e)}"}



async def check_airflow() -> Dict[str, Any]:
    """Check Airflow connectivity."""
    try:
        import os

        import httpx

        # Use Docker service name or localhost for local dev
        airflow_host = os.getenv("AIRFLOW_HOST", "airflow-webserver")
        airflow_port = os.getenv("AIRFLOW_PORT", "8080")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{airflow_host}:{airflow_port}/health", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "message": "Airflow is accessible"}
            else:
                return {"status": "unhealthy", "message": f"Airflow returned status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Airflow connection failed: {str(e)}"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    # Check all services concurrently
    services = await asyncio.gather(check_database(), check_elasticsearch(), check_storage(), check_airflow(), return_exceptions=True)

    # Process results
    service_results = {
        "database": (
            services[0] if not isinstance(services[0], Exception) else {"status": "unhealthy", "message": str(services[0])}
        ),
        "elasticsearch": (
            services[1] if not isinstance(services[1], Exception) else {"status": "unhealthy", "message": str(services[1])}
        ),
        "storage": (
            services[2] if not isinstance(services[2], Exception) else {"status": "unhealthy", "message": str(services[2])}
        ),
        "airflow": (
            services[3] if not isinstance(services[3], Exception) else {"status": "unhealthy", "message": str(services[3])}
        ),
    }

    # Determine overall status
    all_healthy = all(service["status"] == "healthy" for service in service_results.values())
    overall_status = "healthy" if all_healthy else "degraded"

    return {
        "status": overall_status,
        "service": "PrimeData",
        "version": "0.1.0",
        "services": service_results,
        "timestamp": asyncio.get_event_loop().time(),
    }


@app.get("/health/simple")
async def simple_health_check():
    """Simple health check endpoint (app only)."""
    return {"status": "ok", "service": "AIRDops", "version": "0.1.0"}


@app.get("/.well-known/jwks.json")
async def get_jwks():
    """JWKS endpoint for JWT key discovery."""
    return get_public_jwks()


# Handle all OPTIONS requests for preflight CORS
@app.options("/{path_name:path}", include_in_schema=False)
async def preflight_handler(path_name: str):
    """
    Handle CORS preflight requests.
    This endpoint responds to all OPTIONS requests.
    FastAPI's CORSMiddleware will automatically add the necessary CORS headers.
    """
    return {"message": "ok"}


@app.get("/debug/cors")
async def debug_cors(request: Request):
    """Debug endpoint to check CORS configuration and headers."""
    origin = request.headers.get("origin", "No origin header")
    return {
        "message": "CORS Debug Info",
        "request_origin": origin,
        "configured_origins": cors_origins,
        "origin_allowed": origin in cors_origins if origin != "No origin header" else False,
        "request_method": request.method,
        "request_headers": dict(request.headers),
    }


@app.get("/test/cors-headers")
async def test_cors_headers(request: Request):
    """
    Test endpoint to verify CORS headers are being sent.

    This endpoint should return with CORS headers added by the middleware:
    - Access-Control-Allow-Origin
    - Access-Control-Allow-Methods
    - Access-Control-Allow-Headers
    - Access-Control-Allow-Credentials

    Test with:
    curl -H "Origin: https://primedata-frontend.apps-internal.lrl.lilly.com" \\
         -v http://localhost:8000/test/cors-headers
    """
    return {
        "status": "ok",
        "message": "Check response headers for CORS headers",
        "instructions": "If Access-Control-Allow-Origin header is present, CORS is working",
        "expected_headers": {
            "Access-Control-Allow-Origin": "https://primedata-frontend.apps-internal.lrl.lilly.com",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "content-type, authorization",
            "Access-Control-Allow-Credentials": "true",
        }
    }


@app.options("/test/cors-headers", include_in_schema=False)
async def test_cors_preflight():
    """Test preflight endpoint for CORS verification."""
    return {}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
