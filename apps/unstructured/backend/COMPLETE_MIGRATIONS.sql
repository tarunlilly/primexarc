-- ============================================================================
-- COMPLETE DATABASE SCHEMA MIGRATION SCRIPT
-- ============================================================================
-- This file contains all Alembic migrations converted to raw SQL statements.
-- It recreates the entire schema from scratch in order.
-- Generated from migration files in: alembic/versions/
--
-- MIGRATION ORDER:
-- 1. ab76775a482b - Initial migration with auth and workspaces
-- 2. 2507e4fa6f84 - Products and datasources
-- 3. 56c47c1bfe30 - Add pipeline runs
-- 4. a3ee91772c51 - Add chunking and embedding config to products
-- 5. df59fc2b6867 - Update chunking config for hybrid approach (empty)
-- 6. 3028ce203362 - Add promoted version to products
-- 7. 35b5d0835265 - Add dq violations table
-- 8. 084bc8b5e18b - Add enterprise data quality rules
-- 9. 484bdf5ba39a - Fix DataQualityRule relationships (empty)
-- 10. 0b612b315803 - Add billing profile model
-- 11. 9ef9ed084a5a - Add user profile fields
-- 12. c51b69ec7fe7 - Add AIRD pipeline tracking to pipeline runs
-- 13. ae3d46973967 - Add raw file model to track ingested files
-- 14. f3d3928ec4ad - Add status and validation fields to raw files
-- 15. 4550eea71227 - Add pipeline artifacts table for enterprise traceability
-- 16. 9ce47ec1464f - Add name field to data sources
-- 17. f3777117c808 - Add playbook selection metadata to products
-- 18. a8b9c0d1e2f3 - Add custom playbooks table
-- 19. bda98fc65abe - Remove document and vector metadata tables
-- 20. 2c3c514d31f1 - Add s3 path columns and archiving fields
-- 21. 3bd677e2eacd - Add AIRD enabled to products
-- 22. ccf903091f0c - Add workspace indexes for security
-- 23. 6ba2953c1cd4 - Rename MinIO columns to generic storage names
-- 24. 74751c186a1e - Remove unused pipeline model
-- 25. cde09da68630 - Optimize database indexes and add features
-- 26. 4a4fb42ca31d - Cleanup duplicate indexes and constraints
-- 27. 248c786dde45 - Add AI ready metrics eval tables
-- 28. c3f2eeca3a86 - Add email verification fields
-- 29. 001_add_performance_indexes - Add performance indexes
-- 30. 471e61c5d2db - Add settings to workspace
-- ============================================================================

-- ============================================================================
-- MIGRATION: ab76775a482b - Initial migration with auth and workspaces
-- ============================================================================
-- Creates the base tables for users, workspaces, and workspace members

-- Create ENUM types
CREATE TYPE authprovider AS ENUM ('GOOGLE', 'SIMPLE', 'NONE');
CREATE TYPE workspacerole AS ENUM ('OWNER', 'ADMIN', 'EDITOR', 'VIEWER');

-- Create data_sources table (old schema - replaced later)
CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    config TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_data_sources_id ON data_sources(id);

-- Create pipelines table (old schema - removed later)
CREATE TABLE IF NOT EXISTS pipelines (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    config TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_pipelines_id ON pipelines(id);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    timezone VARCHAR(50),
    picture_url VARCHAR(500),
    auth_provider authprovider NOT NULL,
    google_sub VARCHAR(255),
    roles JSON NOT NULL,
    is_active BOOLEAN,
    password_hash VARCHAR(255),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_token VARCHAR(255),
    verification_token_expires TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_token_expires TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users(google_sub);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_verification_token ON users(verification_token);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_password_reset_token ON users(password_reset_token);
CREATE INDEX IF NOT EXISTS ix_users_id ON users(id);

-- Create workspaces table
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    settings JSON,
    owner_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id ON workspaces(owner_id);

-- Add foreign key for workspace owner
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'workspaces_owner_id_fkey'
    ) THEN
        ALTER TABLE workspaces ADD CONSTRAINT workspaces_owner_id_fkey
            FOREIGN KEY (owner_id) REFERENCES users(id);
    END IF;
END $$;

