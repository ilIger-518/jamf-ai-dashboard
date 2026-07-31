# Contributing

## Development setup

1. Copy [.env.example](.env.example) to .env and adjust the values for your environment.
2. Create and activate a Python virtual environment for the backend.
3. Install backend dependencies with `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`.
4. Install frontend dependencies with `npm ci` inside the frontend directory.
5. Run backend tests with `pytest` from the backend directory.
6. Run frontend tests with `npm test` from the frontend directory.

## Pull request checklist

- Keep changes focused and documented.
- Add or update tests when behavior changes.
- Ensure linting and tests pass locally before opening a PR.
- Update relevant docs when configuration or workflows change.
