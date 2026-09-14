"""Tests for version manager service."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from primedata.versioning.version_manager import (
    VersionManager,
    VersionMetadata,
    VersionContent,
    VersionDiff,
    VersionStatus,
    VersionType,
)


class TestVersionCreation:
    """Tests for version creation."""

    def test_create_version_success(self):
        """Test successful version creation."""
        manager = VersionManager()
        data = {"key1": "value1", "key2": 42}

        version = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data=data,
            description="Test version",
            created_by="test_user",
        )

        assert version is not None
        assert version.version_number == 1
        assert version.entity_id == "entity_1"
        assert version.status == VersionStatus.ACTIVE
        assert version.description == "Test version"
        assert version.created_by == "test_user"

    def test_create_version_with_tags_and_metadata(self):
        """Test version creation with tags and custom metadata."""
        manager = VersionManager()
        data = {"data": "test"}

        version = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data=data,
            tags=["prod", "v1"],
            custom_metadata={"env": "production"},
        )

        assert version.tags == ["prod", "v1"]
        assert version.custom_metadata == {"env": "production"}

    def test_create_multiple_versions_increments_number(self):
        """Test that version numbers increment correctly."""
        manager = VersionManager()
        data1 = {"v": 1}
        data2 = {"v": 2}
        data3 = {"v": 3}

        v1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data=data1
        )
        v2 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data=data2
        )
        v3 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data=data3
        )

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_create_version_empty_entity_id_raises_error(self):
        """Test that empty entity_id raises ValueError."""
        manager = VersionManager()

        with pytest.raises(ValueError, match="entity_id cannot be empty"):
            manager.create_version(
                entity_id="",
                entity_type=VersionType.DATASET,
                data={"key": "value"},
            )

    def test_create_version_empty_data_raises_error(self):
        """Test that empty data raises ValueError."""
        manager = VersionManager()

        with pytest.raises(ValueError, match="data cannot be empty"):
            manager.create_version(
                entity_id="entity_1", entity_type=VersionType.DATASET, data={}
            )

    def test_create_version_incremental_ids_are_unique(self):
        """Test that version IDs are unique."""
        manager = VersionManager()
        data = {"test": "data"}

        versions = []
        for i in range(5):
            v = manager.create_version(
                entity_id=f"entity_{i % 2}",
                entity_type=VersionType.DATASET,
                data=data,
            )
            versions.append(v.version_id)

        assert len(set(versions)) == 5


class TestVersionRetrieval:
    """Tests for version retrieval."""

    def test_get_version_by_id(self):
        """Test retrieving version by ID."""
        manager = VersionManager()
        data = {"key": "value"}

        created = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data=data
        )

        retrieved = manager.get_version(created.version_id)
        assert retrieved is not None
        assert retrieved.version_id == created.version_id
        assert retrieved.version_number == 1

    def test_get_version_nonexistent_returns_none(self):
        """Test that retrieving nonexistent version returns None."""
        manager = VersionManager()

        retrieved = manager.get_version("nonexistent_version")
        assert retrieved is None

    def test_get_version_content(self):
        """Test retrieving version content."""
        manager = VersionManager()
        data = {"key1": "value1", "key2": 42, "nested": {"a": 1}}

        version = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data=data
        )

        content = manager.get_version_content(version.version_id)
        assert content == data

    def test_get_version_content_nonexistent_returns_none(self):
        """Test that getting content for nonexistent version returns None."""
        manager = VersionManager()

        content = manager.get_version_content("nonexistent")
        assert content is None

    def test_list_entity_versions_ordered_newest_first(self):
        """Test listing versions with newest first."""
        manager = VersionManager()

        for i in range(3):
            manager.create_version(
                entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": i}
            )

        versions = manager.list_entity_versions("entity_1")
        assert len(versions) == 3
        # Newest first
        assert versions[0].version_number == 3
        assert versions[1].version_number == 2
        assert versions[2].version_number == 1

    def test_list_entity_versions_with_pagination(self):
        """Test listing versions with limit and offset."""
        manager = VersionManager()

        for i in range(10):
            manager.create_version(
                entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": i}
            )

        # First page
        page1 = manager.list_entity_versions("entity_1", limit=3, offset=0)
        assert len(page1) == 3
        assert page1[0].version_number == 10  # Newest

        # Second page
        page2 = manager.list_entity_versions("entity_1", limit=3, offset=3)
        assert len(page2) == 3
        assert page2[0].version_number == 7

    def test_list_entity_versions_nonexistent_entity(self):
        """Test listing versions for nonexistent entity."""
        manager = VersionManager()

        versions = manager.list_entity_versions("nonexistent")
        assert versions == []

    def test_get_latest_version(self):
        """Test getting latest version."""
        manager = VersionManager()

        for i in range(5):
            manager.create_version(
                entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": i}
            )

        latest = manager.get_latest_version("entity_1")
        assert latest is not None
        assert latest.version_number == 5

    def test_get_latest_version_nonexistent_entity(self):
        """Test getting latest version for nonexistent entity."""
        manager = VersionManager()

        latest = manager.get_latest_version("nonexistent")
        assert latest is None


class TestVersionComparison:
    """Tests for version comparison."""

    def test_compare_versions_detects_changes(self):
        """Test comparing versions detects all changes."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"a": 1, "b": 2, "c": 3},
        )

        v2 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"a": 1, "b": 20, "d": 4},  # b modified, c removed, d added
        )

        diff = manager.compare_versions(v1.version_id, v2.version_id)
        assert diff is not None
        assert "b" in diff.modified_keys
        assert "c" in diff.removed_keys
        assert "d" in diff.added_keys

    def test_compare_versions_same_version_raises_error(self):
        """Test comparing same version raises error."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"key": "value"},
        )

        with pytest.raises(ValueError, match="Cannot compare same version"):
            manager.compare_versions(v1.version_id, v1.version_id)

    def test_compare_versions_nonexistent_returns_none(self):
        """Test comparing nonexistent versions returns None."""
        manager = VersionManager()

        diff = manager.compare_versions("nonexistent1", "nonexistent2")
        assert diff is None

    def test_compare_versions_empty_to_populated(self):
        """Test comparison from empty-like to populated."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"a": None}
        )

        v2 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"a": None, "b": 2, "c": 3},
        )

        diff = manager.compare_versions(v1.version_id, v2.version_id)
        assert "b" in diff.added_keys
        assert "c" in diff.added_keys

    def test_compare_versions_complex_changes(self):
        """Test comparison with complex nested changes."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"nested": {"a": 1, "b": 2}, "list": [1, 2, 3]},
        )

        v2 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"nested": {"a": 1, "b": 20}, "list": [1, 2, 3, 4]},
        )

        diff = manager.compare_versions(v1.version_id, v2.version_id)
        assert "nested" in diff.modified_keys
        assert "list" in diff.modified_keys


class TestVersionRollback:
    """Tests for version rollback."""

    def test_rollback_to_version_creates_new_version(self):
        """Test rollback creates new version with old data."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"status": "initial"},
        )

        v2 = manager.create_version(
            entity_id="entity_1",
            entity_type=VersionType.DATASET,
            data={"status": "updated"},
        )

        # Rollback to v1
        rolled_back = manager.rollback_to_version("entity_1", v1.version_id)
        assert rolled_back is not None
        assert rolled_back.version_number == 3  # New version
        assert rolled_back.tags == ["rollback"]

        # Check content
        content = manager.get_version_content(rolled_back.version_id)
        assert content == {"status": "initial"}

    def test_rollback_marks_old_version_rolled_back(self):
        """Test rollback marks source version status."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )

        manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 2}
        )

        manager.rollback_to_version("entity_1", v1.version_id)

        # Check v1 status
        v1_updated = manager.get_version(v1.version_id)
        assert v1_updated.status == VersionStatus.ROLLED_BACK

    def test_rollback_nonexistent_version_raises_error(self):
        """Test rollback to nonexistent version raises error."""
        manager = VersionManager()

        with pytest.raises(ValueError, match="Target version not found"):
            manager.rollback_to_version("entity_1", "nonexistent")

    def test_rollback_wrong_entity_raises_error(self):
        """Test rollback with wrong entity raises error."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )

        with pytest.raises(ValueError, match="belongs to different entity"):
            manager.rollback_to_version("entity_2", v1.version_id)


