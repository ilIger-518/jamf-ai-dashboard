# Jamf AI Dashboard Technical Documentation

Version: workspace snapshot (March 2026)

## 1. Purpose and Scope

Jamf AI Dashboard is a self-hosted operations platform for Jamf Pro environments.

It provides:
- centralized inventory and compliance visibility
- multi-server Jamf management
- AI-assisted workflows with approval controls
- knowledge scraping and local RAG search
- migration tooling between Jamf servers
- role-based access control and audit logging

This document is intended for:
- operators running the stack in Docker
- admins configuring auth, Jamf servers, AI, and scraping
- developers extending backend and frontend code

## 2. High-Level Architecture

### 2.1 Components

- Frontend: Next.js app running on port 3000
- Backend: FastAPI app running on port 8000
- PostgreSQL: primary relational data store
- Redis: refresh-token/session state and runtime cache/status
- ChromaDB: vector store for knowledge documents
- Ollama: local LLM and embedding runtime

### 2.2 Data and request flow

1. Browser calls frontend routes.
2. Frontend calls backend API under /api/v1.
3. Backend authenticates user and applies permission checks.
4. Backend reads/writes PostgreSQL and Redis as needed.
5. Jamf live data is fetched via Jamf API/OAuth client credentials.
6. AI endpoints use Ollama and ChromaDB-backed retrieval.

### 2.3 Runtime orchestration

- Docker Compose controls all services.
- Backend container runs Alembic migrations at startup before serving.
- APScheduler in backend runs periodic sync jobs.
- Healthchecks are configured for all core containers.

## 3. Repository Structure

Top-level important files:
- README.md: quickstart
- Documentation.md: this document
- TODO.md: product roadmap
- CHANGELOG.md: feature history
- docker-compose.yml: local/full stack runtime
- .env.example: configuration template

Backend layout:
- backend/app/main.py: app factory, middleware, router registration, lifecycle
- backend/app/config.py: environment-driven settings
- backend/app/database.py: SQLAlchemy async engine/session
- backend/app/cache.py: Redis connection helpers
- backend/app/models: SQLAlchemy models
- backend/app/schemas: Pydantic schemas
- backend/app/routers: API routes
- backend/app/services: business logic (auth, Jamf sync, scrape, vector store)
- backend/alembic: database migrations

Frontend layout:
- frontend/src/app: App Router pages and route groups
- frontend/src/components: reusable UI components
- frontend/src/lib/api.ts: Axios client + auth refresh handling
- frontend/src/store/authStore.ts: auth state/session bootstrap
- frontend/src/store/uiStore.ts: UI-scoped state
- frontend/src/hooks/useRequireAuth.ts: route protection

## 4. Core Features and How They Work

### 4.1 Authentication and authorization

Implemented auth modes:
- local username/password login
- Microsoft SSO (OIDC, Entra ID) start/callback flow

Local auth behavior:
- login issues access token and refresh token
- refresh token is stored in an httpOnly cookie
- frontend bootstraps session by calling /auth/refresh on app start

Authorization behavior:
- role + permission checks in backend dependencies
- admins can manage users/roles/settings and server operations

Password management:
- user password changes are supported
- forgotten passwords currently require manual admin/database reset

### 4.2 Microsoft SSO flow (new)

Backend endpoints:
- GET /api/v1/auth/sso/microsoft/start
- GET /api/v1/auth/sso/microsoft/callback

Flow:
1. User clicks Sign in with Microsoft.
2. Backend generates state and redirects to Microsoft authorize endpoint.
3. Callback validates state and exchanges auth code for token.
4. Backend reads user profile via Microsoft Graph OIDC userinfo.
5. Existing local user by email is reused; missing user is auto-created.
6. Refresh cookie is issued; frontend callback initializes session.

Current role assignment behavior:
- newly auto-created SSO users are non-admin
- Viewer role is assigned if that role exists
- Entra group-to-role mapping is planned (not yet implemented)

### 4.3 Jamf server management

Settings page supports:
- add/update/delete Jamf server configs
- provision flow for credentials and role setup
- manual per-server sync and sync-all trigger
- sync status readback

Server credentials:
- stored encrypted at rest using Fernet key

### 4.4 Fleet data pages

Operational pages:
- Devices
- Policies
- Smart Groups
- Patches
- Dashboard stats

Behavior:
- server selector supports all servers or single server scope
- filtering, pagination, and detail views
- live Jamf deep links where applicable

### 4.5 Scripts and Packages assets

Scripts page supports:
- list scripts from selected Jamf server
- click script name to load embedded detail view
- script code viewer with optional syntax highlighting and language selection
- script parameter display
- click script ID to open direct Jamf script URL
- back button to return to list-only mode

Packages page supports:
- live package listing from Jamf server

### 4.6 Knowledge base and scraping

Knowledge module supports:
- create scrape jobs from domain/URL
- monitor running/completed jobs
- runtime control: pause/resume/cancel
- CPU cap mode and percentage controls
- source listing and delete operations

