#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -d backend/.venv ]]; then
  PYTHON_BIN="backend/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Python 3 is required" >&2
  exit 1
fi

if [[ -d frontend/node_modules ]]; then
  (
    cd frontend
    npm test
  )
else
  (
    cd frontend
    npm ci
    npm test
  )
fi

"$PYTHON_BIN" -m pytest -q backend/tests
