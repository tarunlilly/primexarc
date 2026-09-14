-- Airflow Database Initialization Script
-- Creates schema and initial setup for Airflow metadata database

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Tables are typically created by Airflow db upgrade command
-- This script just ensures the database is prepared

-- Create airflow_log table if needed (Airflow 2.x standard)
CREATE TABLE IF NOT EXISTS airflow_log (
    id SERIAL PRIMARY KEY,
    dags_id VARCHAR(250),
    task_id VARCHAR(250),
    event VARCHAR(30),
    execution_date TIMESTAMP,
    owner VARCHAR(500),
    log TEXT,
    primary_log_id INTEGER,
    secondary_log_id INTEGER,
    try_number INTEGER,
    task_duration FLOAT,
    task_end_date TIMESTAMP,
    task_start_date TIMESTAMP,
    utc_execution_date TIMESTAMP,
    utc_log_date TIMESTAMP
);

-- Create airflow_dag_code if needed (Airflow 2.x standard)
CREATE TABLE IF NOT EXISTS airflow_dag_code (
    id SERIAL PRIMARY KEY,
    dag_id VARCHAR(250) NOT NULL UNIQUE,
    fileloc VARCHAR(2000) NOT NULL,
    source_code TEXT NOT NULL,
    last_updated TIMESTAMP NOT NULL
);

-- Create basic indexes for performance
CREATE INDEX IF NOT EXISTS idx_airflow_log_dag_id ON airflow_log(dags_id);
CREATE INDEX IF NOT EXISTS idx_airflow_log_task_id ON airflow_log(task_id);
CREATE INDEX IF NOT EXISTS idx_airflow_log_execution_date ON airflow_log(execution_date);

-- Grant permissions to airflow user
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_user WHERE usename = 'airflow') THEN
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO airflow;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO airflow;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO airflow;
    END IF;
END
$$;

-- Create role for primedata app if needed
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'primedata') THEN
        CREATE ROLE primedata WITH LOGIN PASSWORD 'primedata';
        GRANT CONNECT ON DATABASE aird TO primedata;
        GRANT USAGE ON SCHEMA public TO primedata;
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO primedata;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO primedata;
    END IF;
END
$$;

COMMIT;
