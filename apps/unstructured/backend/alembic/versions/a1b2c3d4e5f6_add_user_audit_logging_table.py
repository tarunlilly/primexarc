"""Add user audit logging table

Revision ID: a1b2c3d4e5f6
Revises: f3d3928ec4ad
Create Date: 2026-03-26 16:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f3d3928ec4ad'
branch_labels = None
depends_on = None


def table_exists(table_name, schema='public'):
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names(schema=schema)


def upgrade() -> None:
    """Create user_audit_logs table."""
    if not table_exists('user_audit_logs', schema='public'):
        op.create_table(
            'user_audit_logs',
            sa.Column('id', PG_UUID(as_uuid=True), nullable=False),
            sa.Column('workspace_id', PG_UUID(as_uuid=True), nullable=True, index=True),
            sa.Column('user_id', sa.String(length=255), nullable=True, index=True),
            sa.Column('action', sa.String(length=100), nullable=False, index=True),
            sa.Column('resource_type', sa.String(length=100), nullable=False, index=True),
            sa.Column('resource_id', sa.String(length=255), nullable=False, index=True),
            sa.Column('changes', JSONB(), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, index=True, server_default='success'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('audit_metadata', JSONB(), nullable=True),
            sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, index=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.ForeignKeyConstraint(['user_id'], ['public.users.id'], ),
            sa.ForeignKeyConstraint(['workspace_id'], ['public.workspaces.id'], ),
            sa.PrimaryKeyConstraint('id'),
            schema='public'
        )

        # Create indexes for efficient querying
        op.create_index(
            'idx_user_audit_user_id_timestamp',
            'user_audit_logs',
            ['user_id', 'timestamp'],
            schema='public'
        )
        op.create_index(
            'idx_user_audit_workspace_timestamp',
            'user_audit_logs',
            ['workspace_id', 'timestamp'],
            schema='public'
        )
        op.create_index(
            'idx_user_audit_action_timestamp',
            'user_audit_logs',
            ['action', 'timestamp'],
            schema='public'
        )
        op.create_index(
            'idx_user_audit_resource_type_id',
            'user_audit_logs',
            ['resource_type', 'resource_id'],
            schema='public'
        )


def downgrade() -> None:
    """Drop user_audit_logs table."""
    if table_exists('user_audit_logs', schema='public'):
        # Drop indexes first
        op.drop_index('idx_user_audit_resource_type_id', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_user_audit_action_timestamp', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_user_audit_workspace_timestamp', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_user_audit_user_id_timestamp', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_user_id', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_workspace_id', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_action', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_resource_type', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_status', table_name='user_audit_logs', schema='public')
        op.drop_index('idx_timestamp', table_name='user_audit_logs', schema='public')

        # Drop table
        op.drop_table('user_audit_logs', schema='public')
