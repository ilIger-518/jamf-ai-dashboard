#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 /path/to/backup.sql" >&2
  exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required but was not found in PATH." >&2
  exit 1
fi

CONTAINER_ID="$(docker compose -f docker-compose.prod.yml ps -q postgres 2>/dev/null || true)"
if [[ -z "$CONTAINER_ID" ]]; then
  echo "Postgres container is not running; start the stack first." >&2
  exit 1
fi

docker compose -f docker-compose.prod.yml exec -T postgres psql -U "${POSTGRES_USER:-jamfdash}" -d "${POSTGRES_DB:-jamfdash}" -f - < "$BACKUP_FILE"
