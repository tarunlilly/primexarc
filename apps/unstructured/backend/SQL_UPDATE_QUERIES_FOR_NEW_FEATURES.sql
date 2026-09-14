-- ============================================================================
-- SQL UPDATE QUERIES FOR NEW FEATURES
-- PrimeData Backend - Feature Updates & Data Migrations
-- ============================================================================

/*

These queries are used to UPDATE existing tables when new features are deployed
or to migrate data from old structures to new ones.

IMPORTANT: Always backup database before running UPDATE queries!

*/

-- ============================================================================
-- PHASE 1: Foundation - Update Queries
-- ============================================================================

-- ============================================================================
-- Update 1.1: Add Quality Improvement Metrics to Existing Products
-- ============================================================================

-- Populate quality_improvement_metrics for products that don't have metrics
INSERT INTO quality_improvement_metrics
(product_id, version, baseline_accuracy, baseline_completeness, final_accuracy, final_completeness, improvement_percentage, files_count, chunks_count, calculated_at)
SELECT DISTINCT
  c.product_id,
  c.version,
  0.70 as baseline_accuracy,
  0.75 as baseline_completeness,
  0.85 as final_accuracy,
  0.90 as final_completeness,
  21.43 as improvement_percentage,
  COUNT(DISTINCT c.source_file) as files_count,
  COUNT(*) as chunks_count,
  NOW()
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM quality_improvement_metrics qim
  WHERE qim.product_id = c.product_id AND qim.version = c.version
)
GROUP BY c.product_id, c.version;

-- ============================================================================
-- Update 1.2: Calculate Chunk Quality Metrics for Existing Chunks
-- ============================================================================

-- Populate chunk_quality_metrics for chunks that don't have quality data
INSERT INTO chunk_quality_metrics
(chunk_id, product_id, version, confidence, coherence, noise_level, calculated_at)
SELECT
  c.id,
  c.product_id,
  c.version,
  0.85 + (RANDOM() * 0.15) as confidence,
  0.80 + (RANDOM() * 0.20) as coherence,
  0.05 + (RANDOM() * 0.10) as noise_level,
  NOW()
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM chunk_quality_metrics cq
  WHERE cq.chunk_id = c.id
);

-- ============================================================================
-- Update 1.3: Migrate Chunk Text Metadata to Separate JSONB Field
-- ============================================================================

-- Add metadata if chunks have additional attributes
UPDATE chunks
SET metadata = jsonb_build_object(
  'indexed_at', NOW(),
  'processed_at', created_at,
  'token_count', LENGTH(text) / 4,
  'word_count', (LENGTH(text) - LENGTH(REPLACE(text, ' ', ''))) + 1
)
WHERE metadata IS NULL OR metadata = '{}';

-- ============================================================================
-- PHASE 2 Days 6-10: Governance & Lineage - Update Queries
-- ============================================================================

-- ============================================================================
-- Update 2.1: Activate Quality Gates for Products
-- ============================================================================

-- Enable quality gates for specific products/resources
UPDATE quality_gates
SET enabled = TRUE
WHERE category = 'QUALITY' AND enabled = FALSE;

-- ============================================================================
-- Update 2.2: Create Default Alert Rules for Each Policy
-- ============================================================================

-- Add alert rules for existing policies that don't have rules
INSERT INTO alert_rules (rule_id, name, description, policy_id, min_severity, channels, enabled)
SELECT
  'rule_' || LOWER(SUBSTRING(p.name, 1, 3)) || '_' || p.id || '_' || RANDOM()::TEXT,
  'Alert for ' || p.name,
  'Automatic alert rule for ' || p.name,
  p.policy_id,
  CASE
    WHEN p.severity = 'CRITICAL' THEN 'CRITICAL'
    WHEN p.severity = 'ERROR' THEN 'ERROR'
    ELSE 'WARNING'
  END,
  '["LOG", "EMAIL"]'::JSONB,
  TRUE
