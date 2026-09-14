-- ============================================================================
-- PrimeData Backend SQL Migration Scripts
-- Generated for All Implemented Features
-- Date: March 26, 2026
-- ============================================================================

-- ============================================================================
-- PHASE 1: FOUNDATION (Days 1-5)
-- ============================================================================

-- ============================================================================
-- Day 3: User Audit Logging Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    workspace_id VARCHAR(255),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    changes JSONB DEFAULT '{}',
    audit_metadata JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for audit logging
CREATE INDEX idx_user_audit_log_user_id ON user_audit_log(user_id);
CREATE INDEX idx_user_audit_log_workspace_id ON user_audit_log(workspace_id);
CREATE INDEX idx_user_audit_log_action ON user_audit_log(action);
CREATE INDEX idx_user_audit_log_resource_type ON user_audit_log(resource_type);
CREATE INDEX idx_user_audit_log_created_at ON user_audit_log(created_at);
CREATE INDEX idx_user_audit_log_resource_id ON user_audit_log(resource_id);

-- ============================================================================
-- Day 4-5: Chunk and Quality Analysis Tables
-- ============================================================================

-- Chunks table with metadata
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(255) NOT NULL,
    version INT DEFAULT 1,
    chunk_order INT,
    text TEXT,
    page INT,
    source_file VARCHAR(500),
    metadata JSONB DEFAULT '{}',
    vector_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_product_id ON chunks(product_id);
CREATE INDEX idx_chunks_version ON chunks(version);
CREATE INDEX idx_chunks_page ON chunks(page);
CREATE INDEX idx_chunks_source_file ON chunks(source_file);
CREATE INDEX idx_chunks_created_at ON chunks(created_at);

