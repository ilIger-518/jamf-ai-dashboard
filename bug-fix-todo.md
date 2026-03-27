# Bug Fix TODO

## Reported by user
- [x] Log file download fails
- [x] Policies view fails to load
- [ ] Packages list shows empty even when Jamf Pro has packages

## Full app health check
- [x] Backend container health/startup
- [x] Frontend container health/startup
- [x] Database migration state
- [ ] Auth/login flow basic check
- [x] Dashboard key pages API check
- [ ] Knowledge base page check
- [ ] AI assistant chat check
- [x] Settings/logs/update panels check

## Fix + verify workflow
- [x] Reproduce each issue with logs/evidence
- [x] Implement code fixes
- [x] Rebuild/restart services
- [x] Re-test affected flows
- [x] Update this file with final status

## Notes from latest verification
- `GET /api/v1/system/server-logs` returns files and downloading the returned filename now succeeds (HTTP 200).
- `GET /api/v1/policies` now returns data (HTTP 200), and manual sync no longer fails with the previous duplicate-row exception.
- `GET /api/v1/servers/{id}/sync/status` was fixed from 500 to 200 (Redis decode compatibility fix).
- `GET /api/v1/assets/packages?server_id=...` now returns explicit upstream auth diagnostics instead of silently showing empty UI. Current upstream response for tested server: `modern:403, classic:401, classic-subset:404`.
- Added credential fallback for package reads (`primary` + `ai` OAuth clients). Both clients currently receive the same upstream authorization failures on package endpoints for the tested Jamf server.
