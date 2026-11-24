"""Operational status for the studio UI."""

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models import Chapter
from app.models.app_models import User
from app.schema_check import expected_head
from app.security import get_current_user
from app.services import jobs as jobs_service

router = APIRouter(prefix="/system", tags=["system"])


async def _check_database(session: AsyncSession) -> tuple[str, str | None]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on a broken database
        return "error", str(exc)[:200]
    return "ok", None


async def _check_pgvector(session: AsyncSession) -> str:
    try:
        version = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
    except Exception:
        return "missing"
    return f"ok ({version})" if version else "missing"


async def _check_ollama() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code != 200:
                return f"error ({response.status_code})"
            models = [item.get("name", "") for item in response.json().get("models", [])]
            if not any(settings.EMBEDDING_MODEL in name for name in models):
                return f"missing model {settings.EMBEDDING_MODEL}"
            return "ok"
    except Exception:
        return "unreachable"


async def _check_schema(session: AsyncSession) -> str:
    current = await session.scalar(text("SELECT version_num FROM alembic_version"))
    return "ok" if current == expected_head() else f"behind ({current})"


@router.get("/status")
async def system_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    database, database_detail = await _check_database(session)
    pending = await session.scalar(
        select(func.count(Chapter.id)).where(Chapter.index_status == "pending")
    )
    failed = await session.scalar(
        select(func.count(Chapter.id)).where(Chapter.index_status == "failed")
    )
    job_counts = await jobs_service.counts_by_status(session)
    worker_alive = await jobs_service.worker_is_alive(session)
    status = {
        "database": database,
        "pgvector": await _check_pgvector(session),
        "schema": await _check_schema(session),
        "ollama": await _check_ollama(),
        "pending_chapters": int(pending or 0),
        "failed_chapters": int(failed or 0),
        "running_jobs": job_counts["running"],
        "queued_jobs": job_counts["queued"],
        "dead_jobs": job_counts["dead"],
        # "offline" means the queue is not being drained: run `make worker`.
        "worker": "running" if worker_alive else "offline",
    }
    if database_detail:
        status["database_detail"] = database_detail
    return status
