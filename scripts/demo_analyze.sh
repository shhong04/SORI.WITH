#!/usr/bin/env bash
# Offline analyze demo helper.
# Usage:
#   ./scripts/demo_analyze.sh                          # local in-process
#   ./scripts/demo_analyze.sh http://127.0.0.1:8000    # local API upload
#   ./scripts/demo_analyze.sh https://sori-with.onrender.com
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv — create with python3.13 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

BASE_URL="${1:-}"
if [[ -n "$BASE_URL" ]]; then
  exec .venv/bin/python scripts/demo_analyze.py --base-url "$BASE_URL"
else
  exec .venv/bin/python scripts/demo_analyze.py
fi
