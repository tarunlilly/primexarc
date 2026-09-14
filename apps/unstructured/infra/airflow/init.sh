#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "Airflow Init: Starting initialization"
echo "=========================================="

# Ensure AIRFLOW_HOME is set
export AIRFLOW_HOME="${AIRFLOW_HOME:-/home/airflow/airflow}"

# CRITICAL: Construct and set database connection BEFORE any airflow command runs
echo ""
echo "Step 1: Setting up database connection"
echo "========================================"

if [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${POSTGRES_HOST:-}" ] && [ -n "${POSTGRES_PORT:-}" ] && [ -n "${POSTGRES_AIRFLOW_DB:-}" ]; then
  export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_AIRFLOW_DB}"
  echo "✓ PostgreSQL database URL constructed:"
  echo "  Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
  echo "  Database: ${POSTGRES_AIRFLOW_DB}"
  echo "  User: ${POSTGRES_USER}"
  echo "  Connection: postgresql+psycopg2://<user>:<pass>@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_AIRFLOW_DB}"
else
  echo "ERROR: Missing required PostgreSQL environment variables!"
  echo "Required: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_AIRFLOW_DB"
  echo ""
  echo "Provided values:"
  echo "  POSTGRES_USER: ${POSTGRES_USER:-NOT SET}"
  echo "  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-NOT SET}"
  echo "  POSTGRES_HOST: ${POSTGRES_HOST:-NOT SET}"
  echo "  POSTGRES_PORT: ${POSTGRES_PORT:-NOT SET}"
  echo "  POSTGRES_AIRFLOW_DB: ${POSTGRES_AIRFLOW_DB:-NOT SET}"
  exit 1
fi

# Set other critical Airflow configs
export AIRFLOW__CORE__LOAD_EXAMPLES="${AIRFLOW__CORE__LOAD_EXAMPLES:-false}"
export AIRFLOW__CORE__EXECUTOR="${AIRFLOW__CORE__EXECUTOR:-LocalExecutor}"
export AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION="${AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION:-true}"

echo ""
echo "Airflow configuration:"
echo "  AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: Set to PostgreSQL"
echo "  AIRFLOW__CORE__EXECUTOR: ${AIRFLOW__CORE__EXECUTOR}"
echo "  AIRFLOW__CORE__LOAD_EXAMPLES: ${AIRFLOW__CORE__LOAD_EXAMPLES}"

# Clean up any old SQLite configs
[ -f "$AIRFLOW_HOME/airflow.cfg" ] && rm -f "$AIRFLOW_HOME/airflow.cfg" && echo "  Removed old airflow.cfg"
[ -f "$AIRFLOW_HOME/airflow.db" ] && rm -f "$AIRFLOW_HOME/airflow.db" && echo "  Removed old airflow.db"

echo ""
echo "Step 2: Waiting for PostgreSQL server"
echo "====================================="
ATTEMPTS=0
MAX_ATTEMPTS=60

while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1" >/dev/null 2>&1; then
    echo "✓ PostgreSQL server is reachable."
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ $((ATTEMPTS % 10)) -eq 0 ]; then
    echo "  Still waiting... ($ATTEMPTS/$MAX_ATTEMPTS)"
  fi
  sleep 2
done

if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
  echo "ERROR: PostgreSQL server not reachable after $MAX_ATTEMPTS attempts"
  exit 1
fi

echo ""
echo "Step 3: Creating database if needed"
echo "===================================="

DB_EXISTS=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -tAc "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_AIRFLOW_DB}'" 2>&1 || echo "0")

if [ "$DB_EXISTS" = "1" ]; then
  echo "✓ Database '${POSTGRES_AIRFLOW_DB}' already exists."
else
  echo "Creating database '${POSTGRES_AIRFLOW_DB}'..."
  if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "CREATE DATABASE ${POSTGRES_AIRFLOW_DB};" 2>&1; then
    echo "✓ Database '${POSTGRES_AIRFLOW_DB}' created successfully."
  else
    echo "ERROR: Failed to create database"
    exit 1
  fi
fi

echo ""
echo "Step 4: Verifying database is accessible"
echo "========================================="
ATTEMPTS=0
while [ $ATTEMPTS -lt 30 ]; do
  if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_AIRFLOW_DB}" -c "SELECT 1" >/dev/null 2>&1; then
    echo "✓ Database is accessible."
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  echo "  Database not accessible yet... ($ATTEMPTS/30)"
  sleep 1
done

echo ""
echo "Step 5: Running Airflow database migrations"
echo "==========================================="

# Verify AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is set
if [ -z "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-}" ]; then
  echo "ERROR: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is not set!"
  exit 1
fi

echo "Running: airflow db migrate"
if airflow db migrate; then
  echo "✓ Database migrations completed successfully"
else
  echo "ERROR: Database migration failed"
  exit 1
fi

echo ""
echo "Step 6: Running Airflow database upgrade"
echo "========================================"
echo "Running: airflow db upgrade"
if airflow db upgrade; then
  echo "✓ Database upgrade completed successfully"
else
  echo "ERROR: Database upgrade failed"
  exit 1
fi

echo ""
echo "Step 7: Verifying database"
echo "=========================="
if airflow db check; then
  echo "✓ Database verification successful"
else
  echo "ERROR: Database verification failed"
  exit 1
fi

echo ""
echo "Step 8: Creating default connections"
echo "===================================="
airflow connections create-default-connections || echo "Default connections already exist or creation skipped"

echo ""
echo "Step 9: Initializing plugins"
echo "============================"
airflow plugins list >/dev/null 2>&1 || true

echo ""
echo "Step 10: Creating admin user"
echo "============================"

if airflow users list 2>/dev/null | awk 'NR>2 {print $2}' | grep -Fxq "${AIRFLOW_ADMIN_USER}"; then
  echo "✓ Admin user already exists: ${AIRFLOW_ADMIN_USER}"
else
  echo "Creating admin user: ${AIRFLOW_ADMIN_USER}"
  if airflow users create \
    --username "${AIRFLOW_ADMIN_USER}" \
    --firstname "${AIRFLOW_ADMIN_FIRSTNAME}" \
    --lastname "${AIRFLOW_ADMIN_LASTNAME}" \
    --role Admin \
    --email "${AIRFLOW_ADMIN_EMAIL}" \
    --password "${AIRFLOW_ADMIN_PASSWORD}"; then
    echo "✓ Admin user created successfully"
  else
    echo "WARNING: Admin user creation failed or already exists"
  fi
fi

echo ""
echo "=========================================="
echo "✓ Airflow initialization complete"
echo "=========================================="
echo ""
echo "Database: postgresql+psycopg2://<user>:<pass>@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_AIRFLOW_DB}"
echo "Executor: ${AIRFLOW__CORE__EXECUTOR}"
echo "Ready to start Airflow!"