from logging.config import fileConfig

from app.db import Base
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from dotenv import load_dotenv
import os

import asyncio

# Load environment variables from .env
load_dotenv()

# Fetch variables
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

# Construct the SQLAlchemy connection string
DATABASE_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?ssl=require"

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an AsyncEngine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    # Grab the URL straight from your alembic.ini config mapping
    target_url = config.get_main_option("sqlalchemy.url")
    
    # Recreate the connection specifically as an AsyncEngine
    connectable = create_async_engine(target_url, poolclass=pool.NullPool)

    async def do_run_migrations():
        async with connectable.connect() as connection:
            # run_sync bridges the async connection to Alembic's sync engine
            await connection.run_sync(do_meta_migration)

    def do_meta_migration(sync_conn):
        context.configure(connection=sync_conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    # Safely execute the async block inside Alembic
    asyncio.run(do_run_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


