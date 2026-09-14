Place your company/root CA certificate(s) in this folder as `.crt` files.

Example:

1. Copy your certificate:
   - `infra/airflow/certs/your-company-ca.crt`
2. Rebuild the Airflow image:
   - `podman compose build --no-cache airflow-webserver airflow-scheduler airflow-init`
   - `podman compose up -d --force-recreate airflow-webserver airflow-scheduler airflow-init`

The Dockerfile copies any `.crt` files from this folder into
`/usr/local/share/ca-certificates/` and runs `update-ca-certificates` so HTTPS
requests (e.g., OpenAI) validate correctly inside the container.
