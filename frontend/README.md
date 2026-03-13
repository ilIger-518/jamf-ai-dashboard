# Frontend — Jamf AI Dashboard

Next.js frontend for Jamf AI Dashboard.

## UI Coverage

- Dashboard overview (cards + charts)
- Global server selector integration
- Data pages: Devices, Policies, Smart Groups, Patches
- Assets pages: Scripts, Packages
- Migrator page
- Knowledge Base page (scrape jobs and sources)
- Running-job settings modal (pause/resume/cancel + CPU cap)
- AI Assistant with per-user sessions

## Development

```bash
cd frontend
npm install
npm run dev
```

App URL: `http://localhost:3000`

## Build and Run

```bash
npm run build
npm run start
```

## Test

```bash
npm test
```

## Environment

Frontend expects:

- `NEXT_PUBLIC_API_URL` (for example `http://localhost:8000`)
