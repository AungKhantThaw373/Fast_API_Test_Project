"""Test harness: a real PostgreSQL test database, no provider calls.

The environment must be configured before ``app.config`` is imported, because
settings are read once at import time.
"""

import os

os.environ["DBNAME"] = "stillroom_test"
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_SSL"] = "disable"
os.environ["COOKIE_SECURE"] = "false"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-validation"
os.environ["host"] = os.environ.get("host", "127.0.0.1")
os.environ["port"] = os.environ.get("port", "5432")
os.environ["user"] = os.environ.get("user", "postgres")
os.environ["password"] = os.environ.get("password", "death373")

import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Headers
from sqlalchemy import text

from app.app import app
from app.db import async_session, engine
from app.rate_limits import reset_rate_limits

BACKEND_ROOT = Path(__file__).resolve().parent.parent

TABLES = (
    "users, user_ai_settings, stories, story_chapters, story_chapter_revisions, "
    "story_scene_embeddings, story_chunks, story_bible_entries, continuity_scans, "
    "continuity_findings, editing_folders, editing_draft_files, jobs, worker_heartbeats, "
    "entities, entity_aliases, entity_facts, entity_relationships, story_events, "
    "story_threads, entity_mentions, canon_exceptions, chapter_meta, scene_meta, ai_usage, "
    "login_attempts, auth_sessions, password_reset_tokens, audit_events"
)


@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    """Bring the test database to Alembic head before the first test runs."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        check=True,
        env=os.environ.copy(),
        capture_output=True,
    )
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(prepare_database):
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    reset_rate_limits()
    yield


@pytest_asyncio.fixture
async def client():
    async with make_test_client() as http_client:
        yield http_client


@pytest_asyncio.fixture
async def session():
    async with async_session() as db_session:
        yield db_session


PASSWORD = "correct horse battery"
CSRF_TOKEN = "test-csrf-token-with-enough-entropy"


class CSRFClient(AsyncClient):
    """Echo the double-submit token exactly as the browser client does."""

    async def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            headers = Headers(kwargs.pop("headers", None))
            headers.setdefault("X-CSRF-Token", CSRF_TOKEN)
            kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)


def make_test_client() -> CSRFClient:
    client = CSRFClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set("csrf", CSRF_TOKEN, path="/")
    return client


async def register(client: AsyncClient, username: str, email: str, password: str = PASSWORD):
    return await client.post(
        "/register",
        json={"username": username, "email": email, "password": password},
    )


async def login(client: AsyncClient, email: str, password: str = PASSWORD):
    return await client.post("/token", data={"username": email, "password": password})


@pytest_asyncio.fixture
async def user_client(client):
    await register(client, "writer", "writer@example.com")
    response = await login(client, "writer@example.com")
    assert response.status_code == 200
    return client


@pytest_asyncio.fixture
async def make_client():
    """Factory for independently authenticated clients (multi-user tests)."""
    created: list[AsyncClient] = []

    async def factory(username: str, email: str) -> AsyncClient:
        http_client = make_test_client()
        created.append(http_client)
        assert (await register(http_client, username, email)).status_code == 201
        assert (await login(http_client, email)).status_code == 200
        return http_client

    yield factory
    for http_client in created:
        await http_client.aclose()