Restart resilience:
- jobs left in running state during restart are marked failed at startup

### 4.7 AI assistant

AI module supports:
- user sessions and message history
- request/response chat endpoints
- streaming chat endpoint
- approval-gated actions for sensitive Jamf operations

## 5. API Catalog

All routes are mounted under /api/v1.

### 5.1 Health
- GET /health

### 5.2 Auth
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/logout
- GET /auth/me
- POST /auth/change-password
- GET /auth/sso/microsoft/start
- GET /auth/sso/microsoft/callback

### 5.3 Users and roles
- GET /users
- POST /users
- PATCH /users/{user_id}
- DELETE /users/{user_id}
- GET /users/roles
- POST /users/roles
- PATCH /users/roles/{role_id}
- DELETE /users/roles/{role_id}
- GET /users/permissions

### 5.4 Servers
- GET /servers
- POST /servers
- PATCH /servers/{server_id}
- DELETE /servers/{server_id}
- POST /servers/provision
- POST /servers/{server_id}/sync
- POST /servers/sync-all
- GET /servers/{server_id}/sync/status

### 5.5 Dashboard and inventory
- GET /dashboard/stats
- GET /devices
- GET /devices/{device_id}
- GET /policies
- GET /policies/{policy_id}
- GET /smart-groups
- GET /smart-groups/{group_id}
- GET /patches
- GET /patches/{patch_id}

### 5.6 Assets
- GET /assets/scripts
- GET /assets/scripts/{script_id}
- GET /assets/packages

### 5.7 Knowledge
- POST /knowledge/scrape
- GET /knowledge/scrape
- GET /knowledge/scrape/system
- GET /knowledge/scrape/{job_id}
- GET /knowledge/scrape/{job_id}/logs
- GET /knowledge/scrape/{job_id}/runtime
- PATCH /knowledge/scrape/{job_id}
- DELETE /knowledge/scrape/{job_id}
- GET /knowledge/sources
- DELETE /knowledge/sources/{source_id}

### 5.8 Migrator
- GET /migrator/objects
- POST /migrator/migrate

### 5.9 AI
- GET /ai/sessions
- POST /ai/sessions
- DELETE /ai/sessions/{session_id}
- GET /ai/sessions/{session_id}/messages
- POST /ai/chat
- POST /ai/chat/stream

### 5.10 Logs
- GET /logs

## 6. Configuration Reference

The main config source is .env, loaded by backend settings in backend/app/config.py and frontend env settings in docker-compose runtime.

### 6.1 Required baseline variables

Security and auth:
- SECRET_KEY: JWT signing secret (must be strong)
- JWT_ALGORITHM: default HS256
- ACCESS_TOKEN_EXPIRE_MINUTES
- REFRESH_TOKEN_EXPIRE_DAYS
- FERNET_KEY: encryption key for Jamf credentials

Data and cache:
- DATABASE_URL
- REDIS_URL

AI and retrieval:
- OLLAMA_BASE_URL
- OLLAMA_MODEL
- EMBEDDING_MODEL_NAME
- CHROMA_HOST
- CHROMA_PORT

Sync and API:
- SYNC_INTERVAL_MINUTES
- CORS_ORIGINS
- LOG_LEVEL

Frontend:
- NEXT_PUBLIC_API_URL

### 6.2 Microsoft SSO variables

- MICROSOFT_SSO_ENABLED
- MICROSOFT_TENANT_ID
- MICROSOFT_CLIENT_ID
- MICROSOFT_CLIENT_SECRET
- MICROSOFT_REDIRECT_URI
- FRONTEND_BASE_URL

Configuration notes:
- set MICROSOFT_SSO_ENABLED=true to enable SSO button flow
- callback URL must match Entra app registration exactly
- FRONTEND_BASE_URL is used for post-login redirect target

### 6.3 Cookie and security variables

- COOKIE_SECURE is controlled by cookie_secure setting
- use secure cookies in HTTPS deployments
- keep SECRET_KEY and FERNET_KEY private and rotated by policy

## 7. Setup and Deployment Procedures

### 7.1 Fresh local setup

1. Copy env template:

```bash
cp .env.example .env
```

2. Edit .env values, especially:
- secrets
- Jamf credentials
- Microsoft SSO vars if enabled

3. Start stack:

```bash
docker compose up -d
```

4. Verify services:

```bash
docker compose ps
```

5. Open:
- frontend: http://localhost:3000
- backend docs: http://localhost:8000/docs

### 7.2 Rebuild and redeploy app services

