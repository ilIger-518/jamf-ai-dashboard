# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-03-06

### Added
- **Per-user chat sessions** — every user now has isolated chat history; sessions are scoped by `user_id` and never visible to other users
- **ChatGPT-style AI page** — left sidebar lists all of the current user's sessions (newest first with relative timestamps); clicking a session loads its full message history
- **New Chat button** — starts a fresh conversation without losing any previous sessions
- **Session rename** — inline rename of any session directly from the sidebar
- **Session delete** — trashcan button per session in the sidebar with confirmation prompt
- **Multi-turn context** — Ollama receives the full prior message history on every request so the LLM can refer back to earlier messages in a conversation
- **Session auto-title** — the first 60 characters of the opening message become the session title automatically
- **Persistent messages** — every user and assistant message is stored in PostgreSQL (`chat_messages` table) and reloaded when the session is reopened
- **Suggested prompts** — empty chat state shows four clickable example questions to get started
- **Knowledge source storage size** — the Stored Sources table in the Knowledge Base page now shows a **Size** column (formatted as B / KB / MB)
- `size_bytes` column added to `knowledge_documents` table via Alembic migration `e7a3c2f9b104`
- Scraper now records the UTF-8 byte size of extracted text for every ingested page

### Changed
- `POST /ai/chat` now accepts an optional `session_id`; if omitted a new session is created automatically and its ID is returned in the response
- `GET /ai/sessions` — new endpoint: list current user's sessions ordered by `updated_at DESC`
- `POST /ai/sessions` — new endpoint: create an empty named session
- `DELETE /ai/sessions/{id}` — new endpoint: delete a session and all its messages (ownership enforced)
- `GET /ai/sessions/{id}/messages` — new endpoint: fetch all messages in a session oldest-first (ownership enforced)
- `SourceResponse` schema extended with `size_bytes` field
- Knowledge Base frontend interface updated (`KnowledgeSource` type, `formatBytes` helper, extra table column)

### Fixed
- Scraper: **Zoomin Software SPA support** — pages rendering <300 chars of visible text now fall back to the Zoomin backend API (`https://learn-be.jamf.com/api/bundle/{bundle}/page/{topic}.html`) which returns the full article HTML as JSON
- Scraper: **sitemap seeding** — `_seed_from_sitemap()` parses `/sitemap.xml` (including sitemap index files) to pre-populate the crawl queue; multi-language sites are filtered to `/en-US/` URLs
- Scraper: **login/redirect detection** — pages redirected to a different domain or whose path matches `/login|auth|signin|register|logout|sso` are skipped automatically
- Scraper: **text extraction** — `_extract_text()` now prefers the `<main>` or `<article>` tag and strips `<nav>`, `<footer>`, and `<aside>` elements before returning plain text

## [0.4.0] - 2026-03-05

### Added
- Initial project scaffold: barebone FastAPI backend and Next.js 16 frontend
- `TODO.md` with full feature roadmap across 9 categories
- `README.md` with architecture overview and quick-start guide
- `docker-compose.yml` with postgres, redis, chromadb, ollama, backend, and frontend services
- `.env.example` with all configuration variables
- `pyproject.toml` with ruff and mypy configuration
- Backend `app/` package layout with config, database, cache, models, schemas, routers, and services
- SQLAlchemy ORM models: `JamfServer`, `Device`, `User`, `Policy`, `SmartGroup`, `PatchTitle`, `ComplianceResult`, `SecurityStatus`, `ChatSession`, `ChatMessage`, `KnowledgeDocument`, `PendingAction`, `AiToolAuditLog`
- Alembic migration setup
- JWT authentication with access + refresh token flow
- Pydantic v2 schemas for all models
