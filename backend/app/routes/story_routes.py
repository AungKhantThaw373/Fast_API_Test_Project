import asyncio
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.logging_config import fields, get_logger
from app.models.app_models import User
from app.models.story_models import (
    Chapter,
    ChapterRevision,
    ContinuityFinding,
    ContinuityScan,
    SceneEmbedding,
    Story,
    StoryBibleEntry,
)
from app.schemas.stories import (
    BibleDecision,
    BibleEntryCreate,
    BibleEntryUpdate,
    BibleScanRange,
    ChapterCreate,
    ChapterMove,
    ChapterReorder,
    ChapterUpdate,
    CheckpointCreate,
    FindingReviewUpdate,
    IntentionalUpdate,
    ManuscriptImport,
    StoryCreate,
    StoryUpdate,
    ThreadUpdate,
)
from app.security import get_current_user
from app.services.ai_service import AIProviderHTTPError
from app.services.ai_settings import has_ai_config
from app.services.chapter_order import (
    assign_positions,
    next_position,
    renumber_display,
)
from app.services.continuity import scan_chapter
from app.services.indexing import schedule_bible_extraction, schedule_chapter_reindex
from app.services.snapshots import diff_revisions, record_checkpoint, record_snapshot
from app.services.trash import trash_chapter, trash_story

logger = get_logger("api")
router = APIRouter(prefix="/stories", tags=["writing studio"])
_continuity_locks: dict[UUID, asyncio.Lock] = {}
CHAPTER_HEADING = re.compile(r"(?im)^\s{0,3}(?:#{1,3}\s*)?Chapter\s+([\wIVXLCDM-]+)[^\n]*$")


def _story_data(story: Story) -> dict:
    return {
        "id": str(story.id),
        "title": story.title,
        "collection_name": story.collection_name,
        "scan_interval_words": story.scan_interval_words,
        "external_analysis_enabled": story.external_analysis_enabled,
        "created_at": story.created_at.isoformat(),
        "updated_at": story.updated_at.isoformat(),
        "deleted_at": story.deleted_at.isoformat() if story.deleted_at else None,
    }


def _chapter_data(chapter: Chapter, include_content: bool = True) -> dict:
    result = {
        "id": str(chapter.id),
        "story_id": str(chapter.story_id),
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "word_count": chapter.word_count,
        "revision": chapter.revision,
        "bible_scan_revision": chapter.bible_scan_revision,
        "bible_scan_error": chapter.bible_scan_error,
        "index_status": chapter.index_status,
        "index_error": chapter.index_error,
        "updated_at": chapter.updated_at.isoformat(),
        "deleted_at": chapter.deleted_at.isoformat() if chapter.deleted_at else None,
    }
    if include_content:
        result["content"] = chapter.content
    return result


def _entry_data(entry: StoryBibleEntry) -> dict:
    return {
        "id": str(entry.id),
        "category": entry.category,
        "name": entry.name,
        "description": entry.description,
        "status": entry.status,
        "thread_state": entry.thread_state,
        "confidence": entry.confidence,
        "source_chapter_id": str(entry.source_chapter_id) if entry.source_chapter_id else None,
        "source_quote": entry.source_quote,
        "details": entry.details,
        "updated_at": entry.updated_at.isoformat(),
    }


async def _owned_story(session: AsyncSession, story_id: UUID, user_id: UUID) -> Story:
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


async def _owned_chapter(session: AsyncSession, chapter_id: UUID, user_id: UUID) -> Chapter:
    chapter = await session.scalar(
        select(Chapter)
        .join(Story, Chapter.story_id == Story.id)
        .where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Story.deleted_at.is_(None),
            Story.owner_id == user_id,
        )
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


