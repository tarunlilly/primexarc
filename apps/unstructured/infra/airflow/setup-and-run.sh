#!/bin/bash
# This script sets up Airflow configuration and then runs Airflow
# Use this if Kubernetes overrides the ENTRYPOINT

set -euo pipefail

# Ensure AIRFLOW_HOME is set
export AIRFLOW_HOME="${AIRFLOW_HOME:-/home/airflow/airflow}"

echo "=========================================="
echo "Airflow Setup: Starting initialization"
echo "=========================================="

# Priority 1: If individual POSTGRES_* variables are provided, construct the connection string
if [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${POSTGRES_HOST:-}" ] && [ -n "${POSTGRES_PORT:-}" ] && [ -n "${POSTGRES_AIRFLOW_DB:-}" ]; then
  export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_AIRFLOW_DB}"
  echo "✓ Database URL constructed from POSTGRES_* variables"

# Priority 2: If AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is already set and valid, use it
elif [ -n "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-}" ]; then
  echo "✓ Using AIRFLOW__DATABASE__SQL_ALCHEMY_CONN from environment"

else
  echo "⚠ ERROR: No database configuration found!"
  exit 1
fi

# Clean up old configurations
[ -f "$AIRFLOW_HOME/airflow.cfg" ] && rm -f "$AIRFLOW_HOME/airflow.cfg"
[ -f "$AIRFLOW_HOME/airflow.db" ] && rm -f "$AIRFLOW_HOME/airflow.db"

# Export variables for subprocess
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
export AIRFLOW__CORE__EXECUTOR="${AIRFLOW__CORE__EXECUTOR:-LocalExecutor}"
export AIRFLOW__CORE__LOAD_EXAMPLES="${AIRFLOW__CORE__LOAD_EXAMPLES:-false}"

echo "Configuration ready. Starting Airflow..."
echo ""

# Run the command
exec "$@"