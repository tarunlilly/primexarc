# Airflow Metadata Tables Reference

## Overview

The PrimeData database contains **72 total tables**:
- **13 tables**: PrimeData core application tables
- **50+ tables**: Apache Airflow metadata tables (automatically created)
- **9 tables**: PostgreSQL system tables

This document explains all Airflow tables and their purpose.

## Airflow Tables Breakdown (50+ tables)

### Authentication & Authorization (5 tables)
```
ab_user                 - Airflow UI user accounts
ab_role                 - User roles (Admin, Viewer, Editor, etc.)
ab_permission           - Permissions (can_read, can_write, etc.)
ab_user_role            - User-role relationships
ab_role_permission      - Role-permission relationships
```

### DAG Management (5 tables)
```
dag                     - DAG definitions
dag_tag                 - DAG tags for categorization
dag_owner_attributes    - DAG owner information
dag_code                - Source code of DAGs
serialized_dag          - Serialized DAG for optimization
```

### Task Execution (8 tables)
```
task_instance           - Individual task execution records
task_flow               - Task flow dependencies
task_group              - Grouping of tasks
task_reschedule         - Rescheduled task information
upstream_task_relationship - Task dependencies
task_instance_note      - Notes on task instances
task_fail               - Task failure records
task_retry              - Task retry information
```

### Logging & Monitoring (5 tables)
```
log                     - Airflow operation logs
xcom                    - Cross-communication between tasks
xcom_arg                - XCom arguments
sla_miss                - SLA violations
import_error            - DAG import errors
```

### Configuration (4 tables)
```
connection              - Airflow connections (S3, DB, OpenSearch, etc.)
variable                - Airflow variables (configuration key-value pairs)
pool                    - Resource pools for task queuing
pool_slots              - Pool slot allocation
```

### Job & Task State (8 tables)
```
job                     - Job tracking (DAG runs, schedulers)
dag_run                 - DAG execution runs
task_state_history      - Historical task states
dataset                 - Data-aware scheduling datasets
dataset_dag_run_asset   - Dataset-DAG relationships
event_log               - Event logging for auditing
sensor_instance         - Sensor task instances
trigger                 - Trigger tracking for sensors
```

### Miscellaneous (10+ tables)
```
rendered_template_fields - Rendered template values
celery_taskmeta         - Celery task metadata (if using Celery executor)
celery_periodictask     - Scheduled periodic tasks
celery_periodictaskchangednotification - Notifications for changes
task_duration           - Task duration tracking
task_fail_duration      - Failed task durations
task_restart_count      - Task restart statistics
task_group_code         - Task group source code
dag_pickle              - Pickled DAGs
fernet_key              - Encryption keys for sensitive data
```

## Common Airflow Queries

### Check DAG Status
```sql
SELECT
    dag_id,
    run_id,
    execution_date,
    state,
    start_date,
    end_date
FROM dag_run
WHERE dag_id LIKE '%primedata%'
ORDER BY execution_date DESC
LIMIT 10;
```

### Get Task Instance Details
```sql
SELECT
    dag_id,
    task_id,
    execution_date,
    state,
    start_date,
    end_date,
    duration,
    try_number
FROM task_instance
WHERE dag_id = 'primedata_pipeline'
ORDER BY execution_date DESC
LIMIT 50;
```

### Find Failed Tasks
```sql
SELECT
    dag_id,
    task_id,
    execution_date,
    state,
    log_file
FROM task_instance
WHERE state = 'failed'
AND execution_date > NOW() - INTERVAL '7 days'
ORDER BY execution_date DESC;
```

### View XCom Data (Cross-Task Communication)
```sql
SELECT
    dag_id,
    task_id,
    execution_date,
    key,
    value
FROM xcom
WHERE dag_id = 'primedata_pipeline'
ORDER BY execution_date DESC;
```

### Check Airflow Connections
```sql
SELECT
    conn_id,
    conn_type,
    host,
    port,
    schema,
    login
FROM connection
WHERE conn_type IN ('s3', 'opensearch', 'postgres');
```

