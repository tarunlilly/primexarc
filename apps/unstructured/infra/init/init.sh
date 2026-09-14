#!/bin/bash
# Main Infrastructure Initialization Script
# Sets up PostgreSQL, Qdrant, MinIO, and Airflow

set -e

echo "🚀 Starting PrimeData Infrastructure Initialization..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
POSTGRES_USER="${POSTGRES_USER:-aird}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-aird}"
POSTGRES_DB="${POSTGRES_DB:-aird}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
PRIMEDATA_APP_DB="${PRIMEDATA_APP_DB:-primedata_backend}"

# Function to check service availability
check_service() {
    local service=$1
    local host=$2
    local port=$3
    local max_attempts=30
    local attempt=0

    echo -e "${BLUE}Checking ${service} availability at ${host}:${port}...${NC}"

    while [ $attempt -lt $max_attempts ]; do
        if nc -z ${host} ${port} 2>/dev/null; then
            echo -e "${GREEN}✓ ${service} is available${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -e "${YELLOW}  Attempt ${attempt}/${max_attempts}...${NC}"
        sleep 2
    done

    echo -e "${RED}✗ ${service} is not available after ${max_attempts} attempts${NC}"
    return 1
}

# Wait for PostgreSQL
check_service "PostgreSQL" "${POSTGRES_HOST}" "${POSTGRES_PORT}" || exit 1

# Wait for Qdrant
check_service "Qdrant" "qdrant" "6333" || exit 1

# Wait for MinIO
check_service "MinIO" "minio" "9000" || exit 1

echo -e "${GREEN}All services are ready!${NC}"

# Run database initialization scripts
echo -e "${BLUE}Initializing databases...${NC}"

# Execute SQL initialization scripts
if [ -f "/scripts/init-airflow-db.sql" ]; then
    echo "Running Airflow database initialization..."
    psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -f /scripts/init-airflow-db.sql
else
    echo -e "${YELLOW}Warning: init-airflow-db.sql not found${NC}"
fi

if [ -f "/scripts/init-dev-user.sql" ]; then
    echo "Running development user initialization..."
    psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -f /scripts/init-dev-user.sql
else
    echo -e "${YELLOW}Warning: init-dev-user.sql not found${NC}"
fi

echo -e "${GREEN}Infrastructure initialization completed!${NC}"
