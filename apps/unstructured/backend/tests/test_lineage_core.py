"""
Comprehensive tests for data lineage module.

Tests cover:
- Lineage entities and relationships
- Graph construction
- Upstream/downstream queries
- Path finding
- Graph serialization
- Edge cases and error handling
"""

import pytest
from datetime import datetime

from primedata.lineage.core import (
    LineageEntity,
    LineageRelationship,
    LineageNode,
    LineagePath,
    LineageGraph,
    LineageEntityType,
    LineageRelationType,
)


# ============================================================================
# LINEAGE ENTITY TESTS
# ============================================================================


class TestLineageEntity:
    """Tests for LineageEntity."""

    def test_entity_creation(self):
        """Test creating a lineage entity."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Raw Data",
            description="Raw input data",
        )
        assert entity.entity_id == "dataset_1"
        assert entity.entity_type == LineageEntityType.DATASET
        assert entity.name == "Raw Data"

    def test_entity_with_attributes(self):
        """Test entity with custom attributes."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Raw Data",
            attributes={"size": 1000, "records": 100},
        )
        assert entity.attributes["size"] == 1000
        assert entity.attributes["records"] == 100

    def test_entity_hash(self):
        """Test entity hashing for use in sets."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        entity2 = LineageEntity(
            entity_id="dataset_2",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        assert hash(entity1) != hash(entity2)

    def test_entity_equality(self):
        """Test entity equality by ID."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        entity1_dup = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.FILE,
            name="Different",
        )
        assert entity1 == entity1_dup  # Equal because same ID

    def test_entity_types(self):
        """Test different entity types."""
        for entity_type in LineageEntityType:
            entity = LineageEntity(
                entity_id=f"entity_{entity_type.value}",
                entity_type=entity_type,
                name=f"Test {entity_type.value}",
            )
            assert entity.entity_type == entity_type


# ============================================================================
# LINEAGE RELATIONSHIP TESTS
# ============================================================================


class TestLineageRelationship:
    """Tests for LineageRelationship."""

    def test_relationship_creation(self):
        """Test creating a lineage relationship."""
        rel = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="dataset_1",
            target_entity_id="dataset_2",
            relationship_type=LineageRelationType.INPUT,
        )
        assert rel.source_entity_id == "dataset_1"
        assert rel.target_entity_id == "dataset_2"
        assert rel.relationship_type == LineageRelationType.INPUT

    def test_relationship_with_properties(self):
        """Test relationship with custom properties."""
        rel = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="dataset_1",
            target_entity_id="process_1",
            relationship_type=LineageRelationType.OUTPUT,
            properties={"transformation": "filter"},
        )
        assert rel.properties["transformation"] == "filter"

    def test_relationship_types(self):
        """Test different relationship types."""
        for rel_type in LineageRelationType:
            rel = LineageRelationship(
                relationship_id=f"rel_{rel_type.value}",
                source_entity_id="source",
                target_entity_id="target",
                relationship_type=rel_type,
            )
            assert rel.relationship_type == rel_type


# ============================================================================
# LINEAGE NODE TESTS
# ============================================================================


class TestLineageNode:
    """Tests for LineageNode."""

    def test_node_creation(self):
        """Test creating a lineage node."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        node = LineageNode(entity=entity)
        assert node.entity == entity
        assert len(node.upstream_relationships) == 0
        assert len(node.downstream_relationships) == 0

    def test_node_with_relationships(self):
        """Test node with relationships."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        rel_up = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="source",
            target_entity_id="dataset_1",
            relationship_type=LineageRelationType.INPUT,
        )
        rel_down = LineageRelationship(
            relationship_id="rel_2",
            source_entity_id="dataset_1",
            target_entity_id="target",
            relationship_type=LineageRelationType.OUTPUT,
        )

        node = LineageNode(
            entity=entity,
            upstream_relationships=[rel_up],
            downstream_relationships=[rel_down],
        )

        assert len(node.upstream_relationships) == 1
        assert len(node.downstream_relationships) == 1


# ============================================================================
# LINEAGE GRAPH TESTS
# ============================================================================


