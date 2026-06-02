from collections.abc import AsyncGenerator
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine,async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from app.config import settings

# Construct the SQLAlchemy connection string
DATABASE_URL = f"postgresql+asyncpg://{settings.user}:{settings.password}@{settings.host}:{settings.port}/{settings.dbname}?ssl=require"

# Create the SQLAlchemy engine
# If using Transaction Pooler or Session Pooler, we want to ensure we disable SQLAlchemy client side pooling -
# https://docs.sqlalchemy.org/en/20/core/pooling.html#switching-pool-implementations
engine = create_async_engine(DATABASE_URL, poolclass=NullPool)

async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass    

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session