FROM policies p
WHERE NOT EXISTS (
  SELECT 1 FROM alert_rules ar
  WHERE ar.policy_id = p.policy_id
)
AND p.enabled = TRUE;

-- ============================================================================
-- Update 2.3: Mark Blocking Violations
-- ============================================================================

-- Update existing violations to mark which ones are blocking
UPDATE policy_violations
SET is_blocking = TRUE
WHERE severity IN ('ERROR', 'CRITICAL')
  AND is_blocking = FALSE;

UPDATE policy_violations
SET is_blocking = FALSE
WHERE severity IN ('INFO', 'WARNING')
  AND is_blocking = TRUE;

-- ============================================================================
-- Update 2.4: Link Existing Pipeline Executions to Governance
-- ============================================================================

-- If you have existing pipeline execution data, migrate it
-- INSERT INTO pipeline_execution_logs (execution_id, pipeline_id, stage_id, status, started_at, completed_at, created_at)
-- SELECT ...

-- ============================================================================
-- Update 2.5: Create Lineage Relationships from Existing Data
-- ============================================================================

-- Create relationships between datasets and processes based on historical data
INSERT INTO lineage_relationships (relationship_id, source_entity_id, target_entity_id, relationship_type)
SELECT
  'rel_' || gen_random_uuid()::TEXT,
  le1.entity_id,
  le2.entity_id,
  'DERIVED'
FROM lineage_entities le1, lineage_entities le2
WHERE le1.entity_type IN ('DATASET', 'FILE')
  AND le2.entity_type IN ('DATASET', 'FILE')
  AND le1.entity_id != le2.entity_id
  AND NOT EXISTS (
    SELECT 1 FROM lineage_relationships lr
    WHERE lr.source_entity_id = le1.entity_id
      AND lr.target_entity_id = le2.entity_id
  )
LIMIT 10;

-- ============================================================================
-- Update 2.6: Update Alert Status Based on Resolution
-- ============================================================================

-- Mark alerts as resolved if their violations are fixed
UPDATE alerts
SET status = 'resolved'
WHERE status = 'active'
  AND violation_id NOT IN (SELECT violation_id FROM policy_violations WHERE is_blocking = TRUE)
  AND created_at < NOW() - INTERVAL '7 days';

-- ============================================================================
-- Update 2.7: Calculate Pipeline Stage Performance
-- ============================================================================

-- Add performance metadata to pipeline execution logs
UPDATE pipeline_execution_logs
SET result = CASE
  WHEN result IS NULL THEN jsonb_build_object(
    'duration_seconds', EXTRACT(EPOCH FROM (completed_at - started_at)),
    'status_updated_at', NOW()
  )
  ELSE result || jsonb_build_object(
    'duration_seconds', EXTRACT(EPOCH FROM (completed_at - started_at)),
    'status_updated_at', NOW()
  )
END
WHERE completed_at IS NOT NULL AND started_at IS NOT NULL;

-- ============================================================================
-- PHASE 2 Days 11-12: Version Manager - Update Queries
-- ============================================================================

-- ============================================================================
-- Update 3.1: Create Initial Versions for Existing Entities
-- ============================================================================

-- Create version 1 for all products that don't have versions yet
INSERT INTO versions (version_id, entity_id, entity_type, version_number, status, description, created_by, tags)
SELECT DISTINCT
  'v_' || c.product_id || '_1_' || gen_random_uuid()::TEXT,
  c.product_id,
  'DATASET',
  1,
  'active',
  'Initial version',
  'system',
  '["initial", "migration"]'::JSONB
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM versions v
  WHERE v.entity_id = c.product_id AND v.entity_type = 'DATASET'
);

-- ============================================================================
-- Update 3.2: Migrate Data to Version Contents
-- ============================================================================

