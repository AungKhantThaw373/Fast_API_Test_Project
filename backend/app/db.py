import os
from collections.abc import AsyncGenerator

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

DATABASE_URL = URL.create(
    "postgresql+asyncpg",
    username=settings.user,
    password=settings.password,
    host=settings.host,
    port=settings.port,
    database=settings.dbname,
    query={"ssl": settings.DATABASE_SSL},
)

# A hosted database makes every new connection cost a TLS handshake. NullPool
# opened a fresh connection for each session (over a second against a remote
# Supabase region), which dominated chapter scans and every request path. Reuse
# a small pool instead; 5432 is Supabase's session pooler and supports this.
#
# Every API connection carries a 15s statement timeout: a runaway query fails
# fast instead of holding a request open forever. Worker connections raise it
# (see ``app/worker.py``). Tests use the same engine, so a hang fails loudly.
STATEMENT_TIMEOUT_MS = int(os.environ.get("STATEMENT_TIMEOUT_MS", "15000"))

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"server_settings": {"statement_timeout": str(STATEMENT_TIMEOUT_MS)}},
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
