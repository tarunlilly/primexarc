-- ============================================================================
-- SQL SAMPLE DATA AND QUERY EXAMPLES
-- PrimeData Backend - All Features
-- ============================================================================

-- ============================================================================
-- SAMPLE DATA INSERTION
-- ============================================================================

-- ============================================================================
-- Phase 1: Sample User Audit Log Data
-- ============================================================================

INSERT INTO user_audit_log (user_id, workspace_id, action, resource_type, resource_id, changes, status)
VALUES
  ('user_123', 'ws_001', 'CREATE', 'product', 'prod_456', '{"name": "Test Product"}', 'success'),
  ('user_123', 'ws_001', 'UPDATE', 'product', 'prod_456', '{"status": "active"}', 'success'),
  ('user_124', 'ws_001', 'DELETE', 'chunk', 'chunk_789', '{}', 'success'),
  ('user_125', 'ws_002', 'VIEW', 'report', 'report_001', '{}', 'success');

-- ============================================================================
-- Phase 1: Sample Quality Improvement Metrics
-- ============================================================================

INSERT INTO quality_improvement_metrics
(product_id, version, baseline_accuracy, baseline_completeness, final_accuracy, final_completeness, improvement_percentage, files_count, chunks_count)
VALUES
  ('prod_456', 1, 0.75, 0.80, 0.92, 0.95, 22.66, 50, 5000),
  ('prod_789', 1, 0.68, 0.72, 0.85, 0.88, 25.0, 75, 7500),
  ('prod_101', 1, 0.85, 0.90, 0.95, 0.98, 11.76, 100, 10000);

-- ============================================================================
-- Phase 1: Sample Chunks Data
-- ============================================================================

INSERT INTO chunks (product_id, version, chunk_order, text, page, source_file)
VALUES
  ('prod_456', 1, 1, 'This is the first chunk of text from the document.', 1, 'document1.pdf'),
  ('prod_456', 1, 2, 'This is the second chunk continuing from the previous one.', 1, 'document1.pdf'),
  ('prod_456', 1, 3, 'This is the third chunk on page two.', 2, 'document1.pdf'),
  ('prod_789', 1, 1, 'Different product first chunk.', 1, 'document2.pdf'),
  ('prod_789', 1, 2, 'Different product second chunk.', 2, 'document2.pdf');

-- ============================================================================
-- Phase 1: Sample Chunk Quality Metrics
-- ============================================================================

INSERT INTO chunk_quality_metrics (chunk_id, product_id, version, confidence, coherence, noise_level, has_mid_sentence_start, has_mid_sentence_end)
VALUES
  (1, 'prod_456', 1, 0.95, 0.92, 0.05, FALSE, FALSE),
  (2, 'prod_456', 1, 0.88, 0.85, 0.12, FALSE, TRUE),
  (3, 'prod_456', 1, 0.92, 0.90, 0.08, TRUE, FALSE),
  (4, 'prod_789', 1, 0.91, 0.89, 0.09, FALSE, FALSE),
  (5, 'prod_789', 1, 0.86, 0.84, 0.14, TRUE, TRUE);

-- ============================================================================
-- Phase 2 Day 6: Sample Policies
-- ============================================================================

INSERT INTO policies (policy_id, name, description, category, severity, enabled)
VALUES
  ('policy_quality_001', 'Minimum Quality Score', 'Ensures all chunks have minimum quality', 'QUALITY', 'ERROR', TRUE),
  ('policy_compliance_001', 'Data Compliance', 'Ensures compliance with data standards', 'COMPLIANCE', 'CRITICAL', TRUE),
  ('policy_performance_001', 'Performance Threshold', 'Ensures pipeline meets performance standards', 'PERFORMANCE', 'WARNING', TRUE);

-- ============================================================================
-- Phase 2 Day 6: Sample Policy Violations
-- ============================================================================

