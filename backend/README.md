# Backend

## Local development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Useful commands

- `alembic upgrade head`
- `alembic downgrade -1`
- `ruff check .`
- `ruff format .`
