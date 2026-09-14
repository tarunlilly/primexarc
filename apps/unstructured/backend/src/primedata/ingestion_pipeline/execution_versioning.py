"""
Execution Flow Versioning for Pipeline Traceability

This module provides simplified execution flow versioning for demo purposes.

Format: DATA_SOURCE.STAGE.PIPELINE (e.g., "1.1.1")

Purpose:
- Track data source version through pipeline stages
- Simple version format suitable for demos
- Complement semantic versioning (v1.2.3) which tracks config/data changes

Example:
- Raw Files: 1.0.1 (data_source=1, stage=0, pipeline=1)
- Preprocess: 1.1.1 (data_source=1, stage=1, pipeline=1)
- Scoring: 1.2.1 (data_source=1, stage=2, pipeline=1)
- Fingerprint: 1.3.1 (data_source=1, stage=3, pipeline=1)
- Policy: 1.4.1 (data_source=1, stage=4, pipeline=1)
- Validation: 1.5.1 (data_source=1, stage=5, pipeline=1)
- Indexing: 1.6.1 (data_source=1, stage=6, pipeline=1)

Note: Sub-stage tracking can be added to roadmap for maturity model
"""

from typing import Dict, List, Optional


class ExecutionVersionTracker:
    """Track execution flow through pipeline stages and sub-stages."""

    # Stage number mapping (deterministic)
    STAGE_NUMBERS = {
        "preprocess": 1,
        "scoring": 2,
        "fingerprint": 3,
        "policy": 4,
        "validation": 5,
        "indexing": 6,
    }

    # Stage display names
    STAGE_DISPLAY_NAMES = {
        "preprocess": "Preprocessing",
        "scoring": "Quality Scoring",
        "fingerprint": "Fingerprinting",
        "policy": "Policy Evaluation",
        "validation": "Validation",
        "indexing": "Vector Indexing",
    }

    def get_execution_version(
        self,
        data_source_version: int,
        stage_name: str,
        pipeline_run: int = 1,
        substage_name: Optional[str] = None,  # Reserved for future roadmap
        artifact_index: int = 0  # Reserved for future roadmap
    ) -> str:
        """
        Generate simplified execution flow version string for demos.

        Args:
            data_source_version: Data source version (from product version)
            stage_name: Stage name ("preprocess", "scoring", etc.)
            pipeline_run: Pipeline run number (typically 1)
            substage_name: Reserved for future roadmap (ignored)
            artifact_index: Reserved for future roadmap (ignored)

        Returns:
            Execution version string in format "D.S.P"
            - D: Data source version (product version)
            - S: Stage number (0=raw, 1=preprocess, 2=scoring, 3=fingerprint, 4=policy, 5=validation, 6=indexing)
            - P: Pipeline run number (typically 1)

        Examples:
            - get_execution_version(1, "preprocess", 1) → "1.1.1"
            - get_execution_version(1, "scoring", 1) → "1.2.1"
            - get_execution_version(1, "fingerprint", 1) → "1.3.1"
            - get_execution_version(1, "indexing", 1) → "1.6.1"
            - get_execution_version(2, "preprocess", 1) → "2.1.1" (new data source version)
        """
        stage = self.STAGE_NUMBERS.get(stage_name, 0)
        return f"{data_source_version}.{stage}.{pipeline_run}"

    def parse_execution_version(self, version_str: str) -> Dict[str, int]:
        """
        Parse execution version string into components.

        Args:
            version_str: Version string (e.g., "1.1.1")

        Returns:
            Dictionary with data_source, stage, pipeline numbers
        """
        try:
            parts = version_str.split(".")
            if len(parts) != 3:
                return {"data_source": 0, "stage": 0, "pipeline": 0}

            return {
                "data_source": int(parts[0]),
                "stage": int(parts[1]),
                "pipeline": int(parts[2]),
            }
        except (ValueError, IndexError):
            return {"data_source": 0, "stage": 0, "pipeline": 0}

    def get_stage_name(self, stage_number: int) -> Optional[str]:
        """Get stage name from stage number."""
        reverse_map = {v: k for k, v in self.STAGE_NUMBERS.items()}
        return reverse_map.get(stage_number)

    def get_substage_name(self, stage_name: str, substage_number: int) -> Optional[str]:
        """Reserved for future roadmap — returns None in simplified version."""
        return None

    def get_stage_display_name(self, stage_name: str) -> str:
        """Get display name for stage."""
        return self.STAGE_DISPLAY_NAMES.get(stage_name, stage_name.title())

    def format_execution_path(self, execution_version: str) -> str:
        """
        Format execution version as human-readable path.

        Example:
            format_execution_path("1.1.1") → "Preprocessing"
            format_execution_path("1.6.1") → "Vector Indexing"
        """
        parsed = self.parse_execution_version(execution_version)
        stage_name = self.get_stage_name(parsed["stage"])
        if not stage_name:
            return f"Unknown Stage {parsed['stage']}"
        return self.get_stage_display_name(stage_name)

    def get_execution_lineage(self, execution_version: str) -> List[str]:
        """
        Get full execution path leading to this version.

        Example:
            get_execution_lineage("1.3.1") → [
                "1.0.1",  # Raw Files
                "1.1.1",  # Preprocess
                "1.2.1",  # Scoring
                "1.3.1",  # Fingerprint (current)
            ]
        """
        parsed = self.parse_execution_version(execution_version)
        lineage = []

        data_source = parsed["data_source"]
        current_stage = parsed["stage"]
        pipeline_run = parsed["pipeline"]

        # Add raw files (stage 0)
        lineage.append(f"{data_source}.0.{pipeline_run}")

        # Add all stages up to and including current
        for stage_num in range(1, current_stage + 1):
            lineage.append(f"{data_source}.{stage_num}.{pipeline_run}")

        return lineage

    def get_all_execution_versions(self) -> List[Dict[str, str]]:
        """
        Get all possible execution versions in pipeline (simplified format).

        Useful for documentation, UI dropdowns, and testing.
        """
        versions = []

        # For demo purposes, assume data_source_version=1, pipeline_run=1
        data_source = 1
        pipeline = 1

        # Raw files entry
        versions.append({
            "version": f"{data_source}.0.{pipeline}",
            "description": "Raw Files (Input)",
            "stage": None,
            "data_source": data_source
        })

        # Each stage
        for stage_name, stage_num in self.STAGE_NUMBERS.items():
            stage_display = self.get_stage_display_name(stage_name)
            versions.append({
                "version": f"{data_source}.{stage_num}.{pipeline}",
                "description": stage_display,
                "stage": stage_name,
                "data_source": data_source
            })

        return versions


# Global tracker instance
_execution_tracker = None


def get_execution_tracker() -> ExecutionVersionTracker:
    """Get global execution version tracker instance."""
    global _execution_tracker
    if _execution_tracker is None:
        _execution_tracker = ExecutionVersionTracker()
    return _execution_tracker
