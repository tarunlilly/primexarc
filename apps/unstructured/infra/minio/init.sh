#!/bin/bash
# MinIO Initialization Script
# Creates buckets and sets policies for PrimeData storage

set -e

echo "Initializing MinIO..."

MINIO_ALIAS="${MINIO_ALIAS:-minio}"
MINIO_HOST="${MINIO_HOST:-minio:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minioadmin}"
MINIO_BUCKET_NAME="${MINIO_BUCKET_NAME:-aird}"

# Configure MinIO client
mc alias set ${MINIO_ALIAS} http://${MINIO_HOST} ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}

# Create default bucket if it doesn't exist
if mc ls ${MINIO_ALIAS}/${MINIO_BUCKET_NAME} > /dev/null 2>&1; then
    echo "Bucket '${MINIO_BUCKET_NAME}' already exists."
else
    echo "Creating bucket '${MINIO_BUCKET_NAME}'..."
    mc mb ${MINIO_ALIAS}/${MINIO_BUCKET_NAME}
fi

# Set bucket versioning
echo "Enabling versioning for bucket '${MINIO_BUCKET_NAME}'..."
mc version enable ${MINIO_ALIAS}/${MINIO_BUCKET_NAME}

# Create additional buckets for different purposes
BUCKETS=(
    "primedata-raw"
    "primedata-clean"
    "primedata-chunk"
    "primedata-embed"
    "primedata-exports"
    "primedata-config"
)

for bucket in "${BUCKETS[@]}"; do
    if mc ls ${MINIO_ALIAS}/${bucket} > /dev/null 2>&1; then
        echo "Bucket '${bucket}' already exists."
    else
        echo "Creating bucket '${bucket}'..."
        mc mb ${MINIO_ALIAS}/${bucket}
    fi
    # Enable versioning for each bucket
    mc version enable ${MINIO_ALIAS}/${bucket}
done

echo "MinIO initialization completed successfully!"
