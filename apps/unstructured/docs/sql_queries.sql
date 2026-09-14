-- SQL Queries for PrimeData - Complete Database Reference
-- This file contains DDL and DML for ALL tables in the database
-- Including core PrimeData tables, Airflow metadata tables, and system tables

-- ============================================================================
-- TABLE OVERVIEW
-- ============================================================================
-- Total Tables: 72 (across multiple schemas and subsystems)
--
-- CATEGORIES:
-- 1. PrimeData Core (13 tables)
-- 2. Airflow Metadata (50+ tables)
-- 3. System/PostgreSQL (Internal tables)

-- ============================================================================
-- PRIMEDATA CORE TABLES (13 total)
-- ============================================================================
-- These are the main application tables for PrimeData functionality

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    timezone VARCHAR(50) DEFAULT 'UTC',
    picture_url VARCHAR(500),
    auth_provider VARCHAR(50) NOT NULL DEFAULT 'none',
    google_sub VARCHAR(255) UNIQUE,
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    password_hash VARCHAR(255),
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255) UNIQUE,
    verification_token_expires TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255) UNIQUE,
    password_reset_token_expires TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_users_email (email),
    INDEX idx_users_auth_provider (auth_provider),
    INDEX idx_users_google_sub (google_sub)
);

-- 2. Workspaces Table
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_workspaces_created_at (created_at)
);

-- 3. Workspace Members Table
CREATE TABLE IF NOT EXISTS workspace_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (workspace_id, user_id),
    INDEX idx_workspace_members_workspace_id (workspace_id),
    INDEX idx_workspace_members_user_id (user_id)
);

-- 4. Products Table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    owner_user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    current_version INTEGER NOT NULL DEFAULT 0,
    promoted_version INTEGER,
    aird_enabled BOOLEAN DEFAULT TRUE,
    playbook_id VARCHAR(50),
    playbook_selection JSONB,
    preprocessing_stats JSONB,
    preprocessing_stats_path VARCHAR(1000),
    trust_score FLOAT,
    readiness_fingerprint JSONB,
    readiness_fingerprint_path VARCHAR(1000),
    policy_status VARCHAR(50),
    policy_violations JSONB DEFAULT '[]'::jsonb,
    chunk_metrics JSONB DEFAULT '[]'::jsonb,
    chunk_metrics_path VARCHAR(1000),
    validation_summary_path VARCHAR(500),
    trust_report_path VARCHAR(500),
    chunking_config JSONB,
    embedding_config JSONB,
    vector_creation_enabled BOOLEAN DEFAULT TRUE,
    use_case_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_products_workspace_id (workspace_id),
    INDEX idx_products_status (status),
    INDEX idx_products_owner_user_id (owner_user_id)
);

-- 5. Data Sources Table
CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    type VARCHAR(50) NOT NULL,
    name VARCHAR(255),
    config JSONB,
    test_result JSONB,
    last_test_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_data_sources_product_id (product_id)
);

-- 6. Raw Files Table
CREATE TABLE IF NOT EXISTS raw_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    data_source_id UUID REFERENCES data_sources(id),
    version INTEGER NOT NULL,
    filename VARCHAR(500) NOT NULL,
    file_stem VARCHAR(500) NOT NULL,
    storage_bucket VARCHAR(255) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    content_type VARCHAR(255),
    file_checksum VARCHAR(255),
    storage_etag VARCHAR(255),
    status VARCHAR(50) DEFAULT 'ingested',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (workspace_id, product_id, version, file_stem),
    INDEX idx_raw_files_product_id (product_id),
    INDEX idx_raw_files_version (version),
    INDEX idx_raw_files_status (status)
);

-- 7. Pipeline Runs Table
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL REFERENCES products(id),
    version INTEGER NOT NULL,
    run_id VARCHAR(255) UNIQUE,
    mode VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued',
    triggered_by_user_id VARCHAR(255) REFERENCES users(id),
    airflow_dag_run_id VARCHAR(255),
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pipeline_runs_product_id (product_id),
    INDEX idx_pipeline_runs_status (status)
);

