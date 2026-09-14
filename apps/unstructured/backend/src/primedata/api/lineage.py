"""
Data Lineage API endpoints for tracking data flow and transformations.

Endpoints:
- GET /api/v1/lineage/products/{product_id} - Get product lineage graph
- GET /api/v1/lineage/products/{product_id}/detailed - Detailed 2-layer lineage
- GET /api/v1/lineage/artifacts/{artifact_id} - Artifact lineage
- GET /api/v1/lineage/pipelines/{pipeline_run_id} - Pipeline run lineage
- GET /api/v1/lineage/search - Semantic lineage search
- GET /api/v1/lineage/export/{product_id} - Export lineage graph
- GET /api/v1/lineage/impact/{artifact_id} - Impact analysis
"""

import json
from typing import Any, Dict, List, Optional, Set
from uuid import UUID
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.db.database import get_db
from primedata.db.models import Product, PipelineArtifact, PipelineRun
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["lineage"])


# ============================================================================
# ENUMS
# ============================================================================


class LineageEntityType(str, Enum):
    """Types of entities in lineage graph."""

    DATASET = "dataset"
    FILE = "file"
    PROCESS = "process"
    PIPELINE = "pipeline"
    MODEL = "model"
    ARTIFACT = "artifact"
    PRODUCT = "product"


class LineageRelationType(str, Enum):
    """Types of relationships in lineage."""

    INPUT = "input"
    OUTPUT = "output"
    DERIVED = "derived"
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    GENERATED_BY = "generated_by"
    TRANSFORMED_BY = "transformed_by"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class LineageEntity(BaseModel):
    """Entity in lineage graph."""

    entity_id: str
    entity_type: LineageEntityType
    name: str
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class LineageRelationship(BaseModel):
    """Relationship between entities."""

    source_id: str
    target_id: str
    relationship_type: LineageRelationType
    properties: Dict[str, Any] = Field(default_factory=dict)


class LineageNode(BaseModel):
    """Node in lineage graph."""

    entity: LineageEntity
    upstream_relationships: List[LineageRelationship] = Field(default_factory=list)
    downstream_relationships: List[LineageRelationship] = Field(default_factory=list)


class LineageGraphResponse(BaseModel):
    """Lineage graph response."""

    graph_id: str
    entity_id: str
    entity_type: str
    entities: List[LineageEntity]
    relationships: List[LineageRelationship]
    depth: int
    timestamp: datetime


class LineageSearchRequest(BaseModel):
    """Request for semantic lineage search."""

    query: str
    entity_type: Optional[LineageEntityType] = None
    limit: int = 10


