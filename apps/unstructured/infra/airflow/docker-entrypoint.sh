#!/bin/bash
set -euo pipefail

# Ensure AIRFLOW_HOME is set
export AIRFLOW_HOME="${AIRFLOW_HOME:-/home/airflow/airflow}"

echo "=========================================="
echo "Airflow Entrypoint: Starting initialization"
echo "=========================================="

# Priority 1: If individual POSTGRES_* variables are provided, construct the connection string
if [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${POSTGRES_HOST:-}" ] && [ -n "${POSTGRES_PORT:-}" ] && [ -n "${POSTGRES_AIRFLOW_DB:-}" ]; then
  export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_AIRFLOW_DB}"
  echo "✓ Airflow database URL constructed from POSTGRES_* environment variables:"
  echo "  Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
  echo "  Database: ${POSTGRES_AIRFLOW_DB}"
  echo "  User: ${POSTGRES_USER}"

# Priority 2: If AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is already set and valid, use it
elif [ -n "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-}" ]; then
  echo "✓ Using AIRFLOW__DATABASE__SQL_ALCHEMY_CONN from environment"
  echo "  Connection: ${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN}"

else
  echo "⚠ WARNING: No database configuration found!"
  echo "  Please provide either:"
  echo "    1. POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_AIRFLOW_DB"
  echo "    2. AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
  exit 1
fi

# Remove any existing airflow.cfg to force fresh generation from environment variables
if [ -f "$AIRFLOW_HOME/airflow.cfg" ]; then
  echo "Removing existing airflow.cfg to ensure fresh configuration from environment variables"
  rm -f "$AIRFLOW_HOME/airflow.cfg"
fi

# Remove any existing SQLite database
if [ -f "$AIRFLOW_HOME/airflow.db" ]; then
  echo "Removing existing SQLite database (using PostgreSQL instead)"
  rm -f "$AIRFLOW_HOME/airflow.db"
fi

# Verify environment is set correctly before running Airflow
echo ""
echo "=========================================="
echo "Final Airflow Configuration:"
echo "=========================================="
echo "  AIRFLOW_HOME: $AIRFLOW_HOME"
echo "  AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://<user>:<pass>@${POSTGRES_HOST:-<extracted>}:${POSTGRES_PORT:-<extracted>}/${POSTGRES_AIRFLOW_DB:-<extracted>}"
echo "  AIRFLOW__CORE__EXECUTOR: ${AIRFLOW__CORE__EXECUTOR:-LocalExecutor}"
echo "  AIRFLOW__CORE__LOAD_EXAMPLES: ${AIRFLOW__CORE__LOAD_EXAMPLES:-false}"
echo "  AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: ${AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION:-true}"
echo "=========================================="
echo ""

# Verify the database URL is properly set
if [ -z "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-}" ]; then
  echo "ERROR: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is not set!"
  exit 1
fi

# Ensure environment variables are available to child processes
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
export AIRFLOW__CORE__EXECUTOR="${AIRFLOW__CORE__EXECUTOR:-LocalExecutor}"
export AIRFLOW__CORE__LOAD_EXAMPLES="${AIRFLOW__CORE__LOAD_EXAMPLES:-false}"

# Execute the command passed to docker run with full environment inheritance
exec "$@"