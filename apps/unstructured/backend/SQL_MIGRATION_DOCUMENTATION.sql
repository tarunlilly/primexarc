-- ============================================================================
-- DATABASE MIGRATION STRATEGY & DOCUMENTATION
-- PrimeData Backend - Complete Implementation
-- ============================================================================

/*

DATABASE MIGRATION GUIDE
========================

This document provides comprehensive guidance for migrating the PostgreSQL
database schema to support all new features implemented in the PrimeData backend.

*/

-- ============================================================================
-- TABLE STRUCTURE DOCUMENTATION
-- ============================================================================

/*

1. USER_AUDIT_LOG (Day 3 - User Audit Logging)
────────────────────────────────────────────────

Purpose: Track all user actions on the system for compliance and auditing

Columns:
- id: Primary key
- user_id: ID of the user performing the action
- workspace_id: ID of the workspace where action occurred
- action: Type of action (CREATE, READ, UPDATE, DELETE, VIEW)
- resource_type: Type of resource affected (product, chunk, report, etc.)
- resource_id: ID of the resource
- changes: JSONB object containing before/after changes
- audit_metadata: JSONB for additional audit information
- status: success or failure
- error_message: If status is failure
- created_at: Timestamp of action

Indexes:
- user_id: For filtering by user
- workspace_id: For filtering by workspace
- action: For filtering by action type
- resource_type: For filtering by resource type
- created_at: For time-based queries
- resource_id: For resource-based lookups

Queries:
- Find all actions by a user
- Find all changes to a specific resource
- Generate audit reports by action type
- Compliance reporting by workspace


2. CHUNKS & CHUNK_QUALITY_METRICS (Days 4-5)
─────────────────────────────────────────────

Purpose: Store document chunks and their quality metrics

CHUNKS Table:
- id: Primary key
- product_id: Associated product
- version: Version of the chunk
- chunk_order: Sequence number of chunk
- text: The actual chunk text (up to 1000 chars in API)
- page: Page number in source document
- source_file: File name of source
- metadata: JSONB for additional chunk data
- vector_id: Reference to embedding vector in OpenSearch

CHUNK_QUALITY_METRICS Table:
- chunk_id: Foreign key to chunks
- confidence: Quality confidence score (0-1)
- coherence: Coherence score (0-1)
- noise_level: Noise level (0-1)
- has_mid_sentence_start: Whether chunk starts mid-sentence
- has_mid_sentence_end: Whether chunk ends mid-sentence
- quality_issues: JSONB array of detected quality issues

Indexes:
- Product/version combo for fast filtering
- Confidence/coherence for quality-based filtering
- Page for pagination


3. POLICIES & POLICY_VIOLATIONS (Day 6)
────────────────────────────────────────

Purpose: Define and track policy compliance violations

POLICIES Table:
- policy_id: Unique policy identifier
- name: Human-readable policy name
- category: QUALITY, COMPLIANCE, SECURITY, PERFORMANCE, LINEAGE
- severity: INFO, WARNING, ERROR, CRITICAL
- enabled: Whether policy is active
- parameters: JSONB configuration for policy

POLICY_VIOLATIONS Table:
- violation_id: Unique violation identifier
- policy_id: Which policy was violated
- resource_id: What resource caused violation
- severity: Severity of violation
- is_blocking: Whether this blocks operations
- metadata: JSONB with violation details

Indexes:
- policy_id: For filtering by policy
- is_blocking: For blocking violation queries
- created_at: For time-based reporting


4. QUALITY_GATES & QUALITY_THRESHOLDS (Day 7)
──────────────────────────────────────────────

Purpose: Define metric thresholds that control operation execution

QUALITY_GATES Table:
- gate_id: Unique gate identifier
- name: Human-readable gate name
- category: Type of gate
- severity: Associated severity level
- blocking: Whether gate can block operations
- enabled: Whether gate is active

QUALITY_THRESHOLDS Table:
- gate_id: Associated gate
- metric_name: Name of metric to check
- min_value: Minimum acceptable value (NULL for no minimum)
- max_value: Maximum acceptable value (NULL for no maximum)

Use Cases:
- Confidence > 0.80 AND Coherence > 0.75
- Latency < 1000ms AND Throughput > 100/sec
- Error rate < 0.05


5. ALERT SYSTEM (Day 7)
───────────────────────

Purpose: Multi-channel notification system for violations and issues

ALERT_RULES Table:
- rule_id: Unique rule identifier
- policy_id: Which policy triggers this rule
- min_severity: Minimum severity to trigger alert
- channels: JSONB array of channels [LOG, EMAIL, WEBHOOK, SLACK]
- enabled: Whether rule is active

ALERTS Table:
- alert_id: Unique alert identifier
- rule_id: Which rule triggered this
- violation_id: Associated violation
- resource_id: Affected resource
- priority: Alert priority level
- status: active, resolved, escalated
- sent_at: When alert was sent

ALERT_HISTORY Table:
- Tracks status changes of alerts

Channels:
- LOG: Write to application logs
- EMAIL: Send email notification
- WEBHOOK: POST to webhook endpoint
- SLACK: Send to Slack channel
- DATABASE: Insert into database


6. GOVERNANCE PIPELINES (Day 8)
───────────────────────────────

Purpose: Orchestrate multi-stage data pipelines with governance

GOVERNANCE_PIPELINES Table:
- pipeline_id: Unique identifier
- name: Pipeline name
- type: ingestion, processing, export, etc.
- enabled: Whether pipeline is active

PIPELINE_STAGES Table:
- stage_id: Unique stage identifier
- pipeline_id: Parent pipeline
- stage_name: Stage name
- sequence: Execution order

PIPELINE_EXECUTION_LOGS Table:
- execution_id: Unique execution identifier
- pipeline_id: Which pipeline executed
- stage_id: Which stage executed
- status: success, failed, skipped
- result: JSONB with execution results
- error_message: If status is failed
- started_at: Execution start time
- completed_at: Execution end time

Queries:
- Pipeline execution history
- Stage performance metrics
- Failure analysis by stage
- Duration tracking


7. DATA LINEAGE (Days 9-10)
────────────────────────────

Purpose: Track data flow and transformations through system

LINEAGE_ENTITIES Table:
- entity_id: Unique identifier
- entity_type: DATASET, FILE, PROCESS, PIPELINE, MODEL
- name: Human-readable name
- properties: JSONB for entity-specific data
- metadata: JSONB for additional info

LINEAGE_RELATIONSHIPS Table:
- relationship_id: Unique identifier
- source_entity_id: Source entity
- target_entity_id: Target entity
- relationship_type: INPUT, OUTPUT, DERIVED, DEPENDS_ON, CONTAINS, GENERATED_BY
- properties: JSONB for relationship metadata

LINEAGE_PATHS Table:
- Cached paths for performance optimization
- Calculated using BFS algorithm
- Contains entities_in_path and relationships_in_path as JSONB arrays

Use Cases:
- Impact analysis: What datasets are affected if X fails?
- Provenance: Where did this data come from?
- Data governance: Track data sensitivity through pipeline
- Root cause analysis: Which process introduced the error?


8. VERSION MANAGEMENT (Days 11-12)
──────────────────────────────────

Purpose: Complete version lifecycle management

VERSIONS Table:
- version_id: Unique identifier
- entity_id: What is being versioned
- entity_type: DATASET, PROCESS, PIPELINE, MODEL, CONFIG
- version_number: Sequential version number per entity
- status: active, archived, rolled_back, deprecated
- description: Version description
- created_by: User who created version
- tags: JSONB array for organization
- custom_metadata: JSONB for custom data

VERSION_CONTENTS Table:
- content_id: Unique identifier
- version_id: Associated version
- checksum: SHA256 of content for integrity
- size_bytes: Size of content
- data: JSONB containing actual version data

VERSION_DIFFS Table:
- diff_id: Unique identifier
- from_version_id: Source version
- to_version_id: Target version
- changes: JSONB detailing what changed
- added_keys: JSONB array of new keys
- removed_keys: JSONB array of deleted keys
- modified_keys: JSONB array of changed keys

Capabilities:
- Version creation: Automatic sequential numbering
- Version comparison: Detailed diff detection
- Version rollback: Create new version from old state
- Version lifecycle: Deprecate, archive, delete
- Version statistics: Count by status, total size


9. QUALITY_IMPROVEMENT_METRICS (Phase 1 Support)
────────────────────────────────────────────────

Purpose: Track quality improvements over time

Columns:
- product_id: Associated product
- version: Data version
- baseline_accuracy: Initial accuracy score
- baseline_completeness: Initial completeness
- baseline_consistency: Initial consistency
- final_accuracy: Final accuracy after improvements
- final_completeness: Final completeness
- final_consistency: Final consistency
- improvement_percentage: Overall improvement
- files_count: Number of files processed
- chunks_count: Number of chunks created

*/

