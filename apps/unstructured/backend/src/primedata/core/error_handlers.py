"""Global exception handlers for FastAPI application."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from primedata.utils.log_utils import get_logger
from .exceptions import PrimeDataException

logger = get_logger(__name__)


async def primedata_exception_handler(request: Request, exc: PrimeDataException):
    """
    Handle PrimeData custom exceptions and return structured response.

    CORS SAFETY NOTE:
    This handler is registered via app.add_exception_handler() and runs within
    the FastAPI exception handling layer, which is wrapped by all middleware.
    Therefore, CORSMiddleware will inject Access-Control-Allow-Origin headers
    on this response even though we return JSONResponse directly.

    This is safe and correct — CORS headers will be present on all error responses.
    """
    # ⚠️ Log exception with full context
    logger.error(f"⚠️ PrimeDataException caught - type={exc.__class__.__name__}, status={exc.status_code}, message={exc.message}", exc_info=True)
    logger.debug(f"📋 Exception details - path={request.url.path}, method={request.method}, details={exc.details}")

    response_body = {
        "error": exc.__class__.__name__,
        "message": exc.message,
        **exc.details,
    }

    logger.info(f"❌ Returning error response - status={exc.status_code}, error_type={exc.__class__.__name__}")

    return JSONResponse(
        status_code=exc.status_code,
        content=response_body,
    )