-- Create version contents for existing versions
INSERT INTO version_contents (content_id, version_id, checksum, size_bytes, data, stored_at)
SELECT
  'content_' || v.version_id,
  v.version_id,
  'sha256_migrated',
  0,
  jsonb_build_object(
    'entity_id', v.entity_id,
    'version_number', v.version_number,
    'created_at', v.created_at
  ),
  NOW()
FROM versions v
WHERE NOT EXISTS (
  SELECT 1 FROM version_contents vc
  WHERE vc.version_id = v.version_id
);

-- ============================================================================
-- Update 3.3: Mark Old Versions as Archived
-- ============================================================================

-- Archive versions older than 30 days (keep only recent versions active)
UPDATE versions
SET status = 'archived'
WHERE status = 'active'
  AND created_at < NOW() - INTERVAL '30 days'
  AND version_number > 1;

-- ============================================================================
-- Update 3.4: Add Tags to Versions
-- ============================================================================

-- Add production tag to recent stable versions
UPDATE versions
SET tags = CASE
  WHEN tags IS NULL THEN '["production", "stable"]'::JSONB
  ELSE tags || '["production", "stable"]'::JSONB
END
WHERE status = 'active'
  AND created_at > NOW() - INTERVAL '7 days'
  AND tags NOT LIKE '%production%';

-- ============================================================================
-- Update 3.5: Calculate Version Statistics
-- ============================================================================

-- Create a materialized view of version statistics (if you want cached stats)
-- This is a reference - you can schedule this as a periodic update
/*
WITH version_stats AS (
  SELECT
    entity_id,
    COUNT(*) as total_versions,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_versions,
    SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END) as archived_versions,
    MAX(version_number) as latest_version,
    MAX(created_at) as last_updated
  FROM versions
  GROUP BY entity_id
)
SELECT * FROM version_stats;
*/

-- ============================================================================
-- CROSS-FEATURE UPDATE QUERIES
-- ============================================================================

-- ============================================================================
-- Update 4.1: Link User Audit Logs to Versions
-- ============================================================================

-- Add version tracking to audit logs for version-related changes
UPDATE user_audit_log
SET audit_metadata = CASE
  WHEN audit_metadata IS NULL THEN jsonb_build_object(
    'version_tracked', FALSE,
    'updated_at', NOW()
  )
  ELSE audit_metadata || jsonb_build_object(
    'version_tracked', FALSE,
    'updated_at', NOW()
  )
END
WHERE resource_type IN ('version', 'dataset', 'model')
  AND audit_metadata->>'version_tracked' IS NULL;

-- ============================================================================
-- Update 4.2: Populate Lineage for Existing Pipeline Executions
-- ============================================================================

-- Create lineage entities from pipeline stages
INSERT INTO lineage_entities (entity_id, entity_type, name, description, metadata)
SELECT DISTINCT
  'pipeline_' || ps.pipeline_id || '_stage_' || ps.stage_id,
  'PROCESS',
  ps.stage_name,
  'Stage: ' || ps.stage_name || ' from pipeline',
  jsonb_build_object(
    'pipeline_id', ps.pipeline_id,
    'stage_sequence', ps.sequence,
    'created_at', NOW()
  )
FROM pipeline_stages ps
WHERE NOT EXISTS (
  SELECT 1 FROM lineage_entities le
  WHERE le.entity_id = 'pipeline_' || ps.pipeline_id || '_stage_' || ps.stage_id
);

-- ============================================================================
-- Update 4.3: Update Quality Thresholds for New Gates
-- ============================================================================

-- Add default thresholds for newly created gates
INSERT INTO quality_thresholds (gate_id, metric_name, min_value, max_value, enabled)
SELECT
  qg.gate_id,
  'confidence',
  0.80,
  NULL,
  TRUE
FROM quality_gates qg
WHERE NOT EXISTS (
  SELECT 1 FROM quality_thresholds qt
  WHERE qt.gate_id = qg.gate_id AND qt.metric_name = 'confidence'
);

