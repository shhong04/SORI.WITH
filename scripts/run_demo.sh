#!/usr/bin/env bash
# Demo-safe launch: production mode, path analyze off, tighter upload limit, clean CORS.
# Usage:
#   ./scripts/run_demo.sh
#   TUNNEL_URL=https://xxx.trycloudflare.com ./scripts/run_demo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv — create with: python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

export SORI_WITH_ENVIRONMENT=production
export SORI_WITH_ALLOW_PATH_ANALYZE=false
export SORI_WITH_MAX_UPLOAD_BYTES="${SORI_WITH_MAX_UPLOAD_BYTES:-20971520}"

BASE_CORS="http://127.0.0.1:8000,http://localhost:8000,null"
if [[ -n "${TUNNEL_URL:-}" ]]; then
  export SORI_WITH_CORS_ORIGINS="${BASE_CORS},${TUNNEL_URL}"
elif [[ -n "${SORI_WITH_CORS_ORIGINS:-}" ]]; then
  : # keep caller-provided value
else
  export SORI_WITH_CORS_ORIGINS="$BASE_CORS"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "==> SORI.WITH demo (hardened)"
echo "    environment=$SORI_WITH_ENVIRONMENT"
echo "    path_analyze=$SORI_WITH_ALLOW_PATH_ANALYZE"
echo "    max_upload=$SORI_WITH_MAX_UPLOAD_BYTES bytes"
echo "    cors=$SORI_WITH_CORS_ORIGINS"
echo "    listen=http://${HOST}:${PORT}"
echo ""
echo "Local UI:  http://127.0.0.1:${PORT}/"
echo "API docs:  http://127.0.0.1:${PORT}/docs"
echo ""
echo "Public tunnel (other terminal):"
echo "  cloudflared tunnel --url http://127.0.0.1:${PORT} --protocol http2"
echo "  Then restart with:"
echo "  TUNNEL_URL=https://YOUR.trycloudflare.com $0"
echo ""

exec .venv/bin/python -m uvicorn sori_with.api.main:app --host "$HOST" --port "$PORT"
