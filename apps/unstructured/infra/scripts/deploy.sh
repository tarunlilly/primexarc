#!/bin/bash
# Deployment Script for PrimeData Infrastructure
# Orchestrates the complete deployment process

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env.local}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${BLUE}=== PrimeData Infrastructure Deployment ===${NC}"

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker found${NC}"

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose found${NC}"

# Check for environment file
if [ ! -f "${ENV_FILE}" ]; then
    echo -e "${YELLOW}⚠ Environment file not found at ${ENV_FILE}${NC}"
    echo "Creating minimal environment file..."
    cat > "${ENV_FILE}" << 'EOF'
# PrimeData Infrastructure Environment Configuration

# PostgreSQL Configuration
POSTGRES_USER=aird
POSTGRES_PASSWORD=aird
POSTGRES_DB=aird
POSTGRES_PORT=5432

# Airflow Configuration
AIRFLOW_SECRET_KEY=your-secret-key-here
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin123
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=admin123
AIRFLOW_WEBSERVER_PORT=8080

# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET_NAME=aird
MINIO_HOST_PORT=9002
MINIO_CONSOLE_HOST_PORT=9003

# Qdrant Configuration
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334

# PrimeData App Configuration
PRIMEDATA_APP_DB=primedata_backend
DATABASE_URL=postgresql+psycopg2://aird:aird@postgres:5432/primedata_backend
EOF
fi

# Pull latest images
echo -e "${BLUE}Pulling latest Docker images...${NC}"
docker-compose -f "${COMPOSE_FILE}" pull 2>/dev/null || echo "Note: Some images may not be available on registry"

# Build images
echo -e "${BLUE}Building Docker images...${NC}"
docker-compose -f "${COMPOSE_FILE}" build --no-cache

# Start services
echo -e "${BLUE}Starting services...${NC}"
docker-compose -f "${COMPOSE_FILE}" up -d

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to stabilize...${NC}"
sleep 30

# Run health checks
echo -e "${BLUE}Running health checks...${NC}"
if [ -f "${SCRIPT_DIR}/health-checks/health-check.sh" ]; then
    bash "${SCRIPT_DIR}/health-checks/health-check.sh" || true
fi

# Run final verification
echo -e "${BLUE}Running final verification...${NC}"
if [ -f "${SCRIPT_DIR}/health-checks/final-check.sh" ]; then
    bash "${SCRIPT_DIR}/health-checks/final-check.sh" || {
        echo -e "${YELLOW}⚠ Some verification checks failed, but deployment may still be proceeding${NC}"
    }
fi

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo -e "${BLUE}Service URLs:${NC}"
echo "  Airflow Web UI: http://localhost:8080/airflow"
echo "  MinIO Console: http://localhost:9001"
echo "  Qdrant: http://localhost:6333"
echo "  PostgreSQL: localhost:5432"
echo ""
echo -e "${YELLOW}Default Credentials:${NC}"
echo "  PostgreSQL User: aird"
echo "  PostgreSQL Password: aird"
echo "  MinIO User: minioadmin"
echo "  MinIO Password: minioadmin"
echo "  Airflow User: admin"
echo "  Airflow Password: admin123"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Check service logs: docker-compose logs -f"
echo "  2. Access Airflow at http://localhost:8080/airflow"
echo "  3. Access MinIO at http://localhost:9001"
echo "  4. Configure DAGs and connections as needed"