### View Airflow Configuration Variables
```sql
SELECT key, value
FROM variable
WHERE key LIKE '%S3%'
   OR key LIKE '%OPENSEARCH%'
   OR key LIKE '%PRIMEDATA%'
ORDER BY key;
```

### Monitor DAG Performance
```sql
SELECT
    dag_id,
    COUNT(*) as total_runs,
    SUM(CASE WHEN state = 'success' THEN 1 ELSE 0 END) as successful_runs,
    SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed_runs,
    AVG(EXTRACT(EPOCH FROM (end_date - start_date))) as avg_duration_seconds
FROM dag_run
GROUP BY dag_id
ORDER BY total_runs DESC;
```

### Find Long-Running DAG Runs
```sql
SELECT
    dag_id,
    run_id,
    execution_date,
    start_date,
    EXTRACT(EPOCH FROM (NOW() - start_date)) as running_seconds
FROM dag_run
WHERE state = 'running'
AND start_date < NOW() - INTERVAL '1 hour'
ORDER BY start_date ASC;
```

## Airflow Table Relationships

```
dag (main entity)
  ├─ dag_run (multiple runs per DAG)
  │  ├─ task_instance (multiple tasks per run)
  │  │  ├─ log (execution logs)
  │  │  ├─ xcom (inter-task data)
  │  │  └─ task_reschedule (retries)
  │  ├─ sla_miss (SLA violations)
  │  └─ dataset (data dependencies)
  ├─ dag_tag (categorization)
  ├─ dag_owner_attributes (ownership)
  └─ serialized_dag (optimization)

connection (shared across DAGs)
variable (configuration)
pool (resource management)
```

## When to Use Each Table

| Task | Table | Query |
|------|-------|-------|
| Check if DAG is running | dag_run | WHERE state = 'running' |
| Find failed tasks | task_instance | WHERE state = 'failed' |
| Get task output/XCom | xcom | WHERE task_id = ? |
| Monitor performance | dag_run | GROUP BY dag_id |
| View logs | log | WHERE dag_id = ? |
| Check connections | connection | WHERE conn_type = 's3' |
| Get config values | variable | WHERE key LIKE ? |
| Analyze SLA breaches | sla_miss | ORDER BY execution_date DESC |

## Database Size Distribution

```
PrimeData Core Tables:     ~10-50 MB (depends on data volume)
Airflow Metadata Tables:   ~100-500 MB (grows with execution history)
Logs (log table):          ~50-200 MB (can grow very large)
Total Database:            ~72 tables, typically 1-5 GB
```

## Maintenance Tips

### Clean Up Old Data
```sql
-- Archive old DAG runs (keep last 90 days)
DELETE FROM dag_run
WHERE execution_date < NOW() - INTERVAL '90 days'
  AND state IN ('success', 'skipped');

-- Clean old logs
DELETE FROM log
WHERE dttm < NOW() - INTERVAL '30 days';

-- Clean old XCom data
DELETE FROM xcom
WHERE execution_date < NOW() - INTERVAL '30 days';
```

### Monitor Table Sizes
```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Optimize Airflow Database
```sql
-- Vacuum and analyze
VACUUM ANALYZE;

-- Reindex if needed
REINDEX DATABASE primedata;
```

## Key Difference: PrimeData Core vs Airflow Tables

| Aspect | PrimeData Core | Airflow |
|--------|---|---|
| **Purpose** | Application data | Pipeline orchestration |
| **User Access** | Via API endpoints | Via Airflow UI/REST API |
| **Update Frequency** | Per user action | Per pipeline execution |
| **Retention** | Long-term | Configurable purge |
| **Direct Query** | Sometimes needed | Usually via UI |
| **Critical** | Very (application data) | Yes (operational) |

## References

- Airflow Database Schema: https://airflow.apache.org/docs/apache-airflow/stable/database-erd-ref.html
- Airflow Admin Guide: https://airflow.apache.org/docs/apache-airflow/stable/ui.html

