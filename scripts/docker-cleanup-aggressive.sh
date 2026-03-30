#!/usr/bin/env bash
set -euo pipefail

# Aggressive cleanup: removes all unused build cache/images and optionally unused volumes.
#
# Usage:
#   ./scripts/docker-cleanup-aggressive.sh [--prune-volumes]
#
# --prune-volumes  Also run `docker volume prune -f`.
#                  Without this flag, volumes are always preserved.

PRUNE_VOLUMES=0

for arg in "$@"; do
  case "$arg" in
    --prune-volumes)
      PRUNE_VOLUMES=1
      ;;
    -h|--help)
      sed -n '1,18p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Use --help for usage." >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not in PATH" >&2
  exit 1
fi

echo "== Docker disk usage (before) =="
docker system df || true

echo
echo "Planned cleanup commands:"
echo "- docker builder prune -a -f"
echo "- docker image prune -a -f"
echo "- docker container prune -f"
echo "- docker network prune -f"
if [[ "$PRUNE_VOLUMES" -eq 1 ]]; then
  echo "- docker volume prune -f"
else
  echo "- (skip) docker volume prune -f"
fi

RUNNING_COMPOSE_IDS=""
if docker compose version >/dev/null 2>&1; then
  RUNNING_COMPOSE_IDS="$(docker compose ps -q 2>/dev/null || true)"
fi

if [[ -n "$RUNNING_COMPOSE_IDS" ]]; then
  RUNNING_COUNT=$(echo "$RUNNING_COMPOSE_IDS" | sed '/^$/d' | wc -l | tr -d ' ')
  echo
  echo "Detected $RUNNING_COUNT running docker compose container(s) in this project."
  echo "Any in-use volume is protected by Docker and will not be removed."
fi

echo
echo "Running aggressive cleanup..."

docker builder prune -a -f

docker image prune -a -f

docker container prune -f

docker network prune -f

if [[ "$PRUNE_VOLUMES" -eq 1 ]]; then
  docker volume prune -f
else
  echo "Skipping volume prune (pass --prune-volumes to enable)."
fi

echo
echo "== Docker disk usage (after) =="
docker system df || true

echo
echo "Aggressive cleanup complete."
