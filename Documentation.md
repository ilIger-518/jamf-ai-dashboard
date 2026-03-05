# Jamf AI Dashboard — Documentation

> **Version:** 0.1.0 · **Stack:** FastAPI 0.115 · Next.js 16 · PostgreSQL 16 · Redis 7 · ChromaDB · Ollama

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Getting Started](#4-getting-started)
   - 4.1 [Docker Compose (Recommended)](#41-docker-compose-recommended)
   - 4.2 [Local Development](#42-local-development)
5. [Environment Variables](#5-environment-variables)
6. [Backend](#6-backend)
   - 6.1 [Project Structure](#61-project-structure)
   - 6.2 [Configuration](#62-configuration)
   - 6.3 [Database & Migrations](#63-database--migrations)
   - 6.4 [Authentication & Authorization](#64-authentication--authorization)
   - 6.5 [API Reference](#65-api-reference)
   - 6.6 [Caching (Redis)](#66-caching-redis)
   - 6.7 [Background Sync](#67-background-sync)
7. [Frontend](#7-frontend)
   - 7.1 [Project Structure](#71-project-structure)
   - 7.2 [Auth Flow](#72-auth-flow)
   - 7.3 [State Management](#73-state-management)
   - 7.4 [API Client](#74-api-client)
   - 7.5 [Routing](#75-routing)
8. [AI Module](#8-ai-module)
   - 8.1 [Overview](#81-overview)
   - 8.2 [Read-Only Enforcement](#82-read-only-enforcement)
   - 8.3 [Human-in-the-Loop Approval Flow](#83-human-in-the-loop-approval-flow)
   - 8.4 [RAG Knowledge Base](#84-rag-knowledge-base)
   - 8.5 [Ollama Models](#85-ollama-models)
9. [Jamf Pro Integration](#9-jamf-pro-integration)
   - 9.1 [API Credentials Setup](#91-api-credentials-setup)
   - 9.2 [Multi-Server Support](#92-multi-server-support)
   - 9.3 [Sync Behavior](#93-sync-behavior)
10. [Data Models](#10-data-models)
11. [Security](#11-security)
12. [Deployment](#12-deployment)
13. [Testing](#13-testing)
14. [Troubleshooting](#14-troubleshooting)
15. [Contributing](#15-contributing)

---

## 1. Project Overview

Jamf AI Dashboard is a **self-hosted** web application that gives Mac admins a single pane of glass over one or more Jamf Pro servers. It combines real-time device/policy/compliance data with an AI assistant that is powered entirely by a **local LLM** — no data ever leaves your network.

**Key capabilities:**

| Area | What it does |
|------|-------------|
| Device monitoring | Unified device list across all Jamf servers with OS version, last check-in, managed status, security badges |
| Compliance | Per-device FileVault, SIP, Gatekeeper, Firewall status; custom compliance checks |
| Policies & Smart Groups | Browse, search, and inspect all policies and group criteria |
| Patch management | Track patched vs. unpatched device counts per software title |
| AI assistant | Natural-language queries, policy/script generation, script security analysis — all on-premise |
| AI safety | AI is locked to read-only; any write/create/delete action requires explicit user approval with full command preview |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                           Browser                                │
│                Next.js 16 · React 19 · Tailwind 4                │
│     TanStack Query · TanStack Table · Recharts · Zustand         │
└─────────────────────────┬────────────────────────────────────────┘
                          │  HTTP / SSE (JSON)
                          │  NEXT_PUBLIC_API_URL
┌─────────────────────────▼────────────────────────────────────────┐
│              FastAPI 0.115  (Python 3.12 · uvicorn)              │
│                                                                  │
│  /api/v1/auth      →  JWT auth + refresh tokens                  │
│  /api/v1/health    →  liveness + DB + Redis probes               │
│  /api/v1/servers   →  Jamf server CRUD + manual sync trigger     │
│  /api/v1/devices   →  device list, detail, apps, policies        │
│  /api/v1/policies  →  policy list + detail                       │
│  /api/v1/…         →  smart-groups, patches, compliance          │
│  /api/v1/ai/…      →  chat, sessions, pending-actions, audit     │
│  /metrics          →  Prometheus metrics                         │
│                                                                  │
│  APScheduler → background Jamf sync (every 15 min, configurable) │
└───────┬──────────┬──────────────┬───────────────────────────────┘
        │          │              │
   PostgreSQL    Redis        ChromaDB
   (SQLAlchemy/  (token        (vector store
    Alembic)     store +       for RAG)
                 cache)            │
                               Ollama
                           (local LLM +
                            embeddings)
        │
  Jamf Pro API(s)
  (Classic API + Jamf Pro API v1/v2)
  (one or many on-premise / cloud servers)
```

**Service ports (Docker Compose defaults):**

| Service | Port |
|---------|------|
| Frontend (Next.js) | `3000` |
| Backend (FastAPI) | `8000` |
| PostgreSQL | `5432` |
| Redis | `6379` |
| ChromaDB | `8001` |
| Ollama | `11434` |

---

## 3. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Engine | ≥ 24 | Required for all Docker paths |
| Docker Compose | ≥ 2.20 | Bundled with Docker Desktop |
| Python | 3.12 | Local backend dev only |
| Node.js | 20 LTS | Local frontend dev only |
| Ollama | ≥ 0.3 | Optional if using Docker Compose |
| Jamf Pro | ≥ 10.49 | Required for API access |
| macOS / Linux | — | Windows with WSL2 supported |

---

## 4. Getting Started

### 4.1 Docker Compose (Recommended)

This launches all six services (PostgreSQL, Redis, ChromaDB, Ollama, backend, frontend) with a single command.

**Step 1 — Clone and copy the env file:**

```bash
git clone https://github.com/your-org/jamf-ai-dashboard.git
cd jamf-ai-dashboard
cp .env.example .env
```

**Step 2 — Generate secrets and fill in `.env`:**

```bash
# Generate SECRET_KEY
echo "SECRET_KEY=$(openssl rand -hex 32)"

# Generate FERNET_KEY
python3 -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"
```

Paste the output into `.env`, and also set:
- `POSTGRES_PASSWORD` — a strong password
- `JAMF_SERVER_1_URL` / `JAMF_SERVER_1_CLIENT_ID` / `JAMF_SERVER_1_CLIENT_SECRET` — your first Jamf Pro server
- `JAMF_SERVER_1_AI_CLIENT_ID` / `JAMF_SERVER_1_AI_CLIENT_SECRET` — read-only credentials for the AI (see [Section 9.1](#91-api-credentials-setup))

**Step 3 — Start all services:**

```bash
docker compose up -d
```

**Step 4 — Pull LLM models into Ollama:**

```bash
# Chat model (choose one — smaller models use less RAM)
docker exec -it ollama ollama pull llama3.2:3b        # ~2 GB, fast
docker exec -it ollama ollama pull mistral:7b          # ~4 GB, better quality
docker exec -it ollama ollama pull deepseek-r1:7b      # ~4 GB, strong reasoning

# Embedding model (required for RAG)
docker exec -it ollama ollama pull nomic-embed-text
```

Set `OLLAMA_MODEL` in `.env` to match the chat model you pulled.

**Step 5 — Register the first admin user:**

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"YourStrongPassword1!"}' \
  | python3 -m json.tool
```

The first registered user is automatically promoted to admin.

**Step 6 — Open the dashboard:**

- Dashboard: [http://localhost:3000](http://localhost:3000)
- API docs (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)
- API docs (ReDoc): [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 4.2 Local Development

Use this path for active development. You still need PostgreSQL and Redis — the easiest way is to start just those services via Docker Compose.

**Start infrastructure only:**

```bash
docker compose up postgres redis chroma ollama -d
```

**Backend:**

```bash
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run database migrations
alembic upgrade head

# Start the dev server (auto-reload on file save)
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend

# Install dependencies (already done if you ran npm install previously)
npm install

# Start the dev server
npm run dev
# → http://localhost:3000
```

---

## 5. Environment Variables

All configuration is loaded from the `.env` file in the project root. See [`.env.example`](.env.example) for the complete reference with comments.

### Required variables

| Variable | Example | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://jamfdash:pw@localhost:5432/jamfdash` | Async PostgreSQL connection URL |
| `POSTGRES_PASSWORD` | `changeme` | PostgreSQL password (used by Docker Compose) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `SECRET_KEY` | *(64-char hex)* | Secret used to sign JWT tokens. Generate with `openssl rand -hex 32` |
| `FERNET_KEY` | *(32-byte base64url)* | Fernet symmetric key for encrypting stored Jamf credentials. Generate with Python's `cryptography` library |
| `JAMF_SERVER_1_URL` | `https://yourco.jamfcloud.com` | Base URL of your first Jamf Pro server |
| `JAMF_SERVER_1_CLIENT_ID` | — | Jamf Pro API client ID (admin privileges) |
| `JAMF_SERVER_1_CLIENT_SECRET` | — | Jamf Pro API client secret |

### AI-specific variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JAMF_SERVER_1_AI_CLIENT_ID` | — | Read-only Jamf API client ID used exclusively by the AI module |
| `JAMF_SERVER_1_AI_CLIENT_SECRET` | — | Read-only Jamf API client secret |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama service URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Name of the pulled chat model |
| `EMBEDDING_MODEL_NAME` | `nomic-embed-text` | Ollama embedding model for RAG |
| `LLM_TEMPERATURE` | `0.2` | Temperature for LLM generation (0 = deterministic) |
| `LLM_CONTEXT_WINDOW` | `4096` | Max tokens in the LLM context window |
| `CHROMA_HOST` | `localhost` | ChromaDB hostname |
| `CHROMA_PORT` | `8001` | ChromaDB port |

### Operational variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_INTERVAL_MINUTES` | `15` | How often Jamf data is synced |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed frontend origins |
| `LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL accessible from the browser |

---

## 6. Backend

### 6.1 Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory (lifespan, CORS, Prometheus, exception handler)
│   ├── config.py            # pydantic-settings Settings class; all env vars loaded here
│   ├── database.py          # Async SQLAlchemy engine, AsyncSession, Base declarative class
│   ├── cache.py             # Redis singleton (lazy init, shared across requests)
│   ├── dependencies.py      # Shared FastAPI deps: get_current_user, require_admin, type aliases
│   ├── models/              # SQLAlchemy ORM models (one file per domain)
│   │   ├── user.py
│   │   ├── server.py        # JamfServer
│   │   ├── device.py        # Device, DeviceApplication, DevicePolicy
│   │   ├── policy.py
│   │   ├── smart_group.py
│   │   ├── patch.py         # PatchTitle
│   │   ├── compliance.py    # ComplianceResult, SecurityStatus
│   │   ├── ai.py            # ChatSession, ChatMessage, PendingAction, AiToolAuditLog
│   │   └── knowledge.py     # KnowledgeDocument
│   ├── schemas/             # Pydantic v2 request/response schemas
│   │   └── auth.py
│   ├── routers/             # FastAPI APIRouter per domain
│   │   ├── auth.py          # POST /auth/register, login, refresh, logout; GET /auth/me
│   │   └── health.py        # GET /health
│   ├── services/
│   │   ├── auth.py          # AuthService (hashing, JWT, Redis token store)
│   │   ├── jamf/            # Jamf API client (planned)
│   │   └── ai/              # LLM + RAG logic (planned)
│   ├── crud/                # Database CRUD helpers (planned)
│   └── utils/               # Utility functions (planned)
├── alembic/
│   ├── env.py               # Async Alembic environment
│   ├── script.py.mako       # Migration template
│   └── versions/            # Generated migration files
├── tests/
├── Dockerfile               # Multi-stage Python 3.12-slim image
├── entrypoint.sh            # Runs `alembic upgrade head` then starts uvicorn
├── requirements.txt
└── requirements-dev.txt
```

### 6.2 Configuration

All settings are loaded via `app/config.py` using `pydantic-settings`. The `Settings` class reads from environment variables (and `.env` via `python-dotenv`). Use the `get_settings()` function (cached with `@lru_cache`) to access config anywhere in the app:

```python
from app.config import get_settings

settings = get_settings()
print(settings.ollama_model)
```

### 6.3 Database & Migrations

The backend uses **SQLAlchemy 2.0 async** with `asyncpg` as the PostgreSQL driver.

**Running migrations manually:**

```bash
cd backend
source .venv/bin/activate

# Create a new migration after changing models
alembic revision --autogenerate -m "describe your change"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Show migration history
alembic history --verbose
```

Migrations run automatically at container startup via `entrypoint.sh`.

**Adding a new model:**

1. Create the model file in `backend/app/models/`
2. Import it in `backend/app/models/__init__.py` (so Alembic autodiscovery finds it)
3. Run `alembic revision --autogenerate -m "add MyModel"`
4. Review the generated migration in `alembic/versions/`
5. Run `alembic upgrade head`

### 6.4 Authentication & Authorization

Authentication uses **JWT Bearer tokens** with an `httpOnly` cookie refresh flow.

#### Token lifecycle

```
Client                          Server
  │                                │
  ├── POST /auth/login ──────────► │  Validates credentials
  │                                │  Creates access token (30 min)
  │                                │  Creates refresh token (7 days) → stored in Redis
  │ ◄── access_token (JSON body) ──┤
  │ ◄── refresh_token (httpOnly cookie, path=/api/v1/auth) ──┤
  │                                │
  ├── GET /devices (Bearer: access_token) ──► │  Validates JWT
  │                                │
  │  [access token expires]        │
  ├── POST /auth/refresh (cookie sent automatically) ──► │
  │ ◄── new access_token ──────────┤  Old refresh token invalidated, new one issued
  │                                │
  ├── POST /auth/logout ─────────► │  Deletes refresh token from Redis
```

#### FastAPI dependencies

| Dependency | Type alias | Effect |
|------------|-----------|--------|
| `get_current_user` | `CurrentUser` | Requires valid JWT; returns `User` object |
| `require_admin` | `AdminUser` | Same as above + requires `user.is_admin == True` |
| `get_db` | `DBSession` | Provides an async SQLAlchemy session with auto-commit/rollback |

**Usage in a router:**

```python
from app.dependencies import CurrentUser, DBSession

@router.get("/protected")
async def protected_route(user: CurrentUser, db: DBSession):
    ...
```

#### Password requirements

Passwords must be at least 8 characters and contain at least one uppercase letter, one lowercase letter, and one digit. Enforced by the `RegisterRequest` Pydantic validator.

### 6.5 API Reference

The full interactive API reference is available at `/docs` (Swagger UI) or `/redoc` when the backend is running.

#### Currently implemented endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness check — probes DB and Redis |
| `POST` | `/api/v1/auth/register` | None* | Register a new user |
| `POST` | `/api/v1/auth/login` | None | Obtain access + refresh tokens |
| `POST` | `/api/v1/auth/refresh` | Cookie | Rotate access token |
| `POST` | `/api/v1/auth/logout` | Bearer | Invalidate refresh token |
| `GET` | `/api/v1/auth/me` | Bearer | Get current user info |
| `GET` | `/metrics` | None | Prometheus metrics |

*The first `register` call creates an admin. Subsequent calls require admin authentication (planned).

#### Planned endpoints (see TODO.md)

- `GET/POST/PUT/DELETE /api/v1/servers` — Jamf server management
- `GET /api/v1/devices`, `GET /api/v1/devices/{id}` — device listing and detail
- `GET /api/v1/policies`, `GET /api/v1/smart-groups`, `GET /api/v1/patches`, `GET /api/v1/compliance`
- `POST /api/v1/ai/chat` — streaming AI chat (SSE)
- `GET/POST /api/v1/ai/sessions` — chat session management
- `POST /api/v1/ai/pending-actions/{id}/approve` — approve a pending AI write action
- `POST /api/v1/ai/pending-actions/{id}/reject` — reject a pending AI write action
- `GET /api/v1/ai/audit-log` — AI tool call audit log (admin only)
- `GET /api/v1/dashboard` — aggregated KPI data for the dashboard overview

### 6.6 Caching (Redis)

Redis is used for two purposes:

1. **Refresh token storage** — each token is stored as `refresh:{user_id}:{token_hash}` with a TTL matching the token's expiry. Logout deletes the key.
2. **API response cache** — Jamf OAuth tokens and frequently-read aggregated data (dashboard KPIs, device counts) are cached with configurable TTLs to reduce Jamf API load.

The Redis client is a lazy singleton in `app/cache.py`. Access it anywhere with:

```python
from app.cache import get_redis

redis = await get_redis()
await redis.set("key", "value", ex=300)
value = await redis.get("key")
```

### 6.7 Background Sync

APScheduler runs a sync job every `SYNC_INTERVAL_MINUTES` (default: 15) minutes. The job iterates over all active `JamfServer` records, calls the Jamf API client per server, and upserts data into PostgreSQL.

Sync state (running / idle / error) is tracked per server in Redis. A Server-Sent Events endpoint (`GET /api/v1/servers/{id}/sync/stream`) will stream progress updates to the frontend in real time.

---

## 7. Frontend

### 7.1 Project Structure

```
frontend/src/
├── app/
│   ├── (auth)/
│   │   └── login/page.tsx       # Login form — unauthenticated users land here
│   ├── (dashboard)/
│   │   ├── layout.tsx           # Auth guard + Sidebar + TopNav shell
│   │   ├── page.tsx             # Dashboard overview
│   │   ├── devices/page.tsx
│   │   ├── policies/page.tsx
│   │   ├── smart-groups/page.tsx
│   │   ├── patches/page.tsx
│   │   ├── compliance/page.tsx
│   │   ├── ai/page.tsx          # AI assistant chat interface
│   │   └── settings/page.tsx
│   ├── globals.css
│   ├── layout.tsx               # Root layout: Providers (QueryClient + Toaster)
│   └── page.tsx                 # Redirects to /login
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx          # Collapsible navigation sidebar
│   │   └── TopNav.tsx           # Top bar with user info + sign-out
│   ├── ai/                      # AI chat components (planned)
│   ├── dashboard/               # KPI cards, charts (planned)
│   ├── devices/                 # Device table and detail (planned)
│   ├── policies/                # Policy table (planned)
│   ├── shared/
│   │   └── Providers.tsx        # QueryClientProvider + Toaster + devtools
│   └── ui/                      # shadcn/ui generated components (planned)
├── hooks/
│   └── useRequireAuth.ts        # Auth guard hook (redirects to /login if unauthed)
├── lib/
│   ├── api.ts                   # Axios instance with auth interceptors
│   ├── queryClient.ts           # TanStack Query client configuration
│   └── utils.ts                 # cn() helper (clsx + tailwind-merge)
├── store/
│   ├── authStore.ts             # Zustand auth slice (token in memory)
│   └── uiStore.ts               # Zustand UI slice (sidebar, theme — persisted)
└── types/
    └── index.ts                 # Full TypeScript types for all API entities
```

### 7.2 Auth Flow

```
User visits any dashboard route
       │
       ▼
useRequireAuth() hook
       │
  accessToken?
  ┌────┴────┐
  No       Yes
  │         │
  ▼         ▼
redirect  user loaded?
/login    ┌───┴───┐
          No     Yes
          │       │
          ▼       ▼
       fetchMe()  render page
```

The access token is kept **in memory only** (Zustand store — never `localStorage`). This prevents XSS token theft. The refresh token is an `httpOnly` cookie set by the backend — JavaScript cannot read it.

On 401 responses, the Axios interceptor in `lib/api.ts` automatically calls `POST /api/v1/auth/refresh` (which sends the cookie), updates the access token in Zustand, and retries the original failed request transparently.

### 7.3 State Management

Two Zustand stores manage global client state:

**`authStore`** — in-memory, not persisted:

| Field / Action | Type | Description |
|---------------|------|-------------|
| `accessToken` | `string \| null` | Current JWT access token |
| `user` | `AuthUser \| null` | Logged-in user object |
| `isLoading` | `boolean` | True during login or fetchMe |
| `login(username, password)` | async action | Calls `/auth/login`, updates token + user |
| `logout()` | async action | Calls `/auth/logout`, clears state |
| `fetchMe()` | async action | Calls `/auth/me`, populates `user` |
| `setAccessToken(token)` | action | Used by the Axios refresh interceptor |

**`uiStore`** — persisted to `localStorage` as `jamf-dashboard-ui`:

| Field / Action | Type | Description |
|---------------|------|-------------|
| `sidebarCollapsed` | `boolean` | Sidebar expanded/collapsed state |
| `selectedServerId` | `string \| null` | Currently selected Jamf server filter |
| `theme` | `"light" \| "dark" \| "system"` | Color theme preference |
| `toggleSidebar()` | action | Toggle sidebar |
| `setSelectedServer(id)` | action | Change active server filter |
| `setTheme(theme)` | action | Change color theme |

### 7.4 API Client

`lib/api.ts` exports a pre-configured Axios instance:

```typescript
import { api } from "@/lib/api";

// GET request
const { data } = await api.get<Device[]>("/devices");

// POST request
const { data } = await api.post<TokenResponse>("/auth/login", { username, password });
```

**What it does automatically:**
- Sets `baseURL` to `NEXT_PUBLIC_API_URL/api/v1`
- Sends `withCredentials: true` so the refresh cookie is included
- Injects the `Authorization: Bearer <token>` header from `authStore`
- On 401: calls `/auth/refresh`, updates the token, retries the original request once
- On failed refresh: clears auth state and redirects to `/login`

The TanStack Query client (`lib/queryClient.ts`) wraps all GET requests and provides:
- 1-minute stale time (data is re-fetched in background after 1 minute)
- 5-minute garbage collection time
- Automatic retry (up to 2 times, skips 401 errors)
- Global `onError` mutation handler that shows a toast notification

### 7.5 Routing

The app uses **Next.js App Router** with two route groups:

| Group | Layout | Routes |
|-------|--------|--------|
| `(auth)` | Plain (no sidebar) | `/login` |
| `(dashboard)` | Sidebar + TopNav + auth guard | `/`, `/devices`, `/policies`, `/smart-groups`, `/patches`, `/compliance`, `/ai`, `/settings` |

Unauthenticated users hitting any dashboard route are immediately redirected to `/login` by `useRequireAuth()`.

---

## 8. AI Module

### 8.1 Overview

The AI assistant uses a local LLM served by **Ollama**, augmented by a **RAG (Retrieval-Augmented Generation)** pipeline backed by **ChromaDB**. All processing happens on-premise — no data is sent to external APIs.

The AI can:
- Answer questions about Jamf Pro best practices using the knowledge base
- Query live device/policy data from the internal database (read-only)
- Generate Jamf Pro policy XML/JSON from natural language
- Generate Extension Attribute scripts
- Analyze shell scripts for security issues and best practices
- Explain compliance failures and suggest remediations

The AI **cannot** autonomously:
- Create, modify, or delete devices, policies, groups, or scripts in Jamf Pro
- Execute any Jamf MDM command
- Access any data outside the dashboard's database and Jamf servers

### 8.2 Read-Only Enforcement

Every LangChain tool registered with the agent is annotated with a `ToolPermission` level:

| Permission | Description | Examples |
|-----------|-------------|---------|
| `READ` | Queries data; no side effects | `get_device_by_name`, `get_compliance_summary` |
| `WRITE` | Modifies data in Jamf Pro | *(future)* `send_mdm_command`, `update_policy` |

The `AgentExecutor` intercepts **all** tool calls:
- `READ` tools: executed immediately; the resolved API call is logged to `AiToolAuditLog` and a **Command Preview card** is shown in the chat UI
- `WRITE` tools: the agent is **halted before execution**; a `PendingAction` record is created in the database; an **Approval Card** is displayed in the chat UI requiring explicit user action

The AI Jamf credentials (`JAMF_SERVER_1_AI_CLIENT_ID/SECRET`) must be configured with a **read-only API role** in Jamf Pro. At startup, the backend probes a known write endpoint to verify the credentials cannot perform writes (expects HTTP 403).

### 8.3 Human-in-the-Loop Approval Flow

When the AI proposes a write action:

```
AI proposes write action
        │
        ▼
AgentExecutor intercepts
        │
        ▼
Creates PendingAction record
  - tool_name
  - parameters (JSONB)
  - human_readable_summary
  - status: "pending"
        │
        ▼
Frontend renders Approval Card
  ┌─────────────────────────────┐
  │  🔒 Approval Required       │
  │  Tool: send_mdm_command     │
  │  Device: MacBook-001        │
  │  Command: EnableBluetooth   │
  │                             │
  │  [Approve]     [Reject]     │
  └─────────────────────────────┘
        │
  ┌─────┴─────┐
Approve      Reject
  │              │
  ▼              ▼
POST           POST
/pending-actions/{id}/approve    /pending-actions/{id}/reject
  │              │
  ▼              ▼
Execute      Cancel action
deferred     (AI notified)
tool call
  │
  ▼
Stream result
back to chat
```

All actions (approved, rejected, and auto-READ calls) are recorded permanently in `AiToolAuditLog`.

### 8.4 RAG Knowledge Base

The knowledge base stores Jamf Pro documentation, best practice guides, custom runbooks, and any other documents you ingest. Documents are chunked, embedded via `nomic-embed-text`, and stored in ChromaDB.

**Ingesting documents (planned CLI):**

```bash
cd backend
python -m app.services.ai.ingest \
  --source path/to/docs/ \
  --type pdf        # or: markdown, txt, url
```

The RAG pipeline:
1. Receives the user query
2. Embeds the query using the embedding model
3. Retrieves the top-K relevant chunks from ChromaDB
4. Injects the chunks into the LLM prompt as context
5. Returns the response with source citations (displayed in the chat UI)

### 8.5 Ollama Models

Models must be pulled into the Ollama service before use:

```bash
# If using Docker Compose:
docker exec -it ollama ollama pull llama3.2:3b
docker exec -it ollama ollama pull nomic-embed-text

# List pulled models:
docker exec -it ollama ollama list
```

**Recommended model combinations:**

| Chat Model | RAM Required | Notes |
|-----------|-------------|-------|
| `llama3.2:3b` | ~4 GB | Best for low-resource environments |
| `mistral:7b` | ~6 GB | Good balance of speed and quality |
| `deepseek-r1:7b` | ~6 GB | Strong reasoning; good for script analysis |
| `llama3.1:8b` | ~6 GB | Strong general-purpose model |

The embedding model (`nomic-embed-text`) requires ~300 MB and is always needed for RAG.

---

## 9. Jamf Pro Integration

### 9.1 API Credentials Setup

The dashboard requires **two separate API clients** per Jamf Pro server:

#### 1. Admin client (for syncing data)

1. In Jamf Pro, go to **Settings → System → API Roles and Clients**
2. Create a new **API Role** with at minimum these privileges:
   - Read Computers, Read Mobile Devices
   - Read Policies, Read Computer Groups, Read Mobile Device Groups
   - Read Patch Management, Read Categories, Read Departments, Read Buildings, Read Sites
3. Create a new **API Client**, assign the role above, and note the Client ID and Secret

#### 2. Read-Only AI client

1. Create a second **API Role** with strictly read-only privileges (same list as above — no create/update/delete)
2. Create a second **API Client** assigned to this read-only role
3. Set these as `JAMF_SERVER_1_AI_CLIENT_ID` and `JAMF_SERVER_1_AI_CLIENT_SECRET` in `.env`

> **Why two clients?** The admin client is used for scheduled data sync. The AI client is a separate credential with provably limited scope, ensuring the AI assistant cannot perform writes even if the application code is compromised.

### 9.2 Multi-Server Support

Add additional servers by repeating the numbered blocks in `.env`:

```ini
JAMF_SERVER_2_URL=https://staging.jamfcloud.com
JAMF_SERVER_2_CLIENT_ID=...
JAMF_SERVER_2_CLIENT_SECRET=...
JAMF_SERVER_2_NAME=Staging
JAMF_SERVER_2_AI_CLIENT_ID=...
JAMF_SERVER_2_AI_CLIENT_SECRET=...
```

All data is tagged with a `server_id` foreign key. The dashboard's server selector in the top nav lets users filter all views to a specific server or see aggregated cross-server data.

### 9.3 Sync Behavior

| Phase | Frequency | Method |
|-------|-----------|--------|
| Full sync (initial) | On first server add | Fetches all computers, policies, groups, patches |
| Incremental sync | Every 15 min (configurable) | Uses `lastContactTime` filter to fetch only changed devices |
| Manual sync | On demand | Triggered via Settings page or `POST /api/v1/servers/{id}/sync` |

During sync, Jamf OAuth tokens are cached in Redis (keyed by server ID) and refreshed 60 seconds before expiry. Rate limit responses (HTTP 429) are handled with exponential backoff and jitter via `tenacity`.

---

## 10. Data Models

### Key entities and relationships

```
User (1) ──────────────────────────────── (N) ChatSession
                                                  │
                                                  ├── (N) ChatMessage
                                                  └── (N) PendingAction

JamfServer (1) ─────────────────────────── (N) Device
                                           (N) Policy
                                           (N) SmartGroup
                                           (N) PatchTitle

Device (1) ─────────────────────────────── (N) DeviceApplication
                                           (N) DevicePolicy  ── (N) Policy
                                           (N) ComplianceResult
                                           (1) SecurityStatus
```

### `PendingAction` status values

| Status | Meaning |
|--------|---------|
| `pending` | Waiting for user approval; displayed as Approval Card in chat |
| `approved` | User approved; backend executed the deferred tool call |
| `rejected` | User rejected; action cancelled; AI notified |

---

## 11. Security

### Authentication security

- Passwords hashed with **bcrypt** (passlib, 12 rounds)
- Access tokens are **short-lived JWTs** (30 min), signed with `HS256` and the `SECRET_KEY`
- Refresh tokens are **UUID v4 strings** stored in Redis with TTL; they are never stored in the database
- Refresh tokens are delivered as `httpOnly; SameSite=Lax; Secure` cookies — not accessible to JavaScript
- Jamf credentials are encrypted at rest with **Fernet symmetric encryption** using the `FERNET_KEY`

### AI security

- AI uses a dedicated, **read-only Jamf API client** with no write privileges
- The `AgentExecutor` enforces tool permissions at the framework level — it cannot be bypassed via prompt injection
- Every AI tool call is logged to `AiToolAuditLog` before execution (immutable audit trail)
- All proposed write actions create a `PendingAction` record requiring explicit user approval
- The system prompt instructs the model that it must not attempt to perform write operations and that all mutations require the `PendingAction` approval flow

### Network security

- CORS is configured to only allow the frontend origin (`CORS_ORIGINS`)
- All database connections use TLS in production (set `?ssl=require` in `DATABASE_URL`)
- The `.env` file is excluded from version control via `.gitignore`
- Docker Compose internal services (postgres, redis, chroma, ollama) are not exposed to the host network beyond their defined ports

### OWASP Top 10 mitigations

| Risk | Mitigation |
|------|-----------|
| Broken Access Control | `require_admin` dependency on all admin endpoints; `CurrentUser` dependency on all user endpoints |
| Cryptographic Failures | bcrypt for passwords; Fernet for credentials; HTTPS enforced in production |
| Injection | SQLAlchemy ORM parameterized queries (no raw SQL); Pydantic input validation on all endpoints |
| Insecure Design | AI read-only + human approval for writes; separate credentials per use case |
| Security Misconfiguration | httpOnly cookies; CORS whitelist; no debug mode in production |
| Identification & Auth Failures | Short-lived tokens; refresh token rotation; logout invalidates token in Redis |
| Software Integrity Failures | Pinned dependency versions in `requirements.txt` |
| SSRF | Jamf URL validated at server creation; no arbitrary URL fetch endpoints |

---

## 12. Deployment

### Production checklist

- [ ] Generate strong `SECRET_KEY` (`openssl rand -hex 32`) and `FERNET_KEY`
- [ ] Set `POSTGRES_PASSWORD` to a strong unique value
- [ ] Set `COOKIE_SECURE = True` in backend (already set to `True` in `auth.py`)
- [ ] Set `CORS_ORIGINS` to your production frontend URL only
- [ ] Set `LOG_LEVEL=WARNING` or `ERROR` in production
- [ ] Use a reverse proxy (nginx / Traefik / Caddy) with TLS termination in front of both services
- [ ] Enable PostgreSQL TLS: add `?ssl=require` to `DATABASE_URL`
- [ ] Set up database backups (e.g., `pg_dump` cron or managed backup service)
- [ ] Pull Ollama models before going live
- [ ] Restrict Docker host port exposures for internal services (postgres, redis, chroma, ollama) in production `docker-compose.prod.yml`

### Scaling

The backend is **stateless** (all session state lives in Redis and PostgreSQL). You can run multiple backend replicas behind a load balancer. Ensure all replicas share the same `SECRET_KEY` and `FERNET_KEY`.

Ollama is CPU/GPU-bound and typically runs as a single instance. For higher throughput, run Ollama on a machine with a dedicated GPU and point `OLLAMA_BASE_URL` to it.

---

## 13. Testing

### Backend

```bash
cd backend
source .venv/bin/activate

# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing --cov-fail-under=80

# Run a specific test file
pytest tests/test_auth.py -v

# Run only fast unit tests (exclude slow integration tests)
pytest -m "not integration"
```

Tests use `pytest-asyncio` for async test functions and `httpx.AsyncClient` as the test client for FastAPI endpoints.

### Frontend

```bash
cd frontend

# Unit tests (Vitest)
npm test

# Unit tests with coverage
npm run test:coverage

# E2E tests (Playwright)
npx playwright test

# E2E tests with UI mode
npx playwright test --ui
```

### CI

GitHub Actions runs the full pipeline on every push and pull request:

1. **Lint** — `ruff check` (Python), `eslint` (TypeScript)
2. **Format check** — `ruff format --check`, `prettier --check`
3. **Type check** — `mypy`, `tsc --noEmit`
4. **Unit tests** — `pytest`, `vitest`
5. **Build** — `docker build` (backend), `next build` (frontend)

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for the full workflow definition.

---

## 14. Troubleshooting

### Backend won't start / `alembic upgrade head` fails

**Symptom:** Container exits immediately; logs show database connection error.

**Fix:** Ensure PostgreSQL is healthy before the backend starts. The `docker-compose.yml` uses `depends_on.condition: service_healthy` — if you see the backend starting too early, check that the `postgres` healthcheck is passing:

```bash
docker compose ps
docker compose logs postgres
```

### 401 on every request after login

**Symptom:** Login succeeds but all subsequent requests return 401.

**Fix:** Check that `NEXT_PUBLIC_API_URL` in the frontend matches the actual backend URL including protocol and port. Also verify `CORS_ORIGINS` includes the frontend URL.

### Ollama returns empty responses

**Symptom:** AI chat sends messages but receives empty or truncated responses.

**Fix:** Verify the model is pulled and `OLLAMA_MODEL` matches the pulled model name exactly:

```bash
docker exec -it ollama ollama list
```

If the model is missing, pull it: `docker exec -it ollama ollama pull llama3.2:3b`

### ChromaDB collection errors

**Symptom:** RAG queries fail with collection not found errors.

**Fix:** The collection is created on first document ingestion. Run the ingestion script on at least one document before using RAG features.

### Jamf sync fails with 401

**Symptom:** Sync logs show `401 Unauthorized` from Jamf Pro API.

**Fix:** Jamf Pro OAuth tokens expire. The backend caches tokens with expiry-aware refresh, but if the credentials themselves are wrong or the client is disabled in Jamf Pro, all token requests will fail. Verify credentials by testing them directly:

```bash
curl -s -X POST https://your-jamf-server/api/oauth/token \
  -d "client_id=YOUR_ID&client_secret=YOUR_SECRET&grant_type=client_credentials"
```

### Frontend build fails with TypeScript errors

```bash
cd frontend
npx tsc --noEmit
```

If the errors reference missing modules, run `npm install` first.

---

## 15. Contributing

### Development setup

Follow [Section 4.2 (Local Development)](#42-local-development) to get both services running locally.

### Code style

**Python:** `ruff` handles both linting and formatting. Run before committing:

```bash
cd backend
ruff check . --fix
ruff format .
mypy app/
```

**TypeScript/React:** Prettier + ESLint:

```bash
cd frontend
npm run lint
npx prettier --write src/
```

**Pre-commit hooks** enforce these automatically if you install them:

```bash
pip install pre-commit
pre-commit install
```

### Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable release branch; protected |
| `develop` | Active development; PRs merge here first |
| `feature/*` | Individual features or bugfixes |
| `hotfix/*` | Production bugfixes merged directly to `main` |

### Pull request checklist

- [ ] Tests added/updated for all changed behavior
- [ ] `ruff check` and `ruff format` pass with no warnings
- [ ] `mypy app/` passes with no errors
- [ ] `tsc --noEmit` passes
- [ ] `next build` succeeds
- [ ] `CHANGELOG.md` updated
- [ ] PR description explains the change and references any related issue

---

*Last updated: March 2026 — v0.1.0*