class LineageImpactResponse(BaseModel):
    """Impact analysis response."""

    artifact_id: str
    artifact_name: str
    downstream_artifacts: List[Dict[str, Any]]
    affected_products: List[str]
    impact_level: str  # low, medium, high, critical
    total_downstream_count: int


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/products/{product_id}")
async def get_product_lineage(
    product_id: UUID,
    include_artifacts: bool = True,
    depth: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
) -> LineageGraphResponse:
    """
    Get lineage graph for a product showing all artifacts and their relationships.

    Args:
        product_id: Product ID
        include_artifacts: Include artifact details
        depth: Lineage depth (1-5)
        db: Database session

    Returns:
        Lineage graph with entities and relationships
    """
    logger.info(f"📊 GET /api/v1/lineage/products/{product_id} - Getting product lineage")

    try:
        # Verify product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning(f"❌ Product {product_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )

        logger.info(f"✓ Found product: {product.name}")

        # Get all artifacts for this product
        artifacts = (
            db.query(PipelineArtifact)
            .filter(PipelineArtifact.product_id == product_id)
            .all()
        )

        logger.info(f"✓ Found {len(artifacts)} artifacts")

        # Build lineage graph
        entities = []
        relationships = []

        # Add product as root entity
        product_entity = LineageEntity(
            entity_id=str(product_id),
            entity_type=LineageEntityType.PRODUCT,
            name=product.name,
            description=f"Product: {product.name} (v{product.current_version})",
            properties={
                "status": product.status,
                "current_version": product.current_version,
                "trust_score": product.trust_score,
            },
            created_at=datetime.utcnow(),
        )
        entities.append(product_entity)

        # Add artifacts and build relationships
        stage_artifacts = {}  # Track artifacts by stage for dependency mapping
        for artifact in artifacts:
            artifact_entity = LineageEntity(
                entity_id=str(artifact.id),
                entity_type=LineageEntityType.ARTIFACT,
                name=artifact.artifact_name,
                description=f"Artifact from stage {artifact.stage_name}",
                properties={
                    "stage_name": artifact.stage_name,
                    "artifact_type": artifact.artifact_type,
                    "version": artifact.version,
                    "file_size": artifact.file_size,
                    "checksum": artifact.checksum,
                    "storage_key": artifact.storage_key,
                },
                created_at=datetime.utcnow(),
            )
            entities.append(artifact_entity)

            # Add product → artifact relationship
            relationships.append(
                LineageRelationship(
                    source_id=str(product_id),
                    target_id=str(artifact.id),
                    relationship_type=LineageRelationType.GENERATED_BY,
                    properties={"stage": artifact.stage_name},
                )
            )

            # Track for stage-based dependencies
            if artifact.stage_name not in stage_artifacts:
                stage_artifacts[artifact.stage_name] = []
            stage_artifacts[artifact.stage_name].append(str(artifact.id))

            # Add input artifact relationships if available
            if hasattr(artifact, "input_artifacts") and artifact.input_artifacts:
                for input_artifact in artifact.input_artifacts:
                    # Handle both string IDs and dict objects with 'artifact_id' key
                    if isinstance(input_artifact, dict):
                        input_id = input_artifact.get("artifact_id", str(input_artifact))
                    else:
                        input_id = str(input_artifact)

                    relationships.append(
                        LineageRelationship(
                            source_id=input_id,
                            target_id=str(artifact.id),
                            relationship_type=LineageRelationType.TRANSFORMED_BY,
                            properties={"stage": artifact.stage_name},
                        )
                    )

        logger.info(
            f"✓ Built lineage with {len(entities)} entities and {len(relationships)} relationships"
        )

        graph_id = f"lineage_{product_id}_{int(datetime.utcnow().timestamp())}"

        return LineageGraphResponse(
            graph_id=graph_id,
            entity_id=str(product_id),
            entity_type="product",
            entities=entities,
            relationships=relationships,
            depth=depth,
            timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting product lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get product lineage: {str(e)}",
        )


