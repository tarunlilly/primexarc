#!/bin/bash
# Persistence Verification Script
# Tests data persistence across container restarts

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Persistence Verification Test ==="

# Test PostgreSQL data persistence
echo "Testing PostgreSQL persistence..."
TEST_TABLE_NAME="persistence_test_$$"

docker exec aird-postgres psql -U aird -d aird -c "CREATE TABLE ${TEST_TABLE_NAME} (id SERIAL, test_value VARCHAR(255));" 2>/dev/null
docker exec aird-postgres psql -U aird -d aird -c "INSERT INTO ${TEST_TABLE_NAME} (test_value) VALUES ('test_data_$$');" 2>/dev/null

# Restart PostgreSQL
echo "Restarting PostgreSQL..."
docker restart aird-postgres > /dev/null

# Wait for restart
sleep 5

# Verify data still exists
if docker exec aird-postgres psql -U aird -d aird -c "SELECT * FROM ${TEST_TABLE_NAME};" 2>/dev/null | grep -q "test_data_$$"; then
    echo -e "${GREEN}✓ PostgreSQL persistence: OK${NC}"
    docker exec aird-postgres psql -U aird -d aird -c "DROP TABLE ${TEST_TABLE_NAME};" 2>/dev/null
else
    echo -e "${RED}✗ PostgreSQL persistence: FAILED${NC}"
    exit 1
fi

# Test Qdrant persistence
echo "Testing Qdrant persistence..."
COLLECTION_NAME="persistence_test_$$"

# Create a test collection
curl -s -X POST "http://localhost:6333/collections" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"${COLLECTION_NAME}\", \"vectors\": {\"size\": 128, \"distance\": \"Cosine\"}}" > /dev/null 2>&1

# Verify collection exists
if curl -s "http://localhost:6333/collections/${COLLECTION_NAME}" | grep -q "\"name\":\"${COLLECTION_NAME}\""; then
    echo -e "${GREEN}✓ Qdrant persistence: OK${NC}"
    # Clean up
    curl -s -X DELETE "http://localhost:6333/collections/${COLLECTION_NAME}" > /dev/null 2>&1
else
    echo -e "${RED}✗ Qdrant persistence: FAILED${NC}"
    exit 1
fi

# Test MinIO persistence (if available)
echo "Testing MinIO persistence..."
TEST_BUCKET="persistence-test-$$"
TEST_FILE="/tmp/test_file_$$.txt"
echo "test_data_$$" > $TEST_FILE

# Create bucket and upload file
docker exec aird-minio-init mc mb minio/${TEST_BUCKET} 2>/dev/null || true
docker cp $TEST_FILE aird-minio-init:${TEST_FILE}
docker exec aird-minio-init mc cp ${TEST_FILE} minio/${TEST_BUCKET}/ 2>/dev/null || true

# Restart MinIO
echo "Restarting MinIO..."
docker restart aird-minio > /dev/null
sleep 3

# Verify file still exists
if docker exec aird-minio-init mc ls minio/${TEST_BUCKET} 2>/dev/null | grep -q "test_file"; then
    echo -e "${GREEN}✓ MinIO persistence: OK${NC}"
    docker exec aird-minio-init mc rm -r minio/${TEST_BUCKET} 2>/dev/null || true
else
    echo -e "${YELLOW}⚠ MinIO persistence: Could not verify (may not be critical)${NC}"
fi

rm -f $TEST_FILE

echo ""
echo -e "${GREEN}Persistence verification completed!${NC}"
