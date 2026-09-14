"""Centralized exception handling for PrimeData."""

from typing import Any, Optional, Dict, Type

from fastapi import status
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class PrimeDataException(Exception):
    """Base exception for all PrimeData errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        logger.info(f"⚠️ PrimeDataException.__init__ | exception_class={self.__class__.__name__}, message={message}")
        self.message = message or self.default_message
        self.details = details or {}
        logger.debug(f"📋 PrimeDataException init checkpoint: details={self.details}")
        super().__init__(self.message)
        logger.info(f"✅ PrimeDataException.__init__ complete | {self.__class__.__name__} initialized")


class ResourceNotFoundError(PrimeDataException):
    """Resource not found (404)."""

    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found"


class ProductNotFoundError(ResourceNotFoundError):
    """Product not found (404)."""

    default_message = "Product not found"


class DataSourceNotFoundError(ResourceNotFoundError):
    """Data source not found (404)."""

    default_message = "Data source not found"


class WorkspaceNotFoundError(ResourceNotFoundError):
    """Workspace not found (404)."""

    default_message = "Workspace not found"


class AccessDeniedError(PrimeDataException):
    """Access denied (403)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_message = "Access denied"


class ProductAccessDeniedError(AccessDeniedError):
    """Access denied to product (403)."""

    default_message = "Access denied to product"


class WorkspaceAccessDeniedError(AccessDeniedError):
    """Access denied to workspace (403)."""

    default_message = "Access denied to workspace"


class InvalidRequestError(PrimeDataException):
    """Invalid request (400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Invalid request"


class ConflictError(PrimeDataException):
    """Conflict error (409)."""

    status_code = status.HTTP_409_CONFLICT
    default_message = "Conflict"


class AuthenticationError(PrimeDataException):
    """Authentication error (401)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Authentication failed"


# Helper functions to replace repetitive patterns
def ensure_found(resource: Any, error_class: Type[PrimeDataException] = ResourceNotFoundError) -> Any:
    """Raise error if resource is None.

    :param resource: The resource to check for existence.
    :param error_class: Exception class to raise if resource is None.
    :return: The resource if it is not None.
    :raises PrimeDataException: If resource is None.
    """
    logger.info(f"⚠️ ensure_found | checking if resource is None, error_class={error_class.__name__}")
    try:
        if resource is None:
            logger.error(f"❌ ensure_found failed: resource is None, raising {error_class.__name__}")
            raise error_class()
        logger.debug(f"📋 ensure_found checkpoint: resource exists, returning")
        logger.info(f"✅ ensure_found complete | resource found")
        return resource
    except Exception as e:
        logger.error(f"❌ ensure_found error: {type(e).__name__}: {e}", exc_info=True)
        raise


def ensure_not_none(value: Any, error_class: Type[PrimeDataException] = InvalidRequestError, message: Optional[str] = None) -> Any:
    """Raise error if value is None.

    :param value: The value to check.
    :param error_class: Exception class to raise if value is None.
    :param message: Optional error message for the exception.
    :return: The value if it is not None.
    :raises PrimeDataException: If value is None.
    """
    logger.info(f"⚠️ ensure_not_none | checking if value is None, error_class={error_class.__name__}, message={message}")
    try:
        if value is None:
            logger.error(f"❌ ensure_not_none failed: value is None, raising {error_class.__name__} with message={message}")
            if message:
                raise error_class(message)
            raise error_class()
        logger.debug(f"📋 ensure_not_none checkpoint: value exists, returning")
        logger.info(f"✅ ensure_not_none complete | value is not None")
        return value
    except Exception as e:
        logger.error(f"❌ ensure_not_none error: {type(e).__name__}: {e}", exc_info=True)
        raise