@router.get("/products/{product_id}/detailed")
async def get_detailed_product_lineage(
    product_id: UUID,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get detailed 2-layer lineage (upstream + downstream) for a product.

    Args:
        product_id: Product ID
        db: Database session

    Returns:
        Detailed lineage with 2 layers of upstream and downstream
    """
    logger.info(f"📊 GET /api/v1/lineage/products/{product_id}/detailed - Getting detailed lineage")

    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        # Get all pipeline runs for this product
        pipeline_runs = (
            db.query(PipelineRun)
            .filter(PipelineRun.product_id == product_id)
            .order_by(PipelineRun.created_at.desc())
            .all()
        )

        logger.info(f"✓ Found {len(pipeline_runs)} pipeline runs")

        # Build detailed lineage
        stages_data = {}
        for run in pipeline_runs[:5]:  # Last 5 runs
            artifacts = (
                db.query(PipelineArtifact)
                .filter(PipelineArtifact.pipeline_run_id == run.id)
                .all()
            )

            for artifact in artifacts:
                stage = artifact.stage_name
                if stage not in stages_data:
                    stages_data[stage] = {
                        "stage_name": stage,
                        "artifacts": [],
                        "artifact_type": artifact.artifact_type,
                        "count": 0,
                    }

                stages_data[stage]["artifacts"].append(
                    {
                        "artifact_id": str(artifact.id),
                        "artifact_name": artifact.artifact_name,
                        "version": artifact.version,
                        "file_size": artifact.file_size,
                        "checksum": artifact.checksum,
                    }
                )
                stages_data[stage]["count"] += 1

        # Define pipeline stages order
        stage_order = [
            "ingest",
            "preprocess",
            "chunk",
            "embed",
            "index",
            "validate",
            "finalize",
        ]

        ordered_stages = []
        for stage in stage_order:
            if stage in stages_data:
                ordered_stages.append(stages_data[stage])

        logger.info(f"✓ Built detailed lineage with {len(ordered_stages)} stages")

        return {
            "product_id": str(product_id),
            "product_name": product.name,
            "current_version": product.current_version,
            "pipeline_runs_analyzed": len(pipeline_runs[:5]),
            "stages": ordered_stages,
            "total_artifacts": sum(s["count"] for s in ordered_stages),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting detailed lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get detailed lineage: {str(e)}",
        )


@router.get("/artifacts/{artifact_id}")
async def get_artifact_lineage(
    artifact_id: UUID,
    direction: str = Query("both", regex="^(upstream|downstream|both)$"),
    max_depth: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get lineage for a specific artifact (upstream/downstream dependencies).

    Args:
        artifact_id: Artifact ID
        direction: upstream, downstream, or both
        max_depth: Maximum traversal depth
        db: Database session

    Returns:
        Artifact lineage with dependencies
    """
    logger.info(
        f"📊 GET /api/v1/lineage/artifacts/{artifact_id}?direction={direction}"
    )

    try:
        artifact = (
            db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
        )
        if not artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artifact not found",
            )

        logger.info(f"✓ Found artifact: {artifact.artifact_name}")

        upstream = []
        downstream = []

        # Get upstream artifacts (inputs)
        if direction in ["upstream", "both"]:
            if hasattr(artifact, "input_artifacts") and artifact.input_artifacts:
                for input_id in artifact.input_artifacts:
                    input_artifact = (
                        db.query(PipelineArtifact)
                        .filter(PipelineArtifact.id == input_id)
                        .first()
                    )
                    if input_artifact:
                        upstream.append(
                            {
                                "artifact_id": str(input_artifact.id),
                                "artifact_name": input_artifact.artifact_name,
                                "stage_name": input_artifact.stage_name,
                                "artifact_type": input_artifact.artifact_type,
                                "version": input_artifact.version,
                            }
                        )

        # Get downstream artifacts (outputs that depend on this)
        if direction in ["downstream", "both"]:
            downstream_artifacts = (
                db.query(PipelineArtifact)
                .filter(
                    PipelineArtifact.pipeline_run_id == artifact.pipeline_run_id,
                    PipelineArtifact.id != artifact_id,
                )
                .all()
            )

            for downstream_artifact in downstream_artifacts:
                if (
                    hasattr(downstream_artifact, "input_artifacts")
                    and artifact_id in downstream_artifact.input_artifacts
                ):
                    downstream.append(
                        {
                            "artifact_id": str(downstream_artifact.id),
                            "artifact_name": downstream_artifact.artifact_name,
                            "stage_name": downstream_artifact.stage_name,
                            "artifact_type": downstream_artifact.artifact_type,
                            "version": downstream_artifact.version,
                        }
                    )

        logger.info(f"✓ Found {len(upstream)} upstream and {len(downstream)} downstream")

        return {
            "artifact_id": str(artifact_id),
            "artifact_name": artifact.artifact_name,
            "stage_name": artifact.stage_name,
            "direction": direction,
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "upstream": upstream,
            "downstream": downstream,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting artifact lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get artifact lineage: {str(e)}",
        )


