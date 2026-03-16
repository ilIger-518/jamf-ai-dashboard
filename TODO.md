# Jamf AI Dashboard — Project TODO

> Self-hosted web dashboard for monitoring and managing devices across one or more Jamf Pro servers, with an integrated AI assistant powered by a local LLM and a custom RAG knowledge base.
>
> **Current state:** Multi-page FastAPI + Next.js dashboard with Jamf sync, RBAC (users/roles), AI chat sessions, streaming AI responses, and approval-gated policy/group/script creation previews.

---

## Table of Contents

1. [Setup & Project Infrastructure](#1-setup--project-infrastructure)
2. [Backend](#2-backend)
3. [Frontend](#3-frontend)
4. [Jamf Pro Integration](#4-jamf-pro-integration)
5. [AI Module](#5-ai-module)
6. [Vector Database / RAG Knowledge Base](#6-vector-database--rag-knowledge-base)
7. [Testing](#7-testing)
8. [Deployment](#8-deployment)
9. [Documentation](#9-documentation)

---

## 1. Setup & Project Infrastructure

### 1.1 Repository & Version Control
- [x] Add a root-level `README.md` with project overview, architecture diagram, and quick-start instructions
- [x] Refine `.gitignore` to cover Python (`__pycache__`, `.venv`, `*.pyc`), Node (`node_modules`, `.next`), secrets (`.env*`), vector DB data dirs, and model weights
- [x] Create a `CHANGELOG.md` file
- [ ] Set up branch protection rules (`main` requires PR + CI pass)
- [ ] Define a Git branching strategy (e.g., `main` / `develop` / feature branches)

### 1.2 Python Environment (Backend)
- [x] Create `backend/requirements.txt` (or `pyproject.toml`) with pinned versions:
  - `fastapi>=0.115`
  - `uvicorn[standard]>=0.30`
  - `httpx>=0.27` (async Jamf API calls)
  - `pydantic>=2.7`
  - `pydantic-settings>=2.3` (env-based config)
  - `python-dotenv>=1.0`
  - `sqlalchemy>=2.0` + `alembic>=1.13` (database ORM and migrations)
  - `asyncpg>=0.29` (PostgreSQL async driver)
  - `redis>=5.0` (caching layer)
  - `apscheduler>=3.10` (background sync jobs)
  - `python-jose[cryptography]>=3.3` (JWT auth)
  - `passlib[bcrypt]>=1.7` (password hashing)
  - `langchain>=0.3` + `langchain-community>=0.3`
  - `llama-cpp-python>=0.2` (local LLM inference)
  - `chromadb>=0.5` (vector store)
  - `sentence-transformers>=3.0` (embeddings)
  - `unstructured>=0.15` + `pypdf>=4.0` (document ingestion)
  - `tenacity>=8.3` (retry logic)
  - `structlog>=24.0` (structured logging)
  - `prometheus-fastapi-instrumentator>=7.0` (metrics)
- [ ] Create and activate a Python virtual environment (`python -m venv .venv`)
- [ ] Install all backend dependencies (`pip install -r backend/requirements.txt`)
- [x] Create `backend/requirements-dev.txt`:
  - `pytest>=8`
  - `pytest-asyncio>=0.23`
  - `httpx` (for `TestClient`)
  - `factory-boy>=3.3`
  - `ruff>=0.4` (linter/formatter)
  - `mypy>=1.10`
  - `pre-commit>=3.7`

### 1.3 Node / Frontend Environment
- [x] Install additional frontend dependencies:
  - `@tanstack/react-query` (server-state management)
  - `@tanstack/react-table` (data tables)
  - `recharts` or `chart.js` + `react-chartjs-2` (charts)
  - `zustand` (global client state)
  - `axios` or native `fetch` wrapper
  - `@radix-ui/react-*` primitives (accessible UI atoms)
  - `lucide-react` (icon set)
  - `shadcn/ui` (component library on top of Radix + Tailwind)
  - `date-fns` (date formatting)
  - `react-hot-toast` or `sonner` (toast notifications)
  - `react-markdown` + `remark-gfm` (AI chat message rendering)
  - `highlight.js` or `prism-react-renderer` (code syntax highlighting in AI output)
  - `next-auth` (authentication)
  - `zod` (schema validation for forms/API)
  - `react-hook-form` (form management)
- [x] Install dev dependencies: `@testing-library/react`, `@testing-library/user-event`, `vitest`, `@playwright/test`, `msw`
- [ ] Initialize `shadcn/ui` (`npx shadcn-ui@latest init`)

### 1.4 Database Infrastructure
- [ ] Choose and provision a PostgreSQL instance (local Docker or managed service)
- [x] Create a `docker-compose.yml` at the project root with services:
  - `postgres` (v16, with volume mount)
  - `redis` (v7, for caching and session storage)
  - `backend` (FastAPI container)
  - `frontend` (Next.js container)
  - `chroma` (ChromaDB vector store container)
  - `ollama` (local LLM runtime container with GPU passthrough if available)
- [x] Define environment variable templates in `.env.example`:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `SECRET_KEY` / `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `JAMF_SERVER_1_URL` / `JAMF_SERVER_1_CLIENT_ID` / `JAMF_SERVER_1_CLIENT_SECRET`
  - `CHROMA_HOST` / `CHROMA_PORT`
  - `OLLAMA_BASE_URL` / `OLLAMA_MODEL`
  - `EMBEDDING_MODEL_NAME`
- [ ] Copy `.env.example` to `.env` and populate with local values (add `.env` to `.gitignore`)

### 1.5 Tooling & Code Quality
- [x] Configure `ruff` for linting + formatting in `pyproject.toml` or `ruff.toml`
- [x] Configure `mypy` with `strict` mode in `mypy.ini`
- [x] Set up `pre-commit` hooks (ruff, mypy, prettier, ESLint, trailing-whitespace)
- [x] Configure Prettier for frontend (`.prettierrc`)
- [ ] Configure ESLint rules in `eslint.config.mjs` (already exists — review and expand)
- [x] Set up GitHub Actions CI workflow (`.github/workflows/ci.yml`): lint → unit tests → build

---

## 2. Backend

### 2.1 Project Structure
- [x] Reorganize `backend/` into a proper package layout:
  ```
  backend/
  ├── app/
  │   ├── __init__.py
  │   ├── main.py              # FastAPI app factory
  │   ├── config.py            # Settings via pydantic-settings
  │   ├── dependencies.py      # Shared FastAPI dependencies
  │   ├── database.py          # SQLAlchemy async engine + session factory
  │   ├── cache.py             # Redis client singleton
  │   ├── routers/
  │   │   ├── auth.py
  │   │   ├── servers.py       # Jamf server CRUD
  │   │   ├── devices.py
  │   │   ├── policies.py
  │   │   ├── smart_groups.py
  │   │   ├── patches.py
  │   │   ├── compliance.py
  │   │   ├── ai.py            # AI assistant endpoints
  │   │   └── health.py
  │   ├── models/              # SQLAlchemy ORM models
  │   ├── schemas/             # Pydantic request/response schemas
  │   ├── crud/                # Database CRUD operations
  │   ├── services/            # Business logic layer
  │   │   ├── jamf/            # Jamf API clients
  │   │   ├── ai/              # LLM + RAG logic
  │   │   └── sync.py          # Background sync orchestrator
  │   └── utils/
  ├── alembic/                 # Database migrations
  ├── tests/
  ├── requirements.txt
  └── Dockerfile
  ```
- [x] Move existing `main.py` into `app/main.py` and refactor as app factory with `lifespan`
- [x] Create `app/config.py` using `pydantic_settings.BaseSettings`, loading from `.env`

### 2.2 Database Models (SQLAlchemy)
- [x] `JamfServer` — id, name, url, client_id, client_secret (encrypted), is_active, last_sync
- [x] `Device` — id, jamf_id, server_id (FK), udid, name, serial_number, model, os_version, os_build, last_contact, last_enrollment, is_managed, is_supervised, asset_tag, username, department, building, site
- [x] `DeviceApplication` — id, device_id (FK), name, version, bundle_id, short_version
- [x] `DevicePolicy` — id, device_id (FK), policy_id (FK), last_executed, result
- [x] `Policy` — id, jamf_id, server_id (FK), name, enabled, category, trigger, scope_description, payload_description
- [x] `SmartGroup` — id, jamf_id, server_id (FK), name, criteria, member_count, last_refreshed
- [x] `PatchTitle` — id, jamf_id, server_id (FK), software_title, current_version, latest_version, patched_count, unpatched_count
- [x] `ComplianceResult` — id, device_id (FK), check_name, status (pass/fail/warn), checked_at, details
- [x] `SecurityStatus` — id, device_id (FK), firewall_enabled, sip_enabled, gatekeeper_enabled, filevault_enabled, remote_login_enabled, disk_encryption_status
- [x] `User` — id, username, email, hashed_password, is_admin, is_active, created_at
- [x] `ChatSession` — id, user_id (FK), title, created_at, updated_at
- [x] `ChatMessage` — id, session_id (FK), role (user/assistant), content, sources (JSONB), created_at
- [x] `KnowledgeDocument` — id, title, source, file_path, file_hash, ingested_at, chunk_count
- [x] Run `alembic init alembic` and configure `alembic.ini` + `env.py`
- [x] Create initial migration with `alembic revision --autogenerate -m "initial"`

### 2.3 Authentication & Authorization
- [x] Implement `/api/auth/register` endpoint (admin-only, first user bootstrapping)
- [x] Implement `/api/auth/login` endpoint (returns JWT access token + refresh token)
- [x] Implement `/api/auth/refresh` endpoint (rotates access token using refresh token)
- [x] Implement `/api/auth/logout` endpoint (invalidates refresh token in Redis)
- [x] Create `get_current_user` FastAPI dependency (validates JWT Bearer token)
- [x] Create `require_admin` FastAPI dependency
- [x] Store refresh tokens in Redis with TTL
- [x] Hash passwords with bcrypt via passlib
- [ ] Add Microsoft SSO (Microsoft Entra ID / Azure AD) login with OIDC for web users
- [ ] Add Microsoft SSO role mapping (Entra groups/claims -> local roles/permissions)
- [ ] Add SSO fallback policy (local admin account + emergency access runbook)

### 2.4 Jamf Server Management Endpoints
- [x] `GET /api/servers` — list all configured Jamf servers
- [x] `POST /api/servers` — add a new Jamf server (validate connectivity + credentials)
- [ ] `GET /api/servers/{id}` — get server details + sync status
- [x] `PUT /api/servers/{id}` — update server config
- [x] `DELETE /api/servers/{id}` — remove server and all synced data
- [x] `POST /api/servers/{id}/sync` — trigger manual full sync
- [x] `GET /api/servers/{id}/sync/status` — get current sync progress/status

### 2.5 Device Endpoints
- [x] `GET /api/devices` — paginated list with filters: server, OS version, compliance status, last contact, smart group, search by name/serial/username
- [x] `GET /api/devices/{id}` — full device detail (hardware, OS, apps, policies, security, compliance)
- [ ] `GET /api/devices/{id}/applications` — list installed apps
- [ ] `GET /api/devices/{id}/policies` — policy execution history
- [ ] `GET /api/devices/{id}/security` — security posture detail
- [ ] `GET /api/devices/summary` — aggregate counts for dashboard cards (total, managed, unmanaged, non-compliant, by OS version)
- [ ] `GET /api/devices/os-distribution` — OS version breakdown for charts

### 2.6 Policy Endpoints
- [x] `GET /api/policies` — paginated list with filters: server, category, enabled status
- [x] `GET /api/policies/{id}` — policy detail
- [ ] `GET /api/policies/{id}/devices` — devices where this policy has run

### 2.7 Smart Group Endpoints
- [x] `GET /api/smart-groups` — list all smart groups with member counts
- [x] `GET /api/smart-groups/{id}` — smart group detail + criteria
- [ ] `GET /api/smart-groups/{id}/members` — paginated device member list

### 2.8 Patch Management Endpoints
- [x] `GET /api/patches` — list all patch titles with patched/unpatched counts
- [x] `GET /api/patches/{id}` — patch title detail with version history
- [ ] `GET /api/patches/{id}/devices` — devices needing this patch

### 2.9 Compliance Endpoints
- [ ] `GET /api/compliance/summary` — overall compliance pass/fail/warn breakdown
- [ ] `GET /api/compliance/by-check` — compliance grouped by check name
- [ ] `GET /api/compliance/devices` — devices with compliance failures

### 2.10 Dashboard Summary Endpoint
- [x] `GET /api/dashboard` — single endpoint returning all top-level KPI data needed to populate dashboard cards and charts (with Redis caching, 5-minute TTL)

### 2.11 Background Sync Service
- [x] Create `SyncService` that iterates over all active Jamf servers and calls the Jamf API client
- [x] Implement incremental sync using `lastContactTime` filters where possible
- [x] Schedule sync job with APScheduler every 15 minutes (configurable via env)
- [x] Track sync state (running / idle / error) per server in Redis
- [ ] Emit sync progress events via Server-Sent Events (SSE) endpoint: `GET /api/servers/{id}/sync/stream`
- [ ] Log sync durations, record counts, and errors with structlog

### 2.12 Caching Layer
- [ ] Cache Jamf API OAuth tokens per server in Redis (respect expiry)
- [ ] Cache frequently-read aggregated data (dashboard summary, device counts) with configurable TTL
- [ ] Implement cache invalidation on successful sync completion

### 2.13 API General
- [ ] Add CORS middleware (allow frontend origin)
- [ ] Add global exception handler returning RFC 7807 problem+json responses
- [ ] Add request ID middleware (inject `X-Request-ID` header)
- [ ] Add structured access logging middleware
- [ ] Add Prometheus metrics endpoint (`/metrics`) via `prometheus-fastapi-instrumentator`
- [ ] Add rate limiting middleware (token bucket per user, via Redis)
- [ ] Version all endpoints under `/api/v1/` prefix
- [ ] Generate OpenAPI schema — review and add examples to all schemas

---

## 3. Frontend

### 3.1 Project Structure
- [x] Reorganize `frontend/src/` into a scalable layout:
  ```
  src/
  ├── app/
  │   ├── (auth)/
  │   │   └── login/page.tsx
  │   ├── (dashboard)/
  │   │   ├── layout.tsx         # Sidebar + top nav shell
  │   │   ├── page.tsx           # Overview dashboard
  │   │   ├── devices/
  │   │   │   ├── page.tsx       # Device list
  │   │   │   └── [id]/page.tsx  # Device detail
  │   │   ├── policies/
  │   │   │   ├── page.tsx
  │   │   │   └── [id]/page.tsx
  │   │   ├── smart-groups/
  │   │   │   ├── page.tsx
  │   │   │   └── [id]/page.tsx
  │   │   ├── patches/page.tsx
  │   │   ├── compliance/page.tsx
  │   │   ├── ai/page.tsx        # AI assistant chat
  │   │   └── settings/
  │   │       ├── page.tsx       # Server management
  │   │       └── users/page.tsx
  │   ├── globals.css
  │   └── layout.tsx             # Root layout with providers
  ├── components/
  │   ├── ui/                    # shadcn/ui generated components
  │   ├── layout/
  │   │   ├── Sidebar.tsx
  │   │   ├── TopNav.tsx
  │   │   └── MobileSidebar.tsx
  │   ├── dashboard/
  │   │   ├── KpiCard.tsx
  │   │   ├── OsVersionChart.tsx
  │   │   ├── ComplianceDonut.tsx
  │   │   ├── PatchStatusBar.tsx
  │   │   └── RecentActivityFeed.tsx
  │   ├── devices/
  │   │   ├── DeviceTable.tsx
  │   │   ├── DeviceFilters.tsx
  │   │   ├── DeviceDetailPanel.tsx
  │   │   ├── SecurityStatusBadges.tsx
  │   │   └── AppListTable.tsx
  │   ├── policies/
  │   │   ├── PolicyTable.tsx
  │   │   └── PolicyDetailPanel.tsx
  │   ├── smart-groups/
  │   │   └── SmartGroupTable.tsx
  │   ├── patches/
  │   │   └── PatchTable.tsx
  │   ├── compliance/
  │   │   └── ComplianceTable.tsx
  │   ├── ai/
  │   │   ├── ChatWindow.tsx
  │   │   ├── ChatMessage.tsx
  │   │   ├── ChatInput.tsx
  │   │   ├── SourceCitation.tsx
  │   │   └── SessionList.tsx
  │   └── shared/
  │       ├── StatusBadge.tsx
  │       ├── ServerSelector.tsx
  │       ├── DataTable.tsx       # Generic TanStack Table wrapper
  │       ├── EmptyState.tsx
  │       ├── ErrorBoundary.tsx
  │       └── LoadingSpinner.tsx
  ├── hooks/
  │   ├── useDevices.ts
  │   ├── usePolicies.ts
  │   ├── useSmartGroups.ts
  │   ├── usePatches.ts
  │   ├── useCompliance.ts
  │   ├── useDashboard.ts
  │   ├── useAIChat.ts
  │   └── useAuth.ts
  ├── lib/
  │   ├── api.ts                 # Axios/fetch client with auth interceptors
  │   ├── queryClient.ts         # TanStack Query client config
  │   └── utils.ts               # cn(), formatters, etc.
  ├── store/
  │   ├── authStore.ts           # Zustand auth slice
  │   └── uiStore.ts             # Sidebar collapse, theme, selected server
  └── types/
      ├── device.ts
      ├── policy.ts
      ├── smartGroup.ts
      ├── patch.ts
      ├── compliance.ts
      └── ai.ts
  ```

### 3.2 Layout & Navigation
- [x] Build root `layout.tsx` with `QueryClientProvider`, `AuthProvider`, and theme provider
- [x] Build `Sidebar.tsx` with navigation links, server selector dropdown, and collapse toggle
- [x] Build `TopNav.tsx` with breadcrumbs, sync status indicator, notifications bell, and user menu
- [ ] Build `MobileSidebar.tsx` (slide-in sheet for mobile)
- [ ] Implement dark mode toggle with `next-themes`
- [x] Implement route-level auth guard (redirect to `/login` if unauthenticated)
- [ ] Add loading skeleton for dashboard shell

### 3.3 Authentication UI
- [x] Build login page (`/login`) with username/password form, `react-hook-form` + `zod` validation
- [x] Call `POST /api/auth/login`, store access token in memory (Zustand), refresh token in `httpOnly` cookie (set by backend)
- [x] Implement silent token refresh using `axios` interceptor (retry on 401 with refresh flow)
- [x] Build logout flow (call `/api/auth/logout`, clear state, redirect to `/login`)

### 3.4 Dashboard Overview Page
- [x] Build `KpiCard` displaying: Total Devices, Managed, Unmanaged, Non-Compliant, Pending Patches
- [x] Build `OsVersionChart` — horizontal bar or donut chart showing OS version distribution
- [ ] Build `ComplianceDonut` — pie chart of pass/fail/warn compliance statuses
- [x] Build `PatchStatusBar` — stacked bar showing patched vs unpatched per title (top 10)
- [ ] Build `RecentActivityFeed` — last N sync events and notable compliance changes
- [x] Add auto-refresh (poll `/api/dashboard` every 5 minutes)
- [x] Add manual "Refresh" button with last-updated timestamp

### 3.5 Device List Page
- [ ] Build `DeviceTable` using TanStack Table with virtualization for large datasets
- [ ] Implement columns: Name, Serial, Model, OS Version, Last Contact, Compliance Status, Security badges (FileVault, SIP, Firewall), Managed status
- [ ] Implement column sorting, multi-column filtering, global search
- [ ] Implement `DeviceFilters` sidebar/drawer: filter by Jamf server, OS version, smart group, department, compliance status, last contact range
- [ ] Implement row click → expand in-page detail panel or navigate to `/devices/[id]`
- [ ] Add CSV export of filtered/selected devices

### 3.6 Device Detail Page
- [ ] Header: device name, serial, managed badge, last contact time
- [ ] Hardware info card: model, architecture, RAM, storage, processor
- [ ] OS & security card: OS version, build, SIP, Gatekeeper, FileVault, Firewall icons with status colors
- [ ] Tabs: Overview / Applications / Policies / Groups / Compliance / Security
- [ ] Applications tab: searchable, sortable table of installed apps
- [ ] Policies tab: list of policies run on device with last execution date and result
- [ ] Groups tab: smart and static groups the device belongs to
- [ ] Compliance tab: table of each compliance check with pass/fail/warn and detail message
- [ ] Security tab: full security posture breakdown

### 3.7 Policies Page
- [ ] Table: Policy name, category, server, trigger, enabled status, device scope count
- [ ] Filter by server, category, enabled/disabled
- [ ] Policy detail panel: description, scope devices, payload details

### 3.8 Smart Groups Page
- [ ] Table: Group name, server, member count, last refreshed
- [ ] Smart group detail: criteria, member device list (paginated)

### 3.9 Patch Management Page
- [ ] Table: Software title, current version, latest version, patched count, unpatched count, patch %
- [ ] Color-coded patch status (green/amber/red based on % patched)
- [ ] Click-through to device list filtered to unpatched devices for that title

### 3.10 Compliance Page
- [ ] Overall compliance summary cards
- [ ] Compliance by check table: check name, total devices, pass/fail/warn counts, % pass
- [ ] Click-through to failing devices per check

### 3.11 Settings Page — Server Management
- [x] List of configured Jamf servers with status (connected/error), last sync time, device count
- [x] Add server form: Name, URL, Client ID, Client Secret (masked), test connection button
- [x] Edit/delete server actions
- [ ] Manual sync trigger button with real-time progress via SSE
- [ ] Display sync logs (last N sync events, errors)

### 3.12 Settings Page — User Management
- [x] List of dashboard users
- [x] Add/edit/delete user form (admin only)
- [x] Change own password form

### 3.13 API Client & State
- [x] Create `lib/api.ts` — Axios instance with `baseURL`, auth token injection, 401 refresh interceptor
- [x] Create `lib/queryClient.ts` — TanStack Query client with global error handling and stale times
- [ ] Create custom hooks (`useDevices`, `usePolicies`, etc.) wrapping `useQuery` / `useMutation`
- [x] Define full TypeScript types in `types/` matching backend Pydantic schemas

---

## 4. Jamf Pro Integration

### 4.1 Authentication
- [ ] Implement Jamf Pro OAuth 2.0 client credentials flow (`POST /api/oauth/token`)
- [ ] Store tokens per server in Redis with expiry-aware caching (refresh before expiry)
- [ ] Implement token refresh with retry logic using `tenacity` (exponential backoff)
- [ ] Support both Jamf Pro Cloud and on-premise instances
- [ ] Create a `JamfClient` async class (`httpx.AsyncClient`) wrapping all API calls

### 4.2 Classic API Endpoints (XML-based where needed)
- [ ] `GET /JSSResource/computers` — full computer list
- [ ] `GET /JSSResource/computers/id/{id}` — computer detail (hardware, OS, apps, groups, EA)
- [ ] `GET /JSSResource/policies` — policy list
- [ ] `GET /JSSResource/policies/id/{id}` — policy detail
- [ ] `GET /JSSResource/computergroups` — all computer groups
- [ ] `GET /JSSResource/computergroups/id/{id}` — group detail + membership

### 4.3 Jamf Pro API (v1/v2, JSON-based)
- [ ] `GET /api/v1/computers-preview` — lightweight computer inventory
- [ ] `GET /api/v1/computers/{id}/detail` — detailed inventory (hardware, storage, security, apps)
- [ ] `GET /api/v1/mdm/commands` — pending MDM commands per device
- [ ] `GET /api/v1/patch-software-titles` — patch management titles
- [ ] `GET /api/v1/patch-software-titles/{id}/versions` — version history
- [ ] `GET /api/v1/patch-reports/{id}` — patch compliance report
- [ ] `GET /api/v2/categories` — category list (for policy categorization)
- [ ] `GET /api/v1/sites` — site list
- [ ] `GET /api/v1/departments` — department list
- [ ] `GET /api/v1/buildings` — building list
- [ ] Handle pagination (`page`, `page-size`) consistently across all list endpoints
- [ ] Handle rate limiting (429 responses) with exponential backoff + jitter

### 4.4 Data Normalization
- [ ] Parse and normalize Classic API XML responses to Python dicts/Pydantic models
- [ ] Map Jamf data structures to internal database models
- [ ] Handle multiple Jamf servers — prefix all IDs with server ID to avoid collisions
- [ ] Normalize OS version strings (e.g., "14.3.1" vs "macOS 14.3.1") to semver-comparable format
- [ ] Normalize application version strings for patch comparison

### 4.5 Multi-Server Support
- [x] Store server credentials encrypted at rest (use `cryptography` Fernet symmetric encryption)
- [x] Isolate data per server — all queries filterable by `server_id`
- [ ] Aggregate cross-server data for global dashboard views
- [ ] Handle one server being unavailable without breaking the whole sync cycle
- [ ] Allow enabling/disabling individual servers without data deletion

### 4.6 Extension Attributes
- [ ] Fetch and store computer extension attribute values per device
- [ ] Display EAs in device detail view
- [ ] Allow filtering/searching by EA values

---

## 5. AI Module

### 5.1 LLM Backend Setup
- [ ] Install and configure Ollama locally (`docker pull ollama/ollama`)
- [ ] Pull desired chat model (e.g., `llama3.2:3b`, `mistral:7b`, `deepseek-r1:7b`) via Ollama
- [ ] Pull an embedding model (e.g., `nomic-embed-text`) via Ollama
- [ ] Create `app/services/ai/llm_client.py` — async Ollama client wrapping `langchain_ollama.ChatOllama`
- [ ] Support model switching via environment variable (`OLLAMA_MODEL`)
- [ ] Implement configurable context window size and temperature settings

### 5.2 AI Chat Endpoints
- [x] `POST /api/ai/chat` — standard chat endpoint (message + session_id) with persisted history
- [x] `POST /api/ai/chat/stream` — streaming chat endpoint (NDJSON stage/delta/final events)
- [x] `GET /api/ai/sessions` — list user's chat sessions
- [x] `POST /api/ai/sessions` — create new chat session
- [x] `GET /api/ai/sessions/{id}/messages` — get message history for session
- [x] `DELETE /api/ai/sessions/{id}` — delete a chat session
- [x] Persist chat history to PostgreSQL (`ChatSession` + `ChatMessage` tables)
- [ ] Include source citations in AI responses (document titles + chunk references from RAG)

### 5.3 Tool-Augmented AI (LangChain Tools / Function Calling)
- [ ] Create `JamfDataTool` — allows AI to query live device/policy data from the database (**read-only; all calls go through read-only DB/API credentials**):
  - `get_device_by_name(name)` — look up a specific device
  - `get_devices_by_filter(os_version, compliance_status, smart_group)` — filtered list
  - `get_policy_by_name(name)` — look up a policy
  - `get_smart_group_members(name)` — list devices in a smart group
  - `get_compliance_summary()` — overall compliance stats
  - `get_patch_summary()` — patched vs unpatched counts
- [ ] Create `PolicyGeneratorTool` — generates Jamf Pro policy XML/JSON from natural language description (**output only — never auto-submits to Jamf**)
- [ ] Create `ScriptAnalyzerTool` — analyzes a shell script or Jamf script for security issues, best practices, and intent
- [ ] Create `ExtensionAttributeGeneratorTool` — generates Jamf EA scripts from natural language requirements (**output only — never auto-submits to Jamf**)
- [ ] Set up LangChain `AgentExecutor` with tool routing and structured output parsing
- [ ] Tag every registered tool with a permission level: `READ` or `WRITE` — the agent executor must never invoke a `WRITE` tool without an approved `PendingAction` record in the database

### 5.6 AI Security — Read-Only Enforcement & Human-in-the-Loop Approval

> **Core principle:** The AI assistant may freely read data but must never autonomously mutate anything (create, update, or delete devices, policies, groups, scripts, etc.). Every proposed mutating action must be surfaced to the user as a visible, reviewable command and executed only after explicit approval.

#### Backend
- [ ] Define a `ToolPermission` enum: `READ` and `WRITE`; annotate every LangChain tool with its permission level
- [ ] Enforce at the `AgentExecutor` level: intercept any tool call tagged `WRITE` before execution and halt the agent, returning a `pending_approval` response instead of running the tool
- [x] Implement interim pending-approval flow in AI router: show command preview and require explicit `approve`/`cancel` before executing create actions (policy/group/script)
- [ ] Create a `PendingAction` database model — id, session_id (FK), user_id (FK), tool_name, parameters (JSONB), human_readable_summary, status (`pending` / `approved` / `rejected`), created_at, resolved_at
- [ ] `POST /api/ai/pending-actions/{id}/approve` — user approves; backend executes the deferred tool call and streams the result back
- [ ] `POST /api/ai/pending-actions/{id}/reject` — user rejects; action is cancelled and AI is notified to respond accordingly
- [ ] `GET /api/ai/pending-actions` — list all pending (and recently resolved) actions for the current user
- [ ] For every tool invocation (READ or WRITE), log the full resolved API call (method, endpoint/query, parameters) to a persistent `AiToolAuditLog` table before execution
- [ ] Expose `GET /api/ai/audit-log` (admin only) — paginated log of every tool call the AI has ever made, with user, session, timestamp, tool, parameters, and approval status
- [ ] Enforce read-only Jamf API credentials for AI tool calls: store a separate `jamf_readonly_client_id` / `jamf_readonly_client_secret` per server used exclusively by the AI service layer; these credentials must only have **Read** privileges in the Jamf Pro API Role
- [ ] Validate at startup that the AI Jamf credentials cannot perform write operations (probe a known write-only endpoint and assert 403)

#### Frontend
- [ ] In `ChatMessage.tsx`, when the AI calls any tool, always render a **"Command Preview" card** showing the tool name, all resolved parameters, and the human-readable summary before the result is shown — this applies to READ tools too so users can always see what was queried
- [x] For `WRITE` tool calls, render an **Approval Card** instead of the result: show the proposed command in full, with **Approve** and **Reject** buttons; disable both after one click
- [x] After approval or rejection, display the outcome inline in the chat thread
- [ ] Add a **Pending Approvals** badge on the AI nav item when there are unresolved actions
- [ ] Build a **Pending Actions panel** (slide-out drawer or dedicated page) listing all pending actions with approve/reject controls
- [ ] Build an **AI Audit Log** view under Settings (admin only): searchable, paginated table of all AI tool calls with tool name, parameters, user, timestamp, and approval status
- [ ] Add a visible **"AI is read-only"** indicator in the chat UI header to communicate the security model to users at a glance

---

### 5.4 Prompt Engineering
- [ ] Write a system prompt defining the AI's persona: Jamf expert, professional, concise
- [ ] Include context about connected Jamf servers (names, device counts) in the system prompt
- [ ] Implement conversation history injection (last N turns) for contextual responses
- [ ] Write specialized prompt templates for:
  - Policy generation (structured JSON/XML output)
  - Script analysis (security, logic, portability review)
  - EA generation (output must be valid bash/python/swift)
  - General Jamf Q&A (RAG-augmented)
- [ ] Implement prompt length management (truncate history if context window exceeded)
- [ ] Add guardrails — detect and reject requests to generate destructive or malicious scripts
- [ ] Instruct the model in the system prompt that it must never attempt to perform write operations autonomously; all mutations require user approval via the `PendingAction` flow

### 5.5 AI Frontend — Chat Interface
- [ ] Build `ChatWindow.tsx` — full-screen or panel chat UI
- [ ] Build `ChatMessage.tsx` — renders user and assistant bubbles with Markdown support and code highlighting
- [ ] Build `ChatInput.tsx` — textarea with send button, Enter to send, Shift+Enter for newline
- [ ] Implement streaming response rendering (consume SSE token stream, append to message in real time)
- [ ] Build `SourceCitation.tsx` — collapsible source documents used in the answer
- [ ] Build `SessionList.tsx` — sidebar list of past conversations, ability to rename/delete
- [ ] Add suggested starter prompts on new session (e.g., "Show me all non-compliant devices", "Generate a policy to install Homebrew", "Analyze this script…")
- [ ] Add file drag-and-drop or paste to send scripts/config files for analysis
- [ ] Add "Copy code" button on code blocks in AI responses

---

## 6. Vector Database / RAG Knowledge Base

### 6.1 ChromaDB Setup
- [ ] Start ChromaDB as a persistent service via Docker Compose
- [ ] Create `app/services/ai/vector_store.py` — ChromaDB client wrapper with collection management
- [ ] Create collections: `jamf_docs`, `apple_platform_security`, `custom_scripts`, `policies`
- [ ] Implement `upsert_documents()`, `similarity_search()`, and `delete_document()` methods
- [ ] Configure embedding function using `sentence-transformers` or Ollama embeddings

### 6.2 Document Ingestion Pipeline
- [ ] Create `app/services/ai/ingestion.py` — document loader and chunking pipeline
- [ ] Support source types:
  - PDF files (Jamf documentation PDFs) via `pypdf` + `unstructured`
  - Markdown/text files (custom knowledge base articles)
  - Web URLs (Jamf documentation pages) via `langchain.document_loaders.WebBaseLoader`
  - Jamf API responses (auto-ingest policy descriptions, smart group criteria)
- [ ] Implement recursive text splitter with configurable chunk size (512 tokens) and overlap (50 tokens)
- [ ] Add metadata to each chunk: `source`, `title`, `page_number`, `server_id`, `doc_type`
- [ ] Deduplicate by file hash — skip re-ingestion if file unchanged
- [x] Create `POST /api/knowledge/ingest` endpoint (admin only) to trigger ingestion from uploaded file or URL
- [x] Create `GET /api/knowledge/documents` endpoint — list all ingested documents
- [x] Create `DELETE /api/knowledge/documents/{id}` endpoint — remove document and its chunks

### 6.3 Knowledge Base Content
- [ ] Download and ingest the Jamf Pro Administrator's Guide (latest, PDF)
- [ ] Download and ingest the Jamf Pro Security Guide
- [ ] Download and ingest the Jamf Pro API documentation
- [ ] Download and ingest Apple Platform Security whitepaper
- [ ] Create and ingest custom articles on:
  - Common Jamf smart group criteria patterns
  - Jamf Extension Attribute scripting best practices
  - macOS compliance framework mappings (CIS, NIST, DISA STIG)
  - Common Jamf troubleshooting scenarios
  - Policy scope and trigger explanations
- [ ] Create a folder `knowledge_base/` in the project for custom Markdown documents
- [ ] Document the process for contributors to add new articles to the knowledge base

### 6.4 RAG Query Pipeline
- [ ] Create `app/services/ai/rag.py` — RAG orchestrator
- [ ] Implement `retrieve_context(query, top_k=5)` — embeds query and fetches top-K chunks from ChromaDB
- [ ] Implement re-ranking of retrieved chunks (by relevance score threshold)
- [ ] Format retrieved context into the LLM prompt with clear source attribution
- [ ] Implement query routing: determine if a question requires RAG, Jamf data tools, or pure LLM reasoning
- [ ] Cache frequent query embeddings in Redis to reduce embedding latency

### 6.5 Knowledge Base Admin UI
- [ ] Build Knowledge Base page under Settings in the frontend
- [ ] List all ingested documents with title, source, ingestion date, chunk count
- [ ] Upload new document (PDF or Markdown) via drag-and-drop form
- [ ] Add URL to ingest from web
- [ ] Delete document (removes from vector store)
- [ ] Display ingestion logs and errors
- [ ] Add scrape job control status badges in the jobs table (running/paused/cancelled + active CPU cap like `total 35%` or `core 220%`)

---

## 7. Testing

### 7.1 Backend Unit Tests
- [ ] Test `JamfClient` with mocked `httpx` responses for all API methods
- [ ] Test token caching and refresh logic
- [ ] Test data normalization functions (OS version parsing, app version comparison)
- [ ] Test all CRUD operations against a test PostgreSQL database (use pytest fixtures with transactions)
- [ ] Test sync service logic with mock Jamf clients
- [ ] Test compliance check calculations
- [ ] Test JWT creation, validation, and expiry
- [ ] Test RAG pipeline with mock vector store
- [ ] Test AI tool functions with mock database queries

### 7.2 Backend Integration Tests
- [ ] Test all REST API endpoints via `httpx.AsyncClient` + `TestClient`
- [ ] Test authentication flow (login, protected route access, token refresh, logout)
- [ ] Test multi-server data isolation
- [ ] Test streaming SSE endpoint (sync progress, AI chat)
- [ ] Test rate limiting middleware behavior
- [ ] Achieve ≥80% code coverage; enforce in CI

### 7.3 Frontend Unit Tests (Vitest + Testing Library)
- [ ] Test `KpiCard` renders correct values
- [ ] Test `DeviceTable` renders rows, sorting, and filtering
- [ ] Test `DeviceFilters` triggers correct query param changes
- [ ] Test `ChatMessage` renders Markdown and code blocks correctly
- [ ] Test `ChatInput` sends on Enter, newline on Shift+Enter
- [ ] Test auth flows: login form validation, unauthenticated redirect
- [ ] Test API hooks with `msw` mock server

### 7.4 Frontend End-to-End Tests (Playwright)
- [ ] Login flow
- [ ] Dashboard page loads with mock data
- [ ] Navigate to Devices, filter by OS version, open device detail
- [ ] Navigate to AI assistant, send a message, receive a response
- [ ] Add a new Jamf server in settings and trigger sync
- [ ] Upload a knowledge base document

### 7.5 Test Infrastructure
- [ ] Set up test database (separate PostgreSQL DB or in-memory SQLite for unit tests)
- [ ] Create `conftest.py` with shared fixtures: async DB session, mock Jamf client, authenticated test user
- [ ] Create `msw` handlers for all backend API endpoints used in frontend tests
- [ ] Add test coverage badge to README
- [ ] Configure CI to fail if coverage drops below threshold

---

## 8. Deployment

### 8.1 Docker
- [ ] Write `backend/Dockerfile` (Python 3.12-slim, non-root user, multi-stage if needed)
- [ ] Write `frontend/Dockerfile` (Node 20-alpine, multi-stage: build → serve with output: standalone)
- [ ] Write production `docker-compose.yml` separating from `docker-compose.dev.yml`
- [ ] Add `healthcheck` directives to all services in Docker Compose
- [ ] Use Docker secrets or `env_file` for sensitive environment variables
- [ ] Add `.dockerignore` files for both backend and frontend

### 8.2 Database & Migrations
- [ ] Create `backend/entrypoint.sh` that runs `alembic upgrade head` before starting Uvicorn
- [ ] Test migration rollback (`alembic downgrade -1`)
- [ ] Create database backup/restore scripts
- [ ] Configure PostgreSQL with connection pooling (PgBouncer or SQLAlchemy pool settings)

### 8.3 Reverse Proxy & TLS
- [ ] Write an Nginx or Caddy configuration as a reverse proxy in Docker Compose:
  - Route `/api/*` → backend
  - Route all other traffic → frontend
  - Enable gzip compression
  - Set security headers (`X-Frame-Options`, `CSP`, `HSTS`, etc.)
- [ ] Configure TLS termination (Let's Encrypt via Caddy auto-HTTPS, or manual cert mount for internal deployments)

### 8.4 Ollama / Model Deployment
- [ ] Document GPU requirements for target model sizes
- [ ] Write `ollama/Modelfile` or entrypoint script to pull required models on first start
- [ ] Configure Ollama service in Docker Compose with GPU passthrough (NVIDIA: `deploy.resources.reservations`)
- [ ] Document CPU-only fallback configuration

### 8.5 Observability
- [ ] Deploy Prometheus + Grafana via Docker Compose for metrics visualization
- [ ] Create Grafana dashboard for: API request rates, error rates, sync durations, AI response latencies, DB query times
- [ ] Configure structured log output to stdout (for log aggregation via Docker log driver or Loki)
- [ ] Add `/api/health` detailed endpoint: db connectivity, redis connectivity, Ollama connectivity, last sync status

### 8.6 CI/CD
- [ ] Finalize `.github/workflows/ci.yml`: lint → test → build Docker images → push to GHCR
- [ ] Create `.github/workflows/release.yml`: tag-triggered → build + push versioned image → create GitHub Release
- [ ] Write `deploy/` folder with example server setup scripts (Ansible or shell)
- [ ] Add auto-updater service: poll GitHub repo for new commits/tags on configured branch
- [ ] Auto-updater workflow: pull latest code, run safety checks, then run `docker compose build` + `docker compose up -d`
- [ ] Add rollback guard for updater (keep previous image tag and revert automatically on failed health checks)

---

## 9. Documentation

### 9.1 Project README
- [ ] Project overview and feature list
- [ ] Architecture diagram (Mermaid or image)
- [ ] Prerequisites (Docker, Ollama, Jamf Pro API credentials)
- [ ] Quick-start guide (clone → configure `.env` → `docker compose up`)
- [ ] Configuration reference (all environment variables with descriptions and defaults)
- [ ] Screenshots of key UI pages

### 9.2 Jamf Pro Configuration Guide
- [ ] How to create a Jamf Pro API Role with minimum required privileges
- [ ] How to create a Jamf Pro API Client and obtain Client ID + Secret
- [ ] Required Classic API permissions
- [ ] Network requirements (firewall rules if Jamf is on-premise)

### 9.3 AI Module Documentation
- [ ] Supported Ollama models and recommended specs
- [ ] How to switch models (env var + Ollama pull command)
- [ ] How to add documents to the knowledge base
- [ ] Explanation of RAG pipeline (diagram)
- [ ] Description of available AI tools / function-calling capabilities

### 9.4 Developer Guide
- [ ] Local development setup (without Docker: running backend and frontend separately)
- [ ] Running tests (`pytest`, `vitest`, `playwright`)
- [ ] Adding a new database model + migration
- [ ] Adding a new API endpoint (router → schema → crud → service pattern)
- [ ] Adding a new frontend page + API hook
- [ ] Contributing guidelines and PR checklist

### 9.5 API Reference
- [ ] Ensure OpenAPI (`/docs`) is complete with descriptions and examples for all endpoints
- [ ] Optionally export and commit `openapi.json` to repo for client generation

### 9.6 Operational Runbook
- [ ] How to perform a manual full sync
- [ ] How to check sync logs and diagnose failures
- [ ] How to back up and restore the PostgreSQL database
- [ ] How to update Ollama models
- [ ] Common troubleshooting scenarios (Jamf auth failure, vector DB full, LLM timeout)
- [ ] How to add a new Jamf server to the dashboard

---

## Priority Order (Suggested Milestones)

| Milestone | Tasks |
|-----------|-------|
| **M1 — Foundation** | 1.1–1.5 (Setup), 2.1–2.3 (Backend structure + auth), 3.1–3.3 (Frontend shell + auth) |
| **M2 — Jamf Data** | 4.1–4.6 (Jamf integration), 2.4–2.11 (Backend CRUD + sync), 3.4–3.6 (Dashboard + Devices UI) |
| **M3 — Full Dashboard** | 3.7–3.12 (Remaining frontend pages), 2.12–2.13 (Caching + API polish) |
| **M4 — AI Assistant** | 5.1–5.5 (LLM + chat), 6.1–6.4 (Vector DB + RAG) |
| **M5 — Knowledge Base Admin** | 6.5 (KB UI), 5.3–5.4 (Tool calling + prompts polish) |
| **M6 — Quality & Ops** | 7.1–7.5 (Testing), 8.1–8.6 (Deployment), 9.1–9.6 (Docs) |
