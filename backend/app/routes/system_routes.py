"""Operational status for the studio UI."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.security import get_current_user
from app.services import health as health_service
from app.services import jobs as jobs_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    database, database_detail = await health_service.check_database(session)
    chapters = await health_service.chapter_counts(session)
    job_counts = await jobs_service.counts_by_status(session)
    status: dict[str, object] = {
        "database": database,
        "pgvector": await health_service.check_pgvector(session),
        "schema": await health_service.check_schema(session),
        "ollama": await health_service.check_ollama(),
        "pending_chapters": chapters["pending_chapters"],
        "failed_chapters": chapters["failed_chapters"],
        "running_jobs": job_counts["running"],
        "queued_jobs": job_counts["queued"],
        "dead_jobs": job_counts["dead"],
        # "offline" means the queue is not being drained: run `make worker`.
        "worker": await health_service.check_worker(session),
    }
    if database_detail:
        status["database_detail"] = database_detail
    return status
