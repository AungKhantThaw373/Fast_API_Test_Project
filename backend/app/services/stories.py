"""Story queries: ownership, listing, detail, and updates."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.story_models import Chapter, Story
from app.services.ai_settings import has_ai_config
from app.services.pagination import (
    clamp_limit,
    cursor_timestamp,
    cursor_uuid,
    decode_cursor,
    encode_cursor,
    keyset_predicate,
)


async def owned_story(session: AsyncSession, story_id: UUID, user_id: UUID) -> Story:
    story = await session.scalar(
        select(Story).where(
            Story.id == story_id,
            Story.owner_id == user_id,
            Story.deleted_at.is_(None),
        )
    )
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found.")
    return story


async def list_story_rows(
    session: AsyncSession,
    owner_id: UUID,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> tuple[list[tuple[Story, int, int]], str | None]:
    """One aggregate query for every story, its chapter count, and word count."""
    page_size = clamp_limit(limit)
    columns = (Story.updated_at, Story.id)
    query = (
        select(
            Story,
            func.count(Chapter.id).label("chapter_count"),
            func.coalesce(func.sum(Chapter.word_count), 0).label("word_count"),
        )
        .outerjoin(
            Chapter,
            (Chapter.story_id == Story.id) & Chapter.deleted_at.is_(None),
        )
        .where(Story.owner_id == owner_id, Story.deleted_at.is_(None))
    )
    if cursor:
        updated_at, story_id = decode_cursor(cursor, [cursor_timestamp, cursor_uuid])
        query = query.where(
            keyset_predicate(columns, (updated_at, story_id), descending=True)
        )
    rows = [
        (story, int(chapter_count or 0), int(word_count or 0))
        for story, chapter_count, word_count in await session.execute(
            query.group_by(Story.id)
            .order_by(Story.updated_at.desc(), Story.id.desc())
            .limit(page_size + 1)
        )
    ]
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        story = rows[-1][0]
        next_cursor = encode_cursor((story.updated_at, story.id))
    return rows, next_cursor


async def load_story_detail(session: AsyncSession, story_id: UUID, user_id: UUID) -> Story | None:
    """Load a story with its active chapter summary columns in two round trips."""
    return await session.scalar(
        select(Story)
        .where(
            Story.id == story_id,
            Story.owner_id == user_id,
            Story.deleted_at.is_(None),
        )
        .options(
            selectinload(Story.chapters).load_only(
                Chapter.id,
                Chapter.story_id,
                Chapter.chapter_number,
                Chapter.title,
                Chapter.word_count,
                Chapter.revision,
                Chapter.bible_scan_revision,
                Chapter.bible_scan_error,
                Chapter.index_status,
                Chapter.index_error,
                Chapter.updated_at,
                Chapter.deleted_at,
            )
        )
    )


async def create_story(session: AsyncSession, owner_id: UUID, title: str) -> Story:
    cleaned = title.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Story title cannot be blank.")
    story = Story(owner_id=owner_id, title=cleaned)
    session.add(story)
    await session.commit()
    await session.refresh(story)
    return story


async def apply_updates(
    session: AsyncSession, story: Story, changes: dict, user_id: UUID
) -> Story:
    if changes.get("external_analysis_enabled"):
        if not await has_ai_config(session, user_id):
            raise HTTPException(
                status_code=503,
                detail="Configure an AI provider in Settings → AI before enabling analysis.",
            )
    for name, value in changes.items():
        if name == "title":
            value = value.strip() if value else ""
            if not value:
                raise HTTPException(status_code=422, detail="Story title cannot be blank.")
        if name == "collection_name":
            value = (value or "").strip()
        setattr(story, name, value)
    await session.commit()
    await session.refresh(story)
    return story


async def index_status_rows(session: AsyncSession, story_id: UUID):
    return (
        await session.execute(
            select(
                Chapter.id,
                Chapter.revision,
                Chapter.word_count,
                Chapter.index_status,
                Chapter.index_error,
                Chapter.bible_scan_revision,
                Chapter.bible_scan_error,
            )
            .where(Chapter.story_id == story_id, Chapter.deleted_at.is_(None))
            .order_by(Chapter.position)
        )
    ).all()


def active_chapters(story: Story) -> list[Chapter]:
    return [chapter for chapter in story.chapters if chapter.deleted_at is None]


def touch(story: Story) -> None:
    story.updated_at = datetime.now(UTC)
