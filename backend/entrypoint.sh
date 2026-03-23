#!/bin/sh
# backend/entrypoint.sh — runs DB migrations then starts Uvicorn

set -e

# Ensure local application package is always importable for alembic/uvicorn.
export PYTHONPATH="/app:${PYTHONPATH}"

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