INSERT INTO policy_violations (violation_id, policy_id, resource_id, resource_type, severity, message, is_blocking)
VALUES
  ('violation_001', 'policy_quality_001', 'prod_456', 'product', 'ERROR', 'Quality score below threshold', TRUE),
  ('violation_002', 'policy_compliance_001', 'prod_789', 'product', 'CRITICAL', 'Missing compliance metadata', TRUE),
  ('violation_003', 'policy_performance_001', 'stage_001', 'pipeline_stage', 'WARNING', 'Performance degradation detected', FALSE);

-- ============================================================================
-- Phase 2 Day 7: Sample Quality Thresholds
-- ============================================================================

INSERT INTO quality_thresholds (gate_id, metric_name, min_value, max_value, enabled)
VALUES
  ('gate_quality_001', 'confidence', 0.80, NULL, TRUE),
  ('gate_quality_001', 'coherence', 0.75, NULL, TRUE),
  ('gate_quality_001', 'noise_level', NULL, 0.20, TRUE),
  ('gate_performance_001', 'latency_ms', NULL, 1000.0, TRUE),
  ('gate_performance_001', 'throughput_per_sec', 100.0, NULL, TRUE);

-- ============================================================================
-- Phase 2 Day 7: Sample Quality Gates
-- ============================================================================

INSERT INTO quality_gates (gate_id, name, description, category, severity, blocking)
VALUES
  ('gate_quality_001', 'Quality Gate', 'Checks minimum quality metrics', 'QUALITY', 'ERROR', TRUE),
  ('gate_performance_001', 'Performance Gate', 'Checks performance thresholds', 'PERFORMANCE', 'WARNING', FALSE),
  ('gate_compliance_001', 'Compliance Gate', 'Checks compliance requirements', 'COMPLIANCE', 'CRITICAL', TRUE);

-- ============================================================================
-- Phase 2 Day 7: Sample Alert Rules
-- ============================================================================

INSERT INTO alert_rules (rule_id, name, description, policy_id, min_severity, channels, enabled)
VALUES
  ('rule_alert_001', 'Quality Alert', 'Alerts on quality violations', 'policy_quality_001', 'ERROR', '["LOG", "EMAIL"]', TRUE),
  ('rule_alert_002', 'Compliance Alert', 'Alerts on compliance violations', 'policy_compliance_001', 'CRITICAL', '["LOG", "SLACK", "EMAIL"]', TRUE),
  ('rule_alert_003', 'Performance Warning', 'Alerts on performance issues', 'policy_performance_001', 'WARNING', '["LOG"]', TRUE);

-- ============================================================================
-- Phase 2 Day 7: Sample Alerts
-- ============================================================================

INSERT INTO alerts (alert_id, rule_id, violation_id, resource_id, priority, message, channels, status)
VALUES
  ('alert_001', 'rule_alert_001', 'violation_001', 'prod_456', 'high', 'Quality score below minimum threshold', '{"log": true, "email": true}', 'active'),
  ('alert_002', 'rule_alert_002', 'violation_002', 'prod_789', 'critical', 'Missing critical compliance metadata', '{"log": true, "slack": true, "email": true}', 'active'),
  ('alert_003', 'rule_alert_003', 'violation_003', 'stage_001', 'medium', 'Performance degradation detected', '{"log": true}', 'resolved');

-- ============================================================================
-- Phase 2 Day 8: Sample Pipelines
-- ============================================================================

INSERT INTO governance_pipelines (pipeline_id, name, description, pipeline_type)
VALUES
  ('pipeline_ingestion_001', 'Data Ingestion Pipeline', 'Main data ingestion pipeline', 'ingestion'),
  ('pipeline_processing_001', 'Data Processing Pipeline', 'Main data processing pipeline', 'processing'),
  ('pipeline_export_001', 'Data Export Pipeline', 'Main data export pipeline', 'export');

