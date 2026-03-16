# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Scrape job runtime controls in Knowledge Base: pause, resume, cancel, and CPU cap modes (`total` and Linux-style `core` percent)
- Persistent per-job scrape logs with live log viewer in the Knowledge page
- Scrape runtime diagnostics endpoint/UI for active limiter and worker state
- Role-based access control (RBAC): roles model, permissions catalog, users/roles management APIs, and Settings UI for user/role CRUD
- AI bot split in dashboard chat: `RAG Read-Only` and `Policy & Group Builder`
- Streaming AI chat endpoint with stage events and incremental delta output
- Write-action approval workflow in AI builder: preview command + explicit `approve`/`cancel` before execution
- Quick `Approve` / `Cancel` action buttons in AI chat composer when a pending preview is detected
- Password self-service: authenticated `change-password` API and Settings "My Password" form
- Network diagnostics page at `/debug/network` for client-side API reachability checks

### Changed
- Refreshed project documentation across `README.md`, `Documentation.md`, and `frontend/README.md` to match current architecture and feature set
- AI builder expanded from policy-only operations to support group and script creation flows
- AI responses now render progressively in chat (word-by-word style streaming)
- Frontend API routing defaults to same-origin `/api/v1` with Next.js rewrite proxy to backend
- Frontend login error handling now distinguishes credential failures from API reachability issues
- Frontend container runtime config now supports backend proxying via `BACKEND_INTERNAL_URL`

### Fixed
- Startup auto-heal for interrupted scrape jobs left in `running` state after restarts
- Login regression caused by async role lazy-loading (`MissingGreenlet`) by eager-loading user role in auth dependency
- Migrator reliability for smart/static group detection and static member payload normalization
- Cross-device login/API failures caused by localhost-targeted frontend API URLs

## [0.5.12] - 2026-03-13 (`468fd8f`)

### Added
- Assets API router and schemas for live Scripts and Packages listing
- Migrator router/schema support for Jamf-to-Jamf object migration (including scripts)
- New frontend `Scripts`, `Packages`, and `Migrator` pages

### Changed
- Sidebar navigation now includes `Scripts`, `Packages`, and `Migrator`

## [0.5.11] - 2026-03-13 (`4d633c1`)

### Added
- Global Jamf server selector in the app shell

### Changed
- Dashboard and list queries now include optional `server_id` filtering

## [0.5.10] - 2026-03-09 (`af7ec1a`)

### Added
- Background sync scheduler (APScheduler) for periodic server sync
- Dashboard OS version distribution and patch summary visualizations

## [0.5.9] - 2026-03-09 (`57d0b4e`)

### Changed
- Updated `TODO.md` to mark completed roadmap items

## [0.5.8] - 2026-03-09 (`ae1eb7c`)

### Fixed
- Corrected patch and smart-group Jamf URL formats for reliable deep-link navigation

## [0.5.7] - 2026-03-09 (`673578b`)

### Added
- Server URL links in device, patch, policy, and smart-group detail views

## [0.5.6] - 2026-03-09 (`2171017`)

### Added
- Reusable detail drawer component and entity detail pages for Devices, Patches, Policies, and Smart Groups

## [0.5.5] - 2026-03-09 (`8d30f3b`)

### Added
- Database migration for `smart_groups` and `patch_titles` tables

## [0.5.4] - 2026-03-09 (`beaa576`)

### Added
- Database migration for `policies` table

## [0.5.3] - 2026-03-09 (`aac1c74`)

### Added
- Manual per-server sync and bulk sync-all API endpoints

## [0.5.2] - 2026-03-06 (`4e73fc2`)

### Changed
- Server provisioning flow now supports credential/role preset selection

## [0.5.1] - 2026-03-06 (`2b68827`)

### Added
- Jamf Pro auto-provisioning wizard with role/client creation and credential persistence

## [0.5.0] - 2026-03-06 (`5ee64ea`)

### Changed
- Documentation updated for 0.5.0 features (per-user chat sessions and knowledge source size tracking)

## [0.4.13] - 2026-03-06 (`49f19e8`)

### Changed
- Standardized string quotes and general code formatting across multiple files

## [0.4.12] - 2026-03-06 (`9e480ad`)

### Changed
- Refactored import statements and type hints across multiple files

## [0.4.11] - 2026-03-06 (`2759ce2`)

### Changed
- CI configuration updated for backend and frontend test runs

## [0.4.10] - 2026-03-06 (`a500434`)

### Changed
- Changelog content refreshed to cover 0.5.0 features, changes, and fixes

## [0.4.9] - 2026-03-06 (`33471f2`)

### Added
- `size_bytes` support for knowledge documents and related frontend/backend updates

## [0.4.8] - 2026-03-06 (`424982b`)

### Added
- AI chat improvements: session management, persistent messages, and UI enhancements

## [0.4.7] - 2026-03-06 (`c10de22`)

### Added
- Async web scraper service with sitemap support, Zoomin API integration, and LLM topic filtering

## [0.4.6] - 2026-03-06 (`0845a1e`)

### Added
- Smart Groups management page with search and pagination

## [0.4.5] - 2026-03-05 (`d36fc15`)

### Added
- Initial `Documentation.md`

## [0.4.4] - 2026-03-05 (`f8a9e72`)

### Added
- Initial backend and frontend project structure with core files

## [0.4.3] - 2026-03-03 (`7c2ea88`)

### Added
- Project `.gitignore` and initial `TODO.md`

## [0.4.2] - 2026-03-02 (`2747370`)

### Added
- Frontend file set finalized in repository

## [0.4.1] - 2026-03-02 (`84b6b4e`)

### Added
- Initial repository commit
