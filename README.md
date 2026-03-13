# Jamf AI Dashboard

Self-hosted Jamf Pro operations dashboard with a local AI assistant, multi-server support, migration workflows, and a knowledge scraping pipeline.

## Highlights

- Unified data pages for `Devices`, `Policies`, `Smart Groups`, and `Patches`
- Detail drawers with direct deep-links to Jamf Pro records
- Global Jamf server selector (`All Servers` or one specific server)
- Dashboard KPI cards and charts (including OS distribution and patch status)
- Automatic background sync for active servers
- Knowledge Base scraping + source management
- Scrape job runtime controls: pause/resume/cancel + CPU cap
- Migrator for cross-server Jamf object migration (`Policies`, `Smart Groups`, `Static Groups`, `Scripts`)
- Assets pages for live Jamf `Scripts` and `Packages` catalogs

## Tech Stack

- Backend: FastAPI, SQLAlchemy (async), Alembic, PostgreSQL, Redis, APScheduler
- Frontend: Next.js App Router, React, TanStack Query, Tailwind CSS
- AI/RAG: Ollama + ChromaDB
- Runtime: Docker Compose

## Local URLs

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Quick Start

```bash
# 1) Clone
cd /path/to/workspace
git clone <your-repo-url> jamf-ai-dashboard
cd jamf-ai-dashboard

# 2) Configure env
cp .env.example .env
# edit .env values

# 3) Start services
docker compose up -d
```

Then open `http://localhost:3000`.

## Common Commands

```bash
# Rebuild and redeploy changed app services
docker compose build backend frontend
docker compose up -d backend frontend

# Follow backend logs
docker compose logs -f backend

# Apply migrations manually
docker compose exec -T backend alembic upgrade head
```

## Scrape Job Control Modes

Running scrape jobs can be controlled from the Knowledge Base UI:

- `Pause`
- `Resume`
- `Cancel`
- CPU cap slider modes:
  - `Total CPU`: `1-100%`
  - `Linux style`: `1-(cores*100)%` (for example 6 cores => `1-600%`)

Note: CPU cap is cooperative application-level throttling in the scraper loop.

## Documentation Index

- Technical documentation: `Documentation.md`
- Release history: `CHANGELOG.md`
- Project roadmap and tasks: `TODO.md`
- Frontend-specific notes: `frontend/README.md`
