# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


# Stage 2: Build Python venv (mirrors backend/Dockerfile)
FROM python:3.11-slim AS backend-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir -r requirements.txt


# Stage 3: Runtime
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 app && \
    useradd -u 1000 -g app -s /bin/bash -m app

WORKDIR /app

COPY --from=backend-builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/ .
COPY --from=frontend-builder --chown=app:app /app/dist ./static

ARG CLIENT_ID=""
ARG TENANT_ID=""
RUN printf 'CLIENT_ID=%s\nTENANT_ID=%s\n' "${CLIENT_ID}" "${TENANT_ID}" > /app/.env \
 && chown app:app /app/.env

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    STATIC_DIR="/app/static"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
