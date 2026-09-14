#!/bin/bash
# General Health Check Script
# Verifies all services are running and healthy

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED_CHECKS=0

check_service() {
    local service_name=$1
    local host=$2
    local port=$3
    local health_endpoint=$4

    echo -n "Checking ${service_name}... "

    if nc -z ${host} ${port} 2>/dev/null; then
        if [ -n "${health_endpoint}" ]; then
            if curl -s "${health_endpoint}" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ OK${NC}"
                return 0
            fi
        else
            echo -e "${GREEN}✓ OK${NC}"
            return 0
        fi
    fi

    echo -e "${RED}✗ FAILED${NC}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    return 1
}

echo "=== PrimeData Infrastructure Health Check ==="
echo ""

# Check PostgreSQL
check_service "PostgreSQL" "localhost" "5432" "" || true

# Check Qdrant
check_service "Qdrant" "localhost" "6333" "http://localhost:6333/health" || true

# Check MinIO
check_service "MinIO" "localhost" "9000" "http://localhost:9000" || true

# Check MinIO Console
check_service "MinIO Console" "localhost" "9001" "" || true

# Check Airflow Webserver
check_service "Airflow Webserver" "localhost" "8080" "http://localhost:8080/airflow/api/v1/health" || true

# Check Backend (if running)
check_service "Backend" "localhost" "8000" "http://localhost:8000/health" || true

echo ""
if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}All services are healthy!${NC}"
    exit 0
else
    echo -e "${RED}${FAILED_CHECKS} service(s) failed health check${NC}"
    exit 1
fi
