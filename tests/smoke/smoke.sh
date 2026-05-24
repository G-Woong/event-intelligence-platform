#!/usr/bin/env bash
set -euo pipefail

BACKEND=${BACKEND_URL:-http://localhost:8000}
FRONTEND=${FRONTEND_URL:-http://localhost:3000}

echo "== Backend health"
curl -sf "${BACKEND}/health" | head -c 200
echo

echo "== Frontend health"
curl -sf "${FRONTEND}/api/health"
echo

echo "== Frontend /events (200)"
curl -sf -o /dev/null -w "%{http_code}\n" "${FRONTEND}/events"

echo "== Frontend /search?q=test (200)"
curl -sf -o /dev/null -w "%{http_code}\n" "${FRONTEND}/search?q=test"

echo "== Frontend /admin (200)"
curl -sf -o /dev/null -w "%{http_code}\n" "${FRONTEND}/admin"

echo "== CORS preflight"
curl -si -X OPTIONS "${BACKEND}/api/events" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  | grep -i "access-control-allow-origin"

echo "OK"