-- ============================================================================
-- MIGRATION EXECUTION STEPS
-- ============================================================================

/*

Step 1: Backup Existing Database
─────────────────────────────────

Before running migrations, create a backup:

  pg_dump -U postgres -d primedata > backup_$(date +%Y%m%d_%H%M%S).sql

Step 2: Review Changes
──────────────────────

1. Read SQL_MIGRATION_COMPLETE.sql
2. Identify any conflicts with existing schema
3. Plan for data migration if updating existing tables

Step 3: Create New Tables
──────────────────────────

Execute SQL_MIGRATION_COMPLETE.sql in your PostgreSQL database:

  psql -U postgres -d primedata -f SQL_MIGRATION_COMPLETE.sql

Or run each section individually for better control.

Step 4: Create Indexes
──────────────────────

All indexes are created automatically with the migration script.

Step 5: Load Sample Data (Optional)
───────────────────────────────────

For testing purposes, load sample data:

  psql -U postgres -d primedata -f SQL_QUERIES_AND_SAMPLES.sql

Step 6: Verify Migration
─────────────────────────

Run verification queries:

  SELECT COUNT(*) FROM information_schema.tables
  WHERE table_schema = 'public';

Step 7: Update Application Configuration
─────────────────────────────────────────

Update application database connection strings if needed.
Ensure ORM models match new schema.

*/

