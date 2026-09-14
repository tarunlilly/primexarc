# =============================================================================
# Multi-stage Dockerfile for AIRD Backend (FastAPI + Python)
# Optimized for CATS/EKS deployment with minimal image size
#
# NOTE: Uses consolidated requirements.txt which includes all dependencies:
# - Base dependencies (FastAPI, SQLAlchemy, etc.)
# - Cloud storage (AWS S3, GCS, Azure)
# - ML/AI (sentence-transformers, OpenAI)
# - Analytics (pandas, numpy)
# - Testing (pytest)
# =============================================================================

# Stage 1: Builder with compilation tools
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build tools only in builder stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file (consolidated with all dependencies)
COPY requirements.txt /app/

# Install Python dependencies with --prefix to isolate installation
# NumPy must be installed first for compatibility
RUN pip install --no-cache-dir --prefix=/install \
    "numpy<2.0"

# Install all dependencies from consolidated requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Production image (no build tools)
FROM python:3.11-slim as production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only runtime dependencies (curl for healthcheck, postgresql-client for db init)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder (only compiled packages, no build tools)
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy application code (required)
COPY --chown=appuser:appuser src/ ./src/

# Copy optional files if they exist - these may not always be present
# Note: COPY with non-existent sources will fail in standard Docker builds
# Only core src/ is required; config and alembic are optional
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser alembic/ ./alembic/

# Copy database initialization scripts
COPY --chown=appuser:appuser init-db.sh .
COPY --chown=appuser:appuser docker-entrypoint.sh .
RUN chmod +x init-db.sh docker-entrypoint.sh

# Switch to non-root user
USER appuser

# Set Python path
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 7000

# Health check using built-in Python health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7000/health || exit 1

# Use entrypoint to setup database URL from environment variables
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the application with multiple workers for production
CMD ["uvicorn", "primedata.api.app:app", "--host", "0.0.0.0", "--port", "7000", "--workers", "4"]







