"""
Artifact Analytics - Phase 4

Advanced features for artifact management:
- Comparison tools (compare artifacts across runs)
- Version diffing
- Cost analytics
- Automated cleanup recommendations
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)
from primedata.db.models import ArtifactStatus, ArtifactType, PipelineArtifact
from primedata.ingestion_pipeline.artifact_registry import RetentionPolicy, get_artifact_lineage
from sqlalchemy.orm import Session


def compare_artifacts(
    db: Session,
    artifact_id_1: UUID,
    artifact_id_2: UUID,
) -> Dict[str, Any]:
    """
    Compare two artifacts (Phase 4: comparison tools).

    Args:
        db: Database session
        artifact_id_1: First artifact ID
        artifact_id_2: Second artifact ID

    Returns:
        Dictionary with comparison results
    """
    logger.info(f"📊 ENTRY: compare_artifacts(id1={artifact_id_1}, id2={artifact_id_2})")
    try:
        logger.debug(f"   💾 Retrieving artifact {artifact_id_1}")
        artifact1 = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id_1).first()
        logger.debug(f"   💾 Retrieving artifact {artifact_id_2}")
        artifact2 = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id_2).first()

        if not artifact1 or not artifact2:
            error_msg = "One or both artifacts not found"
            logger.error(f"   ❌ {error_msg}: a1={artifact1 is not None}, a2={artifact2 is not None}")
            raise ValueError(error_msg)

        comparison = {
            "artifact1": {
                "id": str(artifact1.id),
                "stage": artifact1.stage_name,
                "name": artifact1.artifact_name,
                "type": artifact1.artifact_type.value,
                "size": artifact1.file_size,
                "created_at": artifact1.created_at.isoformat() if artifact1.created_at else None,
            },
            "artifact2": {
                "id": str(artifact2.id),
                "stage": artifact2.stage_name,
                "name": artifact2.artifact_name,
                "type": artifact2.artifact_type.value,
                "size": artifact2.file_size,
                "created_at": artifact2.created_at.isoformat() if artifact2.created_at else None,
            },
            "differences": {
                "size_diff_bytes": artifact1.file_size - artifact2.file_size,
                "size_diff_percent": ((artifact1.file_size - artifact2.file_size) / max(artifact2.file_size, 1)) * 100,
                "same_stage": artifact1.stage_name == artifact2.stage_name,
                "same_type": artifact1.artifact_type == artifact2.artifact_type,
                "age_diff_days": (
                    (artifact1.created_at - artifact2.created_at).days if artifact1.created_at and artifact2.created_at else None
                ),
            },
        }

        logger.debug(f"   ✅ Size diff: {comparison['differences']['size_diff_bytes']} bytes ({comparison['differences']['size_diff_percent']:.2f}%)")
        logger.info(f"✅ EXIT: compare_artifacts() -> Comparison computed")

        return comparison
    except Exception as e:
        logger.error(f"   ❌ Error comparing artifacts: {e}", exc_info=True)
        raise


def compare_pipeline_runs(
    db: Session,
    pipeline_run_id_1: UUID,
    pipeline_run_id_2: UUID,
) -> Dict[str, Any]:
    """
    Compare artifacts between two pipeline runs (Phase 4: version diffing).

    Args:
        db: Database session
        pipeline_run_id_1: First pipeline run ID
        pipeline_run_id_2: Second pipeline run ID

    Returns:
        Dictionary with comparison results
    """
    logger.info(f"📊 ENTRY: compare_pipeline_runs(run1={pipeline_run_id_1}, run2={pipeline_run_id_2})")
    try:
        logger.debug(f"   💾 Querying artifacts for run {pipeline_run_id_1}")
        artifacts1 = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.pipeline_run_id == pipeline_run_id_1,
                PipelineArtifact.status != ArtifactStatus.PURGED,
            )
            .all()
        )

        logger.debug(f"   💾 Querying artifacts for run {pipeline_run_id_2}")
        artifacts2 = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.pipeline_run_id == pipeline_run_id_2,
                PipelineArtifact.status != ArtifactStatus.PURGED,
            )
            .all()
        )
        logger.debug(f"   ✅ Run 1: {len(artifacts1)} artifacts, Run 2: {len(artifacts2)} artifacts")

        # Group by stage and artifact name
        artifacts1_by_stage = {}
        artifacts2_by_stage = {}

        for a in artifacts1:
            key = f"{a.stage_name}:{a.artifact_name}"
            if key not in artifacts1_by_stage:
                artifacts1_by_stage[key] = []
            artifacts1_by_stage[key].append(a)

        for a in artifacts2:
            key = f"{a.stage_name}:{a.artifact_name}"
            if key not in artifacts2_by_stage:
                artifacts2_by_stage[key] = []
            artifacts2_by_stage[key].append(a)

        comparison = {
            "run1": {
                "pipeline_run_id": str(pipeline_run_id_1),
                "total_artifacts": len(artifacts1),
                "total_size_bytes": sum(a.file_size for a in artifacts1),
                "by_stage": {k: len(v) for k, v in artifacts1_by_stage.items()},
            },
            "run2": {
                "pipeline_run_id": str(pipeline_run_id_2),
                "total_artifacts": len(artifacts2),
                "total_size_bytes": sum(a.file_size for a in artifacts2),
                "by_stage": {k: len(v) for k, v in artifacts2_by_stage.items()},
            },
            "differences": {
                "artifact_count_diff": len(artifacts1) - len(artifacts2),
                "size_diff_bytes": sum(a.file_size for a in artifacts1) - sum(a.file_size for a in artifacts2),
                "stages_in_run1_only": set(artifacts1_by_stage.keys()) - set(artifacts2_by_stage.keys()),
                "stages_in_run2_only": set(artifacts2_by_stage.keys()) - set(artifacts1_by_stage.keys()),
                "common_stages": set(artifacts1_by_stage.keys()) & set(artifacts2_by_stage.keys()),
            },
        }

        logger.debug(f"   📋 Differences: count_diff={comparison['differences']['artifact_count_diff']}, size_diff={comparison['differences']['size_diff_bytes']} bytes")
        logger.info(f"✅ EXIT: compare_pipeline_runs() -> Comparison computed")

        return comparison
    except Exception as e:
        logger.error(f"   ❌ Error comparing pipeline runs: {e}", exc_info=True)
        raise


def get_cost_analytics(
    db: Session,
    product_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Get cost analytics for artifacts (Phase 4: cost analytics).

    Args:
        db: Database session
        product_id: Optional product ID to filter
        workspace_id: Optional workspace ID to filter
        days: Number of days to analyze

    Returns:
        Dictionary with cost analytics
    """
    logger.info(f"💾 ENTRY: get_cost_analytics(product_id={product_id}, workspace_id={workspace_id}, days={days})")
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        logger.debug(f"   📋 Analysis period: {cutoff_date} to now")

        logger.debug(f"   💾 Querying artifacts")
        query = db.query(PipelineArtifact).filter(
            PipelineArtifact.created_at >= cutoff_date,
            PipelineArtifact.status == ArtifactStatus.ACTIVE,
        )

        if product_id:
            query = query.filter(PipelineArtifact.product_id == product_id)
            logger.debug(f"   📋 Filtered by product_id={product_id}")
        if workspace_id:
            query = query.filter(PipelineArtifact.workspace_id == workspace_id)
            logger.debug(f"   📋 Filtered by workspace_id={workspace_id}")

        artifacts = query.all()
        logger.debug(f"   ✅ Retrieved {len(artifacts)} artifacts")

        # Group by type, stage, retention policy
        by_type = {}
        by_stage = {}
        by_retention = {}
        total_size = 0

        for artifact in artifacts:
            total_size += artifact.file_size

            # By type
            type_key = artifact.artifact_type.value
            if type_key not in by_type:
                by_type[type_key] = {"count": 0, "total_size_bytes": 0}
            by_type[type_key]["count"] += 1
            by_type[type_key]["total_size_bytes"] += artifact.file_size

            # By stage
            stage_key = artifact.stage_name
            if stage_key not in by_stage:
                by_stage[stage_key] = {"count": 0, "total_size_bytes": 0}
            by_stage[stage_key]["count"] += 1
            by_stage[stage_key]["total_size_bytes"] += artifact.file_size

            # By retention
            retention_key = artifact.retention_policy.value
            if retention_key not in by_retention:
                by_retention[retention_key] = {"count": 0, "total_size_bytes": 0}
            by_retention[retention_key]["count"] += 1
            by_retention[retention_key]["total_size_bytes"] += artifact.file_size

        logger.debug(f"   📊 Aggregated by {len(by_type)} types, {len(by_stage)} stages, {len(by_retention)} retention policies")

        # Estimate storage cost (rough estimate: $0.023 per GB per month for S3 standard)
        # This is a simplified calculation
        gb_stored = total_size / (1024**3)
        estimated_monthly_cost_usd = gb_stored * 0.023

        logger.debug(f"   💾 Storage: {gb_stored:.2f} GB, Estimated cost: ${estimated_monthly_cost_usd:.2f}/month")

        analytics = {
            "period_days": days,
            "total_artifacts": len(artifacts),
            "total_size_bytes": total_size,
            "total_size_gb": round(gb_stored, 2),
            "estimated_monthly_cost_usd": round(estimated_monthly_cost_usd, 2),
            "by_type": by_type,
            "by_stage": by_stage,
            "by_retention_policy": by_retention,
            "top_artifacts_by_size": sorted(
                [{"id": str(a.id), "name": a.artifact_name, "stage": a.stage_name, "size_bytes": a.file_size} for a in artifacts],
                key=lambda x: x["size_bytes"],
                reverse=True,
            )[:10],
        }

        logger.info(f"✅ EXIT: get_cost_analytics() -> {len(artifacts)} artifacts, {gb_stored:.2f} GB, ${estimated_monthly_cost_usd:.2f}/month")

        return analytics
    except Exception as e:
        logger.error(f"   ❌ Error calculating cost analytics: {e}", exc_info=True)
        raise


