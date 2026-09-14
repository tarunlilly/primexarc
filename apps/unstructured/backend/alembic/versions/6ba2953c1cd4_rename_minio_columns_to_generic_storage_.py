"""rename_minio_columns_to_generic_storage_names

Revision ID: 6ba2953c1cd4
Revises: 
Create Date: 2025-01-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ba2953c1cd4'
down_revision: Union[str, None] = 'ccf903091f0c'  # Previous migration: add_workspace_indexes_for_security
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Rename MinIO-specific columns to generic storage column names.

    Changes:
    - raw_files: minio_key -> storage_key, minio_bucket -> storage_bucket, minio_etag -> storage_etag
    - pipeline_artifacts: minio_key -> storage_key, minio_bucket -> storage_bucket, minio_etag -> storage_etag
    - Update index names to match new column names

    Idempotent: checks column/index existence before renaming to handle databases
    where this migration was already partially applied.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Rename columns in raw_files table (only if minio columns still exist)
    raw_cols = [c['name'] for c in inspector.get_columns('raw_files')]
    if 'minio_key' in raw_cols:
        op.alter_column('raw_files', 'minio_key', new_column_name='storage_key')
    if 'minio_bucket' in raw_cols:
        op.alter_column('raw_files', 'minio_bucket', new_column_name='storage_bucket')
    if 'minio_etag' in raw_cols:
        op.alter_column('raw_files', 'minio_etag', new_column_name='storage_etag')

    # Rename columns in pipeline_artifacts table (only if minio columns still exist)
    artifact_cols = [c['name'] for c in inspector.get_columns('pipeline_artifacts')]
    if 'minio_key' in artifact_cols:
        op.alter_column('pipeline_artifacts', 'minio_key', new_column_name='storage_key')
    if 'minio_bucket' in artifact_cols:
        op.alter_column('pipeline_artifacts', 'minio_bucket', new_column_name='storage_bucket')
    if 'minio_etag' in artifact_cols:
        op.alter_column('pipeline_artifacts', 'minio_etag', new_column_name='storage_etag')

    # Rename index on pipeline_artifacts (only if old index still exists)
    existing_indexes = [i['name'] for i in inspector.get_indexes('pipeline_artifacts')]
    if 'idx_artifacts_minio_key' in existing_indexes:
        op.drop_index('idx_artifacts_minio_key', table_name='pipeline_artifacts')
    if 'idx_artifacts_storage_key' not in existing_indexes:
        op.create_index('idx_artifacts_storage_key', 'pipeline_artifacts', ['storage_key'])


def downgrade() -> None:
    """
    Revert column names back to MinIO-specific names.
    """
    # Rename index back
    op.drop_index('idx_artifacts_storage_key', table_name='pipeline_artifacts')
    op.create_index('idx_artifacts_minio_key', 'pipeline_artifacts', ['minio_key'])
    
    # Rename columns in pipeline_artifacts table back
    op.alter_column('pipeline_artifacts', 'storage_key', new_column_name='minio_key')
    op.alter_column('pipeline_artifacts', 'storage_bucket', new_column_name='minio_bucket')
    op.alter_column('pipeline_artifacts', 'storage_etag', new_column_name='minio_etag')
    
    # Rename columns in raw_files table back
    op.alter_column('raw_files', 'storage_key', new_column_name='minio_key')
    op.alter_column('raw_files', 'storage_bucket', new_column_name='minio_bucket')
    op.alter_column('raw_files', 'storage_etag', new_column_name='minio_etag')
