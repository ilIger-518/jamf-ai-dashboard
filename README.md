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

## First-Time Setup After Cloning (Detailed)

Use this once on a fresh clone.

1. Prerequisites

- Docker Engine + Docker Compose plugin
- At least 8 GB RAM recommended (Ollama + app services)
- Ports available: `3000`, `5432`, `6379`, `8000`, `8001`, `11434`

2. Create runtime config

```bash
cp .env.example .env
```

3. Set required secrets in `.env`

- `SECRET_KEY`: generate with `openssl rand -hex 32`
- `FERNET_KEY`: generate with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

4. Start the stack

```bash
docker compose up -d
```

5. Verify healthy services

```bash
docker compose ps
docker compose logs --tail=80 backend
```

6. Create the first admin user (bootstrap step)

Important: self-registration is disabled after the first user is created.

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username":"admin",
    "email":"admin@example.com",
    "password":"StrongPass1",
    "is_admin":true
  }'
```

Password requirements:
- minimum 8 chars
- at least one uppercase letter
- at least one digit

7. Sign in

- Open `http://localhost:3000/login`
- Sign in with the user you created

8. Connect your first Jamf server

- Go to Settings -> Jamf Servers
- Use `Setup Wizard` or `Add Jamf Server`
- Run `Sync` and verify data appears on Dashboard/Devices

9. Optional AI model warm-up (recommended)

```bash
docker compose exec -T ollama ollama pull llama3.2:3b
docker compose exec -T ollama ollama pull nomic-embed-text
```

## Microsoft SSO Setup (Full Guide)

This app uses Microsoft Entra ID (OIDC) with backend-managed callback flow.

1. Create an app registration in Entra

- Azure Portal -> Microsoft Entra ID -> App registrations -> New registration
- Name: `Jamf AI Dashboard` (or your choice)
- Supported account type: your tenant choice
- Redirect URI (Web):
  - local: `http://localhost:8000/api/v1/auth/sso/microsoft/callback`
  - production: `https://<your-backend-domain>/api/v1/auth/sso/microsoft/callback`

2. Create a client secret

- App registration -> Certificates & secrets -> New client secret
- Copy the secret value immediately (it is shown once)

3. Configure API permissions

- Add delegated permissions: `openid`, `profile`, `email`
- If user profile fetch fails in your tenant, also add `User.Read`
- Grant admin consent if required by tenant policy

4. Fill `.env`

```env
MICROSOFT_SSO_ENABLED=true
MICROSOFT_TENANT_ID=<tenant-guid-or-common>
MICROSOFT_CLIENT_ID=<application-client-id>
MICROSOFT_CLIENT_SECRET=<client-secret-value>
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/sso/microsoft/callback
FRONTEND_BASE_URL=http://localhost:3000
```

5. Cookie/security settings

- Local HTTP testing: keep `COOKIE_SECURE=false`
- HTTPS production: set `COOKIE_SECURE=true` and use HTTPS frontend/backend URLs

6. Restart backend and frontend after env changes

```bash
docker compose up -d --build backend frontend
```

7. Test SSO

- Open `http://localhost:3000/login`
- Click `Sign in with Microsoft`
- Complete sign-in and confirm redirect to the dashboard

Behavior notes:
- Existing local user is matched by email
- If user does not exist, an account is auto-created as non-admin
- New SSO users receive `Viewer` role when present

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