```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

### 7.3 Migrations and schema changes

Backend startup executes:

```bash
alembic upgrade head
```

Manual migration apply:

```bash
docker compose exec -T backend alembic upgrade head
```

Check current revision:

```bash
docker compose exec -T backend alembic current
```

### 7.4 Production hardening checklist

- set strong SECRET_KEY and FERNET_KEY
- enforce HTTPS and secure cookies
- limit CORS origins to known domains
- rotate Jamf API secrets on schedule
- monitor container health and logs
- backup PostgreSQL and Chroma data volumes

## 8. Day-2 Operations

### 8.1 Routine checks

- container health statuses
- backend logs for sync or auth errors
- knowledge scrape queue and failed jobs
- database growth and index performance
- Redis memory and key health

### 8.2 Useful commands

Stack status:

```bash
docker compose ps
```

Backend logs:

```bash
docker compose logs -f backend
```

Frontend logs:

```bash
docker compose logs -f frontend
```

Database shell:

```bash
docker exec -it jamf-ai-dashboard-postgres-1 psql -U jamfdash -d jamfdash
```

## 9. Troubleshooting Guide

### 9.1 Login fails for local user

Symptoms:
- invalid username/password
- redirect loops to login

Checks:
1. verify backend health endpoint
2. verify refresh cookie path and domain behavior
3. inspect browser network calls for /auth/login and /auth/refresh
4. check user is active in users table

Recovery:
- perform manual password reset if needed
- clear stale cookies and retry

### 9.2 Microsoft SSO does not work

Symptoms:
- redirect error from Microsoft
- callback returns sso_error
- session not initialized after callback

Checks:
1. confirm MICROSOFT_SSO_ENABLED=true
2. confirm client ID/secret/tenant are correct
3. confirm MICROSOFT_REDIRECT_URI exact match in Entra app
4. backend logs for token exchange or userinfo failures
5. ensure frontend and backend URLs match configured origins

Recovery:
- fix env values and restart backend/frontend
- retest with a fresh browser session

### 9.3 Jamf sync fails

Symptoms:
- sync status stuck error
- device/policy pages stale

Checks:
1. validate server credentials in Settings
2. verify Jamf OAuth endpoint accessibility
3. inspect backend logs around sync service
4. verify database connectivity and write permissions

Recovery:
- update server credentials
- run manual sync endpoint
- restart backend if scheduler state is corrupted

### 9.4 Scripts page freezes or stretches layout

Symptoms:
- lag opening script detail
- horizontal overflow or stretched page

Checks:
1. ensure latest frontend build is deployed
2. use Back to all scripts to return list mode
3. disable code highlighting for very large scripts

Recovery:
- rebuild frontend container
- hard refresh browser cache

### 9.5 Knowledge scraping issues

Symptoms:
- jobs stuck running
- no new sources indexed

Checks:
1. verify scraper connectivity to target domain
2. inspect /knowledge/scrape/{job_id}/logs
3. check Chroma and Ollama health
4. check CPU cap is not overly restrictive

Recovery:
- pause/resume or cancel/recreate job
- restart backend to recover interrupted states

### 9.6 Migration failures

Symptoms:
- object migration returns dependency or validation errors

Checks:
1. ensure target Jamf has required dependencies
2. inspect returned migration error details
3. test object fetch via /migrator/objects first

Recovery:
- migrate prerequisite objects first
- retry migration in smaller batches

### 9.7 Backend startup failures

Symptoms:
- backend container unhealthy or restarting

Checks:
1. run docker compose logs backend
2. verify env vars and DB credentials
3. verify Alembic can reach DB

Recovery:
- fix env/config errors
- apply or repair migrations
- restart backend

## 10. Security and Compliance Notes

- Jamf credentials are encrypted at rest with Fernet.
- Refresh tokens are server-controlled and stored in Redis-backed flow.
- Role and permission checks gate sensitive operations.
- Audit logging captures auth and dashboard/server actions.
- For strict environments, isolate services on private networks and enforce TLS.

## 11. Extending the Codebase

### 11.1 Add a new backend feature

1. add/adjust model in backend/app/models
2. add schema in backend/app/schemas
3. add logic in backend/app/services
4. add route in backend/app/routers
5. include route in app/main.py if new router module
6. create Alembic migration for schema changes
7. add tests in backend/tests

### 11.2 Add a new frontend page

1. add route under frontend/src/app/(dashboard)
2. call backend via frontend/src/lib/api.ts
3. manage cache with React Query
4. enforce auth via existing layout/hook patterns
5. add nav entry in sidebar if needed

## 12. Testing and Validation

Backend quick checks:

```bash
cd backend
python3 -m compileall app
```

Frontend build check:

```bash
cd frontend
npm run build
```

Compose-level validation:

```bash
docker compose build backend frontend
docker compose up -d backend frontend
docker compose ps
```

## 13. Known Gaps and Planned Work

- Entra group-to-local-role mapping for SSO users is planned.
- Auto-updater service (GitHub check + pull + rebuild + restart) is planned.
- Expanded automated integration test coverage is still in progress.

## 14. Reference Links

- API docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health endpoint: http://localhost:8000/api/v1/health
- Metrics endpoint: http://localhost:8000/metrics

---

If this documentation and runtime behavior diverge, treat the backend and frontend source code as authoritative, then update this file in the same change set.