class TestLineageGraph:
    """Tests for LineageGraph."""

    @pytest.fixture
    def graph(self):
        """Create a lineage graph."""
        return LineageGraph()

    def test_graph_initialization(self, graph):
        """Test graph initialization."""
        assert len(graph.entities) == 0
        assert len(graph.relationships) == 0

    def test_add_entity(self, graph):
        """Test adding an entity to graph."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
        )
        graph.add_entity(entity)
        assert len(graph.entities) == 1
        assert graph.get_entity("dataset_1") == entity

    def test_add_multiple_entities(self, graph):
        """Test adding multiple entities."""
        for i in range(3):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        assert len(graph.entities) == 3

    def test_add_relationship(self, graph):
        """Test adding a relationship."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data 1",
        )
        entity2 = LineageEntity(
            entity_id="dataset_2",
            entity_type=LineageEntityType.DATASET,
            name="Data 2",
        )
        graph.add_entity(entity1)
        graph.add_entity(entity2)

        rel = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="dataset_1",
            target_entity_id="dataset_2",
            relationship_type=LineageRelationType.INPUT,
        )
        graph.add_relationship(rel)
        assert len(graph.relationships) == 1

    def test_add_relationship_with_missing_entity(self, graph):
        """Test adding relationship with missing entity."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data 1",
        )
        graph.add_entity(entity1)

        rel = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="dataset_1",
            target_entity_id="nonexistent",
            relationship_type=LineageRelationType.INPUT,
        )
        graph.add_relationship(rel)
        # Should not add relationship if target doesn't exist
        assert len(graph.relationships) == 0

    def test_get_upstream_entities(self, graph):
        """Test getting upstream entities."""
        # Create chain: dataset_1 -> dataset_2 -> dataset_3
        for i in range(1, 4):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        for i in range(1, 3):
            rel = LineageRelationship(
                relationship_id=f"rel_{i}",
                source_entity_id=f"dataset_{i}",
                target_entity_id=f"dataset_{i+1}",
                relationship_type=LineageRelationType.INPUT,
            )
            graph.add_relationship(rel)

        upstream = graph.get_upstream_entities("dataset_3")
        assert len(upstream) == 1
        assert upstream[0].entity_id == "dataset_2"

    def test_get_downstream_entities(self, graph):
        """Test getting downstream entities."""
        # Create chain: dataset_1 -> dataset_2 -> dataset_3
        for i in range(1, 4):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        for i in range(1, 3):
            rel = LineageRelationship(
                relationship_id=f"rel_{i}",
                source_entity_id=f"dataset_{i}",
                target_entity_id=f"dataset_{i+1}",
                relationship_type=LineageRelationType.OUTPUT,
            )
            graph.add_relationship(rel)

        downstream = graph.get_downstream_entities("dataset_1")
        assert len(downstream) == 1
        assert downstream[0].entity_id == "dataset_2"

    def test_find_path_direct(self, graph):
        """Test finding a direct path."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data 1",
        )
        entity2 = LineageEntity(
            entity_id="dataset_2",
            entity_type=LineageEntityType.DATASET,
            name="Data 2",
        )
        graph.add_entity(entity1)
        graph.add_entity(entity2)

        rel = LineageRelationship(
            relationship_id="rel_1",
            source_entity_id="dataset_1",
            target_entity_id="dataset_2",
            relationship_type=LineageRelationType.OUTPUT,
        )
        graph.add_relationship(rel)

        path = graph.find_path("dataset_1", "dataset_2")
        assert path is not None
        assert len(path.entities) == 2
        assert path.entities[0].entity_id == "dataset_1"
        assert path.entities[1].entity_id == "dataset_2"

    def test_find_path_multi_hop(self, graph):
        """Test finding a multi-hop path."""
        # Create chain: 1 -> 2 -> 3 -> 4
        for i in range(1, 5):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        for i in range(1, 4):
            rel = LineageRelationship(
                relationship_id=f"rel_{i}",
                source_entity_id=f"dataset_{i}",
                target_entity_id=f"dataset_{i+1}",
                relationship_type=LineageRelationType.OUTPUT,
            )
            graph.add_relationship(rel)

        path = graph.find_path("dataset_1", "dataset_4")
        assert path is not None
        assert len(path.entities) == 4
        assert len(path.relationships) == 3

    def test_find_path_no_path(self, graph):
        """Test finding path when no path exists."""
        entity1 = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data 1",
        )
        entity2 = LineageEntity(
            entity_id="dataset_2",
            entity_type=LineageEntityType.DATASET,
            name="Data 2",
        )
        graph.add_entity(entity1)
        graph.add_entity(entity2)

        path = graph.find_path("dataset_1", "dataset_2")
        assert path is None

    def test_find_path_same_entity(self, graph):
        """Test finding path from entity to itself."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data 1",
        )
        graph.add_entity(entity)

        path = graph.find_path("dataset_1", "dataset_1")
        assert path is not None
        assert len(path.entities) == 1

    def test_graph_summary(self, graph):
        """Test graph summary."""
        for i in range(2):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        entity = LineageEntity(
            entity_id="process_1",
            entity_type=LineageEntityType.PROCESS,
            name="Transform",
        )
        graph.add_entity(entity)

        summary = graph.get_graph_summary()
        assert summary["total_entities"] == 3
        assert summary["entities_by_type"]["dataset"] == 2
        assert summary["entities_by_type"]["process"] == 1

    def test_export_to_dict(self, graph):
        """Test exporting graph to dictionary."""
        entity = LineageEntity(
            entity_id="dataset_1",
            entity_type=LineageEntityType.DATASET,
            name="Data",
            attributes={"size": 1000},
        )
        graph.add_entity(entity)

        exported = graph.export_to_dict()
        assert "entities" in exported
        assert "relationships" in exported
        assert "summary" in exported
        assert len(exported["entities"]) == 1
        assert exported["entities"][0]["entity_id"] == "dataset_1"

    def test_complex_graph(self, graph):
        """Test complex graph with multiple relationships."""
        # Create a diamond-shaped graph: 1 -> 2,3 -> 4
        for i in range(1, 5):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        relationships = [
            ("dataset_1", "dataset_2", LineageRelationType.OUTPUT),
            ("dataset_1", "dataset_3", LineageRelationType.OUTPUT),
            ("dataset_2", "dataset_4", LineageRelationType.OUTPUT),
            ("dataset_3", "dataset_4", LineageRelationType.OUTPUT),
        ]

        for i, (source, target, rel_type) in enumerate(relationships):
            rel = LineageRelationship(
                relationship_id=f"rel_{i}",
                source_entity_id=source,
                target_entity_id=target,
                relationship_type=rel_type,
            )
            graph.add_relationship(rel)

        # Check downstream of dataset_1
        downstream = graph.get_downstream_entities("dataset_1")
        assert len(downstream) == 2
        assert set(e.entity_id for e in downstream) == {"dataset_2", "dataset_3"}

        # Find path from 1 to 4
        path = graph.find_path("dataset_1", "dataset_4")
        assert path is not None
        assert len(path.entities) == 3

    def test_graph_max_depth_limit(self, graph):
        """Test path finding with max depth limit."""
        # Create long chain: 1 -> 2 -> ... -> 20
        for i in range(1, 21):
            entity = LineageEntity(
                entity_id=f"dataset_{i}",
                entity_type=LineageEntityType.DATASET,
                name=f"Data {i}",
            )
            graph.add_entity(entity)

        for i in range(1, 20):
            rel = LineageRelationship(
                relationship_id=f"rel_{i}",
                source_entity_id=f"dataset_{i}",
                target_entity_id=f"dataset_{i+1}",
                relationship_type=LineageRelationType.OUTPUT,
            )
            graph.add_relationship(rel)

        # With max_depth=5, should not find path from 1 to 20
        path = graph.find_path("dataset_1", "dataset_20", max_depth=5)
        assert path is None

        # With max_depth=20, should find path
        path = graph.find_path("dataset_1", "dataset_20", max_depth=20)
        assert path is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
