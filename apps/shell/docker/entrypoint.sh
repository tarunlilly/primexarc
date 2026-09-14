#!/bin/sh
# Inject runtime environment variables into the SPA before nginx starts.
# This runs inside the container, so it can read Kubernetes env vars.
#
# Variables:
#   STRUCTURED_URL   — hostname for ARC (e.g. https://ibu-ard.apps.lrl.lilly.com)
#   UNSTRUCTURED_URL — hostname for PrimeData (e.g. https://primedata.apps.lrl.lilly.com)

cat > /usr/share/nginx/html/config.js << EOF
window.__ENV__ = {
  STRUCTURED_URL: "${STRUCTURED_URL:-}",
  UNSTRUCTURED_URL: "${UNSTRUCTURED_URL:-}"
};
EOF

exec nginx -g "daemon off;"
