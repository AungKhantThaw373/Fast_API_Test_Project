"""Startup guard: the database schema must be at Alembic head.

Running an older schema against newer code produces confusing 500s (missing
columns) long after the operator could have fixed it with one command. Fail
loudly at boot instead.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def expected_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("No Alembic head revision found. The migration tree is broken.")
    return head


async def assert_schema_at_head(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    current = result.scalar_one_or_none()
    head = expected_head()
    if current != head:
        raise RuntimeError(
            "Database schema is not at Alembic head "
            f"(database={current or 'none'}, expected={head}). "
            "Run: cd backend && uv run alembic upgrade head"
        )
