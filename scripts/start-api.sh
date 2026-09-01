#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [ ! -x ".venv/bin/uvicorn" ]; then
  echo "Missing .venv/bin/uvicorn. Run: python3 -m venv .venv && .venv/bin/python -m pip install -e ."
  exit 1
fi

exec .venv/bin/uvicorn engram.api:app --host "${ENGRAM_HOST:-127.0.0.1}" --port "${ENGRAM_PORT:-8732}"