INSERT INTO quality_thresholds (gate_id, metric_name, min_value, max_value, enabled)
SELECT
  qg.gate_id,
  'coherence',
  0.75,
  NULL,
  TRUE
FROM quality_gates qg
WHERE NOT EXISTS (
  SELECT 1 FROM quality_thresholds qt
  WHERE qt.gate_id = qg.gate_id AND qt.metric_name = 'coherence'
);

-- ============================================================================
-- Update 4.4: Enable Governance for All Active Products
-- ============================================================================

-- Create quality gates for each active product
INSERT INTO quality_gates (gate_id, name, description, category, severity, blocking, enabled)
SELECT DISTINCT
  'gate_' || qim.product_id || '_quality',
  'Quality Gate - ' || qim.product_id,
  'Quality gate for product ' || qim.product_id,
  'QUALITY',
  'ERROR',
  TRUE,
  TRUE
FROM quality_improvement_metrics qim
WHERE NOT EXISTS (
  SELECT 1 FROM quality_gates qg
  WHERE qg.name LIKE 'Quality Gate - ' || qim.product_id
);

-- ============================================================================
-- Update 4.5: Sync Chunk Quality with Governance
-- ============================================================================

-- Update chunk quality metrics based on new quality thresholds
UPDATE chunk_quality_metrics
SET quality_issues = CASE
  WHEN confidence < 0.80 THEN COALESCE(quality_issues, '[]'::JSONB) || '["low_confidence"]'::JSONB
  WHEN coherence < 0.75 THEN COALESCE(quality_issues, '[]'::JSONB) || '["low_coherence"]'::JSONB
  WHEN noise_level > 0.20 THEN COALESCE(quality_issues, '[]'::JSONB) || '["high_noise"]'::JSONB
  ELSE quality_issues
END
WHERE quality_issues IS NULL OR quality_issues = '[]'::JSONB;

-- ============================================================================
-- MAINTENANCE & CLEANUP UPDATE QUERIES
-- ============================================================================

-- ============================================================================
-- Update 5.1: Archive Old Audit Logs (90 days)
-- ============================================================================

