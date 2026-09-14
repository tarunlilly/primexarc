# Airflow PostgreSQL Database Auto-Creation Guide

## What Was Fixed

The init script now automatically:
1. **Connects to PostgreSQL server** (lines 38-46)
2. **Checks if the Airflow database exists** (lines 48-56)
3. **Creates the database if missing** (line 54)
4. **Runs migrations** after database is ready (line 68)
5. **Creates admin user** if missing (lines 75-88)

## Key Changes

### `init.sh` (Lines 38-56)
```bash
# Wait for PostgreSQL to be ready
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1"

# Check if database exists
psql ... -c "SELECT 1 FROM pg_databases WHERE datname = '${POSTGRES_AIRFLOW_DB}'"

# Create database if missing
psql ... -c "CREATE DATABASE ${POSTGRES_AIRFLOW_DB};"
```

### `Dockerfile` (Line 17)
Added `postgresql-client` so the `psql` command is available in the container

## How It Works

1. **Connect to "postgres" database** (default system database)
   - Uses provided PostgreSQL credentials
   - Uses `PGPASSWORD` environment variable for authentication

2. **Query if airflow database exists**
   - If exists: skip creation
   - If missing: create it

3. **Run airflow db migrate**
   - Creates all necessary tables
   - Sets up Airflow metadata

4. **Create admin user**
   - Only if it doesn't already exist

## Required Kubernetes Environment Variables

Your Kubernetes deployment MUST provide:

```yaml
env:
  - name: POSTGRES_USER
    valueFrom:
      secretKeyRef:
        name: postgres-credentials
        key: username
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: postgres-credentials
        key: password
  - name: POSTGRES_HOST
    value: "postgres-service"
  - name: POSTGRES_PORT
    value: "5432"
  - name: POSTGRES_AIRFLOW_DB
    value: "airflow"
  - name: AIRFLOW_ADMIN_USER
    value: "admin"
  - name: AIRFLOW_ADMIN_FIRSTNAME
    value: "Admin"
  - name: AIRFLOW_ADMIN_LASTNAME
    value: "User"
  - name: AIRFLOW_ADMIN_EMAIL
    value: "admin@example.com"
  - name: AIRFLOW_ADMIN_PASSWORD
    valueFrom:
      secretKeyRef:
        name: airflow-admin
        key: password
```

## Important Notes

- ✅ Database is created automatically (no manual intervention needed)
- ✅ Works even if database already exists (idempotent)
- ✅ Uses credentials from POSTGRES_* environment variables
- ✅ PostgreSQL server must be accessible from the container
- ✅ The init script runs as an initContainer in Kubernetes

## Error Handling

If the script fails:
1. Check PostgreSQL is running and accessible
2. Verify all POSTGRES_* environment variables are set
3. Ensure PostgreSQL user has CREATE DATABASE permission
4. Check network connectivity to PostgreSQL service