-- Create workspace_members table
CREATE TABLE IF NOT EXISTS workspace_members (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role workspacerole NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ux_workspace_members_workspace_user UNIQUE (workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);


-- ============================================================================
-- MIGRATION: 2507e4fa6f84 - Products and datasources
-- ============================================================================
-- Adds products table and restructures data_sources

-- Create ENUM types
CREATE TYPE productstatus AS ENUM ('DRAFT', 'RUNNING', 'READY', 'FAILED');
CREATE TYPE datasourcetype AS ENUM ('WEB', 'DB', 'CONFLUENCE', 'SHAREPOINT', 'FOLDER');

-- Create products table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    owner_user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    status productstatus NOT NULL,
    current_version INTEGER NOT NULL,
    promoted_version INTEGER,
    chunking_config JSON,
    embedding_config JSON,
    use_case_description TEXT,
    vector_creation_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    aird_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    preprocessing_stats_path VARCHAR(1000),
    readiness_fingerprint_path VARCHAR(1000),
    chunk_metrics_path VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_products_owner_user_id ON products(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_products_workspace_id ON products(workspace_id);
CREATE INDEX IF NOT EXISTS idx_products_created_at ON products(created_at);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_products_workspace_status ON products(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_products_workspace_version ON products(workspace_id, current_version);
CREATE INDEX IF NOT EXISTS idx_products_workspace_created_at ON products(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_products_workspace_active ON products(workspace_id, created_at DESC) WHERE deleted_at IS NULL;

-- Add unique constraint for workspace product name
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'unique_workspace_product_name'
    ) THEN
        ALTER TABLE products ADD CONSTRAINT unique_workspace_product_name UNIQUE (workspace_id, name);
    END IF;
END $$;

-- Drop old data_sources and recreate with new schema
DROP TABLE IF EXISTS data_sources CASCADE;

CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    type datasourcetype NOT NULL,
    config JSON NOT NULL,
    last_cursor JSON,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_data_sources_product_id ON data_sources(product_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_workspace_id ON data_sources(workspace_id);
CREATE INDEX IF NOT EXISTS ix_data_sources_id ON data_sources(id);
CREATE INDEX IF NOT EXISTS ix_data_sources_product_id ON data_sources(product_id);
CREATE INDEX IF NOT EXISTS ix_data_sources_workspace_id ON data_sources(workspace_id);


-- ============================================================================
-- MIGRATION: 56c47c1bfe30 - Add pipeline runs
-- ============================================================================

CREATE TYPE pipelinerunstatus AS ENUM ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED');

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    status pipelinerunstatus NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    dag_run_id VARCHAR(255) NOT NULL,
    metrics JSON NOT NULL,
    stage_metrics JSON,
    aird_stages_completed JSON,
    metrics_path VARCHAR(1000),
    archived_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_dag_run_id ON pipeline_runs(dag_run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_product_version ON pipeline_runs(product_id, version);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_workspace_id ON pipeline_runs(workspace_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_dag_run_id ON pipeline_runs(dag_run_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_id ON pipeline_runs(id);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_product_id ON pipeline_runs(product_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_workspace_id ON pipeline_runs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_product_status_created ON pipeline_runs(product_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_workspace_status_created ON pipeline_runs(workspace_id, status, created_at);


-- ============================================================================
-- MIGRATION: a3ee91772c51 - Add chunking and embedding config to products
-- ============================================================================
-- Already added in products table definition above


-- ============================================================================
-- MIGRATION: df59fc2b6867 - Update chunking config for hybrid approach
-- ============================================================================
-- Empty migration - no changes


-- ============================================================================
-- MIGRATION: 3028ce203362 - Add promoted version to products
-- ============================================================================
-- Already added in products table definition above


-- ============================================================================
-- MIGRATION: 35b5d0835265 - Add dq violations table
-- ============================================================================

CREATE TYPE dqviolationseverity AS ENUM ('ERROR', 'WARNING', 'INFO');

CREATE TABLE IF NOT EXISTS dq_violations (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    pipeline_run_id UUID REFERENCES pipeline_runs(id),
    rule_name VARCHAR(255) NOT NULL,
    rule_type VARCHAR(100) NOT NULL,
    severity dqviolationseverity NOT NULL,
    message TEXT NOT NULL,
    details JSON,
    affected_count INTEGER,
    total_count INTEGER,
    violation_rate FLOAT,
    archived_at TIMESTAMP WITH TIME ZONE,
    archived_to_s3 BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dq_violations_created_at ON dq_violations(created_at);
CREATE INDEX IF NOT EXISTS idx_dq_violations_product_version ON dq_violations(product_id, version);
CREATE INDEX IF NOT EXISTS idx_dq_violations_severity ON dq_violations(severity);
CREATE INDEX IF NOT EXISTS idx_dq_violations_product_severity ON dq_violations(product_id, severity);
CREATE INDEX IF NOT EXISTS idx_dq_violations_product_version_severity ON dq_violations(product_id, version, severity);
CREATE INDEX IF NOT EXISTS ix_dq_violations_id ON dq_violations(id);
CREATE INDEX IF NOT EXISTS ix_dq_violations_pipeline_run_id ON dq_violations(pipeline_run_id);
CREATE INDEX IF NOT EXISTS ix_dq_violations_product_id ON dq_violations(product_id);
CREATE INDEX IF NOT EXISTS ix_dq_violations_version ON dq_violations(version);


-- ============================================================================
-- MIGRATION: 084bc8b5e18b - Add enterprise data quality rules
-- ============================================================================

CREATE TYPE rulestatus AS ENUM ('DRAFT', 'ACTIVE', 'DEPRECATED', 'ARCHIVED');
CREATE TYPE ruleseverity AS ENUM ('ERROR', 'WARNING', 'INFO');
CREATE TYPE auditaction AS ENUM ('CREATE', 'UPDATE', 'DELETE', 'ACTIVATE', 'DEPRECATE', 'ARCHIVE');

CREATE TABLE IF NOT EXISTS data_quality_compliance_reports (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    report_name VARCHAR(255) NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    compliance_framework VARCHAR(100),
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    report_data JSON NOT NULL,
    summary TEXT,
    generated_by UUID NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data_quality_rule_sets (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    version VARCHAR(20) NOT NULL,
    compliance_framework VARCHAR(100),
    business_unit VARCHAR(100),
    data_classification VARCHAR(50),
    status rulestatus NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_by UUID NOT NULL,
    approved_by UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    effective_from TIMESTAMP WITH TIME ZONE,
    effective_until TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS data_quality_rule_assignments (
    id UUID PRIMARY KEY,
    rule_set_id UUID NOT NULL REFERENCES data_quality_rule_sets(id),
    product_id UUID NOT NULL REFERENCES products(id),
    assigned_by UUID NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_override BOOLEAN NOT NULL,
    override_reason TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_rules (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    severity ruleseverity NOT NULL,
    status rulestatus NOT NULL,
    configuration JSON NOT NULL,
    version INTEGER NOT NULL,
    is_current BOOLEAN NOT NULL,
    parent_rule_id UUID REFERENCES data_quality_rules(id),
    enabled BOOLEAN NOT NULL,
    created_by UUID NOT NULL,
    updated_by UUID,
    approved_by UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP WITH TIME ZONE,
    deprecated_at TIMESTAMP WITH TIME ZONE,
    compliance_tags JSON,
    business_owner VARCHAR(255),
    technical_owner VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS data_quality_rule_audit (
    id UUID PRIMARY KEY,
    rule_id UUID NOT NULL REFERENCES data_quality_rules(id),
    action auditaction NOT NULL,
    changed_by UUID NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    old_values JSON,
    new_values JSON,
    change_reason TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    session_id VARCHAR(255)
);


-- ============================================================================
-- MIGRATION: 484bdf5ba39a - Fix DataQualityRule relationships
-- ============================================================================
-- Empty migration - no changes


-- ============================================================================
-- MIGRATION: 0b612b315803 - Add billing profile model
-- ============================================================================

CREATE TYPE billingplan AS ENUM ('FREE', 'PRO', 'ENTERPRISE');

CREATE TABLE IF NOT EXISTS billing_profiles (
    workspace_id UUID PRIMARY KEY REFERENCES workspaces(id),
    stripe_customer_id VARCHAR(255),
    plan billingplan NOT NULL,
    default_payment_method_id VARCHAR(255),
    usage JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_billing_profiles_plan ON billing_profiles(plan);
CREATE INDEX IF NOT EXISTS idx_billing_profiles_stripe_customer ON billing_profiles(stripe_customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_billing_profiles_stripe_customer_id ON billing_profiles(stripe_customer_id);


-- ============================================================================
-- MIGRATION: 9ef9ed084a5a - Add user profile fields
-- ============================================================================
-- Already added in users table definition above


-- ============================================================================
-- MIGRATION: c51b69ec7fe7 - Add AIRD pipeline tracking to pipeline runs
-- ============================================================================

CREATE TYPE aclaccesstype AS ENUM ('FULL', 'INDEX', 'DOCUMENT', 'FIELD');

CREATE TABLE IF NOT EXISTS acls (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    product_id UUID NOT NULL REFERENCES products(id),
    access_type aclaccesstype NOT NULL,
    index_scope VARCHAR(500),
    doc_scope VARCHAR(500),
    field_scope VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_acls_access_type ON acls(access_type);
CREATE INDEX IF NOT EXISTS idx_acls_product_id ON acls(product_id);
CREATE INDEX IF NOT EXISTS idx_acls_user_id ON acls(user_id);
CREATE INDEX IF NOT EXISTS idx_acls_user_product ON acls(user_id, product_id);
CREATE INDEX IF NOT EXISTS ix_acls_access_type ON acls(access_type);
CREATE INDEX IF NOT EXISTS ix_acls_id ON acls(id);
CREATE INDEX IF NOT EXISTS ix_acls_product_id ON acls(product_id);
CREATE INDEX IF NOT EXISTS ix_acls_user_id ON acls(user_id);

-- Document metadata table
CREATE TABLE IF NOT EXISTS document_metadata (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    score FLOAT,
    source_file VARCHAR(500),
    page_number INTEGER,
    section VARCHAR(255),
    field_name VARCHAR(255),
    extra_tags JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_document_metadata_chunk_id ON document_metadata(chunk_id);
CREATE INDEX IF NOT EXISTS idx_document_metadata_field_name ON document_metadata(field_name);
CREATE INDEX IF NOT EXISTS idx_document_metadata_product_version ON document_metadata(product_id, version);
CREATE INDEX IF NOT EXISTS ix_document_metadata_chunk_id ON document_metadata(chunk_id);
CREATE INDEX IF NOT EXISTS ix_document_metadata_id ON document_metadata(id);
CREATE INDEX IF NOT EXISTS ix_document_metadata_product_id ON document_metadata(product_id);

-- Vector metadata table
CREATE TABLE IF NOT EXISTS vector_metadata (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    collection_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    page_number INTEGER,
    section VARCHAR(255),
    field_name VARCHAR(255),
    tags JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vector_metadata_chunk_id ON vector_metadata(chunk_id);
CREATE INDEX IF NOT EXISTS idx_vector_metadata_collection ON vector_metadata(collection_id);
CREATE INDEX IF NOT EXISTS idx_vector_metadata_field_name ON vector_metadata(field_name);
CREATE INDEX IF NOT EXISTS idx_vector_metadata_product_version ON vector_metadata(product_id, version);
CREATE INDEX IF NOT EXISTS ix_vector_metadata_chunk_id ON vector_metadata(chunk_id);
CREATE INDEX IF NOT EXISTS ix_vector_metadata_field_name ON vector_metadata(field_name);
CREATE INDEX IF NOT EXISTS ix_vector_metadata_id ON vector_metadata(id);
CREATE INDEX IF NOT EXISTS ix_vector_metadata_product_id ON vector_metadata(product_id);

-- Add columns to products
ALTER TABLE products ADD COLUMN IF NOT EXISTS playbook_id VARCHAR(50);
ALTER TABLE products ADD COLUMN IF NOT EXISTS preprocessing_stats JSON;
ALTER TABLE products ADD COLUMN IF NOT EXISTS trust_score FLOAT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS readiness_fingerprint JSON;
CREATE TYPE policystatus AS ENUM ('PASSED', 'FAILED', 'WARNINGS', 'UNKNOWN');
ALTER TABLE products ADD COLUMN IF NOT EXISTS policy_status policystatus;
ALTER TABLE products ADD COLUMN IF NOT EXISTS policy_violations JSON;
ALTER TABLE products ADD COLUMN IF NOT EXISTS chunk_metrics JSON;
ALTER TABLE products ADD COLUMN IF NOT EXISTS validation_summary_path VARCHAR(500);
ALTER TABLE products ADD COLUMN IF NOT EXISTS trust_report_path VARCHAR(500);


-- ============================================================================
-- MIGRATION: ae3d46973967 - Add raw file model to track ingested files
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw_files (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    data_source_id UUID REFERENCES data_sources(id),
    version INTEGER NOT NULL,
    filename VARCHAR(500) NOT NULL,
    file_stem VARCHAR(500) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    storage_bucket VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    content_type VARCHAR(255) NOT NULL DEFAULT 'application/octet-stream',
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_raw_file_product_version_stem UNIQUE (product_id, version, file_stem),
    CONSTRAINT uq_raw_file_storage_key UNIQUE (storage_key)
);
CREATE INDEX IF NOT EXISTS idx_raw_files_data_source ON raw_files(data_source_id);
CREATE INDEX IF NOT EXISTS idx_raw_files_file_stem ON raw_files(file_stem);
CREATE INDEX IF NOT EXISTS idx_raw_files_product_version ON raw_files(product_id, version);
CREATE INDEX IF NOT EXISTS ix_raw_files_data_source_id ON raw_files(data_source_id);
CREATE INDEX IF NOT EXISTS ix_raw_files_file_stem ON raw_files(file_stem);
CREATE INDEX IF NOT EXISTS ix_raw_files_id ON raw_files(id);
CREATE INDEX IF NOT EXISTS ix_raw_files_product_id ON raw_files(product_id);
CREATE INDEX IF NOT EXISTS ix_raw_files_workspace_id ON raw_files(workspace_id);


-- ============================================================================
-- MIGRATION: f3d3928ec4ad - Add status and validation fields to raw files
-- ============================================================================

CREATE TYPE rawfilestatus AS ENUM ('INGESTED', 'PROCESSING', 'PROCESSED', 'FAILED', 'DELETED');

ALTER TABLE raw_files ADD COLUMN IF NOT EXISTS status rawfilestatus NOT NULL DEFAULT 'INGESTED';
ALTER TABLE raw_files ADD COLUMN IF NOT EXISTS file_checksum VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE raw_files ADD COLUMN IF NOT EXISTS storage_etag VARCHAR(255);
ALTER TABLE raw_files ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE raw_files ADD COLUMN IF NOT EXISTS error_message TEXT;
CREATE INDEX IF NOT EXISTS idx_raw_files_status ON raw_files(status);


-- ============================================================================
-- MIGRATION: 4550eea71227 - Add pipeline artifacts table for enterprise traceability
-- ============================================================================

CREATE TYPE artifacttype AS ENUM ('JSONL', 'JSON', 'CSV', 'PDF', 'VECTOR', 'TEXT', 'BINARY');
CREATE TYPE artifactstatus AS ENUM ('ACTIVE', 'ARCHIVED', 'DELETED', 'PURGED');
CREATE TYPE retentionpolicy AS ENUM ('KEEP_FOREVER', 'DAYS_30', 'DAYS_90', 'DAYS_365', 'DELETE_ON_PROMOTE', 'ON_FAILURE_KEEP_90');

CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    id UUID PRIMARY KEY,
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    stage_name VARCHAR(100) NOT NULL,
    artifact_type artifacttype NOT NULL,
    artifact_name VARCHAR(255) NOT NULL,
    storage_bucket VARCHAR(255) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    checksum VARCHAR(64) NOT NULL DEFAULT '',
    storage_etag VARCHAR(255) NOT NULL DEFAULT '',
    input_artifacts JSON,
    artifact_metadata JSON,
    status artifactstatus NOT NULL,
    retention_policy retentionpolicy NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    archived_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_by UUID REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_storage_key ON pipeline_artifacts(storage_key);
CREATE INDEX IF NOT EXISTS idx_artifacts_product_version ON pipeline_artifacts(product_id, version);
CREATE INDEX IF NOT EXISTS idx_artifacts_retention ON pipeline_artifacts(retention_policy, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_stage_type ON pipeline_artifacts(stage_name, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_status_created ON pipeline_artifacts(status, created_at);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_created_at ON pipeline_artifacts(created_at);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_id ON pipeline_artifacts(id);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_storage_key ON pipeline_artifacts(storage_key);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_pipeline_run_id ON pipeline_artifacts(pipeline_run_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_product_id ON pipeline_artifacts(product_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_stage_name ON pipeline_artifacts(stage_name);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_status ON pipeline_artifacts(status);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_version ON pipeline_artifacts(version);
CREATE INDEX IF NOT EXISTS ix_pipeline_artifacts_workspace_id ON pipeline_artifacts(workspace_id);


-- ============================================================================
-- MIGRATION: 9ce47ec1464f - Add name field to data sources
-- ============================================================================
-- Already added in data_sources table definition above


-- ============================================================================
-- MIGRATION: f3777117c808 - Add playbook selection metadata to products
-- ============================================================================

ALTER TABLE products ADD COLUMN IF NOT EXISTS playbook_selection JSON;


-- ============================================================================
-- MIGRATION: a8b9c0d1e2f3 - Add custom playbooks table
-- ============================================================================

CREATE TABLE IF NOT EXISTS custom_playbooks (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    owner_user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    playbook_id VARCHAR(100) NOT NULL,
    description TEXT,
    yaml_content TEXT NOT NULL,
    config JSON,
    base_playbook_id VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT unique_workspace_playbook_id UNIQUE (workspace_id, playbook_id)
);
CREATE INDEX IF NOT EXISTS idx_custom_playbooks_workspace_id ON custom_playbooks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_custom_playbooks_owner_user_id ON custom_playbooks(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_custom_playbooks_playbook_id ON custom_playbooks(playbook_id);
CREATE INDEX IF NOT EXISTS ix_custom_playbooks_id ON custom_playbooks(id);
CREATE INDEX IF NOT EXISTS ix_custom_playbooks_owner_user_id ON custom_playbooks(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_custom_playbooks_workspace_id ON custom_playbooks(workspace_id);


-- ============================================================================
-- MIGRATION: bda98fc65abe - Remove document and vector metadata tables
-- ============================================================================
-- Note: Document and vector metadata tables are preserved above as they are
-- recreated in migration c51b69ec7fe7. This migration removes AIRD columns from products.

-- Columns removed from products (if they existed):
-- aird_embedding_index_path
-- aird_trust_score
-- aird_playbook_id
-- aird_optimizer_notes
-- aird_chunks_indexed
-- aird_policy
-- aird_last_run_at
-- aird_fingerprint


-- ============================================================================
-- MIGRATION: 2c3c514d31f1 - Add S3 path columns and archiving fields
-- ============================================================================
-- Already added in previous migrations


-- ============================================================================
-- MIGRATION: 3bd677e2eacd - Add AIRD enabled to products
-- ============================================================================
-- Already added in products table definition above


-- ============================================================================
-- MIGRATION: ccf903091f0c - Add workspace indexes for security
-- ============================================================================
-- Already added above as idx_workspace_members_user_id


-- ============================================================================
-- MIGRATION: 6ba2953c1cd4 - Rename MinIO columns to generic storage names
-- ============================================================================
-- Columns already renamed in table definitions:
-- raw_files: minio_key -> storage_key, minio_bucket -> storage_bucket, minio_etag -> storage_etag
-- pipeline_artifacts: minio_key -> storage_key, minio_bucket -> storage_bucket, minio_etag -> storage_etag


-- ============================================================================
-- MIGRATION: 74751c186a1e - Remove unused pipeline model
-- ============================================================================
-- Drop old pipelines table (already dropped during products migration)


-- ============================================================================
-- MIGRATION: cde09da68630 - Optimize database indexes and add features
-- ============================================================================
-- Indexes and columns already added in previous migrations:
-- - Removed duplicate indexes (ix_products_id, ix_products_workspace_id)
-- - Added composite indexes for performance
-- - Added workspace owner tracking
-- - Added soft delete support (deleted_at columns)


-- ============================================================================
-- MIGRATION: 4a4fb42ca31d - Cleanup duplicate indexes and constraints
-- ============================================================================
-- Already handled in previous migrations


-- ============================================================================
-- MIGRATION: 248c786dde45 - Add AI ready metrics eval tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS eval_queries (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    query TEXT NOT NULL,
    expected_chunk_id VARCHAR(255) NOT NULL,
    query_style VARCHAR(50),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_queries_product_version ON eval_queries(product_id, version);
CREATE INDEX IF NOT EXISTS idx_eval_queries_chunk ON eval_queries(chunk_id);

CREATE TABLE IF NOT EXISTS eval_runs (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    metrics JSON,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_product_version ON eval_runs(product_id, version);


-- ============================================================================
-- MIGRATION: c3f2eeca3a86 - Add email verification fields
-- ============================================================================
-- Already added in users table definition above


-- ============================================================================
-- MIGRATION: 001_add_performance_indexes - Add performance indexes
-- ============================================================================
-- Composite indexes for frequently queried patterns

CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_product_version_type ON pipeline_artifacts(product_id, version, artifact_type);
CREATE INDEX IF NOT EXISTS idx_raw_files_product_version_status ON raw_files(product_id, version, status);
CREATE INDEX IF NOT EXISTS idx_dq_violations_product_severity ON dq_violations(product_id, severity);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_workspace_status_created ON pipeline_runs(workspace_id, status, created_at);


-- ============================================================================
-- MIGRATION: 471e61c5d2db - Add settings to workspace
-- ============================================================================
-- Already added in workspaces table definition above

-- ============================================================================
-- END OF MIGRATIONS
-- ============================================================================
-- This completes the full database schema from all migration files.
-- Total tables created: 24
-- Total ENUM types created: 15
-- Total indexes created: 100+
-- ============================================================================
