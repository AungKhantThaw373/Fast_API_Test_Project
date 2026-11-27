"""Chapter lifecycle: create, save, reorder, move, history, soft delete.

Routers stay thin; the transaction shape lives here so a route cannot forget a
flush, a renumber, or a snapshot.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import (
    Chapter,
    ChapterRevision,
    ContinuityFinding,
    ContinuityScan,
    SceneEmbedding,
    Story,
    StoryBibleEntry,
)
from app.schemas.chapters import ChapterReorder, ChapterUpdate, ManuscriptImport
from app.services.chapter_order import assign_positions, next_position, renumber_display
from app.services.snapshots import diff_revisions, record_checkpoint, record_snapshot
from app.services.stories import owned_story
from app.services.trash import trash_chapter

CHAPTER_HEADING = re.compile(r"(?im)^\s{0,3}(?:#{1,3}\s*)?Chapter\s+([\wIVXLCDM-]+)[^\n]*$")
MAX_IMPORTED_CHAPTERS = 50


class SaveConflict(Exception):
    """A save arrived with a revision the server has already moved past."""

    def __init__(self, chapter: Chapter) -> None:
        self.chapter = chapter
        super().__init__("Chapter changed since it was loaded.")


async def _reload_ordered(
    session: AsyncSession, chapter_ids: list[UUID]
) -> list[Chapter]:
    """Reload rows in one statement, in the given order.

    ``updated_at`` is a server-side ``onupdate`` column, so committing an UPDATE
    expires it; serializing an expired attribute outside the greenlet raises
    ``MissingGreenlet``. Refreshing each row worked but cost one round trip per
    chapter — 1,100 of them on a large reorder.
    """
    if not chapter_ids:
        return []
    rows = await session.scalars(
        select(Chapter)
        .where(Chapter.id.in_(chapter_ids))
        .execution_options(populate_existing=True)
    )
    by_id = {chapter.id: chapter for chapter in rows}
    return [by_id[chapter_id] for chapter_id in chapter_ids if chapter_id in by_id]


async def owned_chapter(
    session: AsyncSession, chapter_id: UUID, user_id: UUID, *, for_update: bool = False
) -> Chapter:
    query = (
        select(Chapter)
        .join(Story, Chapter.story_id == Story.id)
        .where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Story.deleted_at.is_(None),
            Story.owner_id == user_id,
        )
    )
    if for_update:
        query = query.with_for_update(of=Chapter)
    chapter = await session.scalar(query)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


INLINE_MARKUP = re.compile(r"\*\*|~~|==|<[^>]+>|\*")


def count_words(content: str) -> int:
    """Count prose words, not the Markdown/HTML used for inline styling."""
    return len(INLINE_MARKUP.sub("", content).split())


async def create_chapter(session: AsyncSession, story: Story, title: str, content: str) -> Chapter:
    chapter = Chapter(
        story_id=story.id,
        chapter_number=0,
        position=await next_position(session, story.id),
        title=title.strip() or "Untitled chapter",
        content=content,
        word_count=count_words(content),
        revision=1,
        index_status="pending",
    )
    session.add(chapter)
    story.updated_at = datetime.now(UTC)
    await session.flush()
    await renumber_display(session, story.id)
    await session.commit()
    await session.refresh(chapter)
    return chapter


def split_manuscript(filename: str, content: str) -> list[tuple[str, str]]:
    """Split a manuscript into ``(title, body)`` pairs on chapter headings."""
    matches = list(CHAPTER_HEADING.finditer(content))
    if not matches:
        title = re.sub(r"\.(txt|md|markdown)$", "", filename, flags=re.IGNORECASE).strip()
        return [(title[:200] or "Imported manuscript", content.strip())]
    chapters: list[tuple[str, str]] = []
    prefix = content[: matches[0].start()].strip()
    if prefix:
        chapters.append(("Opening", prefix))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        title = match.group(0).strip().lstrip("# ").strip()[:200]
        body = content[match.end() : end].strip()
        chapters.append((title or f"Chapter {index + 1}", body))
    return [(title, text) for title, text in chapters if text][:MAX_IMPORTED_CHAPTERS]


async def import_manuscript(
    session: AsyncSession, story: Story, payload: ManuscriptImport
) -> list[Chapter]:
    parts = split_manuscript(payload.filename, payload.content)
    if not parts:
        raise HTTPException(
            status_code=400, detail="No chapter text could be found in that manuscript."
        )
    position = await next_position(session, story.id)
    created = []
    for offset, (title, content) in enumerate(parts):
        chapter = Chapter(
            story_id=story.id,
            chapter_number=0,
            position=position + offset * 1024.0,
            title=title,
            content=content,
            word_count=count_words(content),
            revision=1,
            index_status="pending",
        )
        session.add(chapter)
        created.append(chapter)
    story.updated_at = datetime.now(UTC)
    await session.flush()
    await renumber_display(session, story.id)
    created_ids = [chapter.id for chapter in created]
    await session.commit()
    return await _reload_ordered(session, created_ids)


async def _drop_stale_suggestions(session: AsyncSession, chapter: Chapter) -> None:
    """Delete AI suggestions whose quote no longer exists in the chapter."""
    suggestions = await session.scalars(
        select(StoryBibleEntry).where(
            StoryBibleEntry.source_chapter_id == chapter.id,
            StoryBibleEntry.status == "suggested",
        )
    )
    for suggestion in suggestions:
        if suggestion.source_quote and suggestion.source_quote not in (chapter.content or ""):
            await session.delete(suggestion)


async def save_chapter(
    session: AsyncSession, chapter_id: UUID, user_id: UUID, payload: ChapterUpdate
) -> tuple[Chapter, bool]:
    """Apply an autosave. Returns the chapter and whether anything changed.

    Raises ``SaveConflict`` when ``expected_revision`` is stale so the route can
    return the current server copy with the 409.
    """
    chapter = await owned_chapter(session, chapter_id, user_id, for_update=True)

    # A retried save (timeout, flaky network) must not create a second revision.
    if payload.client_save_id and chapter.last_client_save_id == payload.client_save_id:
        return chapter, False

    if payload.expected_revision != chapter.revision:
        raise SaveConflict(chapter)

    changes = payload.model_dump(
        exclude={"expected_revision", "client_save_id"}, exclude_unset=True
    )
    if "title" in changes:
        changes["title"] = (changes["title"] or "").strip() or "Untitled chapter"
    changed = any(getattr(chapter, field) != value for field, value in changes.items())
    if changed:
        # Snapshot the pre-change text, then apply the change.
        await record_snapshot(session, chapter, kind="autosave")
        for field, value in changes.items():
            setattr(chapter, field, value)
        chapter.revision += 1
        chapter.last_client_save_id = payload.client_save_id
        chapter.index_status = "pending"
        chapter.index_error = None
        if "content" in changes:
            chapter.word_count = count_words(chapter.content)
            await _drop_stale_suggestions(session, chapter)
        story = await session.get(Story, chapter.story_id)
        if story is not None:
            story.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(chapter)
    return chapter, changed


async def list_revisions(session: AsyncSession, chapter_id: UUID) -> list[ChapterRevision]:
    return list(
        await session.scalars(
            select(ChapterRevision)
            .where(ChapterRevision.chapter_id == chapter_id)
            .order_by(ChapterRevision.revision_number.desc())
        )
    )


async def create_checkpoint(
    session: AsyncSession, chapter: Chapter
) -> ChapterRevision:
    revision = await record_checkpoint(session, chapter)
    await session.commit()
    await session.refresh(revision)
    return revision


async def revision_diff(
    session: AsyncSession, chapter_id: UUID, older: int, newer: int
) -> tuple[ChapterRevision, ChapterRevision, list[dict]]:
    revisions = {
        item.revision_number: item
        for item in await session.scalars(
            select(ChapterRevision).where(
                ChapterRevision.chapter_id == chapter_id,
                ChapterRevision.revision_number.in_({older, newer}),
            )
        )
    }
    if older not in revisions or newer not in revisions:
        raise HTTPException(
            status_code=404, detail="One of those versions could not be found."
        )
    return revisions[older], revisions[newer], diff_revisions(revisions[older], revisions[newer])


async def restore_revision(
    session: AsyncSession, chapter: Chapter, revision_number: int
) -> Chapter:
    snapshot = await session.scalar(
        select(ChapterRevision).where(
            ChapterRevision.chapter_id == chapter.id,
            ChapterRevision.revision_number == revision_number,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="That saved version could not be found.")
    # Keep the pre-restore draft, pinned so retention never prunes it.
    await record_snapshot(session, chapter, kind="restore")
    chapter.title = snapshot.title
    chapter.content = snapshot.content
    chapter.word_count = snapshot.word_count
    chapter.revision += 1
    chapter.index_status = "pending"
    chapter.index_error = None
    await session.commit()
    await session.refresh(chapter)
    return chapter


async def reorder_chapters(
    session: AsyncSession, story: Story, payload: ChapterReorder
) -> list[Chapter]:
    chapters = list(
        await session.scalars(
            select(Chapter)
            .where(Chapter.story_id == story.id, Chapter.deleted_at.is_(None))
            .order_by(Chapter.position)
        )
    )
    by_id = {chapter.id: chapter for chapter in chapters}
    if len(payload.chapter_ids) != len(chapters) or set(payload.chapter_ids) != set(by_id):
        raise HTTPException(
            status_code=422, detail="Include every chapter exactly once when reordering."
        )
    ordered = [by_id[item] for item in payload.chapter_ids]
    # One bulk position rewrite, then two bulk statements for display numbers.
    await assign_positions(session, ordered)
    await session.flush()
    await renumber_display(session, story.id)
    # Cached findings compare against the old order, so they no longer hold.
    await session.execute(delete(ContinuityScan).where(ContinuityScan.story_id == story.id))
    story.updated_at = datetime.now(UTC)
    ordered_ids = [chapter.id for chapter in ordered]
    await session.commit()
    return await _reload_ordered(session, ordered_ids)


async def move_chapter(
    session: AsyncSession, chapter_id: UUID, user_id: UUID, destination_story_id: UUID
) -> tuple[Story, Chapter]:
    chapter = await owned_chapter(session, chapter_id, user_id)
    source_story = await owned_story(session, chapter.story_id, user_id)
    destination = await owned_story(session, destination_story_id, user_id)
    if source_story.id == destination.id:
        return destination, chapter

    entries = list(
        await session.scalars(
            select(StoryBibleEntry).where(StoryBibleEntry.source_chapter_id == chapter.id)
        )
    )
    for entry in entries:
        collision = await session.scalar(
            select(StoryBibleEntry.id).where(
                StoryBibleEntry.story_id == destination.id,
                StoryBibleEntry.category == entry.category,
                StoryBibleEntry.canonical_name == entry.canonical_name,
            )
        )
        if collision:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Destination already has a Story Bible entry named {entry.name}. "
                    "Resolve that duplicate before moving this chapter."
                ),
            )

    source_chapters = list(
        await session.scalars(
            select(Chapter).where(Chapter.story_id == source_story.id).order_by(Chapter.position)
        )
    )
    for item in source_chapters:
        if item.id != chapter.id:
            item.chapter_number = -item.chapter_number
    await session.flush()

    # Findings from the moved chapter use a different story timeline; findings in
    # source chapters that cite it also become invalid.
    await session.execute(delete(ContinuityScan).where(ContinuityScan.story_id == source_story.id))
    await session.execute(
        delete(ContinuityFinding).where(ContinuityFinding.earlier_chapter_id == chapter.id)
    )
    # Park the chapter on a temporary number before changing its story: the
    # destination may already own its display number, and the unique index is
    # checked per row.
    chapter.chapter_number = -1_000_000 - int(uuid4().int % 900_000)
    chapter.story_id = destination.id
    chapter.position = await next_position(session, destination.id)
    await session.flush()
    await session.execute(
        update(SceneEmbedding)
        .where(SceneEmbedding.chapter_id == chapter.id)
        .values(story_id=destination.id)
    )
    for entry in entries:
        entry.story_id = destination.id

    await renumber_display(session, source_story.id)
    await renumber_display(session, destination.id)
    await session.refresh(chapter)
    now = datetime.now(UTC)
    source_story.updated_at = destination.updated_at = now
    await session.commit()
    await session.refresh(chapter)
    return destination, chapter


async def delete_chapter(session: AsyncSession, chapter: Chapter) -> list[Chapter]:
    story_id = chapter.story_id

    # Soft delete: the text stays recoverable from the trash for 30 days.
    await trash_chapter(session, chapter)
    await session.flush()
    await session.execute(
        delete(ContinuityFinding).where(ContinuityFinding.earlier_chapter_id == chapter.id)
    )

    # One bulk statement pair instead of an UPDATE per chapter.
    await renumber_display(session, story_id)
    remaining = list(
        await session.scalars(
            select(Chapter)
            .where(Chapter.story_id == story_id, Chapter.deleted_at.is_(None))
            .order_by(Chapter.position)
        )
    )

    story = await session.get(Story, story_id)
    if story is not None:
        story.updated_at = datetime.now(UTC)
    remaining_ids = [item.id for item in remaining]
    await session.commit()
    return await _reload_ordered(session, remaining_ids)


async def mark_for_reindex(session: AsyncSession, chapter: Chapter) -> Chapter:
    chapter.index_status = "pending"
    chapter.index_error = None
    await session.commit()
    return chapter