class TestVersionLifecycle:
    """Tests for version lifecycle management."""

    def test_deprecate_version(self):
        """Test deprecating a version."""
        manager = VersionManager()

        version = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )

        result = manager.deprecate_version(
            version.version_id, reason="Superseded by v2"
        )
        assert result is True

        updated = manager.get_version(version.version_id)
        assert updated.status == VersionStatus.DEPRECATED
        assert updated.custom_metadata["deprecation_reason"] == "Superseded by v2"

    def test_deprecate_nonexistent_version(self):
        """Test deprecating nonexistent version returns False."""
        manager = VersionManager()

        result = manager.deprecate_version("nonexistent")
        assert result is False

    def test_archive_version(self):
        """Test archiving a version."""
        manager = VersionManager()

        version = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )

        result = manager.archive_version(version.version_id)
        assert result is True

        updated = manager.get_version(version.version_id)
        assert updated.status == VersionStatus.ARCHIVED

    def test_delete_version(self):
        """Test deleting a version."""
        manager = VersionManager()

        version = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )

        result = manager.delete_version(version.version_id)
        assert result is True

        # Verify deleted
        retrieved = manager.get_version(version.version_id)
        assert retrieved is None

    def test_delete_nonexistent_version(self):
        """Test deleting nonexistent version returns False."""
        manager = VersionManager()

        result = manager.delete_version("nonexistent")
        assert result is False


