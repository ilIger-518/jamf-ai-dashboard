# Jamf AI Dashboard

A self-hosted web dashboard for monitoring and managing devices across one or more **Jamf Pro** servers, with an integrated **AI assistant** powered by a local LLM and a custom RAG knowledge base.

## Features

- **Unified device view** — monitor all your Mac fleet across multiple Jamf Pro servers from one screen
- **Security & compliance** — per-device FileVault, SIP, Gatekeeper, Firewall status and CIS/NIST compliance checks
- **Policies & Smart Groups** — browse, inspect, and search all policies and group membership
- **Patch management** — track patched vs. unpatched counts per software title
- **AI assistant** — ask questions about your fleet, get Jamf policy/script generation help, analyze scripts, and query the knowledge base — all powered by a local LLM (no data leaves your network)
- **Read-only AI enforcement** — the AI can only read data; any write action requires explicit user approval with a full command preview

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Browser                               │
│              Next.js 16 + React 19 + Tailwind 4              │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼─────────────────────────────────────┐
│              FastAPI backend (Python 3.12)                   │
│  Auth · Devices · Policies · Patches · Compliance · AI Chat  │
│           APScheduler sync · Redis cache                     │
└──────┬─────────────┬──────────────┬──────────────────────────┘
       │             │              │
  PostgreSQL      Redis        ChromaDB
  (ORM data)   (cache/tokens) (vector store)
                              │
                           Ollama
                       (local LLM / embeddings)
       │
  Jamf Pro API(s)
  (one or many servers)
```

## Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | ≥ 24 |
| Ollama | ≥ 0.3 (if running outside Docker) |
| Python | 3.12 (for local dev without Docker) |
| Node.js | 20 LTS (for local frontend dev) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-org/jamf-ai-dashboard.git
cd jamf-ai-dashboard

# 2. Copy and fill in environment variables
cp .env.example .env
# edit .env with your Jamf Pro credentials, secret key, etc.

# 3. Start all services
docker compose up -d

# 4. The dashboard is now running at http://localhost:3000
#    The API is at http://localhost:8000/docs
```

On first run you will be prompted to create an admin account.

## Configuration

All configuration is via environment variables. See [`.env.example`](.env.example) for the full reference with descriptions and defaults.

Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | Random secret for JWT signing (generate with `openssl rand -hex 32`) |
| `JAMF_SERVER_1_URL` | Base URL of your first Jamf Pro server |
| `JAMF_SERVER_1_CLIENT_ID` | Jamf Pro API client ID |
| `JAMF_SERVER_1_CLIENT_SECRET` | Jamf Pro API client secret |
| `OLLAMA_BASE_URL` | Ollama API base URL (default: `http://ollama:11434`) |
| `OLLAMA_MODEL` | Chat model to use (e.g. `llama3.2:3b`, `mistral:7b`) |

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
# Set DATABASE_URL and REDIS_URL in .env
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Running Tests

```bash
# Backend
cd backend && pytest --cov=app --cov-report=term-missing

# Frontend unit tests
cd frontend && npm test

# Frontend E2E (Playwright)
cd frontend && npx playwright test
```

## Contributing

1. Fork the repo and create a feature branch from `develop`
2. Follow the PR checklist in [CONTRIBUTING.md](docs/CONTRIBUTING.md)
3. All CI checks must pass before merging

## License

MIT
