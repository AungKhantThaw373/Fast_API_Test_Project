"""Recap endpoints: chapter synopsis editing, arc summaries, and Story so far."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.schemas.recaps import (
    ArcSummaryOut,
    ChapterSynopsisOut,
    ChapterSynopsisUpdate,
    StorySoFarOut,
)
from app.security import get_current_user
from app.services import chapters as chapters_service
from app.services import recaps as recaps_service
from app.services import stories as stories_service

router = APIRouter(prefix="/stories", tags=["recaps"])


@router.get("/chapters/{chapter_id}/synopsis", response_model=ChapterSynopsisOut)
async def get_chapter_synopsis(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterSynopsisOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    return await recaps_service.chapter_synopsis(session, chapter)


@router.put("/chapters/{chapter_id}/synopsis", response_model=ChapterSynopsisOut)
async def update_chapter_synopsis(
    chapter_id: UUID,
    payload: ChapterSynopsisUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterSynopsisOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    return await recaps_service.save_synopsis(session, chapter, payload.synopsis)


@router.post("/chapters/{chapter_id}/synopsis/generate", response_model=ChapterSynopsisOut)
async def generate_chapter_synopsis(
    chapter_id: UUID,
    overwrite: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterSynopsisOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    return await recaps_service.generate_synopsis(session, chapter, overwrite=overwrite)


@router.post("/{story_id}/arcs/{arc_id}/summary/generate", response_model=ArcSummaryOut)
async def generate_arc_summary(
    story_id: UUID,
    arc_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ArcSummaryOut:
    arc = await recaps_service.owned_arc(session, arc_id, story_id, user.id)
    return await recaps_service.generate_arc_summary(session, arc)


@router.get("/{story_id}/recap", response_model=StorySoFarOut)
async def story_so_far(
    story_id: UUID,
    limit: int = Query(default=5, ge=1, le=30),
    arc_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StorySoFarOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    return await recaps_service.story_so_far(session, story, limit=limit, arc_id=arc_id)