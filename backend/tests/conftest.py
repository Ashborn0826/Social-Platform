"""Pytest fixtures shared across the test suite.

Uses a temp-file SQLite so multiple engines can share data (we override
the global engine + AsyncSessionLocal via monkey-patch so app code +
persist-style helpers all read/write through the same database).
"""
import os
import tempfile

_test_db_path = os.path.join(tempfile.gettempdir(), "social_platform_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db_path}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import get_session
from app.main import create_app


@pytest_asyncio.fixture
async def db_setup(monkeypatch):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    new_session_local = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.db.session.engine", engine)
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", new_session_local)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def app(db_setup):
    TestSessionLocal = async_sessionmaker(db_setup, expire_on_commit=False)

    async def _override_session():
        async with TestSessionLocal() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_session] = _override_session
    yield application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def session(db_setup):
    SessionLocal = async_sessionmaker(db_setup, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session