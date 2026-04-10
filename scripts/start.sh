#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  Jamf AI Dashboard — one-command startup script
#
#  Usage:
#    ./scripts/start.sh            # pull latest changes, build if needed, start
#    ./scripts/start.sh --no-update  # skip git pull (use current code)
#    ./scripts/start.sh --build    # force a full image rebuild before starting
#    ./scripts/start.sh --help     # show this help
#
#  Run from the repository root or from any sub-directory; the script locates
#  the project root automatically.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Locate project root (directory containing docker-compose.yml) ─────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# ── Colour helpers ─────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

info()    { echo -e "${CYAN}[info]${RESET}  $*"; }
success() { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[error]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── Argument parsing ───────────────────────────────────────────────────────────
OPT_SKIP_UPDATE=false
OPT_FORCE_BUILD=false

for arg in "$@"; do
  case "$arg" in
    --no-update) OPT_SKIP_UPDATE=true ;;
    --build)     OPT_FORCE_BUILD=true ;;
    --help|-h)
      sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^#  \?//'
      exit 0
      ;;
    *)
      error "Unknown option: $arg"
      error "Run '${BASH_SOURCE[0]} --help' for usage."
      exit 1
      ;;
  esac
done

# ── Step 1: Prerequisites ──────────────────────────────────────────────────────
header "Checking prerequisites…"

missing=0
for cmd in docker git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "'$cmd' is not installed or not in PATH."
    missing=1
  else
    success "$cmd found"
  fi
done

# Docker Compose v2 is a plugin: `docker compose` (no hyphen)
if ! docker compose version >/dev/null 2>&1; then
  error "'docker compose' (v2 plugin) is required but not found."
  error "Install the Docker Compose plugin: https://docs.docker.com/compose/install/"
  missing=1
else
  success "docker compose found"
fi

if ! docker info >/dev/null 2>&1; then
  error "Docker daemon is not running. Start Docker and try again."
  missing=1
else
  success "Docker daemon is running"
fi

[[ $missing -eq 0 ]] || exit 1

# ── Step 2: Bootstrap .env if not present ─────────────────────────────────────
header "Checking environment configuration…"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    warn ".env was not found — created from .env.example."
    warn "Please edit .env and set at minimum:"
    warn "  SECRET_KEY  (openssl rand -hex 32)"
    warn "  FERNET_KEY  (python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")"
    warn "  POSTGRES_PASSWORD"
    warn "Then re-run this script."
    exit 1
  else
    error ".env.example not found. Cannot bootstrap configuration."
    exit 1
  fi
fi

success ".env present"

# Warn if placeholder secrets are still set
if grep -qE '^(SECRET_KEY|FERNET_KEY)=replace-' .env 2>/dev/null; then
  warn "It looks like SECRET_KEY and/or FERNET_KEY still contain placeholder values."
  warn "Generate real keys:"
  warn "  SECRET_KEY:  openssl rand -hex 32"
  warn "  FERNET_KEY:  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  warn "The stack may not function correctly until these are set."
fi

# ── Step 3: Pull latest code ───────────────────────────────────────────────────
if [[ "${OPT_SKIP_UPDATE}" == "true" ]]; then
  info "Skipping git pull (--no-update flag set)."
else
  header "Checking for updates…"
  if git remote get-url origin >/dev/null 2>&1; then
    BEFORE_COMMIT="$(git rev-parse --short=12 HEAD)"
    if git pull --ff-only origin "$(git rev-parse --abbrev-ref HEAD)" 2>&1 | tee /tmp/_start_pull.log; then
      AFTER_COMMIT="$(git rev-parse --short=12 HEAD)"
      if [[ "${BEFORE_COMMIT}" != "${AFTER_COMMIT}" ]]; then
        success "Updated ${BEFORE_COMMIT} → ${AFTER_COMMIT}"
        OPT_FORCE_BUILD=true   # code changed, force rebuild
      else
        success "Already up to date (${BEFORE_COMMIT})"
      fi
    else
      warn "git pull failed — continuing with current code."
      warn "$(cat /tmp/_start_pull.log)"
    fi
    rm -f /tmp/_start_pull.log
  else
    info "No git remote configured — skipping update check."
  fi
fi

# ── Step 4: Build images ───────────────────────────────────────────────────────
header "Building images…"

if [[ "${OPT_FORCE_BUILD}" == "true" ]]; then
  info "Running full rebuild (code changed or --build flag)."
  docker compose build backend frontend
else
  # Build only if images are missing
  MISSING_IMAGES=()
  for svc in backend frontend; do
    IMAGE=$(docker compose config --images 2>/dev/null | grep "/${svc}" || true)
    if [[ -z "$(docker images -q "project-${svc}" 2>/dev/null)" ]]; then
      MISSING_IMAGES+=("$svc")
    fi
  done

  if [[ ${#MISSING_IMAGES[@]} -gt 0 ]]; then
    info "Building missing images: ${MISSING_IMAGES[*]}"
    docker compose build "${MISSING_IMAGES[@]}"
  else
    success "Images are up to date — skipping build."
  fi
fi

# ── Step 5: Start the stack ────────────────────────────────────────────────────
header "Starting services…"

docker compose up -d

success "All services started."

# ── Step 6: Wait for backend health ───────────────────────────────────────────
header "Waiting for backend to become healthy…"

BACKEND_HEALTH_URL="http://localhost:8000/api/v1/health"
MAX_WAIT=90
WAITED=0
HEALTHY=false

while [[ $WAITED -lt $MAX_WAIT ]]; do
  HTTP_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${BACKEND_HEALTH_URL}" 2>/dev/null || true)"
  if [[ "${HTTP_STATUS}" == "200" ]]; then
    HEALTHY=true
    break
  fi
  sleep 5
  WAITED=$((WAITED + 5))
  printf '.'
done
echo

if [[ "${HEALTHY}" == "true" ]]; then
  success "Backend is healthy."
else
  warn "Backend did not become healthy within ${MAX_WAIT}s."
  warn "Check logs with:  docker compose logs --tail=80 backend"
fi

# ── Step 7: Summary ────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}  Jamf AI Dashboard is running!${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Frontend:   ${CYAN}http://localhost:3000${RESET}"
echo -e "  Backend:    ${CYAN}http://localhost:8000${RESET}"
echo -e "  Swagger:    ${CYAN}http://localhost:8000/docs${RESET}"
echo -e "  Docs:       ${CYAN}http://localhost:8088${RESET}"
echo
echo -e "  Useful commands:"
echo -e "    docker compose ps"
echo -e "    docker compose logs -f backend"
echo -e "    docker compose logs -f frontend"
echo -e "    docker compose down"
echo