-- ============================================================================
-- PERFORMANCE OPTIMIZATION GUIDELINES
-- ============================================================================

/*

Index Strategy
──────────────

1. Foreign Key Indexes
   - Automatically created on FK columns
   - Improve JOIN performance

2. Filter Indexes
   - Created on frequently filtered columns
   - Examples: status, enabled, created_at

3. Composite Indexes
   - Example: (entity_id, version_number) for version lookups
   - Should match query WHERE clause order

4. JSONB Indexes
   - Consider GIN indexes for complex JSONB queries
   - Example: CREATE INDEX idx_changes_gin ON user_audit_log USING GIN(changes);

Query Optimization
──────────────────

1. Use LIMIT for pagination
   SELECT * FROM alerts ORDER BY created_at DESC LIMIT 100 OFFSET 0;

2. Filter before JOIN
   SELECT a.* FROM alerts a
   WHERE a.status = 'active'
   ORDER BY created_at DESC;

3. Avoid SELECT *
   SELECT alert_id, message, status FROM alerts;

4. Use EXPLAIN to analyze queries
   EXPLAIN ANALYZE SELECT * FROM alerts WHERE status = 'active';

Partitioning Strategy
─────────────────────

For large tables (>10M rows), consider partitioning by:
- user_audit_log: Partition by date (monthly)
- alerts: Partition by status
- pipeline_execution_logs: Partition by date (daily)

*/

-- ============================================================================
-- ROLLBACK PROCEDURE
-- ============================================================================

/*

If you need to rollback all changes:

1. Stop the application
2. Run the rollback script at the end of SQL_MIGRATION_COMPLETE.sql
3. Restore from backup if needed:
   psql -U postgres -d primedata < backup_20260326_120000.sql
4. Restart the application

*/

-- ============================================================================
-- TROUBLESHOOTING
-- ============================================================================

/*

Issue: Foreign Key Constraint Error
───────────────────────────────────

Solution: Ensure parent tables are created before child tables.
Migration script handles this automatically.

Issue: Index Creation Fails
────────────────────────────

Solution: Check for duplicate index names or invalid column names.
Run individual CREATE INDEX statements for debugging.

Issue: Performance Issues After Migration
──────────────────────────────────────────

Solution:
1. Run VACUUM ANALYZE to update table statistics:
   VACUUM ANALYZE;

2. Check index usage:
   SELECT * FROM pg_stat_user_indexes;

3. Monitor slow queries:
   Enable log_min_duration_statement in postgresql.conf

*/

-- ============================================================================
-- MAINTENANCE TASKS
-- ============================================================================

-- ============================================================================
-- Regular Maintenance Schedule
-- ============================================================================

/*

Daily:
- Monitor slow queries
- Check error logs
- Verify backup completion

Weekly:
- Run VACUUM ANALYZE
- Check index usage and fragmentation
- Review alert volumes

Monthly:
- Archive old execution logs
- Clean audit logs older than retention period
- Review and optimize top queries
- Update table statistics

Quarterly:
- Review index strategy
- Assess partitioning needs
- Plan capacity upgrades
- Performance baseline update

*/

-- ============================================================================
-- MONITOR DATABASE HEALTH
-- ============================================================================

-- Check table sizes
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check table row counts
SELECT
  schemaname,
  tablename,
  n_live_tup as live_rows,
  n_dead_tup as dead_rows
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;

-- Check index usage
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan as scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- ============================================================================
-- END OF DOCUMENTATION
-- ============================================================================
