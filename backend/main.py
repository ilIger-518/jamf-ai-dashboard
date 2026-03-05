# Root entrypoint shim — delegates to the app package.
# Run with: uvicorn main:app --reload
# Or via the app package directly: uvicorn app.main:app --reload
from app.main import app  # noqa: F401
