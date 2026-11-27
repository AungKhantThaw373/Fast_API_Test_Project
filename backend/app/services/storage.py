"""Storage accounting and retention cleanup for the diagnostics page.

This reports database-level table sizes (the same figures an operator would get
from psql) and account-level row counts. Cleanup only removes rows that are
already past a documented retention window; it never deletes active prose.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_models import User
from app.models.job_models import Job
from app.models.story_models import Chapter, ChapterRevision, Story, StoryChunk
from app.schemas.system import (
    StorageCounts,
    StorageExpired,
    StorageReportOut,
    StorageTable,
)
from app.services.trash import TRASH_RETENTION_DAYS, purge_expired_trash
from app.services.trash import cutoff as trash_cutoff

FINISHED_JOB_STATUSES = ("succeeded", "cancelled", "dead")
FINISHED_JOB_RETENTION_DAYS = 30


def jobs_cutoff(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=FINISHED_JOB_RETENTION_DAYS)


async def _scalar_count(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)


async def storage_report(session: AsyncSession, user: User) -> StorageReportOut:
    now = datetime.now(UTC)
    size = int(await session.scalar(text("SELECT pg_database_size(current_database())")) or 0)
    table_rows = (
        await session.execute(
            text("""
        SELECT c.relname, pg_total_relation_size(c.oid) AS size
        FROM pg_class c
        WHERE c.relkind = 'r'
          AND c.relnamespace = 'public'::regnamespace
        ORDER BY size DESC
        LIMIT 8
    """)
        )
    ).all()

    owner = Story.owner_id == user.id
    story_chapters = Story.id == Chapter.story_id
    chapter_stories = Chapter.story_id == Story.id
    stories = await _scalar_count(
        session,
        select(func.count()).select_from(Story).where(owner, Story.deleted_at.is_(None)),
    )
    trashed_stories = await _scalar_count(
        session,
        select(func.count()).select_from(Story).where(owner, Story.deleted_at.is_not(None)),
    )
    chapters = await _scalar_count(
        session,
        select(func.count())
        .select_from(Chapter)
        .join(Story, story_chapters)
        .where(owner, Chapter.deleted_at.is_(None)),
    )
    trashed_chapters = await _scalar_count(
        session,
        select(func.count())
        .select_from(Chapter)
        .join(Story, story_chapters)
        .where(owner, Chapter.deleted_at.is_not(None)),
    )
    chunks = await _scalar_count(
        session,
        select(func.count()).select_from(StoryChunk).join(Story, Story.id == StoryChunk.story_id).where(owner),
    )
    revisions = await _scalar_count(
        session,
        select(func.count())
        .select_from(ChapterRevision)
        .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
        .join(Story, chapter_stories)
        .where(owner),
    )
    jobs = await _scalar_count(
        session,
        select(func.count()).select_from(Job).where(Job.owner_id == user.id),
    )

    trash_limit = trash_cutoff(now)
    jobs_limit = jobs_cutoff(now)
    expired_stories = await _scalar_count(
        session,
        select(func.count())
        .select_from(Story)
        .where(owner, Story.deleted_at.is_not(None), Story.deleted_at < trash_limit),
    )
    expired_chapters = await _scalar_count(
        session,
        select(func.count())
        .select_from(Chapter)
        .join(Story, story_chapters)
        .where(owner, Chapter.deleted_at.is_not(None), Chapter.deleted_at < trash_limit),
    )
    expired_jobs = await _scalar_count(
        session,
        select(func.count())
        .select_from(Job)
        .where(
            Job.owner_id == user.id,
            Job.status.in_(FINISHED_JOB_STATUSES),
            Job.updated_at < jobs_limit,
        ),
    )

    return StorageReportOut(
        generated_at=now,
        database_size_bytes=size,
        tables=[StorageTable(name=str(name), size_bytes=int(table_size)) for name, table_size in table_rows],
        counts=StorageCounts(
            stories=stories,
            chapters=chapters,
            chunks=chunks,
            revisions=revisions,
            jobs=jobs,
            trashed_stories=trashed_stories,
            trashed_chapters=trashed_chapters,
        ),
        expired=StorageExpired(
            trash_cutoff=trash_limit,
            jobs_cutoff=jobs_limit,
            stories=expired_stories,
            chapters=expired_chapters,
            jobs=expired_jobs,
        ),
        trash_retention_days=TRASH_RETENTION_DAYS,
        finished_jobs_retention_days=FINISHED_JOB_RETENTION_DAYS,
    )


async def prune_finished_jobs(session: AsyncSession, owner_id: UUID, now: datetime | None = None) -> int:
    """Delete finished jobs that are past the retention window."""
    result = await session.execute(
        delete(Job).where(
            Job.owner_id == owner_id,
            Job.status.in_(FINISHED_JOB_STATUSES),
            Job.updated_at < jobs_cutoff(now),
        )
    )
    assert isinstance(result, CursorResult)
    return int(result.rowcount or 0)


async def cleanup_expired_storage(session: AsyncSession, owner_id: UUID, now: datetime | None = None) -> dict[str, int]:
    """Remove this account's expired trash and finished jobs, then commit."""
    purged = await purge_expired_trash(session, now=now, owner_id=owner_id)
    jobs_deleted = await prune_finished_jobs(session, owner_id, now=now)
    await session.commit()
    return {
        "stories": purged["stories"],
        "chapters": purged["chapters"],
        "jobs": jobs_deleted,
    }