def get_cleanup_recommendations(
    db: Session,
    product_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Get automated cleanup recommendations (Phase 4).

    Analyzes artifacts and recommends which ones can be archived/deleted.

    Args:
        db: Database session
        product_id: Optional product ID to filter
        workspace_id: Optional workspace ID to filter

    Returns:
        List of recommendations
    """
    logger.info(f"📊 ENTRY: get_cleanup_recommendations(product_id={product_id}, workspace_id={workspace_id})")
    try:
        recommendations = []

        # Find artifacts that are older than their retention policy
        policies_to_check = [
            (RetentionPolicy.DAYS_30, 30),
            (RetentionPolicy.DAYS_90, 90),
            (RetentionPolicy.DAYS_365, 365),
        ]

        logger.debug(f"   📋 Checking {len(policies_to_check)} retention policies")

        for policy, days in policies_to_check:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            query = db.query(PipelineArtifact).filter(
                PipelineArtifact.retention_policy == policy,
                PipelineArtifact.status == ArtifactStatus.ACTIVE,
                PipelineArtifact.created_at < cutoff_date,
            )

            if product_id:
                query = query.filter(PipelineArtifact.product_id == product_id)
            if workspace_id:
                query = query.filter(PipelineArtifact.workspace_id == workspace_id)

            artifacts = query.all()

            if artifacts:
                total_size = sum(a.file_size for a in artifacts)
                logger.debug(f"   📋 Policy {policy.value}: {len(artifacts)} artifacts, {total_size} bytes")
                recommendations.append(
                    {
                        "action": "archive",
                        "reason": f"Artifacts older than {days} days (retention policy: {policy.value})",
                        "artifact_count": len(artifacts),
                        "total_size_bytes": total_size,
                        "total_size_gb": round(total_size / (1024**3), 2),
                        "estimated_cost_savings_usd": round((total_size / (1024**3)) * 0.023, 2),
                        "policy": policy.value,
                    }
                )

        # Find duplicate artifacts (same stage, name, size - potential duplicates)
        logger.debug(f"   📋 Scanning for duplicate artifacts")
        query = db.query(
            PipelineArtifact.stage_name,
            PipelineArtifact.artifact_name,
            PipelineArtifact.file_size,
            PipelineArtifact.storage_key,
        ).filter(
            PipelineArtifact.status == ArtifactStatus.ACTIVE,
        )

        if product_id:
            query = query.filter(PipelineArtifact.product_id == product_id)
        if workspace_id:
            query = query.filter(PipelineArtifact.workspace_id == workspace_id)

        # This is a simplified check - in production, you'd want to check checksums
        artifacts_by_key = {}
        for row in query.all():
            key = f"{row.stage_name}:{row.artifact_name}:{row.file_size}"
            if key not in artifacts_by_key:
                artifacts_by_key[key] = []
            artifacts_by_key[key].append(row.storage_key)

        duplicates = {k: v for k, v in artifacts_by_key.items() if len(v) > 1}
        if duplicates:
            logger.debug(f"   ⚠️  Found {len(duplicates)} duplicate groups")
            recommendations.append(
                {
                    "action": "review_duplicates",
                    "reason": "Potential duplicate artifacts found (same stage, name, size)",
                    "duplicate_groups": len(duplicates),
                    "total_duplicates": sum(len(v) - 1 for v in duplicates.values()),
                }
            )

        logger.info(f"✅ EXIT: get_cleanup_recommendations() -> {len(recommendations)} recommendations")

        return recommendations
    except Exception as e:
        logger.error(f"   ❌ Error generating cleanup recommendations: {e}", exc_info=True)
        raise


def get_artifact_lineage_graph(
    db: Session,
    artifact_id: UUID,
    max_depth: int = 5,
) -> Dict[str, Any]:
    """
    Get full lineage graph for an artifact (Phase 4: advanced lineage).

    Traverses both upstream and downstream to build a complete dependency graph.

    Args:
        db: Database session
        artifact_id: Root artifact ID
        max_depth: Maximum depth to traverse

    Returns:
        Dictionary with lineage graph
    """
    logger.info(f"📊 ENTRY: get_artifact_lineage_graph(artifact_id={artifact_id}, max_depth={max_depth})")
    try:
        visited = set()
        graph = {
            "root_artifact_id": str(artifact_id),
            "upstream": [],
            "downstream": [],
            "total_depth": 0,
        }

        logger.debug(f"   🔗 Building artifact lineage graph")

        def traverse_upstream(artifact_id: UUID, depth: int = 0):
            if depth >= max_depth or artifact_id in visited:
                return

            visited.add(artifact_id)
            logger.debug(f"   📋 Traversing upstream at depth {depth}")
            upstream = get_artifact_lineage(db, artifact_id, direction="upstream")

            for up_artifact in upstream:
                graph["upstream"].append(
                    {
                        "artifact_id": str(up_artifact.id),
                        "stage": up_artifact.stage_name,
                        "name": up_artifact.artifact_name,
                        "depth": depth,
                    }
                )
                traverse_upstream(up_artifact.id, depth + 1)

        def traverse_downstream(artifact_id: UUID, depth: int = 0):
            if depth >= max_depth or artifact_id in visited:
                return

            visited.add(artifact_id)
            logger.debug(f"   📋 Traversing downstream at depth {depth}")
            downstream = get_artifact_lineage(db, artifact_id, direction="downstream")

            for down_artifact in downstream:
                graph["downstream"].append(
                    {
                        "artifact_id": str(down_artifact.id),
                        "stage": down_artifact.stage_name,
                        "name": down_artifact.artifact_name,
                        "depth": depth,
                    }
                )
                traverse_downstream(down_artifact.id, depth + 1)

        logger.debug(f"   📋 Starting upstream traversal")
        traverse_upstream(artifact_id, 0)
        visited.clear()
        logger.debug(f"   📋 Starting downstream traversal")
        traverse_downstream(artifact_id, 0)

        graph["total_depth"] = max(
            max((item["depth"] for item in graph["upstream"]), default=0),
            max((item["depth"] for item in graph["downstream"]), default=0),
        )

        logger.debug(f"   ✅ Graph computed: {len(graph['upstream'])} upstream, {len(graph['downstream'])} downstream, depth={graph['total_depth']}")
        logger.info(f"✅ EXIT: get_artifact_lineage_graph() -> Lineage graph with depth {graph['total_depth']}")

        return graph
    except Exception as e:
        logger.error(f"   ❌ Error building lineage graph: {e}", exc_info=True)
        raise
