#!/bin/bash
# Airflow Health Check Script
# Monitors Airflow webserver and scheduler health

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

AIRFLOW_HOST="${AIRFLOW_HOST:-localhost}"
AIRFLOW_PORT="${AIRFLOW_PORT:-8080}"

echo "=== Airflow Health Check ==="

# Check Airflow Webserver
echo -n "Checking Airflow Webserver (${AIRFLOW_HOST}:${AIRFLOW_PORT})... "
if curl -s "http://${AIRFLOW_HOST}:${AIRFLOW_PORT}/airflow/api/v1/health" | grep -q "\"is_healthy\": true"; then
    echo -e "${GREEN}✓ Healthy${NC}"
else
    echo -e "${RED}✗ Unhealthy${NC}"
    exit 1
fi

# Check Airflow Scheduler
echo -n "Checking Airflow Scheduler logs... "
SCHEDULER_CONTAINER=$(docker ps -q -f name=airflow-scheduler 2>/dev/null || echo "")
if [ -n "$SCHEDULER_CONTAINER" ]; then
    if docker logs $SCHEDULER_CONTAINER 2>&1 | grep -q "ERROR"; then
        echo -e "${YELLOW}⚠ Errors found in logs (check details)${NC}"
    else
        echo -e "${GREEN}✓ Running${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Scheduler container not found${NC}"
fi

# Check DAG parsing
echo -n "Checking DAG parsing... "
if curl -s "http://${AIRFLOW_HOST}:${AIRFLOW_PORT}/airflow/api/v1/dags" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Airflow health check completed!${NC}"