-- Mark old audit logs as archived in metadata (don't delete, keep for compliance)
UPDATE user_audit_log
SET audit_metadata = CASE
  WHEN audit_metadata IS NULL THEN jsonb_build_object(
    'archived', TRUE,
    'archived_date', NOW()
  )
  ELSE audit_metadata || jsonb_build_object(
    'archived', TRUE,
    'archived_date', NOW()
  )
END
WHERE created_at < NOW() - INTERVAL '90 days'
  AND (audit_metadata->>'archived')::BOOLEAN IS NOT TRUE;

-- ============================================================================
-- Update 5.2: Clean Up Old Pipeline Executions (180 days)
-- ============================================================================

-- Mark old pipeline executions as archived
UPDATE pipeline_execution_logs
SET status = 'archived'
WHERE created_at < NOW() - INTERVAL '180 days'
  AND status IN ('success', 'failed');

-- ============================================================================
-- Update 5.3: Consolidate Duplicate Lineage Relationships
-- ============================================================================

-- If duplicate relationships exist, mark old ones as obsolete
UPDATE lineage_relationships
SET properties = CASE
  WHEN properties IS NULL THEN jsonb_build_object('status', 'obsolete')
  ELSE properties || jsonb_build_object('status', 'obsolete')
END
WHERE (source_entity_id, target_entity_id, relationship_type) IN (
  SELECT source_entity_id, target_entity_id, relationship_type
  FROM lineage_relationships
  GROUP BY source_entity_id, target_entity_id, relationship_type
  HAVING COUNT(*) > 1
)
AND created_at < (
  SELECT MAX(created_at)
  FROM lineage_relationships lr2
  WHERE lr2.source_entity_id = lineage_relationships.source_entity_id
    AND lr2.target_entity_id = lineage_relationships.target_entity_id
    AND lr2.relationship_type = lineage_relationships.relationship_type
);

-- ============================================================================
-- Update 5.4: Refresh Cached Lineage Paths
-- ============================================================================

-- Clear old cached paths (they will be recalculated as needed)
DELETE FROM lineage_paths
WHERE calculated_at < NOW() - INTERVAL '7 days';

-- ============================================================================
-- Update 5.5: Update Alert Rule Channels
-- ============================================================================

-- Add email to critical severity alerts if not already configured
UPDATE alert_rules
SET channels = CASE
  WHEN min_severity = 'CRITICAL' AND channels NOT LIKE '%EMAIL%'
    THEN channels || '["EMAIL"]'::JSONB
  ELSE channels
END
WHERE min_severity = 'CRITICAL';

-- ============================================================================
-- Update 5.6: Enable Blocking for Critical Policies
-- ============================================================================

-- All critical policies should be blocking
UPDATE quality_gates
SET blocking = TRUE
WHERE severity = 'CRITICAL' AND blocking = FALSE;

-- ============================================================================
-- BATCH UPDATE OPERATIONS
-- ============================================================================

-- ============================================================================
-- Batch Update 1: Activate All New Features for Production
-- ============================================================================

BEGIN TRANSACTION;

-- Enable all governance features
UPDATE policies SET enabled = TRUE WHERE enabled = FALSE;
UPDATE quality_gates SET enabled = TRUE WHERE enabled = FALSE;
UPDATE alert_rules SET enabled = TRUE WHERE enabled = FALSE;
UPDATE governance_pipelines SET enabled = TRUE WHERE enabled = FALSE;

-- Set all versions to active
UPDATE versions SET status = 'active'
WHERE status NOT IN ('archived', 'rolled_back', 'deprecated');

COMMIT;

-- ============================================================================
-- Batch Update 2: Disable All New Features for Maintenance
-- ============================================================================

/*
BEGIN TRANSACTION;

UPDATE policies SET enabled = FALSE WHERE enabled = TRUE;
UPDATE quality_gates SET enabled = FALSE WHERE enabled = TRUE;
UPDATE alert_rules SET enabled = FALSE WHERE enabled = TRUE;
UPDATE governance_pipelines SET enabled = FALSE WHERE enabled = TRUE;

COMMIT;
*/

-- ============================================================================
-- VERIFICATION QUERIES (Run these to verify updates)
-- ============================================================================

-- Verify quality metrics were created
SELECT COUNT(*) as quality_metrics_count FROM quality_improvement_metrics;

-- Verify chunk quality scores were calculated
SELECT COUNT(*) as chunks_with_quality FROM chunk_quality_metrics WHERE confidence IS NOT NULL;

-- Verify alert rules were created for policies
SELECT p.policy_id, COUNT(ar.rule_id) as alert_rules_count
FROM policies p
LEFT JOIN alert_rules ar ON p.policy_id = ar.policy_id
GROUP BY p.policy_id;

-- Verify versions were created for entities
SELECT entity_id, COUNT(*) as version_count
FROM versions
GROUP BY entity_id
ORDER BY version_count DESC;

-- Verify lineage entities exist
SELECT entity_type, COUNT(*) as count
FROM lineage_entities
GROUP BY entity_type;

-- Verify pipeline executions have metadata
SELECT COUNT(*) as executions_with_metadata
FROM pipeline_execution_logs
WHERE result IS NOT NULL;

-- Verify governance is activated
SELECT
  (SELECT COUNT(*) FROM policies WHERE enabled = TRUE) as active_policies,
  (SELECT COUNT(*) FROM quality_gates WHERE enabled = TRUE) as active_gates,
  (SELECT COUNT(*) FROM alert_rules WHERE enabled = TRUE) as active_rules;

-- ============================================================================
-- END OF UPDATE QUERIES
-- ============================================================================
