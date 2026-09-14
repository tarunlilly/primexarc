#!/bin/bash
# Final Verification Script - UPDATED FOR OPENSEARCH
# Comprehensive end-to-end deployment verification
# FIXED: Changed from Qdrant (deprecated) to OpenSearch (current)

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Final Deployment Verification (OpenSearch) ===${NC}"

TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

run_check() {
    local check_name=$1
    local check_command=$2

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo -n "[$TOTAL_CHECKS] ${check_name}... "

    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Infrastructure Checks
echo -e "${BLUE}Infrastructure Checks:${NC}"
run_check "PostgreSQL running" "docker ps | grep -q aird-postgres"
run_check "OpenSearch running" "docker ps | grep -q aird-opensearch"  # FIXED: Changed from qdrant
run_check "MinIO running" "docker ps | grep -q aird-minio"
run_check "Airflow webserver running" "docker ps | grep -q aird-airflow-webserver"
run_check "Airflow scheduler running" "docker ps | grep -q aird-airflow-scheduler"

# Port Availability Checks
echo -e "${BLUE}Port Availability Checks:${NC}"
run_check "PostgreSQL port (5432)" "nc -z localhost 5432"
run_check "OpenSearch port (9200)" "nc -z localhost 9200"  # FIXED: Changed from 6333 (Qdrant) to 9200 (OpenSearch)
run_check "MinIO port (9000)" "nc -z localhost 9000"
run_check "MinIO Console port (9001)" "nc -z localhost 9001"
run_check "Airflow port (8080)" "nc -z localhost 8080"
run_check "OpenSearch Dashboards port (5601)" "nc -z localhost 5601"  # NEW: Added OpenSearch Dashboards check

# Service Health Checks
echo -e "${BLUE}Service Health Checks:${NC}"
run_check "PostgreSQL health" "docker exec aird-postgres pg_isready -U aird -d aird"
run_check "OpenSearch health" "curl -s http://localhost:9200/_cluster/health | grep -q 'status'"  # FIXED: Changed health endpoint
run_check "Airflow health" "curl -s http://localhost:8080/airflow/api/v1/health | grep -q is_healthy"

# Data Integrity Checks
echo -e "${BLUE}Data Integrity Checks:${NC}"
run_check "PostgreSQL data volume" "docker volume ls | grep -q postgres_data"
run_check "OpenSearch data volume" "docker volume ls | grep -q opensearch_data"  # FIXED: Changed from qdrant_data to opensearch_data
run_check "MinIO data volume" "docker volume ls | grep -q minio_data"
run_check "Airflow logs volume" "docker volume ls | grep -q airflow_logs"

# Network Checks
echo -e "${BLUE}Network Checks:${NC}"
run_check "aird-network exists" "docker network ls | grep -q aird-network"
run_check "Services on network" "docker network inspect aird-network | grep -q connected"

# Logs Check
echo -e "${BLUE}Log Analysis:${NC}"
run_check "No critical errors in PostgreSQL" "! docker logs aird-postgres 2>&1 | grep -qi 'FATAL\\|ERROR' | head -1"
run_check "Airflow initialized" "curl -s http://localhost:8080/airflow/api/v1/dags | grep -q 'dags'"
run_check "No critical errors in OpenSearch" "! docker logs aird-opensearch 2>&1 | grep -qi 'FATAL\\|CRITICAL' | head -1"  # NEW: Added OpenSearch log check

# Backend/Frontend (if running)
echo -e "${BLUE}Optional Backend/Frontend Checks:${NC}"
run_check "Backend (optional)" "docker ps | grep -q primedata-backend" || true
run_check "Frontend (optional)" "docker ps | grep -q primedata-frontend" || true

echo ""
echo -e "${BLUE}=== Verification Summary ===${NC}"
echo -e "Total Checks: ${TOTAL_CHECKS}"
echo -e "${GREEN}Passed: ${PASSED_CHECKS}${NC}"
echo -e "${RED}Failed: ${FAILED_CHECKS}${NC}"
echo ""

if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Deployment verified with OpenSearch.${NC}"
    echo -e "${BLUE}Access Points:${NC}"
    echo "  - Airflow UI: http://localhost:8080"
    echo "  - OpenSearch Dashboards: http://localhost:5601"
    echo "  - MinIO Console: http://localhost:9001"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some checks failed. Please review the output above.${NC}"
    exit 1
fi
