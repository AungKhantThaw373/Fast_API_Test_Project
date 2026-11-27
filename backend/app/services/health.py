"""Dependency checks shared by ``/system/status`` and ``/ready``.

``/health`` must stay cheap — it may be polled often and answers only "is this
process alive". ``/ready`` pays for real checks because it is asked rarely, by a
deploy script or an operator.
"""

from __future__ import annotations

import time

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.story_models import Chapter
from app.schema_check import expected_head
from app.services import jobs as jobs_service


async def check_database(session: AsyncSession) -> tuple[str, str | None]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on a broken database
        return "error", str(exc)[:200]
    return "ok", None


async def check_pgvector(session: AsyncSession) -> str:
    try:
        version = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
    except Exception:  # pragma: no cover - depends on a broken database
        return "missing"
    return f"ok ({version})" if version else "missing"


async def check_ollama() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code != 200:
                return f"error ({response.status_code})"
            models = [item.get("name", "") for item in response.json().get("models", [])]
            for required in (settings.EMBEDDING_MODEL, settings.OLLAMA_CHAT_MODEL):
                if not any(required in name for name in models):
                    return f"missing model {required}"
            return "ok"
    except Exception:
        return "unreachable"


async def check_schema(session: AsyncSession) -> str:
    current = await session.scalar(text("SELECT version_num FROM alembic_version"))
    return "ok" if current == expected_head() else f"behind ({current})"


async def check_worker(session: AsyncSession) -> str:
    return "running" if await jobs_service.worker_is_alive(session) else "offline"


async def chapter_counts(session: AsyncSession) -> dict[str, int]:
    pending = await session.scalar(
        select(func.count(Chapter.id)).where(Chapter.index_status == "pending")
    )
    failed = await session.scalar(
        select(func.count(Chapter.id)).where(Chapter.index_status == "failed")
    )
    return {"pending_chapters": int(pending or 0), "failed_chapters": int(failed or 0)}


async def readiness_report(session: AsyncSession) -> tuple[bool, dict[str, object]]:
    started = time.perf_counter()
    database, database_detail = await check_database(session)
    report: dict[str, object] = {
        "database": database,
        "pgvector": await check_pgvector(session),
        "schema": await check_schema(session),
        "ollama": await check_ollama(),
        "worker": await check_worker(session),
        "duration_ms": 0,
    }
    if database_detail:
        report["database_detail"] = database_detail
    ready = all(
        str(report[key]).startswith("ok") or report[key] == "running"
        for key in ("database", "pgvector", "schema", "ollama", "worker")
    )
    report["duration_ms"] = round((time.perf_counter() - started) * 1000)
    return ready, report
