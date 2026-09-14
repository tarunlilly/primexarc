#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "Backend Entrypoint: Starting"
echo "=========================================="

# Ensure PYTHONPATH is set
export PYTHONPATH="${PYTHONPATH:-/app/src}"

# Construct DATABASE_URL from environment variables if not already set
if [ -z "${DATABASE_URL:-}" ]; then
  # Set defaults for development
  POSTGRES_USER="${POSTGRES_USER:-primedata}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-primedata123}"
  POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  POSTGRES_PORT="${POSTGRES_PORT:-5433}"
  POSTGRES_DB="${POSTGRES_DB:-primedata}"

  export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT POSTGRES_DB
  export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
  echo "✓ DATABASE_URL constructed from POSTGRES_* environment variables (with defaults):"
  echo "  Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
  echo "  Database: ${POSTGRES_DB}"
else
  echo "✓ Using DATABASE_URL from environment"
fi

echo ""
echo "Backend configuration:"
echo "  Python Path: ${PYTHONPATH}"
echo "  Database: ${POSTGRES_DB:-<extracted>}"
echo "  Database URL: ${DATABASE_URL}"
echo ""
echo "Running database migrations (verbose output)..."
cd /app
# DISABLED: Alembic migrations moved to separate initialization step
# Use COMPLETE_MIGRATIONS.sql instead for initial schema setup
# alembic upgrade heads
echo "⚠ Database migrations disabled in entrypoint"
echo "  Use: psql -f COMPLETE_MIGRATIONS.sql"
echo ""

# Execute the command passed to docker run
exec "$@"
