#!/bin/bash
# Stability Verification Script
# Tests system stability and performance under normal operation

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== System Stability Verification ==="

# Check for container restarts
echo "Checking for unexpected container restarts..."
RESTART_COUNT=$(docker ps -a --format '{{.RestartCount}}' | awk '{s+=$1} END {print s}')
if [ "$RESTART_COUNT" -lt 5 ]; then
    echo -e "${GREEN}✓ Restart count acceptable: ${RESTART_COUNT}${NC}"
else
    echo -e "${YELLOW}⚠ High restart count detected: ${RESTART_COUNT}${NC}"
fi

# Check container memory usage
echo "Checking container memory usage..."
docker ps --format '{{.Names}}\t{{.ID}}' | while read name id; do
    MEMORY=$(docker stats --no-stream $id 2>/dev/null | tail -1 | awk '{print $7}')
    if echo "$MEMORY" | grep -q "GB\|MB"; then
        echo "  ${name}: ${MEMORY}"
    fi
done

# Check disk space
echo "Checking volume disk space..."
VOLUME_USAGE=$(docker system df | grep "Local Volumes" | awk '{print $4}' | tr -d 'B')
if [ -n "$VOLUME_USAGE" ]; then
    echo -e "${GREEN}✓ Volume space: ${VOLUME_USAGE}${NC}"
fi

# Check PostgreSQL connection pool
echo "Checking PostgreSQL connection status..."
CONN_COUNT=$(docker exec aird-postgres psql -U aird -d aird -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null || echo "0")
echo "  Active connections: $CONN_COUNT"

# Check Airflow DAG parsing time
echo "Checking Airflow DAG parsing performance..."
if curl -s "http://localhost:8080/airflow/api/v1/dags" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ DAG endpoint responding${NC}"
else
    echo -e "${RED}✗ DAG endpoint not responding${NC}"
fi

# Check for critical error logs
echo "Checking for critical errors in logs..."
CRITICAL_ERRORS=$(docker ps --format '{{.Names}}' | while read name; do
    docker logs $name 2>&1 | grep -i "ERROR\|FATAL\|CRITICAL" | wc -l
done | awk '{s+=$1} END {print s}')

if [ "$CRITICAL_ERRORS" -lt 10 ]; then
    echo -e "${GREEN}✓ Error count acceptable: $CRITICAL_ERRORS${NC}"
else
    echo -e "${YELLOW}⚠ High error count detected: $CRITICAL_ERRORS${NC}"
fi

echo ""
echo -e "${GREEN}Stability verification completed!${NC}"
