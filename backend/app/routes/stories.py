"""Story endpoints: list, create, detail, update, and index status."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User
from app.models.story_models import Story
from app.schemas.chapters import ChapterIndexRowOut, ChapterIndexStatusOut, ChapterSummaryOut
from app.schemas.stories import (
    StoryCreate,
    StoryDetailsOut,
    StoryListOut,
    StoryOut,
    StorySummaryOut,
    StoryUpdate,
)
from app.security import get_current_user
from app.services import jobs as jobs_service
from app.services import stories as stories_service
from app.services.audit import record_audit
from app.services.trash import trash_story

router = APIRouter(prefix="/stories", tags=["stories"])

# A novel has hundreds of chapters, not millions. Above this the detail payload
# is truncated and ``chapters_truncated`` tells the client to fetch in pages.
CHAPTER_LIST_CAP = 2000


def _summary(story: Story, chapter_count: int, word_count: int) -> StorySummaryOut:
    fields = StoryOut.model_validate(story).model_dump()
    return StorySummaryOut(
        **fields,
        chapter_count=chapter_count,
        word_count=word_count,
        chapter_warning_at=settings.STORY_CHAPTER_WARNING,
    )


@router.get("", response_model=StoryListOut)
async def list_stories(
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryListOut:
    rows, next_cursor = await stories_service.list_story_rows(
        session, user.id, limit=limit, cursor=cursor
    )
    return StoryListOut(
        stories=[_summary(story, count, words) for story, count, words in rows],
        next_cursor=next_cursor,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=StoryOut)
async def create_story(
    payload: StoryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Story:
    return await stories_service.create_story(session, user.id, payload.title)


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    story = await stories_service.owned_story(session, story_id, user.id)
    await trash_story(session, story)
    record_audit(
        session,
        "story_trashed",
        user_id=user.id,
        email=user.email,
        target_type="story",
        target_id=str(story.id),
        detail={"title": story.title},
        request=request,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{story_id}", response_model=StoryDetailsOut)
async def get_story(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryDetailsOut:
    story = await stories_service.load_story_detail(session, story_id, user.id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found.")
    chapters = stories_service.active_chapters(story)
    summary = _summary(
        story,
        chapter_count=len(chapters),
        word_count=sum(chapter.word_count for chapter in chapters),
    )
    return StoryDetailsOut(
        **summary.model_dump(),
        chapters=[
            ChapterSummaryOut.model_validate(chapter)
            for chapter in chapters[:CHAPTER_LIST_CAP]
        ],
        chapters_truncated=len(chapters) > CHAPTER_LIST_CAP,
    )


@router.get("/{story_id}/index-status", response_model=ChapterIndexStatusOut)
async def get_story_index_status(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterIndexStatusOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await stories_service.index_status_rows(session, story_id)
    return ChapterIndexStatusOut(
        chapters=[ChapterIndexRowOut.model_validate(row) for row in rows],
        worker_alive=await jobs_service.worker_is_alive(session),
    )


@router.patch("/{story_id}", response_model=StoryOut)
async def update_story(
    story_id: UUID,
    payload: StoryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Story:
    story = await stories_service.owned_story(session, story_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    return await stories_service.apply_updates(session, story, changes, user.id)
