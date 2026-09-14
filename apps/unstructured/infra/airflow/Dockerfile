# infra/airflow/Dockerfile
# Airflow base image pinned to your current version
FROM apache/airflow:2.7.1-python3.11

USER root

# Optional: avoid failing apt-get update on corp networks / extra repos
# (Base image sometimes carries extra apt sources; we only need Debian official repos)
RUN rm -f /etc/apt/sources.list.d/*microsoft* /etc/apt/sources.list.d/*pgdg* || true
RUN rm -f /etc/apt/sources.list.d/* || true


RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    postgresql-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
  
USER airflow

# Copy Airflow constraints + extra requirements (installed under constraints to avoid conflicts)
COPY infra/airflow/constraints/constraints-3.11.txt /opt/airflow/constraints-3.11.txt
COPY infra/airflow/requirements-extra.txt /opt/airflow/requirements-extra.txt

# Optional custom CA certs (place *.crt in airflow/certs/)
USER root
COPY infra/airflow/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates || true
USER airflow

# Keep pip sane; use constraints to avoid dependency conflicts
RUN python -m pip install --no-cache-dir --upgrade "pip<25" "setuptools<67" "wheel"

# Install extra deps using Airflow constraints (prevents urllib3/cffi conflicts)
# Install deps that must respect Airflow constraints
RUN pip install --no-cache-dir \
  --constraint /opt/airflow/constraints-3.11.txt \
  -r /opt/airflow/requirements-extra.txt

# Set Airflow configuration via environment variables to ensure PostgreSQL is used
# These will be read by Airflow before it creates airflow.cfg
# NOTE: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN is constructed dynamically by entrypoint from POSTGRES_* vars
# Do NOT set it here - let the runtime environment variables take precedence
ENV AIRFLOW__CORE__LOAD_EXAMPLES=false
ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor
ENV AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true
ENV AIRFLOW__CORE__UNIT_TEST_MODE=false

# Copy DAG files into the image
# These will be available to Airflow for DAG discovery
COPY infra/airflow/dags/ /opt/airflow/dags/
COPY infra/airflow/docker-entrypoint.sh /opt/airflow/docker-entrypoint.sh
# Copy backend source code for task imports
# Allows DAG tasks to import from primedata.* modules
COPY backend/src/ /opt/airflow/backend/src/

# Copy entrypoint script that constructs AIRFLOW__DATABASE__SQL_ALCHEMY_CONN from env variables
USER root
RUN chmod +x /opt/airflow/docker-entrypoint.sh
USER airflow

# Set PYTHONPATH to include backend source and dags for imports
ENV PYTHONPATH=/opt/airflow/backend/src:/opt/airflow/dags

ENTRYPOINT ["/opt/airflow/docker-entrypoint.sh"]
CMD ["airflow", "webserver"]