#!/usr/bin/env bash
set -euo pipefail

# Safe cleanup: removes stale build cache and dangling artifacts only.

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not in PATH" >&2
  exit 1
fi

echo "== Docker disk usage (before) =="
docker system df || true

echo
echo "Planned cleanup commands:"
echo "- docker builder prune -f --filter until=24h"
echo "- docker image prune -f"
echo "- docker container prune -f"
echo "- docker network prune -f"
echo
echo "Running safe cleanup..."

docker builder prune -f --filter until=24h

docker image prune -f

docker container prune -f

docker network prune -f

echo
echo "== Docker disk usage (after) =="
docker system df || true

echo
echo "Safe cleanup complete. Volumes were not touched."