@router.get("")
async def list_stories(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = []
    rows = await session.execute(
        select(
            Story,
            func.count(Chapter.id).label("chapter_count"),
            func.coalesce(func.sum(Chapter.word_count), 0).label("word_count"),
        )
        .outerjoin(
            Chapter,
            (Chapter.story_id == Story.id) & Chapter.deleted_at.is_(None),
        )
        .where(Story.owner_id == user.id, Story.deleted_at.is_(None))
        .group_by(Story.id)
        .order_by(Story.updated_at.desc())
    )
    for story, chapter_count, word_count in rows:
        data = _story_data(story)
        data.update({"chapter_count": chapter_count or 0, "word_count": word_count or 0})
        result.append(data)
    return {"stories": result}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_story(
    payload: StoryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Story title cannot be blank.")
    story = Story(owner_id=user.id, title=title)
    session.add(story)
    await session.commit()
    await session.refresh(story)
    return _story_data(story)


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    await trash_story(session, story)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{story_id}")
async def get_story(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await session.scalar(
        select(Story)
        .where(
            Story.id == story_id,
            Story.owner_id == user.id,
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
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found.")
    active_chapters = [chapter for chapter in story.chapters if chapter.deleted_at is None]
    return {
        **_story_data(story),
        "chapter_count": len(active_chapters),
        "word_count": sum(chapter.word_count for chapter in active_chapters),
        "chapters": [
            _chapter_data(chapter, include_content=False) for chapter in active_chapters
        ],
    }


@router.get("/{story_id}/index-status")
async def get_story_index_status(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _owned_story(session, story_id, user.id)
    rows = await session.execute(
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
    return {
        "chapters": [
            {"id": str(row.id), "revision": row.revision, "word_count": row.word_count,
             "index_status": row.index_status, "index_error": row.index_error,
             "bible_scan_revision": row.bible_scan_revision,
             "bible_scan_error": row.bible_scan_error}
            for row in rows
        ]
    }


@router.patch("/{story_id}")
async def update_story(
    story_id: UUID,
    payload: StoryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "external_analysis_enabled" in changes and changes["external_analysis_enabled"]:
        if not await has_ai_config(session, user.id):
            raise HTTPException(status_code=503, detail="Configure an AI provider in Settings → AI before enabling analysis.")
    for field, value in changes.items():
        if field == "title":
            value = value.strip() if value else ""
            if not value:
                raise HTTPException(status_code=422, detail="Story title cannot be blank.")
        if field == "collection_name":
            value = (value or "").strip()
        setattr(story, field, value)
    await session.commit()
    await session.refresh(story)
    return _story_data(story)


@router.post("/{story_id}/chapters", status_code=status.HTTP_201_CREATED)
async def create_chapter(
    story_id: UUID,
    payload: ChapterCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    position = await next_position(session, story.id)
    chapter = Chapter(
        story_id=story.id,
        chapter_number=0,
        position=position,
        title=payload.title.strip() or "Untitled chapter",
        content=payload.content,
        word_count=len(payload.content.split()),
        revision=1,
        index_status="pending",
    )
    session.add(chapter)
    story.updated_at = datetime.now(UTC)
    await session.flush()
    await renumber_display(session, story.id)
    await session.commit()
    await session.refresh(chapter)
    background_tasks.add_task(schedule_chapter_reindex, chapter.id)
    return _chapter_data(chapter)


def _split_manuscript(filename: str, content: str) -> list[tuple[str, str]]:
    matches = list(CHAPTER_HEADING.finditer(content))
    if not matches:
        title = re.sub(r"\.(txt|md|markdown)$", "", filename, flags=re.IGNORECASE).strip() or "Imported manuscript"
        return [(title[:200], content.strip())]
    chapters: list[tuple[str, str]] = []
    prefix = content[: matches[0].start()].strip()
    if prefix:
        chapters.append(("Opening", prefix))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        title = match.group(0).strip().lstrip("# ").strip()[:200]
        body = content[match.end() : end].strip()
        chapters.append((title or f"Chapter {index + 1}", body))
    return [(title, text) for title, text in chapters if text][:50]


@router.post("/{story_id}/import", status_code=status.HTTP_201_CREATED)
async def import_manuscript(
    story_id: UUID,
    payload: ManuscriptImport,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    parts = _split_manuscript(payload.filename, payload.content)
    if not parts:
        raise HTTPException(status_code=400, detail="No chapter text could be found in that manuscript.")
    position = await next_position(session, story.id)
    created = []
    for offset, (title, content) in enumerate(parts):
        chapter = Chapter(
            story_id=story.id,
            chapter_number=0,
            position=position + offset * 1024.0,
            title=title,
            content=content,
            word_count=len(content.split()),
            revision=1,
            index_status="pending",
        )
        session.add(chapter)
        created.append(chapter)
    story.updated_at = datetime.now(UTC)
    await session.flush()
    await renumber_display(session, story.id)
    await session.commit()
    for chapter in created:
        await session.refresh(chapter)
        background_tasks.add_task(schedule_chapter_reindex, chapter.id)
    return {"chapters": [_chapter_data(chapter, include_content=False) for chapter in created]}


@router.put("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: UUID,
    payload: ChapterUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await session.scalar(
        select(Chapter).join(Story, Chapter.story_id == Story.id)
        .where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Story.deleted_at.is_(None),
            Story.owner_id == user.id,
        )
        .with_for_update(of=Chapter)
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    # A retried save (timeout, flaky network) must not create a second revision.
    if payload.client_save_id and chapter.last_client_save_id == payload.client_save_id:
        return _chapter_data(chapter)

    if payload.expected_revision != chapter.revision:
        # Return everything the conflict dialog needs so the writer does not wait
        # for another round trip to see the saved version.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This chapter changed since it was loaded. Reload before saving.",
                "current_revision": chapter.revision,
                "current_title": chapter.title,
                "current_content": chapter.content,
                "updated_at": chapter.updated_at.isoformat(),
            },
        )

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
            chapter.word_count = len(chapter.content.split())
            suggestions = await session.scalars(
                select(StoryBibleEntry).where(
                    StoryBibleEntry.source_chapter_id == chapter.id,
                    StoryBibleEntry.status == "suggested",
                )
            )
            for suggestion in suggestions:
                if suggestion.source_quote and suggestion.source_quote not in (chapter.content or ""):
                    await session.delete(suggestion)
        story = await session.get(Story, chapter.story_id)
        if story is not None:
            story.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(chapter)
    if changed:
        background_tasks.add_task(schedule_chapter_reindex, chapter.id)
    return _chapter_data(chapter)


@router.get("/chapters/{chapter_id}/revisions")
async def list_chapter_revisions(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _owned_chapter(session, chapter_id, user.id)
    revisions = await session.scalars(
        select(ChapterRevision)
        .where(ChapterRevision.chapter_id == chapter_id)
        .order_by(ChapterRevision.revision_number.desc())
    )
    return {"revisions": [{
        "revision_number": item.revision_number,
        "title": item.title,
        "word_count": item.word_count,
        "kind": item.kind,
        "char_count": item.char_count,
        "created_at": item.created_at.isoformat(),
    } for item in revisions]}


@router.post("/chapters/{chapter_id}/checkpoint", status_code=status.HTTP_201_CREATED)
async def create_chapter_checkpoint(
    chapter_id: UUID,
    payload: CheckpointCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    revision = await record_checkpoint(session, chapter)
    await session.commit()
    return {
        "revision_number": revision.revision_number,
        "kind": revision.kind,
        "word_count": revision.word_count,
        "char_count": revision.char_count,
        "created_at": revision.created_at.isoformat(),
        "label": payload.label,
    }


@router.get("/chapters/{chapter_id}/revisions/{older}/diff/{newer}")
async def diff_chapter_revisions(
    chapter_id: UUID,
    older: int,
    newer: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _owned_chapter(session, chapter_id, user.id)
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
        raise HTTPException(status_code=404, detail="One of those versions could not be found.")
    hunks = diff_revisions(revisions[older], revisions[newer])
    return {
        "older": {
            "revision_number": older,
            "word_count": revisions[older].word_count,
            "kind": revisions[older].kind,
            "created_at": revisions[older].created_at.isoformat(),
        },
        "newer": {
            "revision_number": newer,
            "word_count": revisions[newer].word_count,
            "kind": revisions[newer].kind,
            "created_at": revisions[newer].created_at.isoformat(),
        },
        "hunks": hunks,
    }


@router.post("/chapters/{chapter_id}/revisions/{revision_number}/restore")
async def restore_chapter_revision(
    chapter_id: UUID,
    revision_number: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await session.scalar(
        select(Chapter).join(Story, Chapter.story_id == Story.id)
        .where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Story.deleted_at.is_(None),
            Story.owner_id == user.id,
        )
        .with_for_update(of=Chapter)
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    snapshot = await session.scalar(select(ChapterRevision).where(
        ChapterRevision.chapter_id == chapter.id,
        ChapterRevision.revision_number == revision_number,
    ))
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
    background_tasks.add_task(schedule_chapter_reindex, chapter.id)
    return _chapter_data(chapter)


@router.put("/{story_id}/chapters/order")
async def reorder_chapters(
    story_id: UUID,
    payload: ChapterReorder,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    chapters = list(await session.scalars(
        select(Chapter)
        .where(Chapter.story_id == story.id, Chapter.deleted_at.is_(None))
        .order_by(Chapter.position)
    ))
    by_id = {chapter.id: chapter for chapter in chapters}
    if len(payload.chapter_ids) != len(chapters) or set(payload.chapter_ids) != set(by_id):
        raise HTTPException(status_code=422, detail="Include every chapter exactly once when reordering.")
    ordered = [by_id[item] for item in payload.chapter_ids]
    # One bulk position rewrite, then two bulk statements for display numbers.
    await assign_positions(session, ordered)
    await session.flush()
    await renumber_display(session, story.id)
    await session.execute(delete(ContinuityScan).where(ContinuityScan.story_id == story.id))
    story.updated_at = datetime.now(UTC)
    await session.commit()
    # ``updated_at`` is a server-side onupdate column, so committing an UPDATE
    # expires it. Reload before serializing or the response touches expired
    # attributes outside the greenlet and fails.
    for chapter in ordered:
        await session.refresh(chapter)
    return {"chapters": [_chapter_data(chapter, include_content=False) for chapter in ordered]}


@router.post("/chapters/{chapter_id}/move")
async def move_chapter(
    chapter_id: UUID,
    payload: ChapterMove,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    source_story = await _owned_story(session, chapter.story_id, user.id)
    destination = await _owned_story(session, payload.destination_story_id, user.id)
    if source_story.id == destination.id:
        return {"story_id": str(destination.id), "chapter": _chapter_data(chapter)}

    entries = list(await session.scalars(select(StoryBibleEntry).where(
        StoryBibleEntry.source_chapter_id == chapter.id
    )))
    for entry in entries:
        collision = await session.scalar(select(StoryBibleEntry.id).where(
            StoryBibleEntry.story_id == destination.id,
            StoryBibleEntry.category == entry.category,
            StoryBibleEntry.canonical_name == entry.canonical_name,
        ))
        if collision:
            raise HTTPException(status_code=409, detail=f"Destination already has a Story Bible entry named {entry.name}. Resolve that duplicate before moving this chapter.")

    source_chapters = list(await session.scalars(select(Chapter).where(
        Chapter.story_id == source_story.id
    ).order_by(Chapter.position)))
    for item in source_chapters:
        if item.id != chapter.id:
            item.chapter_number = -item.chapter_number
    await session.flush()

    # Findings from the moved chapter use a different story timeline; findings in
    # source chapters that cite it also become invalid.
    await session.execute(delete(ContinuityScan).where(ContinuityScan.story_id == source_story.id))
    await session.execute(delete(ContinuityFinding).where(ContinuityFinding.earlier_chapter_id == chapter.id))
    # Park the chapter on a temporary number before changing its story: the
    # destination may already own its display number, and the unique index is
    # checked per row.
    chapter.chapter_number = -1_000_000 - int(uuid4().int % 900_000)
    chapter.story_id = destination.id
    chapter.position = await next_position(session, destination.id)
    await session.flush()
    await session.execute(update(SceneEmbedding).where(SceneEmbedding.chapter_id == chapter.id).values(
        story_id=destination.id
    ))
    for entry in entries:
        entry.story_id = destination.id

    await renumber_display(session, source_story.id)
    await renumber_display(session, destination.id)
    await session.refresh(chapter)
    now = datetime.now(UTC)
    source_story.updated_at = destination.updated_at = now
    await session.commit()
    await session.refresh(chapter)
    return {"story_id": str(destination.id), "chapter": _chapter_data(chapter)}


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    story_id = chapter.story_id

    # Soft delete: the text stays recoverable from the trash for 30 days.
    await trash_chapter(session, chapter)
    await session.flush()
    await session.execute(
        delete(ContinuityFinding).where(ContinuityFinding.earlier_chapter_id == chapter.id)
    )

    # One bulk statement pair instead of an UPDATE per chapter.
    await renumber_display(session, story_id)
    remaining = list(await session.scalars(
        select(Chapter)
        .where(Chapter.story_id == story_id, Chapter.deleted_at.is_(None))
        .order_by(Chapter.position)
    ))

    story = await session.get(Story, story_id)
    if story is not None:
        story.updated_at = datetime.now(UTC)
    await session.commit()
    for item in remaining:
        await session.refresh(item)
    return {"chapters": [_chapter_data(item, include_content=False) for item in remaining]}


@router.get("/chapters/{chapter_id}/status")
async def get_chapter_status(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    return {
        "id": str(chapter.id),
        "revision": chapter.revision,
        "bible_scan_revision": chapter.bible_scan_revision,
        "bible_scan_error": chapter.bible_scan_error,
        "word_count": chapter.word_count,
        "index_status": chapter.index_status,
        "index_error": chapter.index_error,
    }


@router.post("/chapters/{chapter_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def retry_chapter_index(
    chapter_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    chapter.index_status = "pending"
    chapter.index_error = None
    await session.commit()
    background_tasks.add_task(schedule_chapter_reindex, chapter.id)
    return {"id": str(chapter.id), "index_status": chapter.index_status}


@router.get("/chapters/{chapter_id}")
async def get_chapter(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    return _chapter_data(chapter)


@router.get("/chapters/{chapter_id}/scan")
async def get_latest_scan(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    scan = await session.scalar(
        select(ContinuityScan)
        .where(ContinuityScan.chapter_id == chapter.id)
        .order_by(ContinuityScan.created_at.desc())
    )
    if scan is None:
        return {"scan": None, "findings": []}
    findings = list(await session.scalars(
        select(ContinuityFinding)
        .where(ContinuityFinding.scan_id == scan.id)
        .order_by(ContinuityFinding.draft_line)
    ))
    chapters = {
        str(chapter.id): chapter.title
        for chapter in await session.scalars(
            select(Chapter).where(Chapter.id.in_([item.earlier_chapter_id for item in findings if item.earlier_chapter_id]))
        )
    }
    return {
        "scan": {
            "id": str(scan.id),
            "chapter_revision": scan.chapter_revision,
            "chapter_word_count": scan.chapter_word_count,
            "created_at": scan.created_at.isoformat(),
        },
        "findings": [
            {
                "id": str(item.id),
                "draft_quote": item.draft_quote,
                "draft_line": item.draft_line,
                "earlier_quote": item.earlier_quote,
                "earlier_chapter_id": str(item.earlier_chapter_id) if item.earlier_chapter_id else None,
                "earlier_chapter_number": item.earlier_chapter_number,
                "earlier_chapter_title": chapters.get(str(item.earlier_chapter_id), "Earlier chapter"),
                "explanation": item.explanation,
                "confidence": item.confidence,
                "intentional": item.intentional,
                "review_status": item.review_status,
            }
            for item in findings
        ],
    }


@router.post("/chapters/{chapter_id}/scan")
async def check_chapter_continuity(
    chapter_id: UUID,
    force: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _owned_chapter(session, chapter_id, user.id)
    story = await _owned_story(session, chapter.story_id, user.id)
    if not story.external_analysis_enabled:
        raise HTTPException(status_code=403, detail="Enable external analysis in story settings before scanning.")
    if not await has_ai_config(session, user.id):
        raise HTTPException(status_code=503, detail="Configure an AI provider in Settings → AI before scanning.")
    if not chapter.content.strip():
        raise HTTPException(status_code=400, detail="Write some draft text before checking continuity.")
    if chapter.index_status != "indexed":
        raise HTTPException(status_code=409, detail="This chapter is still being indexed. Try the check again shortly.")
    earlier_chapters = await session.scalar(
        select(func.count(Chapter.id)).where(
            Chapter.story_id == story.id,
            Chapter.chapter_number < chapter.chapter_number,
        )
    )
    if not earlier_chapters:
        raise HTTPException(status_code=409, detail="There are no earlier chapters to compare against yet.")
    chapters_still_indexing = await session.scalar(
        select(func.count(Chapter.id)).where(
            Chapter.story_id == story.id,
            Chapter.chapter_number < chapter.chapter_number,
            Chapter.index_status != "indexed",
        )
    )
    if chapters_still_indexing:
        raise HTTPException(status_code=409, detail="Wait for all earlier chapters to finish indexing before checking continuity.")
    earlier_count = await session.scalar(
        select(func.count(SceneEmbedding.id))
        .join(Chapter, SceneEmbedding.chapter_id == Chapter.id)
        .where(
            SceneEmbedding.story_id == story.id,
            SceneEmbedding.chapter_number < chapter.chapter_number,
            Chapter.index_status == "indexed",
        )
    )
    if not earlier_count:
        raise HTTPException(status_code=409, detail="Earlier chapters do not contain searchable text yet.")

    previous = await session.scalar(
        select(ContinuityScan)
        .where(ContinuityScan.chapter_id == chapter.id)
        .order_by(ContinuityScan.created_at.desc())
    )
    if previous and previous.chapter_revision == chapter.revision and not force:
        # Reuse only while the evidence set is unchanged. Editing an earlier chapter
        # invalidates the cached result even when this draft itself was not touched.
        earlier_changed_at = await session.scalar(
            select(func.max(Chapter.updated_at)).where(
                Chapter.story_id == story.id,
                Chapter.chapter_number < chapter.chapter_number,
            )
        )
        if earlier_changed_at is None or earlier_changed_at <= previous.created_at:
            logger.info(
                "[continuity] reuse  %s",
                fields(chapter=str(chapter.id)[:8], revision=chapter.revision, scan=str(previous.id)[:8], findings=previous.finding_count),
            )
            return {
                "scan_id": str(previous.id),
                "finding_count": previous.finding_count,
                "chapter_revision": previous.chapter_revision,
                "reused": True,
            }
        logger.info(
            "[continuity] rerun  %s",
            fields(chapter=str(chapter.id)[:8], revision=chapter.revision, reason="earlier_chapters_edited"),
        )

    # One provider request per chapter at a time. A second press while a slow
    # model is still answering used to start a duplicate check and double both
    # the wait and the token cost.
    lock = _continuity_locks.setdefault(chapter.id, asyncio.Lock())
    if lock.locked():
        logger.info(
            "[continuity] busy   %s",
            fields(chapter=str(chapter.id)[:8], revision=chapter.revision),
        )
        raise HTTPException(
            status_code=409,
            detail="A continuity check is already running for this chapter. Wait for it to finish before starting another.",
        )
    await lock.acquire()
    try:
        # A request that arrived while the lock was free may still find a stored
        # scan for this revision, so check the cache again inside the lock.
        stored = await session.scalar(
            select(ContinuityScan)
            .where(ContinuityScan.chapter_id == chapter.id)
            .order_by(ContinuityScan.created_at.desc())
        )
        if stored and stored.chapter_revision == chapter.revision and not force:
            earlier_changed_at = await session.scalar(
                select(func.max(Chapter.updated_at)).where(
                    Chapter.story_id == story.id,
                    Chapter.chapter_number < chapter.chapter_number,
                )
            )
            if earlier_changed_at is None or earlier_changed_at <= stored.created_at:
                logger.info(
                    "[continuity] reuse  %s",
                    fields(chapter=str(chapter.id)[:8], revision=chapter.revision, scan=str(stored.id)[:8], findings=stored.finding_count),
                )
                return {
                    "scan_id": str(stored.id),
                    "finding_count": stored.finding_count,
                    "chapter_revision": stored.chapter_revision,
                    "reused": True,
                }
        previous = stored

        try:
            draft_findings = await scan_chapter(session, story.id, chapter, user.id)
        except AIProviderHTTPError as exc:
            response_status = exc.status_code if exc.status_code in {429, 504} else 502
            logger.warning(
                "[continuity] provider error %s",
                fields(
                    chapter=str(chapter.id)[:8],
                    status=exc.status_code,
                    retry_after=exc.retry_after_seconds,
                    message=str(exc),
                ),
            )
            headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds else None
            raise HTTPException(status_code=response_status, detail=str(exc), headers=headers) from None
        except Exception as exc:
            logger.exception("[continuity] failed %s", fields(chapter=str(chapter.id)[:8], revision=chapter.revision))
            message = str(exc)
            if " returned HTTP " in message or "provider returned" in message:
                raise HTTPException(status_code=502, detail=message) from None
            raise HTTPException(status_code=503, detail="Continuity check failed. Check Ollama and your AI provider settings.") from None

        previous_reviews: dict[tuple[int, str, str], str] = {}
        if previous:
            old_findings = await session.scalars(
                select(ContinuityFinding).where(ContinuityFinding.scan_id == previous.id)
            )
            previous_reviews = {
                (item.draft_line, item.draft_quote.casefold(), item.earlier_quote.casefold()): item.review_status
                for item in old_findings
            }

        scan = ContinuityScan(
            story_id=story.id,
            chapter_id=chapter.id,
            chapter_revision=chapter.revision,
            chapter_word_count=chapter.word_count,
            finding_count=len(draft_findings),
        )
        session.add(scan)
        await session.flush()
        for item in draft_findings:
            key = (item.draft_line, item.draft_quote.casefold(), item.earlier_quote.casefold())
            session.add(
                ContinuityFinding(
                    scan_id=scan.id,
                    draft_quote=item.draft_quote,
                    draft_line=item.draft_line,
                    earlier_quote=item.earlier_quote,
                    earlier_chapter_id=item.earlier_chapter_id,
                    earlier_chapter_number=item.earlier_chapter_number,
                    explanation=item.explanation,
                    confidence=item.confidence,
                    intentional=previous_reviews.get(key) == "dismissed",
                    review_status=previous_reviews.get(key, "open"),
                )
            )
        await session.commit()
        logger.info(
            "[continuity] stored %s",
            fields(
                chapter=str(chapter.id)[:8],
                revision=chapter.revision,
                findings=len(draft_findings),
                scan=str(scan.id)[:8],
            ),
        )
        return {
            "scan_id": str(scan.id),
            "finding_count": len(draft_findings),
            "chapter_revision": chapter.revision,
            "reused": False,
        }
    finally:
        lock.release()
        if not lock.locked():
            _continuity_locks.pop(chapter.id, None)


@router.get("/{story_id}/bible")
async def get_story_bible(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _owned_story(session, story_id, user.id)
    entries = await session.scalars(
        select(StoryBibleEntry)
        .where(StoryBibleEntry.story_id == story_id)
        .order_by(StoryBibleEntry.status, StoryBibleEntry.category, StoryBibleEntry.name)
    )
    return {"entries": [_entry_data(entry) for entry in entries]}


@router.post("/{story_id}/bible", status_code=status.HTTP_201_CREATED)
async def create_bible_entry(
    story_id: UUID,
    payload: BibleEntryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="Name and description cannot be blank.")
    entry = StoryBibleEntry(
        story_id=story.id,
        category=payload.category,
        name=name,
        canonical_name=name.casefold()[:220],
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
        raise HTTPException(status_code=409, detail="An entry with this category and name already exists.") from None
    await session.refresh(entry)
    return _entry_data(entry)


@router.post("/{story_id}/bible/scan", status_code=status.HTTP_202_ACCEPTED)
async def scan_story_bible_range(
    story_id: UUID,
    payload: BibleScanRange,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _owned_story(session, story_id, user.id)
    if payload.start_chapter > payload.end_chapter:
        raise HTTPException(status_code=422, detail="The first chapter must be before or equal to the last chapter.")
    chapters = list((await session.execute(
        select(Chapter.id, Chapter.revision, Chapter.bible_scan_revision, Chapter.content)
        .where(
            Chapter.story_id == story.id,
            Chapter.deleted_at.is_(None),
            Chapter.chapter_number >= payload.start_chapter,
            Chapter.chapter_number <= payload.end_chapter,
        )
        .order_by(Chapter.position)
    )).all())
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters were found in that range.")

    nonempty_chapters = [row for row in chapters if row.content.strip()]
    if payload.force:
        selected = nonempty_chapters
    else:
        selected = [row for row in nonempty_chapters if row.bible_scan_revision != row.revision]

    if selected and not await has_ai_config(session, user.id):
        raise HTTPException(status_code=503, detail="Configure an AI provider before scanning the Story Bible.")

    if payload.force and selected:
        await session.execute(
            update(Chapter)
            .where(Chapter.id.in_([chapter.id for chapter in selected]))
            .values(bible_scan_revision=None, bible_scan_error=None)
        )
        await session.commit()
    elif selected:
        await session.execute(
            update(Chapter)
            .where(Chapter.id.in_([chapter.id for chapter in selected]))
            .values(bible_scan_error=None)
        )
        await session.commit()

    for chapter in selected:
        schedule_bible_extraction(chapter.id, chapter.revision)
    logger.info(
        "[bible] queue  %s",
        fields(
            story=str(story.id)[:8],
            start=payload.start_chapter,
            end=payload.end_chapter,
            force=payload.force,
            chapters_in_range=len(chapters),
            scheduled=len(selected),
            skipped=len(chapters) - len(selected),
        ),
    )
    return {
        "scheduled_count": len(selected),
        "skipped_count": len(chapters) - len(selected),
        "scheduled_chapters": [
            {"id": str(chapter.id), "revision": chapter.revision}
            for chapter in selected
        ],
    }


@router.patch("/bible/{entry_id}/decision")
async def decide_bible_entry(
    entry_id: UUID,
    payload: BibleDecision,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(StoryBibleEntry.id == entry_id, Story.owner_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Story Bible suggestion not found.")
    if entry.status != "suggested":
        raise HTTPException(status_code=409, detail="This suggestion has already been reviewed.")
    entry.status = payload.status
    await session.commit()
    await session.refresh(entry)
    return _entry_data(entry)


@router.put("/bible/{entry_id}")
async def edit_bible_entry(
    entry_id: UUID,
    payload: BibleEntryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(StoryBibleEntry.id == entry_id, Story.owner_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Story Bible entry not found.")
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="Name and description cannot be blank.")
    canonical_name = name.casefold()[:220]
    duplicate = await session.scalar(select(StoryBibleEntry.id).where(
        StoryBibleEntry.story_id == entry.story_id,
        StoryBibleEntry.category == payload.category,
        StoryBibleEntry.canonical_name == canonical_name,
        StoryBibleEntry.id != entry.id,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="An entry with this category and name already exists.")
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
    return _entry_data(entry)


@router.delete("/bible/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bible_entry(
    entry_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(StoryBibleEntry.id == entry_id, Story.owner_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Story Bible entry not found.")
    await session.delete(entry)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/bible/{entry_id}/thread")
async def update_plot_thread(
    entry_id: UUID,
    payload: ThreadUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    entry = await session.scalar(
        select(StoryBibleEntry)
        .join(Story, Story.id == StoryBibleEntry.story_id)
        .where(
            StoryBibleEntry.id == entry_id,
            StoryBibleEntry.category == "plot_thread",
            Story.owner_id == user.id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Plot thread not found.")
    entry.thread_state = payload.thread_state
    await session.commit()
    await session.refresh(entry)
    return _entry_data(entry)


@router.patch("/findings/{finding_id}/intentional")
async def mark_finding_intentional(
    finding_id: UUID,
    payload: IntentionalUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    finding = await session.scalar(
        select(ContinuityFinding)
        .join(ContinuityScan, ContinuityScan.id == ContinuityFinding.scan_id)
        .join(Story, Story.id == ContinuityScan.story_id)
        .where(ContinuityFinding.id == finding_id, Story.owner_id == user.id)
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Continuity flag not found.")
    finding.intentional = payload.intentional
    if payload.intentional:
        finding.review_status = "dismissed"
    elif finding.review_status == "dismissed":
        finding.review_status = "open"
    await session.commit()
    return {"id": str(finding.id), "intentional": finding.intentional}


@router.patch("/findings/{finding_id}/review")
async def review_finding(
    finding_id: UUID,
    payload: FindingReviewUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    finding = await session.scalar(
        select(ContinuityFinding)
        .join(ContinuityScan, ContinuityScan.id == ContinuityFinding.scan_id)
        .join(Story, Story.id == ContinuityScan.story_id)
        .where(ContinuityFinding.id == finding_id, Story.owner_id == user.id)
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Continuity finding not found.")
    finding.review_status = payload.review_status
    if payload.review_status == "dismissed":
        finding.intentional = True
    elif payload.review_status == "open":
        finding.intentional = False
    await session.commit()
    return {"id": str(finding.id), "review_status": finding.review_status, "intentional": finding.intentional}