class TestVersionStatistics:
    """Tests for version statistics."""

    def test_get_version_stats_no_versions(self):
        """Test stats for entity with no versions."""
        manager = VersionManager()

        stats = manager.get_entity_version_stats("nonexistent")
        assert stats["total_versions"] == 0
        assert stats["active_versions"] == 0

    def test_get_version_stats_multiple_versions(self):
        """Test stats for entity with multiple versions."""
        manager = VersionManager()

        for i in range(3):
            manager.create_version(
                entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": i}
            )

        stats = manager.get_entity_version_stats("entity_1")
        assert stats["total_versions"] == 3
        assert stats["active_versions"] == 3
        assert stats["latest_version_number"] == 3

    def test_get_version_stats_with_status_variations(self):
        """Test stats with different version statuses."""
        manager = VersionManager()

        v1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 1}
        )
        v2 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 2}
        )
        v3 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"v": 3}
        )

        manager.archive_version(v1.version_id)
        manager.deprecate_version(v2.version_id)

        stats = manager.get_entity_version_stats("entity_1")
        assert stats["total_versions"] == 3
        assert stats["active_versions"] == 1
        assert stats["archived_versions"] == 1
        assert stats["deprecated_versions"] == 1

    def test_get_version_stats_size_calculation(self):
        """Test stats includes total size."""
        manager = VersionManager()

        for i in range(2):
            manager.create_version(
                entity_id="entity_1",
                entity_type=VersionType.DATASET,
                data={"large_data": "x" * 1000},
            )

        stats = manager.get_entity_version_stats("entity_1")
        assert stats["total_size_bytes"] > 0


class TestVersionMetadataConversion:
    """Tests for metadata conversion."""

    def test_version_metadata_to_dict(self):
        """Test converting version metadata to dict."""
        version = VersionMetadata(
            version_id="v_1",
            entity_id="e_1",
            entity_type=VersionType.DATASET,
            version_number=1,
            status=VersionStatus.ACTIVE,
            description="Test",
            created_by="user_1",
            tags=["tag1"],
            custom_metadata={"key": "value"},
        )

        data = version.to_dict()
        assert data["version_id"] == "v_1"
        assert data["entity_id"] == "e_1"
        assert data["entity_type"] == VersionType.DATASET.value
        assert data["status"] == VersionStatus.ACTIVE.value
        assert data["created_by"] == "user_1"

    def test_version_diff_to_dict(self):
        """Test converting version diff to dict."""
        diff = VersionDiff(
            diff_id="d_1",
            from_version="v_1",
            to_version="v_2",
            from_version_number=1,
            to_version_number=2,
            changes={"key": {"action": "modified"}},
            added_keys=["new"],
            removed_keys=["old"],
            modified_keys=["key"],
        )

        data = diff.to_dict()
        assert data["diff_id"] == "d_1"
        assert data["from_version"] == "v_1"
        assert data["to_version"] == "v_2"


class TestVersionManagerIntegration:
    """Integration tests for version manager."""

    def test_full_version_lifecycle(self):
        """Test complete version lifecycle."""
        manager = VersionManager()

        # Create v1
        v1 = manager.create_version(
            entity_id="dataset_1",
            entity_type=VersionType.DATASET,
            data={"status": "new"},
            created_by="user_1",
        )
        assert v1.version_number == 1

        # Create v2
        v2 = manager.create_version(
            entity_id="dataset_1",
            entity_type=VersionType.DATASET,
            data={"status": "processed"},
            created_by="user_1",
        )
        assert v2.version_number == 2

        # Compare
        diff = manager.compare_versions(v1.version_id, v2.version_id)
        assert "status" in diff.modified_keys

        # Rollback
        rolled_back = manager.rollback_to_version("dataset_1", v1.version_id)
        assert rolled_back.version_number == 3
        content = manager.get_version_content(rolled_back.version_id)
        assert content["status"] == "new"

        # Archive old
        manager.archive_version(v1.version_id)

        # Stats
        stats = manager.get_entity_version_stats("dataset_1")
        assert stats["total_versions"] == 3
        assert stats["active_versions"] == 2
        assert stats["archived_versions"] == 1

    def test_multiple_entities_independent_versions(self):
        """Test versions are independent across entities."""
        manager = VersionManager()

        v1_e1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"e": 1}
        )
        v1_e2 = manager.create_version(
            entity_id="entity_2", entity_type=VersionType.DATASET, data={"e": 2}
        )

        v2_e1 = manager.create_version(
            entity_id="entity_1", entity_type=VersionType.DATASET, data={"e": 1, "v": 2}
        )

        # entity_1 should have v2, entity_2 should have v1
        stats1 = manager.get_entity_version_stats("entity_1")
        stats2 = manager.get_entity_version_stats("entity_2")

        assert stats1["total_versions"] == 2
        assert stats1["latest_version_number"] == 2
        assert stats2["total_versions"] == 1
        assert stats2["latest_version_number"] == 1