-- 8. Pipeline Artifacts Table
CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    version INTEGER NOT NULL,
    stage_name VARCHAR(255) NOT NULL,
    artifact_type VARCHAR(50) NOT NULL,
    artifact_name VARCHAR(255) NOT NULL,
    storage_bucket VARCHAR(255) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    file_size BIGINT,
    checksum VARCHAR(255),
    storage_etag VARCHAR(255),
    artifact_metadata JSONB,
    status VARCHAR(50) DEFAULT 'active',
    retention_policy VARCHAR(50) DEFAULT 'auto_delete',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_pipeline_artifacts_pipeline_run_id (pipeline_run_id),
    INDEX idx_pipeline_artifacts_product_id (product_id)
);

-- 9. DQ Violations Table
CREATE TABLE IF NOT EXISTS dq_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    version INTEGER NOT NULL,
    chunk_id VARCHAR(255),
    violation_type VARCHAR(255) NOT NULL,
    severity VARCHAR(50),
    rule_id VARCHAR(255),
    details JSONB,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dq_violations_product_id (product_id),
    INDEX idx_dq_violations_severity (severity)
);

-- 10. ACL (Access Control List) Table
CREATE TABLE IF NOT EXISTS acls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    resource_type VARCHAR(255) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    permission VARCHAR(255) NOT NULL,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_acls_user_id (user_id),
    INDEX idx_acls_resource_id (resource_id)
);

-- 11. User Audit Logs Table
CREATE TABLE IF NOT EXISTS user_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    user_id VARCHAR(255) REFERENCES users(id),
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(255),
    resource_id VARCHAR(255),
    old_value JSONB,
    new_value JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_logs_user_id (user_id),
    INDEX idx_audit_logs_resource_id (resource_id),
    INDEX idx_audit_logs_created_at (created_at)
);

-- 12. Billing Profiles Table
CREATE TABLE IF NOT EXISTS billing_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL UNIQUE REFERENCES workspaces(id),
    stripe_customer_id VARCHAR(255) UNIQUE,
    stripe_subscription_id VARCHAR(255),
    plan_name VARCHAR(50) DEFAULT 'free',
    status VARCHAR(50),
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- 13. Data Quality Rules Table (Enterprise)
CREATE TABLE IF NOT EXISTS data_quality_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID REFERENCES products(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rule_type VARCHAR(255) NOT NULL,
    severity VARCHAR(50),
    configuration JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255) NOT NULL,
    updated_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_dq_rules_product_id (product_id),
    INDEX idx_dq_rules_enabled (enabled)
);

-- ============================================================================
-- AIRFLOW METADATA TABLES (50+ tables)
-- ============================================================================
-- These tables are created automatically by Apache Airflow
-- for DAG/task tracking, logging, and state management
--
-- To view all Airflow tables, run:
-- SELECT tablename FROM pg_tables
-- WHERE schemaname = 'public' AND tablename LIKE '%airflow%'
-- OR tablename IN ('dag', 'task', 'log', 'xcom', 'import_error', etc);
--
-- Common Airflow tables include:
-- - ab_user, ab_role, ab_permission (Authentication/Authorization)
-- - dag, dag_run, dag_tag (DAG management)
-- - task_instance, task_flow, task_group (Task execution)
-- - log, xcom (Logging and cross-communication)
-- - sla_miss, import_error (Monitoring/Errors)
-- - connection, variable (Configuration)
-- - job, serialized_dag (Job tracking)
-- - And many more for state management and metrics

-- Example: Get all Airflow tables
-- SELECT tablename FROM pg_tables
-- WHERE schemaname = 'public'
-- ORDER BY tablename;

-- ============================================================================
-- QUERY ALL TABLES IN DATABASE
-- ============================================================================

-- Get count of all tables
SELECT COUNT(*) as total_tables
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');

-- Get all tables grouped by schema
SELECT
    schemaname,
    COUNT(*) as table_count,
    STRING_AGG(tablename, ', ' ORDER BY tablename) as tables
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;

-- Get all PrimeData core tables (13)
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN (
    'users', 'workspaces', 'workspace_members', 'products', 'data_sources',
    'raw_files', 'pipeline_runs', 'pipeline_artifacts', 'dq_violations',
    'acls', 'user_audit_logs', 'billing_profiles', 'data_quality_rules'
)
ORDER BY tablename;

