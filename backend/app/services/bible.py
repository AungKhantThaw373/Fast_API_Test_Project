"""Story Bible reads and edits.

The knowledge model v2 (entities, facts, mentions) arrives in Phase 3. Until
then these functions are the single place that touches ``story_bible_entries``.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, Story, StoryBibleEntry
from app.schemas.bible import BibleEntryUpdate
from app.services.ai_settings import has_ai_config
from app.services.pagination import (
    clamp_limit,
    cursor_text,
    cursor_uuid,
    decode_cursor,
    encode_cursor,
    keyset_predicate,
)


@dataclass(frozen=True)
class BibleScanSelection:
    selected: list[tuple[UUID, int]]
    in_range: int
    skipped: int


async def list_entries(
    session: AsyncSession,
    story_id: UUID,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> tuple[list[StoryBibleEntry], str | None]:
    page_size = clamp_limit(limit, default=500, maximum=2000)
    columns = (
        StoryBibleEntry.status,
        StoryBibleEntry.category,
        StoryBibleEntry.name,
        StoryBibleEntry.id,
    )
    query = select(StoryBibleEntry).where(StoryBibleEntry.story_id == story_id)
    if cursor:
        values = decode_cursor(cursor, [cursor_text, cursor_text, cursor_text, cursor_uuid])
        query = query.where(keyset_predicate(columns, values, descending=False))
    entries = list(
        await session.scalars(query.order_by(*columns).limit(page_size + 1))
    )
    next_cursor = None
    if len(entries) > page_size:
        entries = entries[:page_size]
        last = entries[-1]
        next_cursor = encode_cursor((last.status, last.category, last.name, last.id))
    return entries, next_cursor


async def owned_entry(session: AsyncSession, entry_id: UUID, user_id: UUID) -> StoryBibleEntry:
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(StoryBibleEntry.id == entry_id, Story.owner_id == user_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Story Bible entry not found.")
    return entry


async def owned_thread(session: AsyncSession, entry_id: UUID, user_id: UUID) -> StoryBibleEntry:
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(
            StoryBibleEntry.id == entry_id,
            StoryBibleEntry.category == "plot_thread",
            Story.owner_id == user_id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Plot thread not found.")
    return entry


def _clean(payload: BibleEntryUpdate) -> tuple[str, str, str]:
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="Name and description cannot be blank.")
    return name, description, name.casefold()[:220]


async def create_entry(
    session: AsyncSession, story: Story, payload: BibleEntryUpdate
) -> StoryBibleEntry:
    name, description, canonical_name = _clean(payload)
    entry = StoryBibleEntry(
        story_id=story.id,
        category=payload.category,
        name=name,
        canonical_name=canonical_name,
        description=description,
        status="accepted",
        thread_state="open" if payload.category == "plot_thread" else None,
        details=payload.details,
    )
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="An entry with this category and name already exists."
        ) from None
    await session.refresh(entry)
    return entry


async def update_entry(
    session: AsyncSession, entry: StoryBibleEntry, payload: BibleEntryUpdate
) -> StoryBibleEntry:
    name, description, canonical_name = _clean(payload)
    duplicate = await session.scalar(
        select(StoryBibleEntry.id).where(
            StoryBibleEntry.story_id == entry.story_id,
            StoryBibleEntry.category == payload.category,
            StoryBibleEntry.canonical_name == canonical_name,
            StoryBibleEntry.id != entry.id,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409, detail="An entry with this category and name already exists."
        )
    entry.category = payload.category
    entry.name = name
    entry.canonical_name = canonical_name
    entry.description = description
    entry.details = payload.details
    if payload.category == "plot_thread":
        entry.thread_state = entry.thread_state or "open"
    else:
        entry.thread_state = None
    await session.commit()
    await session.refresh(entry)
    return entry


async def decide_entry(
    session: AsyncSession, entry: StoryBibleEntry, status: str
) -> StoryBibleEntry:
    if entry.status != "suggested":
        raise HTTPException(
            status_code=409, detail="This suggestion has already been reviewed."
        )
    entry.status = status
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_entry(session: AsyncSession, entry: StoryBibleEntry) -> None:
    await session.delete(entry)
    await session.commit()


async def set_thread_state(
    session: AsyncSession, entry: StoryBibleEntry, state: str
) -> StoryBibleEntry:
    entry.thread_state = state
    await session.commit()
    await session.refresh(entry)
    return entry


async def select_scan_range(
    session: AsyncSession,
    story: Story,
    user_id: UUID,
    *,
    start_chapter: int,
    end_chapter: int,
    force: bool,
) -> BibleScanSelection:
    """Pick the chapters that still need extraction and clear their error state."""
    if start_chapter > end_chapter:
        raise HTTPException(
            status_code=422,
            detail="The first chapter must be before or equal to the last chapter.",
        )
    chapters = list(
        (
            await session.execute(
                select(Chapter.id, Chapter.revision, Chapter.bible_scan_revision, Chapter.content)
                .where(
                    Chapter.story_id == story.id,
                    Chapter.deleted_at.is_(None),
                    Chapter.chapter_number >= start_chapter,
                    Chapter.chapter_number <= end_chapter,
                )
                .order_by(Chapter.position)
            )
        ).all()
    )
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters were found in that range.")

    nonempty = [row for row in chapters if row.content.strip()]
    if force:
        selected = nonempty
    else:
        selected = [row for row in nonempty if row.bible_scan_revision != row.revision]

    if selected and not await has_ai_config(session, user_id):
        raise HTTPException(
            status_code=503,
            detail="Configure an AI provider before scanning the Story Bible.",
        )

    if selected:
        values = {"bible_scan_error": None}
        if force:
            values["bible_scan_revision"] = None
        await session.execute(
            update(Chapter)
            .where(Chapter.id.in_([chapter.id for chapter in selected]))
            .values(**values)
        )
        await session.commit()

    selection: BibleScanSelection = BibleScanSelection(
        selected=[(chapter.id, chapter.revision) for chapter in selected],
        in_range=len(chapters),
        skipped=len(chapters) - len(selected),
    )
    return selection