-- ============================================================================
-- Phase 2 Day 8: Sample Pipeline Stages
-- ============================================================================

INSERT INTO pipeline_stages (stage_id, pipeline_id, stage_name, sequence)
VALUES
  ('stage_001', 'pipeline_ingestion_001', 'raw_ingestion', 1),
  ('stage_002', 'pipeline_ingestion_001', 'validation', 2),
  ('stage_003', 'pipeline_ingestion_001', 'enrichment', 3),
  ('stage_004', 'pipeline_ingestion_001', 'indexing', 4),
  ('stage_005', 'pipeline_processing_001', 'preprocessing', 1),
  ('stage_006', 'pipeline_processing_001', 'transformation', 2),
  ('stage_007', 'pipeline_processing_001', 'aggregation', 3);

-- ============================================================================
-- Phase 2 Days 9-10: Sample Lineage Entities
-- ============================================================================

INSERT INTO lineage_entities (entity_id, entity_type, name, description)
VALUES
  ('entity_raw_001', 'DATASET', 'Raw Data Input', 'Original raw data from source'),
  ('entity_proc_001', 'PROCESS', 'Data Processor', 'Process that transforms raw data'),
  ('entity_clean_001', 'DATASET', 'Cleaned Data', 'Data after cleaning process'),
  ('entity_model_001', 'MODEL', 'ML Model v1', 'Machine learning model version 1'),
  ('entity_export_001', 'DATASET', 'Export Output', 'Final exported dataset'),
  ('entity_pipeline_001', 'PIPELINE', 'Main Pipeline', 'Main data processing pipeline');

-- ============================================================================
-- Phase 2 Days 9-10: Sample Lineage Relationships
-- ============================================================================

INSERT INTO lineage_relationships (relationship_id, source_entity_id, target_entity_id, relationship_type)
VALUES
  ('rel_001', 'entity_raw_001', 'entity_proc_001', 'INPUT'),
  ('rel_002', 'entity_proc_001', 'entity_clean_001', 'OUTPUT'),
  ('rel_003', 'entity_clean_001', 'entity_model_001', 'INPUT'),
  ('rel_004', 'entity_model_001', 'entity_export_001', 'GENERATED_BY'),
  ('rel_005', 'entity_pipeline_001', 'entity_proc_001', 'CONTAINS'),
  ('rel_006', 'entity_clean_001', 'entity_pipeline_001', 'DEPENDS_ON');

-- ============================================================================
-- Phase 2 Days 11-12: Sample Versions
-- ============================================================================

INSERT INTO versions (version_id, entity_id, entity_type, version_number, status, description, created_by, tags)
VALUES
  ('v_prod_456_1_abc123', 'prod_456', 'DATASET', 1, 'active', 'Initial dataset version', 'user_123', '["production", "v1"]'),
  ('v_prod_456_2_def456', 'prod_456', 'DATASET', 2, 'active', 'Updated with new data', 'user_124', '["production", "v2"]'),
  ('v_prod_456_3_ghi789', 'prod_456', 'DATASET', 3, 'rolled_back', 'Rollback from v2', 'user_125', '["rollback"]'),
  ('v_model_001_1_jkl012', 'model_001', 'MODEL', 1, 'active', 'Initial model', 'user_123', '["production"]'),
  ('v_model_001_2_mno345', 'model_001', 'MODEL', 2, 'deprecated', 'Deprecated model', 'user_124', '["deprecated"]');

-- ============================================================================
-- Phase 2 Days 11-12: Sample Version Contents
-- ============================================================================

INSERT INTO version_contents (content_id, version_id, checksum, size_bytes, data)
VALUES
  ('content_1_abc123', 'v_prod_456_1_abc123', 'sha256_hash_1', 1024, '{"records": 1000, "fields": 10}'),
  ('content_2_def456', 'v_prod_456_2_def456', 'sha256_hash_2', 2048, '{"records": 2000, "fields": 10}'),
  ('content_3_ghi789', 'v_prod_456_3_ghi789', 'sha256_hash_1', 1024, '{"records": 1000, "fields": 10}');

