"""
Pipeline stage tracking for AIRD stages.

Tracks stage execution and stores metrics in PipelineRun model.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import logging
logger = logging.getLogger(__name__)
from primedata.db.models import PipelineRun
from sqlalchemy.orm import Session

from .base import StageResult, StageStatus


class StageTracker:
    """Tracks AIRD stage execution and updates PipelineRun metrics."""

    def __init__(self, db: Session, pipeline_run: PipelineRun):
        """Initialize tracker.

        Args:
            db: Database session
            pipeline_run: PipelineRun model instance
        """
        self.db = db
        self.pipeline_run = pipeline_run
        self.logger = logger
        # Store context for logging
        self._pipeline_run_id = str(pipeline_run.id)
        self._product_id = str(pipeline_run.product_id)
        self._version = pipeline_run.version

    def record_stage_result(self, result: StageResult) -> None:
        """Record a stage execution result.

        Args:
            result: StageResult from stage execution
        """
        logger.info(f"🎯 StageTracker.record_stage_result() entry | stage_name={result.stage_name}, status={result.status.value}")
        # Initialize metrics if not present (JSON field defaults to dict but may be None)
        if self.pipeline_run.metrics is None:
            logger.debug(f"📋 Initializing metrics dictionary")
            self.pipeline_run.metrics = {}

        # Initialize aird_stages if not present
        if "aird_stages" not in self.pipeline_run.metrics:
            logger.debug(f"📋 Initializing aird_stages dictionary")
            self.pipeline_run.metrics["aird_stages"] = {}

        # Store stage result
        logger.debug(f"📋 Storing stage result | stage_name={result.stage_name}, metrics_count={len(result.metrics)}")
        stage_data = result.to_dict()
        self.pipeline_run.metrics["aird_stages"][result.stage_name] = stage_data

        # Update aird_stages_completed list
        if "aird_stages_completed" not in self.pipeline_run.metrics:
            logger.debug(f"📋 Initializing aird_stages_completed list")
            self.pipeline_run.metrics["aird_stages_completed"] = []

        if result.status == StageStatus.SUCCEEDED:
            if result.stage_name not in self.pipeline_run.metrics["aird_stages_completed"]:
                logger.info(f"✅ Adding {result.stage_name} to completed stages")
                self.pipeline_run.metrics["aird_stages_completed"].append(result.stage_name)
        elif result.status == StageStatus.FAILED:
            # Remove from completed list if it was there
            if result.stage_name in self.pipeline_run.metrics["aird_stages_completed"]:
                logger.warning(f"⚠️ Removing {result.stage_name} from completed stages (failed)")
                self.pipeline_run.metrics["aird_stages_completed"].remove(result.stage_name)

        # Update overall pipeline run status based on stage results
        logger.debug(f"📋 Updating pipeline status...")
        self._update_pipeline_status()

        # Commit changes
        logger.debug(f"💾 Committing database changes...")
        self.db.commit()
        logger.info(f"✅ Database commit successful")

        self.logger.info(
            f"✅ Recorded stage result: {result.stage_name} = {result.status.value} (metrics: {result.metrics})"
        )

    def _update_pipeline_status(self) -> None:
        """Update pipeline run status based on stage results."""
        logger.debug(f"🎯 _update_pipeline_status() entry")
        stages = self.pipeline_run.metrics.get("aird_stages", {})

        if not stages:
            logger.debug(f"📋 No stages to evaluate")
            return

        # Check if any stage failed
        has_failed = any(stage.get("status") == StageStatus.FAILED.value for stage in stages.values())
        logger.debug(f"📋 Stage status check | has_failed={has_failed}, total_stages={len(stages)}")

        # Check if all required stages succeeded
        # For now, we'll keep the existing status logic
        # This can be enhanced in future milestones
        if has_failed and self.pipeline_run.status.value == "running":
            # Don't auto-update to failed - let Airflow handle it
            # But we can log it
            logger.warning(f"⚠️ One or more AIRD stages failed, but keeping pipeline status as running")
        else:
            logger.info(f"✅ Pipeline status stable | no failures detected")

    def get_stage_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Get result for a specific stage.

        Args:
            stage_name: Name of the stage

        Returns:
            Stage result dictionary, or None if not found
        """
        logger.debug(f"🎯 get_stage_result() entry | stage_name={stage_name}")
        stages = self.pipeline_run.metrics.get("aird_stages", {})
        result = stages.get(stage_name)
        if result:
            logger.debug(f"✅ Found stage result for {stage_name}")
        else:
            logger.warning(f"⚠️ Stage result not found for {stage_name}")
        return result

    def get_completed_stages(self) -> list[str]:
        """Get list of completed stage names.

        Returns:
            List of stage names that have succeeded
        """
        logger.debug(f"🎯 get_completed_stages() entry")
        completed = self.pipeline_run.metrics.get("aird_stages_completed", [])
        logger.info(f"✅ Retrieved completed stages | count={len(completed)}, stages={completed}")
        return completed


def track_stage_execution(
    db: Session,
    pipeline_run_id: UUID,
    result: StageResult,
) -> None:
    """Convenience function to track stage execution.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run UUID
        result: Stage execution result
    """
    logger.info(f"🎯 track_stage_execution() entry | pipeline_run_id={pipeline_run_id}, stage_name={result.stage_name}, status={result.status.value}")
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
    if not pipeline_run:
        logger.error(f"❌ Pipeline run {pipeline_run_id} not found")
        return

    logger.debug(f"📋 Found pipeline run, creating tracker...")
    tracker = StageTracker(db, pipeline_run)
    logger.info(f"✅ Recording stage result...")
    tracker.record_stage_result(result)
    logger.info(f"✅ Stage execution tracked successfully")
