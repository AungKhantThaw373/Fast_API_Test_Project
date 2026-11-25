"""Trash: soft-deleted stories and chapters, with restore and permanent delete."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.story_models import Chapter, Story
from app.security import get_current_user
from app.services.audit import record_audit
from app.services.trash import TRASH_RETENTION_DAYS, next_free_number

router = APIRouter(prefix="/trash", tags=["trash"])


def _chapter_row(chapter: Chapter, story_title: str) -> dict:
    return {
        "id": str(chapter.id),
        "story_id": str(chapter.story_id),
        "story_title": story_title,
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "word_count": chapter.word_count,
        "deleted_at": chapter.deleted_at.isoformat() if chapter.deleted_at else None,
    }


def _story_row(story: Story, chapter_count: int) -> dict:
    return {
        "id": str(story.id),
        "title": story.title,
        "chapter_count": chapter_count,
        "deleted_at": story.deleted_at.isoformat() if story.deleted_at else None,
    }


@router.get("")
async def list_trash(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    stories = list(
        await session.scalars(
            select(Story)
            .where(Story.owner_id == user.id, Story.deleted_at.is_not(None))
            .order_by(Story.deleted_at.desc())
        )
    )
    chapters = list(
        (
            await session.execute(
                select(Chapter, Story.title)
                .join(Story, Story.id == Chapter.story_id)
                .where(
                    Story.owner_id == user.id,
                    Story.deleted_at.is_(None),
                    Chapter.deleted_at.is_not(None),
                )
                .order_by(Chapter.deleted_at.desc())
            )
        ).all()
    )
    story_counts: dict[UUID, int] = {
        story_id: int(count)
        for story_id, count in (
            await session.execute(
                select(Chapter.story_id, func.count(Chapter.id))
                .where(Chapter.story_id.in_([story.id for story in stories] or []))
                .group_by(Chapter.story_id)
            )
        ).all()
    }
    return {
        "retention_days": TRASH_RETENTION_DAYS,
        "stories": [_story_row(story, story_counts.get(story.id, 0)) for story in stories],
        "chapters": [_chapter_row(chapter, title) for chapter, title in chapters],
    }


async def _trashed_story(session: AsyncSession, story_id: UUID, user_id: UUID) -> Story:
    story = await session.scalar(
        select(Story).where(
            Story.id == story_id,
            Story.owner_id == user_id,
            Story.deleted_at.is_not(None),
        )
    )
    if story is None:
        raise HTTPException(status_code=404, detail="That story is not in the trash.")
    return story


async def _trashed_chapter(session: AsyncSession, chapter_id: UUID, user_id: UUID) -> Chapter:
    chapter = await session.scalar(
        select(Chapter)
        .join(Story, Story.id == Chapter.story_id)
        .where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_not(None),
            Story.owner_id == user_id,
        )
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="That chapter is not in the trash.")
    return chapter


@router.post("/chapters/{chapter_id}/restore")
async def restore_chapter(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _trashed_chapter(session, chapter_id, user.id)
    story = await session.get(Story, chapter.story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="The chapter's story no longer exists.")
    if story.deleted_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Restore the story first; its chapters come back with it.",
        )

    renumbered_from = None
    taken = await session.scalar(
        select(Chapter.id).where(
            Chapter.story_id == story.id,
            Chapter.chapter_number == chapter.chapter_number,
            Chapter.deleted_at.is_(None),
        )
    )
    if taken:
        renumbered_from = chapter.chapter_number
        chapter.chapter_number = await next_free_number(session, story.id)

    chapter.deleted_at = None
    story.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(chapter)
    return {
        "chapter": {
            "id": str(chapter.id),
            "story_id": str(chapter.story_id),
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
        },
        "renumbered_from": renumbered_from,
    }


@router.post("/stories/{story_id}/restore")
async def restore_story(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _trashed_story(session, story_id, user.id)
    deleted_at = story.deleted_at
    story.deleted_at = None
    # Only the chapters trashed with the story come back; chapters deleted
    # earlier stay in the trash, and chapters deleted later stay deleted.
    chapters = list(
        await session.scalars(
            select(Chapter).where(Chapter.story_id == story.id, Chapter.deleted_at.is_not(None))
        )
    )
    restored = 0
    for chapter in chapters:
        if deleted_at is not None and chapter.deleted_at is not None and chapter.deleted_at >= deleted_at:
            chapter.deleted_at = None
            restored += 1
    story.updated_at = datetime.now(UTC)
    await session.commit()
    return {"story_id": str(story.id), "restored_chapters": restored}


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chapter_permanently(
    chapter_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    chapter = await _trashed_chapter(session, chapter_id, user.id)
    title, story_id = chapter.title, chapter.story_id
    await session.delete(chapter)
    record_audit(
        session,
        "chapter_deleted",
        user_id=user.id,
        email=user.email,
        target_type="chapter",
        target_id=str(chapter_id),
        detail={"title": title, "story_id": str(story_id), "permanent": True},
        request=request,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/stories/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story_permanently(
    story_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    story = await _trashed_story(session, story_id, user.id)
    title = story.title
    await session.delete(story)
    record_audit(
        session,
        "story_deleted",
        user_id=user.id,
        email=user.email,
        target_type="story",
        target_id=str(story_id),
        detail={"title": title, "permanent": True},
        request=request,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
