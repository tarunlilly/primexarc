"""
Pipeline Versioning System

Provides automatic version calculation and tracking for pipeline runs based on:
- Input data (file checksums/ETags)
- Configuration (playbook content, chunking config)
- Stage code versions

Version Logic:
- If config + data unchanged → Rerun (same version, rerun_count++)
- If config or data changed → New version (semantic version increment)

Usage:
    version_manager = PipelineVersionManager(db, product_id)
    version_info = version_manager.calculate_pipeline_version(
        playbook_id="HEALTHCARE",
        playbook_content=playbook_yaml_content,
        chunking_config={"strategy": "sentence", "max_tokens": 800},
        stage_code_versions={"preprocess": "1.1.0", "scoring": "1.0.5", ...},
        raw_files=[...]
    )
    # Returns: {"version": "v1.2.3", "is_rerun": False, "rerun_count": 0, ...}
"""

import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session

from primedata.db.models import PipelineRun


class PipelineVersionManager:
    """Calculate and manage pipeline versions based on configuration and data."""

    def __init__(self, db: Session, product_id: UUID):
        """
        Initialize version manager for a specific product.

        Args:
            db: Database session
            product_id: UUID of the product
        """
        self.db = db
        self.product_id = product_id

    def calculate_config_hash(
        self,
        playbook_id: str,
        playbook_content: str,
        chunking_config: Dict[str, Any],
        stage_code_versions: Dict[str, str],
        data_source_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Calculate hash of all pipeline configuration.

        This hash represents the "recipe" for processing data. If any configuration
        changes (playbook normalizers, chunking strategy, stage code, data source),
        the hash changes.

        Returns:
            16-character hex hash (e.g., "abc123def4567890")
        """
        config_dict = {
            "playbook_id": playbook_id,
            "playbook_content": playbook_content,
            "chunking_config": chunking_config,
            "stage_code_versions": stage_code_versions,
            "data_source_config": data_source_config or {}
        }

        # Sort keys for deterministic hashing
        config_json = json.dumps(config_dict, sort_keys=True)
        full_hash = hashlib.sha256(config_json.encode()).hexdigest()

        # Return first 16 chars for brevity (still 64 bits = 2^64 combinations)
        return full_hash[:16]

    def calculate_data_hash(self, raw_files: List[Dict[str, Any]]) -> str:
        """
        Calculate hash of all input data files.

        Uses file ETags or checksums to detect if input data changed.
        If any file is added, removed, or modified, the hash changes.

        Returns:
            16-character hex hash
        """
        file_hashes = []

        for rf in raw_files:
            # Prefer ETag (from S3/GCS), fallback to checksum, fallback to storage_key
            file_identifier = rf.get("etag") or rf.get("checksum") or rf.get("storage_key")

            if not file_identifier:
                # If no identifier available, use filename + size as fallback
                file_identifier = f"{rf.get('filename', 'unknown')}_{rf.get('file_size', 0)}"

            file_hashes.append(str(file_identifier))

        # Sort to make hash deterministic regardless of file order
        combined = "|".join(sorted(file_hashes))
        full_hash = hashlib.sha256(combined.encode()).hexdigest()

        return full_hash[:16]

    def calculate_pipeline_version(
        self,
        playbook_id: str,
        playbook_content: str,
        chunking_config: Dict[str, Any],
        stage_code_versions: Dict[str, str],
        raw_files: List[Dict[str, Any]],
        data_source_config: Optional[Dict[str, Any]] = None,
        previous_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Determine pipeline version for current run.

        Logic:
        1. Calculate config_hash (playbook + chunking + stage versions + data source)
        2. Calculate data_hash (input file checksums)
        3. Check if this combination exists in previous runs:
           - If YES → Rerun (same version, increment rerun_count)
           - If NO → New version (increment semantic version)

        Returns:
            Dict with version, config_hash, data_hash, combined_hash, is_rerun,
            rerun_count, parent_run_id, change_summary
        """
        # Calculate hashes
        config_hash = self.calculate_config_hash(
            playbook_id=playbook_id,
            playbook_content=playbook_content,
            chunking_config=chunking_config,
            stage_code_versions=stage_code_versions,
            data_source_config=data_source_config
        )

        data_hash = self.calculate_data_hash(raw_files)
        combined_hash = f"{config_hash}_{data_hash}"

        # Check for previous runs with same config + data
        previous_run = self.db.query(PipelineRun).filter(
            PipelineRun.product_id == self.product_id,
            PipelineRun.combined_hash == combined_hash
        ).order_by(PipelineRun.created_at.desc()).first()

        if previous_run:
            # RERUN: Same config + data, increment rerun count
            return {
                "version": previous_run.pipeline_version,
                "config_hash": config_hash,
                "data_hash": data_hash,
                "combined_hash": combined_hash,
                "is_rerun": True,
                "rerun_count": previous_run.rerun_count + 1,
                "parent_run_id": previous_run.id,
                "change_summary": {
                    "config_changed": False,
                    "data_changed": False,
                    "data_source_changed": False,
                    "reason": "rerun",
                    "changes": []
                }
            }

        # NEW VERSION: Config or data changed
        latest_run = self.db.query(PipelineRun).filter(
            PipelineRun.product_id == self.product_id
        ).order_by(PipelineRun.created_at.desc()).first()

        change_summary = self._analyze_detailed_changes(
            latest_run=latest_run,
            new_config_hash=config_hash,
            new_data_hash=data_hash,
            new_playbook_id=playbook_id,
            new_playbook_content=playbook_content,
            new_chunking_config=chunking_config,
            new_stage_versions=stage_code_versions,
            new_data_source_config=data_source_config,
            new_raw_files=raw_files,
            previous_config=previous_config
        )

        # Increment version
        if latest_run and latest_run.pipeline_version:
            new_version = self._increment_version(
                current_version=latest_run.pipeline_version,
                change_summary=change_summary
            )
        else:
            new_version = "v1.0.0"

        return {
            "version": new_version,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "combined_hash": combined_hash,
            "is_rerun": False,
            "rerun_count": 0,
            "parent_run_id": None,
            "change_summary": change_summary
        }

    def _analyze_detailed_changes(
        self,
        latest_run: Optional[PipelineRun],
        new_config_hash: str,
        new_data_hash: str,
        new_playbook_id: str,
        new_playbook_content: str,
        new_chunking_config: Dict[str, Any],
        new_stage_versions: Dict[str, str],
        new_data_source_config: Optional[Dict[str, Any]],
        new_raw_files: List[Dict[str, Any]],
        previous_config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze detailed changes compared to latest run."""
        if not latest_run:
            return {
                "config_changed": False,
                "data_changed": False,
                "data_source_changed": False,
                "reason": "initial_run",
                "changes": [{"type": "initial_run", "description": "First pipeline run for this product"}]
            }

        config_changed = latest_run.config_hash != new_config_hash
        data_changed = latest_run.data_hash != new_data_hash

        changes = []

        # Detailed config change detection
        if config_changed and previous_config:
            # Compare playbook
            prev_playbook_id = previous_config.get("playbook_id")
            if prev_playbook_id != new_playbook_id:
                changes.append({
                    "type": "playbook_changed",
                    "description": f"Playbook changed from '{prev_playbook_id}' to '{new_playbook_id}'",
                    "old_value": prev_playbook_id,
                    "new_value": new_playbook_id
                })
            elif previous_config.get("playbook_content") != new_playbook_content:
                changes.append({
                    "type": "playbook_content_changed",
                    "description": "Playbook configuration updated (normalizers, patterns, or settings changed)",
                    "playbook_id": new_playbook_id
                })

            # Compare chunking config
            prev_chunking = previous_config.get("chunking_config", {})
            chunking_diffs = self._compare_dicts(prev_chunking, new_chunking_config)
            if chunking_diffs:
                changes.append({
                    "type": "chunking_config_changed",
                    "description": "Chunking configuration updated",
                    "changes": chunking_diffs
                })

            # Compare stage versions
            prev_stage_versions = previous_config.get("stage_code_versions", {})
            stage_diffs = self._compare_dicts(prev_stage_versions, new_stage_versions)
            if stage_diffs:
                changes.append({
                    "type": "stage_versions_changed",
                    "description": "Stage code versions updated",
                    "changes": stage_diffs
                })

            # Compare data source config
            prev_data_source = previous_config.get("data_source_config", {})
            data_source_diffs = self._compare_dicts(prev_data_source, new_data_source_config or {})
            if data_source_diffs:
                changes.append({
                    "type": "data_source_config_changed",
                    "description": "Data source configuration updated",
                    "changes": data_source_diffs
                })

        # Detailed data change detection
        if data_changed:
            prev_file_count = 0
            new_file_count = len(new_raw_files)

            if latest_run.metrics:
                prev_file_count = latest_run.metrics.get("raw_files_count", 0)

            if prev_file_count != new_file_count:
                changes.append({
                    "type": "file_count_changed",
                    "description": f"Number of input files changed from {prev_file_count} to {new_file_count}",
                    "old_value": prev_file_count,
                    "new_value": new_file_count
                })
            else:
                changes.append({
                    "type": "file_content_changed",
                    "description": "Input file content changed (files modified, added, or removed)",
                    "file_count": new_file_count
                })

        # Determine overall reason
        data_source_changed = any(c["type"] == "data_source_config_changed" for c in changes)

        if config_changed and data_changed:
            reason = "config_and_data_changed"
        elif config_changed:
            reason = "config_changed_including_data_source" if data_source_changed else "config_changed"
        elif data_changed:
            reason = "data_changed"
        else:
            reason = "unknown"

        return {
            "config_changed": config_changed,
            "data_changed": data_changed,
            "data_source_changed": data_source_changed,
            "reason": reason,
            "changes": changes
        }

    def _compare_dicts(self, old_dict: Dict[str, Any], new_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compare two dictionaries and return list of changes."""
        diffs = []
        all_keys = set(old_dict.keys()) | set(new_dict.keys())

        for key in all_keys:
            old_val = old_dict.get(key)
            new_val = new_dict.get(key)

            if old_val != new_val:
                if key not in old_dict:
                    diffs.append({"field": key, "old_value": None, "new_value": new_val, "change_type": "added"})
                elif key not in new_dict:
                    diffs.append({"field": key, "old_value": old_val, "new_value": None, "change_type": "removed"})
                else:
                    diffs.append({"field": key, "old_value": old_val, "new_value": new_val, "change_type": "modified"})

        return diffs

    def _increment_version(
        self,
        current_version: str,
        change_summary: Dict[str, Any]
    ) -> str:
        """
        Increment semantic version based on what changed.

        Version scheme: vMAJOR.MINOR.PATCH
        - MAJOR: Breaking changes (reserved)
        - MINOR: Config changes (playbook, chunking, stage code)
        - PATCH: Data changes (input files)
        """
        version_str = current_version.lstrip("v")
        parts = version_str.split(".")

        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2])
        except (IndexError, ValueError):
            return "v1.0.0"

        if change_summary.get("config_changed"):
            minor += 1
            patch = 0
        else:
            patch += 1

        return f"v{major}.{minor}.{patch}"

    def get_version_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get version history for this product."""
        runs = self.db.query(PipelineRun).filter(
            PipelineRun.product_id == self.product_id
        ).order_by(PipelineRun.created_at.desc()).limit(limit).all()

        history = []
        for run in runs:
            history.append({
                "version": run.version,
                "pipeline_run_id": str(run.id),
                "is_rerun": run.is_rerun,
                "rerun_count": run.rerun_count,
                "config_hash": run.config_hash,
                "data_hash": run.data_hash,
                "status": run.status,
                "created_at": run.created_at.isoformat() if run.created_at else None
            })

        return history


def get_stage_code_versions() -> Dict[str, str]:
    """
    Get current code versions for all pipeline stages.

    Returns:
        Dict of stage_name -> version
    """
    return {
        "preprocess": "1.1.0",
        "scoring": "1.0.5",
        "fingerprint": "1.0.2",
        "policy": "1.0.0",
        "validation": "1.0.1",
        "indexing": "1.2.0"
    }


def format_version_metadata(
    pipeline_version: str,
    stage_name: str,
    stage_version: str,
    config_hash: str,
    is_rerun: bool,
    rerun_count: int,
    playbook_id: str,
    playbook_content: str,
    chunking_config: Dict[str, Any],
    change_summary: Optional[Dict[str, Any]] = None,
    data_source_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format version metadata for artifact JSON.

    This metadata is stored in PipelineArtifact.artifact_metadata field.
    """
    playbook_hash = hashlib.sha256(playbook_content.encode()).hexdigest()[:16]
    chunking_hash = hashlib.sha256(
        json.dumps(chunking_config, sort_keys=True).encode()
    ).hexdigest()[:16]

    data_source_hash = None
    if data_source_config:
        data_source_hash = hashlib.sha256(
            json.dumps(data_source_config, sort_keys=True).encode()
        ).hexdigest()[:16]

    metadata = {
        "pipeline_version": pipeline_version,
        "stage_version": f"{pipeline_version}-{stage_name}-v{stage_version}",
        "config_hash": config_hash,
        "is_rerun": is_rerun,
        "rerun_count": rerun_count,
        "version_metadata": {
            "playbook_id": playbook_id,
            "playbook_version_hash": playbook_hash,
            "chunking_config_hash": chunking_hash,
            "data_source_config_hash": data_source_hash,
            "stage_code_version": stage_version,
            "stage_name": stage_name,
            "created_at": datetime.utcnow().isoformat()
        }
    }

    if change_summary:
        metadata["change_summary"] = {
            "version_changed": not is_rerun,
            "config_changed": change_summary.get("config_changed", False),
            "data_changed": change_summary.get("data_changed", False),
            "data_source_changed": change_summary.get("data_source_changed", False),
            "reason": change_summary.get("reason", "unknown"),
            "changes": change_summary.get("changes", [])
        }

    return metadata
