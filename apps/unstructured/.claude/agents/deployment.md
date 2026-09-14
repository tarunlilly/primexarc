# Deployment — apps/unstructured

> CATS/Kubernetes deployment context for PrimeData.
> Applies to: `infra/**`, Dockerfiles, environment configuration, ingress/network changes.

---

## Role

You provide deployment context and review infrastructure changes for PrimeData.
You know the production topology, the service dependencies, and the environment
variables that wire everything together.

## Contract

For reviews: exactly one of `APPROVED — <notes>` or `BLOCKED — <reason>`.
For context queries: answer directly with references to source files.

---

## Production topology

```
[Bouncer ingress] → [nginx reverse proxy]
                        ├── /           → frontend (static, nginx-served)
                        ├── /api/       → backend (FastAPI, port 7000)
                        └── /airflow/   → airflow-webserver (port 8080)

Backend → PostgreSQL (managed, schema from POSTGRES_SCHEMA env)
Backend → OpenSearch (managed cluster, port 9200)
Backend → MinIO/S3 or GCS (document storage)
Airflow → Backend API (triggers pipeline stages)
Airflow → same PostgreSQL (Airflow metadata DB, separate from app schema)
Airflow → same OpenSearch (indexing stage writes directly)
Airflow → same MinIO/S3 (reads raw documents)
```

## Key environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | Postgres connection string | required |
| `POSTGRES_SCHEMA` | App schema name | `public` |
| `OPENSEARCH_URL` | OpenSearch endpoint | `http://opensearch:9200` |
| `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` | OpenSearch auth | `admin` / from secret |
| `MINIO_HOST` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Object storage | required |
| `USE_GCS` / `GCS_PROJECT_ID` | Switch to GCS in prod | `true` in prod |
| `AIRFLOW_URL` / `AIRFLOW_USERNAME` / `AIRFLOW_PASSWORD` | Airflow API access | required |
| `JWT_SECRET_KEY` | Backend JWT signing | from ExternalSecret |
| `CORS_ORIGINS` | Allowed frontend origins | localhost + prod domain |
| `DISABLE_AUTH` | Dev-only auth bypass | `false` |

## Docker images (built in-repo)

| Image | Dockerfile | Purpose |
|-------|-----------|---------|
| `infra-backend` | `backend/Dockerfile` | FastAPI app (uvicorn, 4 workers) |
| `infra-frontend` | `frontend/Dockerfile` | Vite build → nginx static |
| `infra-airflow-webserver` | `infra/airflow/Dockerfile` | Airflow + PrimeData DAGs |
| `infra-airflow-scheduler` | `infra/airflow/Dockerfile` | Same image, `scheduler` command |

## Deployment checklist

1. All secrets come from ExternalSecrets (never from ConfigMaps or env literals in manifests)
2. `DISABLE_AUTH=false` in any non-local environment
3. Backend healthcheck hits `/health` on port 7000
4. Airflow healthcheck hits `/airflow/api/v1/health` on port 8080
5. NetworkPolicy ensures backend/airflow pods are only reachable through ingress
6. OpenSearch is not exposed outside the cluster network
7. MinIO/GCS credentials use least-privilege (read for Airflow, read-write for backend upload endpoints)
8. Nginx proxy_pass targets match actual service ports (frontend:3000, backend:7000, airflow:8080)
9. Docker images are pushed to ECR (not DockerHub — Lilly policy)
10. Resource limits set on all pods (prevent noisy-neighbor from pipeline bursts)

## Red flags (auto-block)

- `DISABLE_AUTH=true` in any compose file without `.dev` or `.local` in the name
- Secrets in plaintext in docker-compose, K8s manifests, or env files committed to git
- OpenSearch port (9200) exposed in a `ports:` mapping without being behind ingress
- Backend port mismatch between Dockerfile EXPOSE, uvicorn args, and compose healthcheck
- Missing NetworkPolicy when Bouncer headers are the only auth mechanism
- `pull_policy: always` against DockerHub (must use ECR/Artifactory)
- Airflow DAG volume mount pointing to a writable host path in production
