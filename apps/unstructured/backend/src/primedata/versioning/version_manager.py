"""Version Manager Service for tracking, comparing, and rolling back versions.

Provides comprehensive version management capabilities including:
- Version creation and tracking
- Version comparison (before/after diff)
- Version rollback mechanism
- Version history management
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
from enum import Enum

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class VersionStatus(str, Enum):
    """Version status enumeration."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"
    DEPRECATED = "deprecated"


class VersionType(str, Enum):
    """Type of version for different data entities."""

    DATASET = "dataset"
    PROCESS = "process"
    PIPELINE = "pipeline"
    MODEL = "model"
    CONFIG = "config"


@dataclass
class VersionMetadata:
    """Metadata for a version."""

    version_id: str
    entity_id: str
    entity_type: VersionType
    version_number: int
    status: VersionStatus = VersionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["status"] = self.status.value
        data["entity_type"] = self.entity_type.value
        return data


@dataclass
class VersionContent:
    """Content of a version snapshot."""

    content_id: str
    version_id: str
    checksum: str
    size_bytes: int
    data: Dict[str, Any] = field(default_factory=dict)
    stored_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VersionDiff:
    """Difference between two versions."""

    diff_id: str
    from_version: str
    to_version: str
    from_version_number: int
    to_version_number: int
    changes: Dict[str, Any] = field(default_factory=dict)
    added_keys: List[str] = field(default_factory=list)
    removed_keys: List[str] = field(default_factory=list)
    modified_keys: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class VersionManager:
    """Manages versioning for entities."""

    def __init__(self):
        """Initialize version manager."""
        self.versions: Dict[str, VersionMetadata] = {}
        self.contents: Dict[str, VersionContent] = {}
        self.diffs: Dict[str, VersionDiff] = {}
        self.version_history: Dict[str, List[str]] = {}  # entity_id -> [version_ids]
        logger.info("VersionManager initialized")

    def create_version(
        self,
        entity_id: str,
        entity_type: VersionType,
        data: Dict[str, Any],
        description: str = "",
        created_by: Optional[str] = None,
        tags: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> VersionMetadata:
        """Create a new version for an entity.

        Args:
            entity_id: ID of the entity being versioned
            entity_type: Type of the entity
            data: The actual content/data of the version
            description: Human-readable description
            created_by: User/process that created this version
            tags: Optional tags for organization
            custom_metadata: Optional custom metadata

        Returns:
            VersionMetadata: The created version metadata

        Raises:
            ValueError: If entity_id or data is empty
        """
        if not entity_id:
            raise ValueError("entity_id cannot be empty")
        if not data:
            raise ValueError("data cannot be empty")

        # Calculate version number
        entity_versions = self.version_history.get(entity_id, [])
        version_number = len(entity_versions) + 1

        # Create version ID
        version_id = f"v_{entity_id}_{version_number}_{str(uuid4())[:8]}"

        # Create metadata
        metadata = VersionMetadata(
            version_id=version_id,
            entity_id=entity_id,
            entity_type=entity_type,
            version_number=version_number,
            status=VersionStatus.ACTIVE,
            description=description,
            created_by=created_by,
            tags=tags or [],
            custom_metadata=custom_metadata or {},
        )

        # Store content
        content_id = f"content_{version_id}"
        checksum = self._calculate_checksum(data)
        size_bytes = len(str(data).encode("utf-8"))
        content = VersionContent(
            content_id=content_id,
            version_id=version_id,
            checksum=checksum,
            size_bytes=size_bytes,
            data=data,
        )

        # Store everything
        self.versions[version_id] = metadata
        self.contents[content_id] = content
        entity_versions.append(version_id)
        self.version_history[entity_id] = entity_versions

        logger.info(
            f"Version created: {version_id} for entity {entity_id} "
            f"(version #{version_number})"
        )

        return metadata

    def get_version(self, version_id: str) -> Optional[VersionMetadata]:
        """Get version metadata by ID.

        Args:
            version_id: ID of the version to retrieve

        Returns:
            VersionMetadata if found, None otherwise
        """
        return self.versions.get(version_id)

    def get_version_content(self, version_id: str) -> Optional[Dict[str, Any]]:
        """Get version content/data.

        Args:
            version_id: ID of the version

        Returns:
            Dict with version data if found, None otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            logger.warning(f"Version not found: {version_id}")
            return None

        content_id = f"content_{version_id}"
        content = self.contents.get(content_id)
        if not content:
            logger.warning(f"Content not found for version: {version_id}")
            return None

        return content.data

    def list_entity_versions(
        self, entity_id: str, limit: int = 100, offset: int = 0
    ) -> List[VersionMetadata]:
        """List all versions of an entity.

        Args:
            entity_id: ID of the entity
            limit: Maximum number of versions to return
            offset: Number of versions to skip

        Returns:
            List of VersionMetadata objects
        """
        version_ids = self.version_history.get(entity_id, [])
        # Reverse to get newest first
        version_ids = list(reversed(version_ids))
        selected_ids = version_ids[offset : offset + limit]
        return [self.versions[vid] for vid in selected_ids if vid in self.versions]

    def compare_versions(
        self, version_id_1: str, version_id_2: str
    ) -> Optional[VersionDiff]:
        """Compare two versions and identify differences.

        Args:
            version_id_1: ID of the first version
            version_id_2: ID of the second version to compare against

        Returns:
            VersionDiff with changes, or None if versions don't exist

        Raises:
            ValueError: If comparing same version or versions don't exist
        """
        if version_id_1 == version_id_2:
            raise ValueError("Cannot compare same version")

        version1 = self.versions.get(version_id_1)
        version2 = self.versions.get(version_id_2)

        if not version1 or not version2:
            logger.warning(
                f"Could not compare versions: "
                f"{version_id_1} (found={bool(version1)}), "
                f"{version_id_2} (found={bool(version2)})"
            )
            return None

        # Get content
        content_id_1 = f"content_{version_id_1}"
        content_id_2 = f"content_{version_id_2}"
        content1 = self.contents.get(content_id_1, VersionContent("", "", "", 0))
        content2 = self.contents.get(content_id_2, VersionContent("", "", "", 0))

        # Calculate diff
        changes = {}
        added_keys = []
        removed_keys = []
        modified_keys = []

        all_keys = set(content1.data.keys()) | set(content2.data.keys())
        for key in all_keys:
            val1 = content1.data.get(key)
            val2 = content2.data.get(key)

            if key not in content1.data:
                added_keys.append(key)
                changes[key] = {"action": "added", "value": val2}
            elif key not in content2.data:
                removed_keys.append(key)
                changes[key] = {"action": "removed", "old_value": val1}
            elif val1 != val2:
                modified_keys.append(key)
                changes[key] = {"action": "modified", "old_value": val1, "new_value": val2}

        diff_id = f"diff_{version_id_1}_to_{version_id_2}_{str(uuid4())[:8]}"
        diff = VersionDiff(
            diff_id=diff_id,
            from_version=version_id_1,
            to_version=version_id_2,
            from_version_number=version1.version_number,
            to_version_number=version2.version_number,
            changes=changes,
            added_keys=added_keys,
            removed_keys=removed_keys,
            modified_keys=modified_keys,
        )

        self.diffs[diff_id] = diff
        logger.info(
            f"Version comparison: {len(added_keys)} added, "
            f"{len(removed_keys)} removed, {len(modified_keys)} modified"
        )

        return diff

    def rollback_to_version(
        self, entity_id: str, target_version_id: str, created_by: Optional[str] = None
    ) -> Optional[VersionMetadata]:
        """Rollback entity to a specific version by creating a new version from that state.

        Args:
            entity_id: ID of the entity
            target_version_id: Version to rollback to
            created_by: User/process requesting rollback

        Returns:
            New VersionMetadata of the rollback version, or None on failure

        Raises:
            ValueError: If target version not found
        """
        target_version = self.versions.get(target_version_id)
        if not target_version:
            raise ValueError(f"Target version not found: {target_version_id}")

        if target_version.entity_id != entity_id:
            raise ValueError(
                f"Target version belongs to different entity: "
                f"{target_version.entity_id} != {entity_id}"
            )

        # Get content of target version
        content = self.get_version_content(target_version_id)
        if not content:
            logger.error(f"Could not retrieve content for rollback: {target_version_id}")
            return None

        # Create new version from the target content
        new_version = self.create_version(
            entity_id=entity_id,
            entity_type=target_version.entity_type,
            data=content,
            description=f"Rollback to version {target_version.version_number}",
            created_by=created_by,
            tags=["rollback"],
            custom_metadata={"rolled_back_from": target_version_id},
        )

        # Mark old versions appropriately
        target_version.status = VersionStatus.ROLLED_BACK
        logger.info(
            f"Rollback completed: {entity_id} rolled back to version "
            f"{target_version.version_number}, new version: {new_version.version_number}"
        )

        return new_version

    def deprecate_version(self, version_id: str, reason: str = "") -> bool:
        """Mark a version as deprecated.

        Args:
            version_id: ID of the version to deprecate
            reason: Optional reason for deprecation

        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            logger.warning(f"Version not found for deprecation: {version_id}")
            return False

        version.status = VersionStatus.DEPRECATED
        if reason:
            version.custom_metadata["deprecation_reason"] = reason

        logger.info(f"Version deprecated: {version_id} - {reason}")
        return True

    def archive_version(self, version_id: str) -> bool:
        """Archive a version.

        Args:
            version_id: ID of the version to archive

        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            logger.warning(f"Version not found for archival: {version_id}")
            return False

        version.status = VersionStatus.ARCHIVED
        logger.info(f"Version archived: {version_id}")
        return True

    def get_latest_version(self, entity_id: str) -> Optional[VersionMetadata]:
        """Get the latest version of an entity.

        Args:
            entity_id: ID of the entity

        Returns:
            Latest VersionMetadata, or None if no versions exist
        """
        version_ids = self.version_history.get(entity_id, [])
        if not version_ids:
            return None

        latest_id = version_ids[-1]
        return self.versions.get(latest_id)

    def delete_version(self, version_id: str) -> bool:
        """Delete a version (hard delete).

        Args:
            version_id: ID of the version to delete

        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            logger.warning(f"Version not found for deletion: {version_id}")
            return False

        entity_id = version.entity_id
        content_id = f"content_{version_id}"

        # Remove from tracking
        del self.versions[version_id]
        if content_id in self.contents:
            del self.contents[content_id]

        # Remove from history
        if entity_id in self.version_history:
            self.version_history[entity_id] = [
                v for v in self.version_history[entity_id] if v != version_id
            ]

        logger.info(f"Version deleted: {version_id}")
        return True

    def get_entity_version_stats(self, entity_id: str) -> Dict[str, Any]:
        """Get statistics about versions for an entity.

        Args:
            entity_id: ID of the entity

        Returns:
            Dictionary with version statistics
        """
        version_ids = self.version_history.get(entity_id, [])
        versions = [self.versions[vid] for vid in version_ids if vid in self.versions]

        if not versions:
            return {
                "entity_id": entity_id,
                "total_versions": 0,
                "active_versions": 0,
                "archived_versions": 0,
                "deprecated_versions": 0,
                "rolled_back_versions": 0,
            }

        active = sum(1 for v in versions if v.status == VersionStatus.ACTIVE)
        archived = sum(1 for v in versions if v.status == VersionStatus.ARCHIVED)
        deprecated = sum(1 for v in versions if v.status == VersionStatus.DEPRECATED)
        rolled_back = sum(1 for v in versions if v.status == VersionStatus.ROLLED_BACK)

        total_size = sum(
            self.contents.get(f"content_{vid}", VersionContent("", "", "", 0)).size_bytes
            for vid in version_ids
        )

        return {
            "entity_id": entity_id,
            "total_versions": len(versions),
            "active_versions": active,
            "archived_versions": archived,
            "deprecated_versions": deprecated,
            "rolled_back_versions": rolled_back,
            "total_size_bytes": total_size,
            "latest_version_number": versions[-1].version_number if versions else 0,
        }

    @staticmethod
    def _calculate_checksum(data: Dict[str, Any]) -> str:
        """Calculate checksum for data.

        Args:
            data: The data to checksum

        Returns:
            Hex string checksum
        """
        import hashlib
        import json

        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
