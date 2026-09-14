"""
Monitoring and Observability Utilities for Airflow DAGs

Provides metrics collection, performance tracking, and health monitoring
for production pipeline operations.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from functools import wraps
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TaskMetrics:
    """Metrics for a single task execution."""

    task_id: str
    start_time: float
    end_time: Optional[float] = None
    duration_seconds: Optional[float] = None
    status: str = "RUNNING"  # RUNNING, SUCCESS, FAILED, SKIPPED
    records_processed: int = 0
    records_failed: int = 0
    error: Optional[str] = None

    def complete(self, status: str = "SUCCESS", error: Optional[str] = None):
        """Mark task as complete."""
        self.end_time = time.time()
        self.duration_seconds = self.end_time - self.start_time
        self.status = status
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def throughput(self) -> Optional[float]:
        """Calculate records per second."""
        if self.duration_seconds and self.duration_seconds > 0:
            return self.records_processed / self.duration_seconds
        return None


class MetricsCollector:
    """Collect and aggregate metrics from DAG executions."""

    def __init__(self):
        """Initialize collector."""
        self.tasks: Dict[str, TaskMetrics] = {}
        self.dag_metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.alerts: List[Dict[str, Any]] = []

    def start_task(self, task_id: str) -> TaskMetrics:
        """Start tracking a task."""
        metrics = TaskMetrics(
            task_id=task_id,
            start_time=time.time(),
        )
        self.tasks[task_id] = metrics
        logger.debug(f"📊 Started tracking task: {task_id}")
        return metrics

    def end_task(
        self,
        task_id: str,
        status: str = "SUCCESS",
        error: Optional[str] = None,
        records_processed: int = 0,
        records_failed: int = 0,
    ) -> Optional[TaskMetrics]:
        """End task tracking."""
        if task_id not in self.tasks:
            logger.warning(f"⚠️ No metrics for task: {task_id}")
            return None

        metrics = self.tasks[task_id]
        metrics.records_processed = records_processed
        metrics.records_failed = records_failed
        metrics.complete(status, error)

        throughput = metrics.throughput()
        logger.info(
            f"✓ Task completed: {task_id} | "
            f"Status: {status} | "
            f"Duration: {metrics.duration_seconds:.1f}s | "
            f"Records: {records_processed} | "
            f"Throughput: {throughput:.0f} rec/s" if throughput else f"Duration: {metrics.duration_seconds:.1f}s"
        )

        return metrics

    def get_task_metrics(self, task_id: str) -> Optional[TaskMetrics]:
        """Get metrics for a specific task."""
        return self.tasks.get(task_id)

    def get_all_metrics(self) -> Dict[str, TaskMetrics]:
        """Get all task metrics."""
        return self.tasks.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated metrics summary."""
        if not self.tasks:
            return {}

        successful = sum(1 for m in self.tasks.values() if m.status == "SUCCESS")
        failed = sum(1 for m in self.tasks.values() if m.status == "FAILED")
        total_records = sum(m.records_processed for m in self.tasks.values())
        total_errors = sum(m.records_failed for m in self.tasks.values())
        total_duration = sum(
            m.duration_seconds for m in self.tasks.values() if m.duration_seconds
        )
        slowest_task = max(
            self.tasks.values(),
            key=lambda m: m.duration_seconds or 0,
            default=None,
        )

        return {
            "total_tasks": len(self.tasks),
            "successful_tasks": successful,
            "failed_tasks": failed,
            "success_rate": (successful / len(self.tasks) * 100) if self.tasks else 0,
            "total_records_processed": total_records,
            "total_records_failed": total_errors,
            "error_rate": (total_errors / total_records * 100) if total_records > 0 else 0,
            "total_duration_seconds": total_duration,
            "slowest_task": slowest_task.task_id if slowest_task else None,
            "slowest_task_duration": slowest_task.duration_seconds if slowest_task else None,
        }

    def check_performance_sla(
        self,
        task_id: str,
        max_duration_seconds: float,
    ) -> bool:
        """Check if task met performance SLA."""
        metrics = self.get_task_metrics(task_id)
        if not metrics or not metrics.duration_seconds:
            return False

        met_sla = metrics.duration_seconds <= max_duration_seconds
        status = "✓" if met_sla else "⚠️"
        logger.info(
            f"{status} Task {task_id} SLA: "
            f"{metrics.duration_seconds:.1f}s / {max_duration_seconds}s"
        )
        return met_sla

    def check_quality_threshold(
        self,
        task_id: str,
        max_error_rate: float,
    ) -> bool:
        """Check if task met quality threshold."""
        metrics = self.get_task_metrics(task_id)
        if not metrics:
            return False

        error_rate = (
            metrics.records_failed / metrics.records_processed
            if metrics.records_processed > 0
            else 0
        )
        threshold_met = error_rate <= max_error_rate
        status = "✓" if threshold_met else "⚠️"
        logger.info(
            f"{status} Task {task_id} Quality: "
            f"Error rate {error_rate:.2%} / {max_error_rate:.2%}"
        )
        return threshold_met

    def add_alert(self, alert: Dict[str, Any]) -> None:
        """Add an alert."""
        self.alerts.append({
            **alert,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.warning(f"🚨 Alert: {alert.get('message', 'Unknown')}")

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get all alerts."""
        return self.alerts.copy()


# Global metrics collector instance
_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def track_task_execution(
    max_duration_seconds: Optional[float] = None,
    max_error_rate: Optional[float] = None,
) -> callable:
    """
    Decorator to track task execution metrics.

    Args:
        max_duration_seconds: Alert if task exceeds this duration
        max_error_rate: Alert if error rate exceeds this threshold

    Returns:
        Decorated function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, task_id: str = None, **kwargs):
            if not task_id:
                task_id = func.__name__

            collector = get_metrics_collector()
            metrics = collector.start_task(task_id)

            try:
                result = func(*args, task_id=task_id, **kwargs)

                # Extract metrics from result if dict
                records_processed = 0
                records_failed = 0
                if isinstance(result, dict):
                    records_processed = result.get("records_processed", 0)
                    records_failed = result.get("records_failed", 0)

                collector.end_task(
                    task_id,
                    status="SUCCESS",
                    records_processed=records_processed,
                    records_failed=records_failed,
                )

                if max_duration_seconds:
                    collector.check_performance_sla(task_id, max_duration_seconds)

                if max_error_rate and records_processed > 0:
                    collector.check_quality_threshold(task_id, max_error_rate)

                return result

            except Exception as e:
                collector.end_task(
                    task_id,
                    status="FAILED",
                    error=str(e),
                )
                raise

        return wrapper

    return decorator


def get_dashboard_metrics(dag_id: str) -> Dict[str, Any]:
    """Get metrics suitable for dashboard display."""
    collector = get_metrics_collector()
    summary = collector.get_summary()

    return {
        "dag_id": dag_id,
        "timestamp": datetime.utcnow().isoformat(),
        "summary": summary,
        "tasks": [m.to_dict() for m in collector.get_all_metrics().values()],
        "alerts": collector.get_alerts(),
    }


def log_metrics_summary(dag_id: str) -> None:
    """Log a summary of all metrics."""
    metrics = get_dashboard_metrics(dag_id)
    summary = metrics["summary"]

    logger.info(f"📊 DAG {dag_id} Metrics Summary:")
    logger.info(f"   Total Tasks: {summary.get('total_tasks', 0)}")
    logger.info(
        f"   Success Rate: {summary.get('success_rate', 0):.1f}%"
    )
    logger.info(
        f"   Error Rate: {summary.get('error_rate', 0):.1f}%"
    )
    logger.info(
        f"   Total Duration: {summary.get('total_duration_seconds', 0):.1f}s"
    )
