#!/bin/sh
# Build and run primedata-ui Docker image locally using Colima

set -e

IMAGE="primedata-ui:local"
CONTAINER="primedata-ui-local"
PORT=3000

# Stop and remove existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Stopping existing container..."
  docker rm -f "$CONTAINER"
fi

# Build image
echo "Building image..."
docker build -t "$IMAGE" .

# Run container
echo "Starting container..."
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:3000" \
  -e VITE_API_URL="${VITE_API_URL:-http://127.0.0.1:8000}" \
  -e VITE_AIRFLOW_URL="${VITE_AIRFLOW_URL:-http://localhost:8080}" \
  "$IMAGE"

echo ""
echo "Running at http://localhost:${PORT}"
echo ""
echo "Useful commands:"
echo "  Logs:  docker logs -f ${CONTAINER}"
echo "  Stop:  docker rm -f ${CONTAINER}"
