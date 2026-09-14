#!/bin/bash
# Debug script to test database initialization

set -euo pipefail

echo "=========================================="
echo "Database Initialization Debug"
echo "=========================================="

# Check environment variables
echo ""
echo "1. Checking environment variables..."
echo "POSTGRES_USER: ${POSTGRES_USER:-NOT SET}"
echo "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-NOT SET}"
echo "POSTGRES_HOST: ${POSTGRES_HOST:-NOT SET}"
echo "POSTGRES_PORT: ${POSTGRES_PORT:-NOT SET}"
echo "POSTGRES_DB: ${POSTGRES_DB:-NOT SET}"

# Check if psql is available
echo ""
echo "2. Checking if psql is available..."
if command -v psql &> /dev/null; then
  echo "✓ psql found: $(psql --version)"
else
  echo "✗ psql NOT found - postgresql-client not installed!"
  exit 1
fi

# Test PostgreSQL connection
echo ""
echo "3. Testing PostgreSQL connection..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1" >/dev/null 2>&1; then
  echo "✓ PostgreSQL connection successful"
else
  echo "✗ PostgreSQL connection FAILED"
  echo "  Trying again with verbose output:"
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1" || true
  exit 1
fi

# List existing databases
echo ""
echo "4. Listing existing databases..."
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -lqt | cut -d \| -f 1 | grep -v ^$ || echo "No databases found"

# Check if database exists
echo ""
echo "5. Checking if database '${POSTGRES_DB}' exists..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -tAc "SELECT 1 FROM pg_databases WHERE datname = '${POSTGRES_DB}'" | grep -q 1; then
  echo "✓ Database '${POSTGRES_DB}' exists"

  # List tables in database
  echo ""
  echo "6. Listing tables in database..."
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "\dt" || echo "Could not list tables"
else
  echo "✗ Database '${POSTGRES_DB}' DOES NOT EXIST"
  echo "  Will need to create it"
fi

# Check if alembic is available
echo ""
echo "7. Checking if alembic is available..."
if command -v alembic &> /dev/null; then
  echo "✓ alembic found: $(alembic --version 2>/dev/null || echo 'version check failed')"
else
  echo "✗ alembic NOT found"
  exit 1
fi

echo ""
echo "=========================================="
echo "Debug complete"
echo "=========================================="