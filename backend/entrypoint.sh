#!/bin/sh
# backend/entrypoint.sh — runs DB migrations then starts Uvicorn

set -e

# Ensure local application package is always importable for alembic/uvicorn.
export PYTHONPATH="/app:${PYTHONPATH}"

LOG_DIR="${SERVER_LOGS_DIR:-/app/logs/server-runs}"
mkdir -p "$LOG_DIR"

# If mounted volume permissions prevent writes, fall back to /tmp so startup never loops/crashes.
if ! touch "$LOG_DIR/.write-test" 2>/dev/null; then
	echo "WARN: Cannot write to $LOG_DIR, falling back to /tmp/server-runs" >&2
	LOG_DIR="/tmp/server-runs"
	mkdir -p "$LOG_DIR"
fi
rm -f "$LOG_DIR/.write-test" 2>/dev/null || true
export SERVER_LOGS_DIR="$LOG_DIR"

RUN_ID="$(date -u +"%Y%m%dT%H%M%SZ")"
LOG_FILE="$LOG_DIR/server-$RUN_ID.log"
export CURRENT_SERVER_LOG_FILE="$LOG_FILE"

log_header() {
	printf '\n================================================================================\n' | tee -a "$LOG_FILE"
	printf '%s\n' "$1" | tee -a "$LOG_FILE"
	printf 'timestamp=%s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" | tee -a "$LOG_FILE"
	printf '================================================================================\n' | tee -a "$LOG_FILE"
}

prefix_and_tee() {
	python -u -c 'import datetime, sys
for line in sys.stdin:
		ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
		sys.stdout.write(f"{ts} | {line}")
		sys.stdout.flush()' | tee -a "$LOG_FILE"
}

log_header "Jamf AI Dashboard backend startup"

printf 'Running Alembic migrations...\n' | tee -a "$LOG_FILE"
alembic upgrade head 2>&1 | prefix_and_tee

printf 'Starting Uvicorn...\n' | tee -a "$LOG_FILE"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 2>&1 | prefix_and_tee
