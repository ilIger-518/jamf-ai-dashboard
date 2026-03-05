# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
