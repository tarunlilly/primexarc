#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "Backend Database Init: Starting"
echo "=========================================="

# Ensure APP_HOME is set
export APP_HOME="${APP_HOME:-/app}"
export PYTHONPATH="${PYTHONPATH:-/app/src}"

# Verify database connection parameters
if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_PASSWORD:-}" ] || [ -z "${POSTGRES_HOST:-}" ] || [ -z "${POSTGRES_PORT:-}" ] || [ -z "${POSTGRES_DB:-}" ]; then
  echo "ERROR: Missing required PostgreSQL environment variables!"
  echo "Required: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB"
  exit 1
fi

echo "✓ PostgreSQL connection parameters verified:"
echo "  Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "  Database: ${POSTGRES_DB}"
echo "  User: ${POSTGRES_USER}"

# Database URL for backend
export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

echo ""
echo "Waiting for PostgreSQL server to be reachable..."
for i in {1..30}; do
  if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1" >/dev/null 2>&1; then
    echo "✓ PostgreSQL server is reachable."
    break
  fi
  echo "  PostgreSQL not ready yet... ($i/30)"
  sleep 2
done

echo ""
echo "Checking if database '${POSTGRES_DB}' exists..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -tAc "SELECT 1 FROM pg_databases WHERE datname = '${POSTGRES_DB}'" | grep -q 1; then
  echo "✓ Database '${POSTGRES_DB}' already exists."
else
  echo "Creating database '${POSTGRES_DB}'..."
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "CREATE DATABASE ${POSTGRES_DB};"
  echo "✓ Database '${POSTGRES_DB}' created successfully."
fi

echo ""
echo "Running Alembic database migrations..."
cd "${APP_HOME}"

# Run migrations
alembic upgrade head

echo ""
echo "Verifying database tables were created..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "\dt" | grep -q workspace; then
  echo "✓ Database tables verified - migrations successful."
else
  echo "WARNING: Could not verify tables, but migration command completed."
fi

echo ""
echo "=========================================="
echo "✓ Backend database initialization complete"
echo "=========================================="