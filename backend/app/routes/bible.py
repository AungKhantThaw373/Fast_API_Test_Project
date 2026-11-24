"""Story Bible endpoints: entries, decisions, plot threads, and range scans."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.logging_config import fields, get_logger
from app.models.app_models import User
from app.models.story_models import StoryBibleEntry
from app.schemas.bible import (
    BibleDecision,
    BibleEntryCreate,
    BibleEntryOut,
    BibleEntryUpdate,
    BibleListOut,
    BibleScanOut,
    BibleScanRange,
    ScheduledBibleChapterOut,
    ThreadUpdate,
)
from app.security import get_current_user
from app.services import bible as bible_service
from app.services import indexing
from app.services import stories as stories_service

logger = get_logger("api")
router = APIRouter(prefix="/stories", tags=["bible"])


@router.get("/{story_id}/bible", response_model=BibleListOut)
async def get_story_bible(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> BibleListOut:
    await stories_service.owned_story(session, story_id, user.id)
    entries = await bible_service.list_entries(session, story_id)
    return BibleListOut(entries=[BibleEntryOut.model_validate(entry) for entry in entries])


@router.post("/{story_id}/bible", status_code=status.HTTP_201_CREATED, response_model=BibleEntryOut)
async def create_bible_entry(
    story_id: UUID,
    payload: BibleEntryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryBibleEntry:
    story = await stories_service.owned_story(session, story_id, user.id)
    return await bible_service.create_entry(session, story, payload)


@router.post("/{story_id}/bible/scan", status_code=status.HTTP_202_ACCEPTED, response_model=BibleScanOut)
async def scan_story_bible_range(
    story_id: UUID,
    payload: BibleScanRange,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> BibleScanOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    selection = await bible_service.select_scan_range(
        session,
        story,
        user.id,
        start_chapter=payload.start_chapter,
        end_chapter=payload.end_chapter,
        force=payload.force,
    )
    for chapter_id, revision in selection.selected:
        indexing.schedule_bible_extraction(chapter_id, revision)
    logger.info(
        "[bible] queue  %s",
        fields(
            story=str(story.id)[:8],
            start=payload.start_chapter,
            end=payload.end_chapter,
            force=payload.force,
            chapters_in_range=selection.in_range,
            scheduled=len(selection.selected),
            skipped=selection.skipped,
        ),
    )
    return BibleScanOut(
        scheduled_count=len(selection.selected),
        skipped_count=selection.skipped,
        scheduled_chapters=[
            ScheduledBibleChapterOut(id=chapter_id, revision=revision)
            for chapter_id, revision in selection.selected
        ],
    )


@router.patch("/bible/{entry_id}/decision", response_model=BibleEntryOut)
async def decide_bible_entry(
    entry_id: UUID,
    payload: BibleDecision,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryBibleEntry:
    entry = await bible_service.owned_entry(session, entry_id, user.id)
    return await bible_service.decide_entry(session, entry, payload.status)


@router.put("/bible/{entry_id}", response_model=BibleEntryOut)
async def edit_bible_entry(
    entry_id: UUID,
    payload: BibleEntryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryBibleEntry:
    entry = await bible_service.owned_entry(session, entry_id, user.id)
    return await bible_service.update_entry(session, entry, payload)


@router.delete("/bible/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bible_entry(
    entry_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    entry = await bible_service.owned_entry(session, entry_id, user.id)
    await bible_service.delete_entry(session, entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/bible/{entry_id}/thread", response_model=BibleEntryOut)
async def update_plot_thread(
    entry_id: UUID,
    payload: ThreadUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryBibleEntry:
    entry = await bible_service.owned_thread(session, entry_id, user.id)
    return await bible_service.set_thread_state(session, entry, payload.thread_state)