-- Chunk quality metrics table
CREATE TABLE IF NOT EXISTS chunk_quality_metrics (
    id SERIAL PRIMARY KEY,
    chunk_id INT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    product_id VARCHAR(255) NOT NULL,
    version INT DEFAULT 1,
    confidence FLOAT DEFAULT 0.0,
    coherence FLOAT DEFAULT 0.0,
    noise_level FLOAT DEFAULT 0.0,
    has_mid_sentence_start BOOLEAN DEFAULT FALSE,
    has_mid_sentence_end BOOLEAN DEFAULT FALSE,
    quality_issues JSONB DEFAULT '[]',
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunk_quality_chunk_id ON chunk_quality_metrics(chunk_id);
CREATE INDEX idx_chunk_quality_product_id ON chunk_quality_metrics(product_id);
CREATE INDEX idx_chunk_quality_version ON chunk_quality_metrics(version);
CREATE INDEX idx_chunk_quality_confidence ON chunk_quality_metrics(confidence);
CREATE INDEX idx_chunk_quality_coherence ON chunk_quality_metrics(coherence);

-- ============================================================================
-- PHASE 2: GOVERNANCE & LINEAGE (Days 6-10)
-- ============================================================================

-- ============================================================================
-- Day 6: Policy Engine Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS policies (
    id SERIAL PRIMARY KEY,
    policy_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    severity VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE,
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_policies_policy_id ON policies(policy_id);
CREATE INDEX idx_policies_category ON policies(category);
CREATE INDEX idx_policies_severity ON policies(severity);
CREATE INDEX idx_policies_enabled ON policies(enabled);

-- Policy violations table
CREATE TABLE IF NOT EXISTS policy_violations (
    id SERIAL PRIMARY KEY,
    violation_id VARCHAR(255) UNIQUE NOT NULL,
    policy_id VARCHAR(255) NOT NULL REFERENCES policies(policy_id),
    resource_id VARCHAR(255),
    resource_type VARCHAR(100),
    severity VARCHAR(50),
    message TEXT,
    is_blocking BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_policy_violations_policy_id ON policy_violations(policy_id);
CREATE INDEX idx_policy_violations_resource_id ON policy_violations(resource_id);
CREATE INDEX idx_policy_violations_severity ON policy_violations(severity);
CREATE INDEX idx_policy_violations_is_blocking ON policy_violations(is_blocking);
CREATE INDEX idx_policy_violations_created_at ON policy_violations(created_at);

-- ============================================================================
-- Day 7: Quality Gates and Alerts Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_thresholds (
    id SERIAL PRIMARY KEY,
    gate_id VARCHAR(255),
    metric_name VARCHAR(255) NOT NULL,
    min_value FLOAT,
    max_value FLOAT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quality_thresholds_gate_id ON quality_thresholds(gate_id);
CREATE INDEX idx_quality_thresholds_metric_name ON quality_thresholds(metric_name);

-- Quality gates table
CREATE TABLE IF NOT EXISTS quality_gates (
    id SERIAL PRIMARY KEY,
    gate_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    severity VARCHAR(50),
    blocking BOOLEAN DEFAULT TRUE,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quality_gates_gate_id ON quality_gates(gate_id);
CREATE INDEX idx_quality_gates_category ON quality_gates(category);
CREATE INDEX idx_quality_gates_severity ON quality_gates(severity);
CREATE INDEX idx_quality_gates_blocking ON quality_gates(blocking);

-- Alert rules table
CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    policy_id VARCHAR(255),
    min_severity VARCHAR(50),
    channels JSONB DEFAULT '["LOG"]',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_rules_rule_id ON alert_rules(rule_id);
CREATE INDEX idx_alert_rules_policy_id ON alert_rules(policy_id);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(255) UNIQUE NOT NULL,
    rule_id VARCHAR(255) REFERENCES alert_rules(rule_id),
    violation_id VARCHAR(255),
    resource_id VARCHAR(255),
    priority VARCHAR(50),
    message TEXT,
    channels JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'active',
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_alert_id ON alerts(alert_id);
CREATE INDEX idx_alerts_rule_id ON alerts(rule_id);
CREATE INDEX idx_alerts_resource_id ON alerts(resource_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_created_at ON alerts(created_at);

-- Alert history table
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(255) REFERENCES alerts(alert_id) ON DELETE CASCADE,
    action VARCHAR(50),
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_history_alert_id ON alert_history(alert_id);
CREATE INDEX idx_alert_history_changed_at ON alert_history(changed_at);

-- ============================================================================
-- Day 8: Pipeline Integration Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS governance_pipelines (
    id SERIAL PRIMARY KEY,
    pipeline_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    pipeline_type VARCHAR(100),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_governance_pipelines_pipeline_id ON governance_pipelines(pipeline_id);
CREATE INDEX idx_governance_pipelines_type ON governance_pipelines(pipeline_type);

-- Pipeline stages table
CREATE TABLE IF NOT EXISTS pipeline_stages (
    id SERIAL PRIMARY KEY,
    stage_id VARCHAR(255) UNIQUE NOT NULL,
    pipeline_id VARCHAR(255) REFERENCES governance_pipelines(pipeline_id),
    stage_name VARCHAR(255) NOT NULL,
    sequence INT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_stages_stage_id ON pipeline_stages(stage_id);
CREATE INDEX idx_pipeline_stages_pipeline_id ON pipeline_stages(pipeline_id);
CREATE INDEX idx_pipeline_stages_sequence ON pipeline_stages(sequence);

-- Pipeline execution logs
CREATE TABLE IF NOT EXISTS pipeline_execution_logs (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR(255) UNIQUE NOT NULL,
    pipeline_id VARCHAR(255) REFERENCES governance_pipelines(pipeline_id),
    stage_id VARCHAR(255),
    status VARCHAR(50),
    result JSONB DEFAULT '{}',
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_execution_logs_execution_id ON pipeline_execution_logs(execution_id);
CREATE INDEX idx_pipeline_execution_logs_pipeline_id ON pipeline_execution_logs(pipeline_id);
CREATE INDEX idx_pipeline_execution_logs_stage_id ON pipeline_execution_logs(stage_id);
CREATE INDEX idx_pipeline_execution_logs_status ON pipeline_execution_logs(status);
CREATE INDEX idx_pipeline_execution_logs_created_at ON pipeline_execution_logs(created_at);

-- ============================================================================
-- Days 9-10: Data Lineage Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS lineage_entities (
    id SERIAL PRIMARY KEY,
    entity_id VARCHAR(255) UNIQUE NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    name VARCHAR(255),
    description TEXT,
    properties JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lineage_entities_entity_id ON lineage_entities(entity_id);
CREATE INDEX idx_lineage_entities_entity_type ON lineage_entities(entity_type);
CREATE INDEX idx_lineage_entities_name ON lineage_entities(name);

-- Lineage relationships table
CREATE TABLE IF NOT EXISTS lineage_relationships (
    id SERIAL PRIMARY KEY,
    relationship_id VARCHAR(255) UNIQUE NOT NULL,
    source_entity_id VARCHAR(255) REFERENCES lineage_entities(entity_id),
    target_entity_id VARCHAR(255) REFERENCES lineage_entities(entity_id),
    relationship_type VARCHAR(100) NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lineage_relationships_relationship_id ON lineage_relationships(relationship_id);
CREATE INDEX idx_lineage_relationships_source ON lineage_relationships(source_entity_id);
CREATE INDEX idx_lineage_relationships_target ON lineage_relationships(target_entity_id);
CREATE INDEX idx_lineage_relationships_type ON lineage_relationships(relationship_type);

-- Lineage paths table (cached for performance)
CREATE TABLE IF NOT EXISTS lineage_paths (
    id SERIAL PRIMARY KEY,
    path_id VARCHAR(255) UNIQUE NOT NULL,
    source_entity_id VARCHAR(255) REFERENCES lineage_entities(entity_id),
    target_entity_id VARCHAR(255) REFERENCES lineage_entities(entity_id),
    path_length INT,
    entities_in_path JSONB DEFAULT '[]',
    relationships_in_path JSONB DEFAULT '[]',
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lineage_paths_source ON lineage_paths(source_entity_id);
CREATE INDEX idx_lineage_paths_target ON lineage_paths(target_entity_id);
CREATE INDEX idx_lineage_paths_path_length ON lineage_paths(path_length);

-- ============================================================================
-- PHASE 2: VERSION MANAGER SERVICE (Days 11-12)
-- ============================================================================

-- ============================================================================
-- Day 11-12: Version Management Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS versions (
    id SERIAL PRIMARY KEY,
    version_id VARCHAR(255) UNIQUE NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    version_number INT NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    description TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags JSONB DEFAULT '[]',
    custom_metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_versions_version_id ON versions(version_id);
CREATE INDEX idx_versions_entity_id ON versions(entity_id);
CREATE INDEX idx_versions_entity_type ON versions(entity_type);
CREATE INDEX idx_versions_version_number ON versions(version_number);
CREATE INDEX idx_versions_status ON versions(status);
CREATE INDEX idx_versions_created_at ON versions(created_at);
CREATE INDEX idx_versions_entity_id_version_number ON versions(entity_id, version_number);

-- Version content table
CREATE TABLE IF NOT EXISTS version_contents (
    id SERIAL PRIMARY KEY,
    content_id VARCHAR(255) UNIQUE NOT NULL,
    version_id VARCHAR(255) REFERENCES versions(version_id) ON DELETE CASCADE,
    checksum VARCHAR(255),
    size_bytes INT,
    data JSONB DEFAULT '{}',
    stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_version_contents_content_id ON version_contents(content_id);
CREATE INDEX idx_version_contents_version_id ON version_contents(version_id);
CREATE INDEX idx_version_contents_checksum ON version_contents(checksum);

-- Version diffs table (for tracking differences)
CREATE TABLE IF NOT EXISTS version_diffs (
    id SERIAL PRIMARY KEY,
    diff_id VARCHAR(255) UNIQUE NOT NULL,
    from_version_id VARCHAR(255) REFERENCES versions(version_id),
    to_version_id VARCHAR(255) REFERENCES versions(version_id),
    from_version_number INT,
    to_version_number INT,
    changes JSONB DEFAULT '{}',
    added_keys JSONB DEFAULT '[]',
    removed_keys JSONB DEFAULT '[]',
    modified_keys JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_version_diffs_diff_id ON version_diffs(diff_id);
CREATE INDEX idx_version_diffs_from_version ON version_diffs(from_version_id);
CREATE INDEX idx_version_diffs_to_version ON version_diffs(to_version_id);

-- Version metadata table for tracking lifecycle
CREATE TABLE IF NOT EXISTS version_metadata (
    id SERIAL PRIMARY KEY,
    version_id VARCHAR(255) REFERENCES versions(version_id) ON DELETE CASCADE,
    lifecycle_event VARCHAR(100),
    event_description TEXT,
    event_metadata JSONB DEFAULT '{}',
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_version_metadata_version_id ON version_metadata(version_id);
CREATE INDEX idx_version_metadata_lifecycle_event ON version_metadata(lifecycle_event);
CREATE INDEX idx_version_metadata_occurred_at ON version_metadata(occurred_at);

-- ============================================================================
-- QUALITY IMPROVEMENT METRICS (Phase 1 Support)
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_improvement_metrics (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(255) NOT NULL,
    version INT DEFAULT 1,
    baseline_accuracy FLOAT DEFAULT 0.0,
    baseline_completeness FLOAT DEFAULT 0.0,
    baseline_consistency FLOAT DEFAULT 0.0,
    final_accuracy FLOAT DEFAULT 0.0,
    final_completeness FLOAT DEFAULT 0.0,
    final_consistency FLOAT DEFAULT 0.0,
    improvement_percentage FLOAT DEFAULT 0.0,
    files_count INT DEFAULT 0,
    chunks_count INT DEFAULT 0,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quality_improvement_product_id ON quality_improvement_metrics(product_id);
CREATE INDEX idx_quality_improvement_version ON quality_improvement_metrics(version);
CREATE INDEX idx_quality_improvement_calculated_at ON quality_improvement_metrics(calculated_at);

-- ============================================================================
-- MIGRATION HELPER TABLES (Optional)
-- ============================================================================

CREATE TABLE IF NOT EXISTS migration_log (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version INT NOT NULL,
    description VARCHAR(500),
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Record current schema version
INSERT INTO schema_version (version, description) VALUES
(1, 'Phase 1: Foundation - Quality Metrics, Audit Logging, Chunks'),
(2, 'Phase 2 Days 6-10: Governance, Lineage, Policy Engine, Alerts, Pipeline'),
(3, 'Phase 2 Days 11-12: Version Manager Service');

-- ============================================================================
-- GRANT PERMISSIONS (Optional - adjust as needed)
-- ============================================================================

-- Uncomment and modify as needed for your database user
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- ============================================================================
-- ROLLBACK SCRIPTS (If needed)
-- ============================================================================

-- To rollback all changes, run:
/*
DROP TABLE IF EXISTS version_metadata;
DROP TABLE IF EXISTS version_diffs;
DROP TABLE IF EXISTS version_contents;
DROP TABLE IF EXISTS versions;
DROP TABLE IF EXISTS lineage_paths;
DROP TABLE IF EXISTS lineage_relationships;
DROP TABLE IF EXISTS lineage_entities;
DROP TABLE IF EXISTS pipeline_execution_logs;
DROP TABLE IF EXISTS pipeline_stages;
DROP TABLE IF EXISTS governance_pipelines;
DROP TABLE IF EXISTS alert_history;
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS alert_rules;
DROP TABLE IF EXISTS quality_gates;
DROP TABLE IF EXISTS quality_thresholds;
DROP TABLE IF EXISTS policy_violations;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS chunk_quality_metrics;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS user_audit_log;
DROP TABLE IF EXISTS quality_improvement_metrics;
DROP TABLE IF EXISTS migration_log;
DROP TABLE IF EXISTS schema_version;
*/

-- ============================================================================
-- END OF MIGRATION SCRIPTS
-- ============================================================================
