"""
Base stage class for AIRD pipeline stages.

Provides common interface and utilities for all AIRD stages integrated into PrimeData.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

import logging
logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """Status of a pipeline stage execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""

    status: StageStatus
    stage_name: str
    product_id: UUID
    version: int
    metrics: Dict[str, Any]
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifacts: Optional[Dict[str, str]] = None  # Map of artifact names to S3/GCS paths

    def to_dict(self) -> Dict[str, Any]:
        """Convert the StageResult to a dictionary for JSON serialization.

        :return: Dictionary representation with all fields serialized to JSON-safe types.
        """
        return {
            "status": self.status.value,
            "stage_name": self.stage_name,
            "product_id": str(self.product_id),
            "version": self.version,
            "metrics": self.metrics,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "artifacts": self.artifacts,
        }


class AirdStage(ABC):
    """Base class for AIRD pipeline stages.

    All AIRD stages should inherit from this class and implement the execute method.
    Stages are designed to be stateless and can be executed multiple times.
    """

    def __init__(
        self,
        product_id: UUID,
        version: int,
        workspace_id: UUID,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the AIRD pipeline stage with product and workspace context.

        :param product_id: Unique identifier of the product being processed.
        :param version: Product version number for this pipeline run.
        :param workspace_id: Unique identifier of the workspace owning the product.
        :param config: Optional stage-specific configuration dictionary.
        """
        self.product_id = product_id
        self.version = version
        self.workspace_id = workspace_id
        self.config = config or {}
        self.logger = logger
        # Store context for logging without structlog
        self._log_context = {
            "stage": self.stage_name,
            "product_id": str(product_id),
            "version": version,
            "workspace_id": str(workspace_id),
        }
        logger.info(f"🎯 AirdStage initialized | stage={self.stage_name}, product_id={product_id}, version={version}, workspace_id={workspace_id}, config_keys={list(self.config.keys())}")

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Return the unique name of this stage (e.g., 'preprocess', 'score').

        :return: String identifier used for logging and result tracking.
        """
        pass

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute the stage logic.

        :param context: Stage execution context which may include previous stage results and shared resources.
        :return: StageResult containing execution status, metrics, and optional artifacts.
        """
        pass

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate inputs before execution.

        :param context: Stage execution context containing required keys.
        :return: True if inputs are valid, False otherwise.
        """
        logger.info(f"✔️ Validating inputs for stage {self.stage_name} | context_keys={list(context.keys())}")
        return True

    def get_required_artifacts(self) -> list[str]:
        """Return list of required artifact names from previous stages.

        :return: List of artifact name strings (e.g., ['processed_jsonl', 'metrics']).
        """
        return []

    def _create_result(
        self,
        status: StageStatus,
        metrics: Dict[str, Any],
        error: Optional[str] = None,
        artifacts: Optional[Dict[str, str]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> StageResult:
        """Create a StageResult with common fields pre-populated from this stage.

        :param status: Execution status (SUCCEEDED, FAILED, SKIPPED, etc.).
        :param metrics: Dictionary of stage metrics to include in the result.
        :param error: Error message if the stage failed.
        :param artifacts: Map of artifact names to their S3/GCS storage paths.
        :param started_at: Stage start time; defaults to current UTC time if not provided.
        :param finished_at: Stage finish time; defaults to current UTC time if not provided.
        :return: StageResult instance with all fields populated.
        """
        result = StageResult(
            status=status,
            stage_name=self.stage_name,
            product_id=self.product_id,
            version=self.version,
            metrics=metrics,
            error=error,
            artifacts=artifacts,
            started_at=started_at or datetime.utcnow(),
            finished_at=finished_at or datetime.utcnow(),
        )

        if status == StageStatus.SUCCEEDED:
            logger.info(f"✅ Stage {self.stage_name} succeeded | metrics_count={len(metrics)}, artifacts={len(artifacts or {})}")
        elif status == StageStatus.FAILED:
            logger.error(f"❌ Stage {self.stage_name} failed | error={error}, metrics_count={len(metrics)}")
        elif status == StageStatus.SKIPPED:
            logger.warning(f"⊘ Stage {self.stage_name} skipped | reason={metrics.get('reason', 'unknown')}")

        return result