-- ============================================================================
-- USEFUL QUERIES
-- ============================================================================

-- ============================================================================
-- Query 1: Get all user audit logs for a specific user
-- ============================================================================
SELECT * FROM user_audit_log
WHERE user_id = 'user_123'
ORDER BY created_at DESC;

-- ============================================================================
-- Query 2: Get quality improvement metrics by product
-- ============================================================================
SELECT
  product_id,
  version,
  baseline_accuracy,
  final_accuracy,
  improvement_percentage,
  files_count,
  chunks_count
FROM quality_improvement_metrics
WHERE product_id = 'prod_456'
ORDER BY version DESC;

-- ============================================================================
-- Query 3: Get chunks with low quality scores
-- ============================================================================
SELECT
  c.id,
  c.product_id,
  c.chunk_order,
  c.source_file,
  cq.confidence,
  cq.coherence,
  cq.noise_level
FROM chunks c
JOIN chunk_quality_metrics cq ON c.id = cq.chunk_id
WHERE cq.confidence < 0.80 OR cq.coherence < 0.80
ORDER BY cq.confidence ASC;

-- ============================================================================
-- Query 4: Get active blocking policy violations
-- ============================================================================
SELECT
  pv.violation_id,
  pv.policy_id,
  p.name as policy_name,
  pv.resource_id,
  pv.severity,
  pv.message
FROM policy_violations pv
JOIN policies p ON pv.policy_id = p.policy_id
WHERE pv.is_blocking = TRUE
ORDER BY pv.created_at DESC;

-- ============================================================================
-- Query 5: Get active alerts
-- ============================================================================
SELECT
  a.alert_id,
  a.rule_id,
  ar.name as rule_name,
  a.resource_id,
  a.priority,
  a.message,
  a.status,
  a.created_at
FROM alerts a
JOIN alert_rules ar ON a.rule_id = ar.rule_id
WHERE a.status = 'active'
ORDER BY a.created_at DESC;

-- ============================================================================
-- Query 6: Get pipeline execution history
-- ============================================================================
SELECT
  pel.execution_id,
  pel.pipeline_id,
  pel.stage_id,
  pel.status,
  pel.started_at,
  pel.completed_at,
  EXTRACT(EPOCH FROM (pel.completed_at - pel.started_at)) as duration_seconds
FROM pipeline_execution_logs pel
ORDER BY pel.created_at DESC
LIMIT 100;

-- ============================================================================
-- Query 7: Get lineage path from raw data to export
-- ============================================================================
SELECT
  lp.path_id,
  lp.source_entity_id,
  lp.target_entity_id,
  lp.path_length,
  le_source.name as source_name,
  le_target.name as target_name
FROM lineage_paths lp
JOIN lineage_entities le_source ON lp.source_entity_id = le_source.entity_id
JOIN lineage_entities le_target ON lp.target_entity_id = le_target.entity_id
WHERE le_source.entity_type = 'DATASET' AND le_target.entity_type = 'DATASET'
ORDER BY lp.path_length ASC;

-- ============================================================================
-- Query 8: Get all versions of a specific entity
-- ============================================================================
SELECT
  version_id,
  entity_id,
  version_number,
  status,
  description,
  created_by,
  created_at
FROM versions
WHERE entity_id = 'prod_456'
ORDER BY version_number DESC;

-- ============================================================================
-- Query 9: Get version comparison (diff)
-- ============================================================================
SELECT
  vd.diff_id,
  vd.from_version_number,
  vd.to_version_number,
  vd.added_keys,
  vd.removed_keys,
  vd.modified_keys
FROM version_diffs vd
WHERE vd.from_version_id = 'v_prod_456_1_abc123'
  AND vd.to_version_id = 'v_prod_456_2_def456';

