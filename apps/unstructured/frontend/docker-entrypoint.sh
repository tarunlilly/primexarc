#!/bin/sh
# PrimeData UI (Vite SPA) entrypoint
# nginx serves the static build; this script is kept for Kubernetes compatibility.

set -e

echo "=========================================="
echo "PrimeData UI (Vite SPA) Starting"
echo "=========================================="
echo "  Note: API URL is baked into the bundle at build time (VITE_API_URL/VITE_API_BASE)"
echo "  Serving static files via nginx on port 3000"
echo "=========================================="

exec nginx -g "daemon off;"