-- Get all Airflow tables (50+)
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
AND tablename NOT IN (
    'users', 'workspaces', 'workspace_members', 'products', 'data_sources',
    'raw_files', 'pipeline_runs', 'pipeline_artifacts', 'dq_violations',
    'acls', 'user_audit_logs', 'billing_profiles', 'data_quality_rules'
)
ORDER BY tablename;

-- Get table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    (SELECT count(*) FROM information_schema.columns
     WHERE table_schema = schemaname AND table_name = tablename) as column_count
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================================================
-- PRIMEDATA CORE QUERIES (Same as before)
-- ============================================================================

-- Get user by ID
SELECT * FROM users WHERE id = $1;

-- List products in workspace
SELECT * FROM products
WHERE workspace_id = $1
ORDER BY created_at DESC;

-- Get raw files for product version
SELECT * FROM raw_files
WHERE product_id = $1 AND version = $2 AND status != 'deleted'
ORDER BY created_at DESC;

-- Get pipeline artifacts
SELECT * FROM pipeline_artifacts
WHERE pipeline_run_id = $1
ORDER BY stage_name, created_at DESC;

-- Get DQ violations
SELECT * FROM dq_violations
WHERE product_id = $1 AND version = $2
ORDER BY detected_at DESC;

-- ============================================================================
-- AIRFLOW SPECIFIC QUERIES
-- ============================================================================

-- Get Airflow DAG information
SELECT * FROM dag WHERE dag_id LIKE '%primedata%';

-- Get DAG runs
SELECT dag_id, run_id, execution_date, start_date, end_date, state
FROM dag_run
WHERE dag_id LIKE '%primedata%'
ORDER BY execution_date DESC
LIMIT 10;

-- Get task instances for a specific DAG run
SELECT task_id, state, start_date, end_date, duration
FROM task_instance
WHERE dag_id = $1 AND execution_date = $2
ORDER BY start_date;

-- Get Airflow logs
SELECT dag_id, task_id, execution_date, log
FROM log
WHERE dag_id LIKE '%primedata%'
ORDER BY dttm DESC
LIMIT 100;

-- Get connections (for S3, OpenSearch, etc.)
SELECT conn_id, conn_type, host, port, schema, login
FROM connection
WHERE conn_type IN ('s3', 'opensearch', 'postgres', 'http');

-- Get Airflow variables (configuration)
SELECT key, value
FROM variable
WHERE key LIKE '%PRIMEDATA%' OR key LIKE '%S3%' OR key LIKE '%OPENSEARCH%';

-- ============================================================================
-- MONITORING & DIAGNOSTICS
-- ============================================================================

-- Check for failed tasks in Airflow
SELECT
    dag_id, task_id, execution_date,
    state, start_date, end_date,
    try_number, max_tries
FROM task_instance
WHERE state = 'failed'
ORDER BY execution_date DESC
LIMIT 50;

-- Check for stuck DAG runs
SELECT
    dag_id, run_id, execution_date, state,
    EXTRACT(EPOCH FROM (NOW() - start_date)) as running_seconds
FROM dag_run
WHERE state = 'running'
AND start_date < NOW() - INTERVAL '1 hour';

-- Get PrimeData pipeline statistics
SELECT
    pr.status,
    COUNT(*) as count,
    MIN(pr.created_at) as oldest,
    MAX(pr.created_at) as newest
FROM pipeline_runs pr
GROUP BY pr.status
ORDER BY count DESC;

-- Get file upload statistics
SELECT
    rf.status,
    COUNT(*) as file_count,
    SUM(rf.file_size) as total_size_bytes,
    AVG(rf.file_size) as avg_file_size
FROM raw_files rf
GROUP BY rf.status;

-- ============================================================================
-- MAINTENANCE
-- ============================================================================

-- Vacuum and analyze all tables
VACUUM ANALYZE;

-- Get table bloat information
SELECT
    schemaname, tablename,
    round(100 * pg_relation_size(schemaname||'.'||tablename) /
    pg_total_relation_size(schemaname||'.'||tablename)) as table_bloat_ratio
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Find unused indexes
SELECT
    schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

