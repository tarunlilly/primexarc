#!/bin/sh
# Inject runtime environment variables into the SPA before nginx starts.
# This runs inside the container, so it can read Kubernetes env vars.

cat > /usr/share/nginx/html/config.js << EOF
window.__ENV__ = {
  VITE_API_URL: "${VITE_API_URL:-}",
  VITE_AIRFLOW_URL: "${VITE_AIRFLOW_URL:-}"
};
EOF

# Template the nginx config with runtime env vars (needed for the API proxy block)
envsubst '${VITE_API_URL}' < /etc/nginx/conf.d/default.conf > /tmp/nginx.conf
cp /tmp/nginx.conf /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