-- ============================================================================
-- Query 10: Get recent rollback versions
-- ============================================================================
SELECT
  version_id,
  entity_id,
  version_number,
  status,
  created_at,
  created_by
FROM versions
WHERE status = 'rolled_back'
ORDER BY created_at DESC;

-- ============================================================================
-- Query 11: Get audit log statistics by action
-- ============================================================================
SELECT
  action,
  COUNT(*) as count,
  COUNT(DISTINCT user_id) as unique_users
FROM user_audit_log
GROUP BY action
ORDER BY count DESC;

-- ============================================================================
-- Query 12: Get quality gate status summary
-- ============================================================================
SELECT
  qg.gate_id,
  qg.name,
  qg.category,
  qg.severity,
  qg.blocking,
  COUNT(qt.id) as threshold_count
FROM quality_gates qg
LEFT JOIN quality_thresholds qt ON qg.gate_id = qt.gate_id
GROUP BY qg.id, qg.gate_id, qg.name, qg.category, qg.severity, qg.blocking
ORDER BY qg.created_at DESC;

-- ============================================================================
-- Query 13: Get alert statistics
-- ============================================================================
SELECT
  ar.rule_id,
  ar.name,
  COUNT(a.id) as total_alerts,
  SUM(CASE WHEN a.status = 'active' THEN 1 ELSE 0 END) as active_alerts,
  SUM(CASE WHEN a.status = 'resolved' THEN 1 ELSE 0 END) as resolved_alerts
FROM alert_rules ar
LEFT JOIN alerts a ON ar.rule_id = a.rule_id
GROUP BY ar.id, ar.rule_id, ar.name
ORDER BY total_alerts DESC;

-- ============================================================================
-- Query 14: Get pipeline performance metrics
-- ============================================================================
SELECT
  pipeline_id,
  stage_id,
  COUNT(*) as executions,
  AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
  MIN(EXTRACT(EPOCH FROM (completed_at - started_at))) as min_duration_seconds,
  MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_duration_seconds,
  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_executions
FROM pipeline_execution_logs
WHERE completed_at IS NOT NULL
GROUP BY pipeline_id, stage_id
ORDER BY avg_duration_seconds DESC;

-- ============================================================================
-- Query 15: Get entity relationships (direct and inherited)
-- ============================================================================
SELECT
  lr.relationship_id,
  le_source.name as source_name,
  le_source.entity_type as source_type,
  lr.relationship_type,
  le_target.name as target_name,
  le_target.entity_type as target_type
FROM lineage_relationships lr
JOIN lineage_entities le_source ON lr.source_entity_id = le_source.entity_id
JOIN lineage_entities le_target ON lr.target_entity_id = le_target.entity_id
ORDER BY le_source.name, lr.relationship_type;

-- ============================================================================
-- MAINTENANCE QUERIES
-- ============================================================================

-- ============================================================================
-- Update version status
-- ============================================================================
UPDATE versions
SET status = 'archived'
WHERE version_id = 'v_prod_456_1_abc123';

-- ============================================================================
-- Mark alert as resolved
-- ============================================================================
UPDATE alerts
SET status = 'resolved'
WHERE alert_id = 'alert_001';

-- ============================================================================
-- Disable a policy
-- ============================================================================
UPDATE policies
SET enabled = FALSE
WHERE policy_id = 'policy_performance_001';

-- ============================================================================
-- Clean old audit logs (older than 90 days)
-- ============================================================================
DELETE FROM user_audit_log
WHERE created_at < NOW() - INTERVAL '90 days';

-- ============================================================================
-- Archive old pipeline executions (older than 180 days)
-- ============================================================================
DELETE FROM pipeline_execution_logs
WHERE created_at < NOW() - INTERVAL '180 days';

-- ============================================================================
-- Get database statistics
-- ============================================================================
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================================================
-- END OF SQL QUERIES
-- ============================================================================
