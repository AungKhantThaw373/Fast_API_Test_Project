"""Soft delete, restore, and purging.

Writers delete the wrong chapter. A 30-day trash window turns that from a
disaster into an undo. `chapter_number` stays unique among *active* chapters
through a partial index, so a trashed chapter does not block renumbering.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, Story

TRASH_RETENTION_DAYS = 30


def cutoff(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=TRASH_RETENTION_DAYS)


async def trash_story(session: AsyncSession, story: Story) -> None:
    now = datetime.now(UTC)
    story.deleted_at = now
    await session.execute(
        update(Chapter)
        .where(Chapter.story_id == story.id, Chapter.deleted_at.is_(None))
        .values(deleted_at=now)
    )


async def trash_chapter(session: AsyncSession, chapter: Chapter) -> None:
    chapter.deleted_at = datetime.now(UTC)


async def next_free_number(
    session: AsyncSession, story_id, *, exclude_chapter_id=None
) -> int:
    taken = set(
        await session.scalars(
            select(Chapter.chapter_number).where(
                Chapter.story_id == story_id, Chapter.deleted_at.is_(None)
            )
        )
    )
    if exclude_chapter_id is not None:
        taken.discard(None)
    number = 1
    while number in taken:
        number += 1
    return number


async def purge_expired_trash(session: AsyncSession, now: datetime | None = None) -> dict:
    """Permanently delete stories and chapters trashed before the cutoff."""
    limit = cutoff(now)
    expired_stories = list(
        await session.scalars(
            select(Story).where(Story.deleted_at.is_not(None), Story.deleted_at < limit)
        )
    )
    for story in expired_stories:
        await session.delete(story)

    expired_chapter_ids = list(
        await session.scalars(
            select(Chapter.id).where(
                Chapter.deleted_at.is_not(None),
                Chapter.deleted_at < limit,
            )
        )
    )
    if expired_chapter_ids:
        await session.execute(delete(Chapter).where(Chapter.id.in_(expired_chapter_ids)))
    await session.flush()
    return {"stories": len(expired_stories), "chapters": len(expired_chapter_ids)}
