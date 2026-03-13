# Jamf AI Dashboard — Technical Documentation

Version: Current workspace state (0.5.x line)

## 1. Overview

Jamf AI Dashboard is a self-hosted web platform for operating one or more Jamf Pro environments from a single UI. It combines operational visibility (devices, policies, groups, patch state), AI-assisted workflows, documentation scraping, and cross-server migration tooling.

## 2. Functional Areas

### 2.1 Core fleet data

- Devices list + detail drawer
- Policies list + detail drawer
- Smart Groups list + detail drawer
- Patches list + detail drawer
- Jamf deep-links from details

### 2.2 Dashboard analytics

- KPI cards
- OS distribution chart
- Patch summaries
- Manual refresh and periodic query refresh
- Optional server-scoped statistics via `server_id`

### 2.3 Multi-server operations

- Jamf server CRUD/provisioning in Settings
- Global server selector in app shell
- Server filter propagated through dashboard and list queries

### 2.4 Knowledge Base

- Create scrape jobs from URL/domain
- Track status, progress, errors, and source ingestion
- Delete completed jobs/sources
- Runtime control for active jobs:
  - pause/resume/cancel
  - CPU cap modes:
    - `total`: `1-100%`
    - `core`: `1-(cpu_cores*100)%`

### 2.5 Assets

- Scripts page: live Jamf scripts catalog for selected server
- Packages page: live Jamf packages catalog for selected server

### 2.6 Migrator

Source-to-target migration between Jamf servers for:

- Policies
- Smart Groups
- Static Groups
- Scripts

## 3. Backend Architecture

- FastAPI app: `backend/app/main.py`
- Router modules in `backend/app/routers/`
- Service layer in `backend/app/services/`
- Persistence via PostgreSQL + SQLAlchemy async models
- Schema evolution via Alembic migrations
- Redis for caching/token/session support
- APScheduler for automated sync intervals

### 3.1 Important routers

- `/api/v1/auth/*`
- `/api/v1/servers/*`
- `/api/v1/devices`, `/policies`, `/smart-groups`, `/patches`
- `/api/v1/dashboard/stats`
- `/api/v1/knowledge/scrape`, `/api/v1/knowledge/sources`
- `/api/v1/knowledge/scrape/system`
- `/api/v1/assets/scripts`, `/api/v1/assets/packages`
- `/api/v1/migrator/objects`, `/api/v1/migrator/migrate`
- `/api/v1/ai/*`

### 3.2 Scrape runtime control endpoints

- `GET /api/v1/knowledge/scrape/system`
  - returns CPU core info and slider maxima
- `PATCH /api/v1/knowledge/scrape/{job_id}`
  - action: `pause`, `resume`, `cancel`
  - accepts `cpu_cap_mode` and `cpu_cap_percent`

## 4. Frontend Architecture

- Next.js App Router structure under `frontend/src/app/`
- Shared API client in `frontend/src/lib/api.ts`
- React Query for server state and caching
- Zustand stores for auth/ui selections

### 4.1 Key routes

- `/` dashboard
- `/devices`, `/policies`, `/smart-groups`, `/patches`
- `/scripts`, `/packages`
- `/migrator`
- `/knowledge`
- `/ai`
- `/settings`

## 5. Data and Migration Notes

- Backend container startup runs `alembic upgrade head`
- Multiple Alembic heads must be merged before deployment (merge revision exists in current workspace)
- Scrape job schema includes runtime control fields (`pause_requested`, `cancel_requested`, `cpu_cap_mode`, `cpu_cap_percent`)

## 6. Operations Runbook

### 6.1 Start stack

```bash
docker compose up -d
```

### 6.2 Rebuild app services

```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

### 6.3 Follow backend logs

```bash
docker compose logs -f backend
```

### 6.4 Apply DB migrations manually

```bash
docker compose exec -T backend alembic upgrade head
```

## 7. Security Model

- JWT auth with refresh flow
- Admin authorization on privileged endpoints
- Jamf credentials encrypted at rest (Fernet)
- Local-model AI and local vector store architecture for self-hosted privacy

## 8. Known Constraints

- Scrape CPU cap is cooperative throttling, not hard cgroup quota enforcement
- Migrator requires compatible dependencies on target Jamf (for example referenced categories/scripts/scope objects)
- Static group membership portability depends on environment identity alignment

## 9. Related Docs

- `README.md`
- `CHANGELOG.md`
- `TODO.md`
- `frontend/README.md`
