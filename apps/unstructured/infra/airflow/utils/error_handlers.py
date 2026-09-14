# """
# Error Handling and Recovery Utilities for Airflow DAGs
#
# Provides centralized error handling, retry strategies, and recovery mechanisms
# for production-grade data pipeline operations.
# """
#
# import logging
# import os
# from typing import Callable, Optional, Any, Dict, List
# from functools import wraps
# from datetime import timedelta
# import time
#
# logger = logging.getLogger(__name__)
#
#
# class AirflowTaskError(Exception):
#     """Base exception for Airflow task errors."""
#
#     pass
#
#
# class RetryableError(AirflowTaskError):
#     """Error that should trigger a retry."""
#
#     pass
#
#
# class NonRetryableError(AirflowTaskError):
#     """Error that should not be retried."""
#
#     pass
#
#
# class ErrorRecovery:
#     """Centralized error recovery handler."""
#
#     # Retry configuration
#     MAX_RETRIES = 3
#     BASE_DELAY_SECONDS = 5
#     MAX_DELAY_SECONDS = 300
#     EXPONENTIAL_BASE = 2
#
#     @staticmethod
#     def exponential_backoff(retry_count: int) -> int:
#         """
#         Calculate exponential backoff delay.
#
#         Args:
#             retry_count: Number of retries so far
#
#         Returns:
#             Delay in seconds
#         """
#         delay = ErrorRecovery.BASE_DELAY_SECONDS * (
#             ErrorRecovery.EXPONENTIAL_BASE ** retry_count
#         )
#         delay = min(delay, ErrorRecovery.MAX_DELAY_SECONDS)
#         jitter = time.time() % 1  # Add up to 1 second jitter
#         return int(delay + jitter)
#
#     @staticmethod
#     def get_retry_delay() -> timedelta:
#         """Get Airflow-compatible retry delay."""
#         return timedelta(minutes=5)
#
#     @staticmethod
#     def should_retry(error: Exception) -> bool:
#         """
#         Determine if an error should be retried.
#
#         Args:
#             error: Exception that occurred
#
#         Returns:
#             True if should retry, False otherwise
#         """
#         if isinstance(error, NonRetryableError):
#             return False
#
#         if isinstance(error, RetryableError):
#             return True
#
#         # Retry on network/temporary errors
#         error_str = str(error).lower()
#         retryable_patterns = [
#             "timeout",
#             "connection",
#             "refused",
#             "temporarily unavailable",
#             "too many requests",
#             "rate limit",
#             "503",
#             "502",
#             "504",
#         ]
#
#         return any(pattern in error_str for pattern in retryable_patterns)
#
#     @staticmethod
#     def log_error_context(
#         error: Exception,
#         context: str,
#         task_id: Optional[str] = None,
#     ) -> None:
#         """
#         Log error with full context.
#
#         Args:
#             error: Exception that occurred
#             context: Context description
#             task_id: Airflow task ID if available
#         """
#         task_info = f"[Task: {task_id}]" if task_id else ""
#         logger.error(
#             f"❌ Error {task_info}: {context}\n"
#             f"   Type: {type(error).__name__}\n"
#             f"   Message: {str(error)}"
#         )
#
#
# def retry_with_backoff(
#     max_retries: int = 3,
#     base_delay: int = 2,
#     max_delay: int = 60,
# ) -> Callable:
#     """
#     Decorator for functions that should retry on failure with exponential backoff.
#
#     Args:
#         max_retries: Maximum number of retries
#         base_delay: Initial delay in seconds
#         max_delay: Maximum delay in seconds
#
#     Returns:
#         Decorated function that retries on exception
#     """
#
#     def decorator(func: Callable) -> Callable:
#         @wraps(func)
#         def wrapper(*args, **kwargs) -> Any:
#             last_error = None
#             for attempt in range(max_retries + 1):
#                 try:
#                     logger.debug(
#                         f"🔄 Executing {func.__name__} (attempt {attempt + 1}/{max_retries + 1})"
#                     )
#                     return func(*args, **kwargs)
#
#                 except Exception as e:
#                     last_error = e
#
#                     if not ErrorRecovery.should_retry(e):
#                         logger.error(
#                             f"❌ Non-retryable error in {func.__name__}: {e}"
#                         )
#                         raise
#
#                     if attempt < max_retries:
#                         delay = min(
#                             base_delay * (2 ** attempt), max_delay
#                         ) + time.time() % 1
#                         logger.warning(
#                             f"⚠️ {func.__name__} failed (attempt {attempt + 1}), "
#                             f"retrying in {delay:.0f}s: {e}"
#                         )
#                         time.sleep(delay)
#                     else:
#                         logger.error(
#                             f"❌ {func.__name__} failed after {max_retries + 1} attempts"
#                         )
#
#             raise last_error
#
#         return wrapper
#
#     return decorator
#
#
# def handle_task_error(
#     task_id: str,
#     error: Exception,
#     context: Optional[Dict[str, Any]] = None,
# ) -> None:
#     """
#     Handle task error with logging and notification.
#
#     Args:
#         task_id: Airflow task ID
#         error: Exception that occurred
#         context: Airflow context dict
#     """
#     ErrorRecovery.log_error_context(error, f"Task failed", task_id)
#
#     # Could integrate with notification service here
#     # e.g., Slack, email, PagerDuty, etc.
#
#     if context:
#         execution_date = context.get("execution_date")
#         dag_id = context.get("dag").dag_id if context.get("dag") else None
#         logger.error(
#             f"📋 DAG: {dag_id}, Execution: {execution_date}, Task: {task_id}"
#         )
#
#
# class DeadLetterQueue:
#     """Simple in-memory dead-letter queue for failed records."""
#
#     def __init__(self, max_size: int = 10000):
#         """Initialize DLQ."""
#         self.queue: List[Dict[str, Any]] = []
#         self.max_size = max_size
#
#     def add(
#         self,
#         record: Any,
#         error: Exception,
#         task_id: str,
#         metadata: Optional[Dict[str, Any]] = None,
#     ) -> None:
#         """
#         Add failed record to DLQ.
#
#         Args:
#             record: The record that failed
#             error: Exception that occurred
#             task_id: Airflow task ID
#             metadata: Additional metadata
#         """
#         if len(self.queue) >= self.max_size:
#             logger.warning(f"⚠️ DLQ at capacity ({self.max_size}), dropping oldest")
#             self.queue.pop(0)
#
#         dlq_entry = {
#             "record": record,
#             "error": str(error),
#             "error_type": type(error).__name__,
#             "task_id": task_id,
#             "timestamp": time.time(),
#             "metadata": metadata or {},
#         }
#
#         self.queue.append(dlq_entry)
#         logger.info(
#             f"📨 Added to DLQ: {task_id} ({len(self.queue)}/{self.max_size})"
#         )
#
#     def get_failed_records(self) -> List[Dict[str, Any]]:
#         """Get all failed records."""
#         return self.queue.copy()
#
#     def clear(self) -> None:
#         """Clear the DLQ."""
#         size = len(self.queue)
#         self.queue.clear()
#         logger.info(f"🗑️  DLQ cleared ({size} records)")
#
#
# # Global DLQ instance
# _global_dlq: Optional[DeadLetterQueue] = None
#
#
# def get_dlq() -> DeadLetterQueue:
#     """Get or create global DLQ instance."""
#     global _global_dlq
#     if _global_dlq is None:
#         _global_dlq = DeadLetterQueue()
#     return _global_dlq
#
#
# def record_failure(
#     record: Any,
#     error: Exception,
#     task_id: str,
#     metadata: Optional[Dict[str, Any]] = None,
# ) -> None:
#     """
#     Record a failed item to the dead-letter queue.
#
#     Args:
#         record: Failed record
#         error: Exception that occurred
#         task_id: Airflow task ID
#         metadata: Additional context
#     """
#     dlq = get_dlq()
#     dlq.add(record, error, task_id, metadata)