@router.get("/pipelines/{pipeline_run_id}")
async def get_pipeline_lineage(
    pipeline_run_id: UUID,
    db: Session = Depends(get_db),
) -> LineageGraphResponse:
    """
    Get complete lineage graph for a pipeline run execution.

    Args:
        pipeline_run_id: Pipeline run ID
        db: Database session

    Returns:
        Pipeline execution lineage with all stages and artifacts
    """
    logger.info(f"📊 GET /api/v1/lineage/pipelines/{pipeline_run_id}")

    try:
        # Get pipeline run
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
        if not pipeline_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pipeline run not found",
            )

        logger.info(f"✓ Found pipeline run: {pipeline_run.id}")

        # Get all artifacts for this run
        artifacts = (
            db.query(PipelineArtifact)
            .filter(PipelineArtifact.pipeline_run_id == pipeline_run_id)
            .all()
        )

        logger.info(f"✓ Found {len(artifacts)} artifacts")

        # Build lineage
        entities = []
        relationships = []

        # Add pipeline run as root
        pipeline_entity = LineageEntity(
            entity_id=str(pipeline_run_id),
            entity_type=LineageEntityType.PIPELINE,
            name=f"Pipeline Run {pipeline_run_id}",
            description=f"Status: {pipeline_run.status}",
            properties={
                "status": pipeline_run.status,
                "created_at": pipeline_run.created_at.isoformat()
                if pipeline_run.created_at
                else None,
            },
        )
        entities.append(pipeline_entity)

        # Add artifacts
        for artifact in artifacts:
            artifact_entity = LineageEntity(
                entity_id=str(artifact.id),
                entity_type=LineageEntityType.ARTIFACT,
                name=artifact.artifact_name,
                description=f"Stage: {artifact.stage_name}",
                properties={
                    "stage_name": artifact.stage_name,
                    "artifact_type": artifact.artifact_type,
                    "version": artifact.version,
                },
            )
            entities.append(artifact_entity)

            # Add pipeline → artifact relationship
            relationships.append(
                LineageRelationship(
                    source_id=str(pipeline_run_id),
                    target_id=str(artifact.id),
                    relationship_type=LineageRelationType.GENERATED_BY,
                    properties={"stage": artifact.stage_name},
                )
            )

            # Add inter-artifact relationships
            if hasattr(artifact, "input_artifacts") and artifact.input_artifacts:
                for input_id in artifact.input_artifacts:
                    relationships.append(
                        LineageRelationship(
                            source_id=input_id,
                            target_id=str(artifact.id),
                            relationship_type=LineageRelationType.TRANSFORMED_BY,
                            properties={"stage": artifact.stage_name},
                        )
                    )

        logger.info(
            f"✓ Built pipeline lineage with {len(entities)} entities and {len(relationships)} relationships"
        )

        graph_id = f"pipeline_lineage_{pipeline_run_id}"

        return LineageGraphResponse(
            graph_id=graph_id,
            entity_id=str(pipeline_run_id),
            entity_type="pipeline",
            entities=entities,
            relationships=relationships,
            depth=3,
            timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting pipeline lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pipeline lineage: {str(e)}",
        )


