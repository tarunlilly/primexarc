"""
Audit Middleware for tracking user actions across API endpoints.

Captures user actions, changes, and metadata for compliance and auditing purposes.
"""

import json
from typing import Optional, Dict, Any, Callable, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from primedata.db.models import UserAuditLog
from primedata.db.database import get_db
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware for auditing user API actions.

    Logs all API requests/responses to capture:
    - User ID and workspace
    - Action (POST, PUT, DELETE, GET)
    - Resource type and ID
    - Changes (before/after)
    - Status (success/failure)
    - Metadata (IP, user agent, etc.)
    """

    # Endpoints to skip audit logging (e.g., health checks, docs)
    SKIP_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/docs",
    }

    # Actions that don't require audit logging (read-only)
    SKIP_METHODS = {"OPTIONS", "HEAD"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log audit trail.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response
        """
        # Skip audit for certain paths and methods
        if self._should_skip(request):
            return await call_next(request)

        try:
            # Capture request details
            request_data = await self._capture_request(request)

            # Call next middleware/handler
            response = await call_next(request)

            # Log audit trail
            await self._log_audit(request, response, request_data)

            return response

        except Exception as e:
            logger.error(f"Error in audit middleware: {e}", exc_info=True)
            # Don't fail the request on audit error
            return await call_next(request)

    def _should_skip(self, request: Request) -> bool:
        """Check if request should skip audit logging."""
        # Skip docs and health endpoints
        if request.url.path in self.SKIP_PATHS:
            return True

        # Skip read-only methods (GET is usually fine, but can be configured)
        if request.method in self.SKIP_METHODS:
            return True

        return False

    async def _capture_request(self, request: Request) -> Dict[str, Any]:
        """
        Capture request details for audit logging.

        Args:
            request: HTTP request

        Returns:
            Dictionary with request details
        """
        # Try to get user from request state or dependencies
        user_id = getattr(request.state, "user_id", None)
        workspace_id = getattr(request.state, "workspace_id", None)

        # Try to extract from path
        if not workspace_id and "workspace" in request.url.path:
            parts = request.url.path.split("/")
            if "workspaces" in parts:
                idx = parts.index("workspaces")
                if idx + 1 < len(parts):
                    workspace_id = parts[idx + 1]

        # Capture body if present (for POST/PUT requests)
        body = None
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                body = await request.body()
                if body:
                    body = json.loads(body)
            except Exception as e:
                logger.debug(f"Could not capture request body: {e}")

        return {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "body": body,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
        }

    async def _log_audit(
        self,
        request: Request,
        response: Response,
        request_data: Dict[str, Any],
    ) -> None:
        """
        Log audit trail to database.

        Args:
            request: HTTP request
            response: HTTP response
            request_data: Captured request details
        """
        try:
            # Extract audit details
            user_id = request_data.get("user_id")
            workspace_id = request_data.get("workspace_id")
            method = request_data.get("method")
            path = request_data.get("path")
            headers = request_data.get("headers", {})
            body = request_data.get("body")

            # Determine action from HTTP method
            action = self._get_action_from_method(method)

            # Extract resource type and ID from path
            resource_type, resource_id = self._extract_resource_info(path, body)

            # Determine status
            status = "success" if 200 <= response.status_code < 300 else "failure"
            error_message = None if status == "success" else f"HTTP {response.status_code}"

            # Get IP and user agent
            ip_address = request.client.host if request.client else None
            user_agent = headers.get("user-agent", "")[:500]

            # Create metadata
            metadata = {
                "http_method": method,
                "http_status": response.status_code,
                "path": path,
                "query_params": request_data.get("query_params", {}),
            }

            # Get database session
            db_gen = get_db()
            db = next(db_gen)

            try:
                # Create audit log entry
                audit_log = UserAuditLog(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    changes={"body": body} if body else None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status=status,
                    error_message=error_message,
                    audit_metadata=metadata,
                )

                db.add(audit_log)
                db.commit()

                logger.debug(
                    f"Audit log created | user={user_id}, action={action}, "
                    f"resource={resource_type}/{resource_id}, status={status}"
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error logging audit trail: {e}", exc_info=True)
            # Don't raise - audit logging should not fail the request

    @staticmethod
    def _get_action_from_method(method: str) -> str:
        """Map HTTP method to audit action."""
        mapping = {
            "GET": "VIEW",
            "POST": "CREATE",
            "PUT": "UPDATE",
            "PATCH": "UPDATE",
            "DELETE": "DELETE",
        }
        return mapping.get(method, method.upper())

    @staticmethod
    def _extract_resource_info(path: str, body: Optional[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Extract resource type and ID from request path and body.

        Args:
            path: Request path
            body: Request body

        Returns:
            Tuple of (resource_type, resource_id)
        """
        # Default values
        resource_type = "UNKNOWN"
        resource_id = ""

        # Try to extract from path pattern: /api/v1/{resource_type}/{resource_id}/...
        parts = path.split("/")

        # Filter out empty parts and api version
        filtered_parts = [p for p in parts if p and p not in {"api", "v1"}]

        if len(filtered_parts) >= 1:
            # If we have at least one part, use it as resource type
            resource_type = filtered_parts[0].upper()
            # If we have a second part, use it as resource_id
            if len(filtered_parts) >= 2:
                resource_id = filtered_parts[1]

        # Override with body ID if present
        if body and isinstance(body, dict):
            if "id" in body:
                resource_id = str(body["id"])
            elif "product_id" in body:
                resource_type = "PRODUCT"
                resource_id = str(body["product_id"])

        return resource_type, resource_id[:255]  # Limit to DB column size
