"""Operational status and diagnostics for the studio UI."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User, UserAISettings
from app.models.wiki_models import AIUsage
from app.schemas.system import (
    AIUsageMetric,
    BackupStatus,
    DiagnosticsOut,
    JobStatusCounts,
)
from app.security import get_current_user
from app.services import health as health_service
from app.services import jobs as jobs_service

router = APIRouter(prefix="/system", tags=["system"])

REPO_ROOT = Path(__file__).resolve().parents[2]


def _backup_dir() -> Path:
    path = Path(settings.BACKUP_DIR)
    return path if path.is_absolute() else REPO_ROOT / path


def _latest_backup() -> BackupStatus | None:
    directory = _backup_dir()
    if not directory.is_dir():
        return None
    candidates = sorted(
        directory.glob("stillroom-*.dump"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    newest = candidates[0]
    stat = newest.stat()
    return BackupStatus(
        filename=newest.name,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
    )


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
        "worker": await health_service.check_worker(session),
    }
    if database_detail:
        status["database_detail"] = database_detail
    return status


@router.get("/diagnostics", response_model=DiagnosticsOut)
async def system_diagnostics(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> DiagnosticsOut:
    database, database_detail = await health_service.check_database(session)
    if database_detail:
        database = f"error ({database_detail})"
    size = await session.scalar(text("SELECT pg_database_size(current_database())"))
    start = datetime.now(UTC) - timedelta(days=30)
    usage_rows = (await session.execute(
        select(
            AIUsage.purpose,
            func.count(AIUsage.id),
            func.coalesce(func.sum(AIUsage.input_tokens), 0),
            func.coalesce(func.sum(AIUsage.output_tokens), 0),
            func.coalesce(func.sum(AIUsage.cost_estimate), 0),
        )
        .where(AIUsage.user_id == user.id, AIUsage.created_at >= start)
        .group_by(AIUsage.purpose)
        .order_by(func.sum(AIUsage.cost_estimate).desc())
    )).all()
    ai = await session.get(UserAISettings, user.id)
    counts = await jobs_service.counts_by_status(session)
    return DiagnosticsOut(
        generated_at=datetime.now(UTC),
        database=database,
        database_size_bytes=int(size or 0),
        pgvector=await health_service.check_pgvector(session),
        schema_status=await health_service.check_schema(session),
        worker=await health_service.check_worker(session),
        ollama=await health_service.check_ollama(),
        jobs=JobStatusCounts(**counts),
        ai_provider=ai.provider if ai else "ollama",
        ai_model=ai.model if ai else settings.OLLAMA_CHAT_MODEL,
        ai_usage_30d=[
            AIUsageMetric(
                purpose=str(purpose),
                calls=int(calls),
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                cost_estimate=float(cost),
            )
            for purpose, calls, input_tokens, output_tokens, cost in usage_rows
        ],
        last_backup=_latest_backup(),
        slow_query_ms=settings.SLOW_QUERY_MS,
    )