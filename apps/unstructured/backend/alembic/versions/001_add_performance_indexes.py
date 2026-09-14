"""add_performance_indexes

Revision ID: 001_perf_idx
Revises: f3d3928ec4ad
Create Date: 2026-02-13

Performance optimization: Add composite indexes for frequently queried patterns.
Targets: Analytics dashboard, product listings, violation lookups.

Expected impact: 5-10x faster queries on common patterns.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '001_perf_idx'
down_revision = 'f3d3928ec4ad'
branch_labels = None
depends_on = None


def index_exists(index_name, table_name):
    """Check if an index exists on a table."""
    try:
        bind = op.get_bind()
        inspector = inspect(bind)
        indices = [idx['name'] for idx in inspector.get_indexes(table_name)]
        return index_name in indices
    except Exception:
        return False


def upgrade() -> None:
    """Add composite indexes for performance optimization."""

    # 1. Pipeline artifacts: frequently queried by (product_id, version, artifact_type)
    # Used in: products.py artifacts endpoint, analytics.py dashboard
    if not index_exists('idx_pipeline_artifacts_product_version_type', 'pipeline_artifacts'):
        op.create_index(
            'idx_pipeline_artifacts_product_version_type',
            'pipeline_artifacts',
            ['product_id', 'version', 'artifact_type'],
            unique=False
        )

    # 2. Raw files: frequently queried by (product_id, version, status)
    # Used in: datasources.py file listing, analytics.py
    if not index_exists('idx_raw_files_product_version_status', 'raw_files'):
        op.create_index(
            'idx_raw_files_product_version_status',
            'raw_files',
            ['product_id', 'version', 'status'],
            unique=False
        )

    # 3. DQ violations: dashboard queries by (product_id, severity)
    # Used in: analytics.py violations dashboard
    if not index_exists('idx_dq_violations_product_severity', 'dq_violations'):
        op.create_index(
            'idx_dq_violations_product_severity',
            'dq_violations',
            ['product_id', 'severity'],
            unique=False
        )

    # 4. Pipeline runs: recent runs query by (workspace_id, status, created_at DESC)
    # Used in: pipeline.py monitoring endpoint, analytics.py
    if not index_exists('idx_pipeline_runs_workspace_status_created', 'pipeline_runs'):
        op.create_index(
            'idx_pipeline_runs_workspace_status_created',
            'pipeline_runs',
            ['workspace_id', 'status', 'created_at'],
            unique=False
        )


def downgrade() -> None:
    """Remove performance indexes."""

    op.drop_index(
        'idx_pipeline_artifacts_product_version_type',
        table_name='pipeline_artifacts',
        if_exists=True
    )
    op.drop_index(
        'idx_raw_files_product_version_status',
        table_name='raw_files',
        if_exists=True
    )
    op.drop_index(
        'idx_dq_violations_product_severity',
        table_name='dq_violations',
        if_exists=True
    )
    op.drop_index(
        'idx_pipeline_runs_workspace_status_created',
        table_name='pipeline_runs',
        if_exists=True
    )
