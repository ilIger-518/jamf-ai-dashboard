import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app


@pytest.fixture
async def async_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda s: None)

    async with TestSessionLocal() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def client_override(monkeypatch):
    async def override_get_db():
        yield None

    monkeypatch.setattr("app.database.get_db", override_get_db)
    return override_get_db