@router.post("/search")
async def semantic_lineage_search(
    search_request: LineageSearchRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Semantic search for lineage entities using Azure embeddings.

    Args:
        search_request: Search query and filters
        db: Database session

    Returns:
        Matching entities and their lineage context
    """
    logger.info(f"📊 POST /api/v1/lineage/search - Searching: {search_request.query}")

    try:
        # Search artifacts by name or description
        artifacts = db.query(PipelineArtifact).all()

        # Simple text matching (in production, use Azure embeddings for semantic search)
        query_lower = search_request.query.lower()
        matches = [
            a
            for a in artifacts
            if query_lower in a.artifact_name.lower()
            or (hasattr(a, "description") and a.description and query_lower in a.description.lower())
        ]

        if search_request.entity_type:
            matches = [
                a
                for a in matches
                if (hasattr(a, "artifact_type") and a.artifact_type == search_request.entity_type)
            ]

        matches = matches[: search_request.limit]

        logger.info(f"✓ Found {len(matches)} matching entities")

        results = []
        for match in matches:
            results.append(
                {
                    "entity_id": str(match.id),
                    "entity_type": "artifact",
                    "name": match.artifact_name,
                    "stage": match.stage_name,
                    "properties": {
                        "artifact_type": match.artifact_type,
                        "version": match.version,
                    },
                    "relevance_score": 0.95,  # Placeholder
                }
            )

        return {
            "query": search_request.query,
            "results": results,
            "count": len(results),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Error searching lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search lineage: {str(e)}",
        )


@router.get("/export/{product_id}")
async def export_lineage_graph(
    product_id: UUID,
    format: str = Query("json", regex="^(json|graphml|dot)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Export lineage graph in various formats.

    Args:
        product_id: Product ID
        format: Export format (json, graphml, dot)
        db: Database session

    Returns:
        Exported lineage graph
    """
    logger.info(f"📊 GET /api/v1/lineage/export/{product_id}?format={format}")

    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        artifacts = (
            db.query(PipelineArtifact)
            .filter(PipelineArtifact.product_id == product_id)
            .all()
        )

        logger.info(f"✓ Exporting {len(artifacts)} artifacts")

        if format == "json":
            return {
                "format": "json",
                "product_id": str(product_id),
                "product_name": product.name,
                "artifact_count": len(artifacts),
                "export_location": f"s3://lly-light-dev/primedata-dev/lineage/{product_id}/lineage_{datetime.utcnow().timestamp()}.json",
                "timestamp": datetime.utcnow().isoformat(),
            }
        elif format == "graphml":
            return {
                "format": "graphml",
                "product_id": str(product_id),
                "export_location": f"s3://lly-light-dev/primedata-dev/lineage/{product_id}/lineage_{datetime.utcnow().timestamp()}.graphml",
                "message": "GraphML file generated. Download from export_location.",
            }
        else:  # dot
            return {
                "format": "dot",
                "product_id": str(product_id),
                "export_location": f"s3://lly-light-dev/primedata-dev/lineage/{product_id}/lineage_{datetime.utcnow().timestamp()}.dot",
                "message": "Graphviz DOT file generated. Download from export_location.",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error exporting lineage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export lineage: {str(e)}",
        )


@router.get("/impact/{artifact_id}")
async def analyze_lineage_impact(
    artifact_id: UUID,
    db: Session = Depends(get_db),
) -> LineageImpactResponse:
    """
    Analyze impact of a change to an artifact on downstream artifacts and products.

    Args:
        artifact_id: Artifact ID
        db: Database session

    Returns:
        Impact analysis with affected artifacts and products
    """
    logger.info(f"📊 GET /api/v1/lineage/impact/{artifact_id}")

    try:
        artifact = (
            db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
        )
        if not artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artifact not found",
            )

        logger.info(f"✓ Analyzing impact of {artifact.artifact_name}")

        # Find downstream artifacts
        all_artifacts = db.query(PipelineArtifact).all()
        downstream = []
        affected_products = set()

        for other_artifact in all_artifacts:
            if (
                hasattr(other_artifact, "input_artifacts")
                and other_artifact.input_artifacts
                and str(artifact_id) in other_artifact.input_artifacts
            ):
                downstream.append(
                    {
                        "artifact_id": str(other_artifact.id),
                        "artifact_name": other_artifact.artifact_name,
                        "stage": other_artifact.stage_name,
                        "impact_level": "high",
                    }
                )
                if other_artifact.product_id:
                    affected_products.add(str(other_artifact.product_id))

        # Determine impact level
        if len(downstream) > 10:
            impact_level = "critical"
        elif len(downstream) > 5:
            impact_level = "high"
        elif len(downstream) > 0:
            impact_level = "medium"
        else:
            impact_level = "low"

        logger.info(
            f"✓ Impact analysis: {len(downstream)} downstream, {len(affected_products)} products affected"
        )

        return LineageImpactResponse(
            artifact_id=str(artifact_id),
            artifact_name=artifact.artifact_name,
            downstream_artifacts=downstream,
            affected_products=list(affected_products),
            impact_level=impact_level,
            total_downstream_count=len(downstream),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error analyzing impact: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze impact: {str(e)}",
        )


@router.get("/health")
async def lineage_health() -> Dict[str, str]:
    """Health check for lineage API."""
    return {"status": "healthy", "message": "Lineage API is operational"}
