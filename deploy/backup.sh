#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$BACKUP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required but was not found in PATH." >&2
  exit 1
fi

CONTAINER_ID="$(docker compose -f docker-compose.prod.yml ps -q postgres 2>/dev/null || true)"
if [[ -z "$CONTAINER_ID" ]]; then
  echo "Postgres container is not running; nothing to back up." >&2
  exit 1
fi

docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U "${POSTGRES_USER:-jamfdash}" "${POSTGRES_DB:-jamfdash}" > "$BACKUP_DIR/jamfdash-$TS.sql"
echo "Backup written to $BACKUP_DIR/jamfdash-$TS.sql"
