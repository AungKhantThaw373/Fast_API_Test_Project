"""Story thread, event, and inbox endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.wiki_models import CanonException
from app.schemas.wiki import (
    EventCreate,
    EventListOut,
    EventOut,
    EventUpdate,
    ExceptionCreate,
    ExceptionListOut,
    ExceptionOut,
    InboxOut,
    ThreadCreate,
    ThreadListOut,
    ThreadOut,
    ThreadUpdate,
)
from app.security import get_current_user
from app.services import canon_exceptions as exceptions_service
from app.services import inbox as inbox_service
from app.services import stories as stories_service
from app.services import threads as threads_service

router = APIRouter(tags=["wiki"])


async def _owned_thread_story(session: AsyncSession, thread_id: UUID, user: User) -> UUID:
    thread = await threads_service.get_thread(session, thread_id)
    await stories_service.owned_story(session, thread.story_id, user.id)
    return thread.story_id


@router.get("/stories/{story_id}/threads", response_model=ThreadListOut)
async def list_threads(
    story_id: UUID,
    state_filter: str | None = Query(default=None, alias="state"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await threads_service.list_threads(session, story_id, state=state_filter)
    return ThreadListOut(threads=[ThreadOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/threads",
    status_code=status.HTTP_201_CREATED,
    response_model=ThreadOut,
)
async def create_thread(
    story_id: UUID,
    payload: ThreadCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadOut:
    await stories_service.owned_story(session, story_id, user.id)
    thread = await threads_service.create_thread(session, story_id, payload)
    await session.commit()
    await session.refresh(thread)
    return ThreadOut.model_validate(thread)


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def update_thread(
    thread_id: UUID,
    payload: ThreadUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadOut:
    await _owned_thread_story(session, thread_id, user)
    thread = await threads_service.get_thread(session, thread_id)
    await threads_service.update_thread(session, thread, payload)
    await session.commit()
    await session.refresh(thread)
    return ThreadOut.model_validate(thread)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await _owned_thread_story(session, thread_id, user)
    thread = await threads_service.get_thread(session, thread_id)
    await threads_service.delete_thread(session, thread)
    await session.commit()


@router.get("/stories/{story_id}/events", response_model=EventListOut)
async def list_events(
    story_id: UUID,
    chapter_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await threads_service.list_events(session, story_id, chapter_id=chapter_id)
    return EventListOut(events=[EventOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/events",
    status_code=status.HTTP_201_CREATED,
    response_model=EventOut,
)
async def create_event(
    story_id: UUID,
    payload: EventCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventOut:
    await stories_service.owned_story(session, story_id, user.id)
    event = await threads_service.create_event(session, story_id, payload)
    await session.commit()
    await session.refresh(event)
    return EventOut.model_validate(event)


@router.put("/events/{event_id}", response_model=EventOut)
async def update_event(
    event_id: UUID,
    payload: EventUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventOut:
    event = await threads_service.get_event(session, event_id)
    await stories_service.owned_story(session, event.story_id, user.id)
    await threads_service.update_event(session, event, payload)
    await session.commit()
    await session.refresh(event)
    return EventOut.model_validate(event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    event = await threads_service.get_event(session, event_id)
    await stories_service.owned_story(session, event.story_id, user.id)
    await threads_service.delete_event(session, event)
    await session.commit()


@router.get("/stories/{story_id}/exceptions", response_model=ExceptionListOut)
async def list_exceptions(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ExceptionListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await exceptions_service.list_exceptions(session, story_id)
    return ExceptionListOut(exceptions=[ExceptionOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/exceptions",
    status_code=status.HTTP_201_CREATED,
    response_model=ExceptionOut,
)
async def create_exception(
    story_id: UUID,
    payload: ExceptionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ExceptionOut:
    await stories_service.owned_story(session, story_id, user.id)
    exception = await exceptions_service.create_exception(
        session,
        story_id,
        exceptions_service.ExceptionCreate(
            scope=payload.scope,
            reason=payload.reason,
            pattern=payload.pattern,
            entity_id=payload.entity_id,
            predicate=payload.predicate,
        ),
    )
    await session.commit()
    await session.refresh(exception)
    return ExceptionOut.model_validate(exception)


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(
    exception_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    exception = await session.get(CanonException, exception_id)
    if exception is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    await stories_service.owned_story(session, exception.story_id, user.id)
    await exceptions_service.delete_exception(session, exception.story_id, exception_id)
    await session.commit()


@router.get("/stories/{story_id}/inbox", response_model=InboxOut)
async def get_inbox(
    story_id: UUID,
    kind: str | None = Query(default=None, description="Comma separated: fact,finding"),
    status_filter: str = Query(default="open", alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> InboxOut:
    await stories_service.owned_story(session, story_id, user.id)
    kinds = [part.strip() for part in kind.split(",")] if kind else None
    items, next_cursor = await inbox_service.collect(
        session, story_id, kinds=kinds, status=status_filter, limit=limit, cursor=cursor
    )
    return InboxOut(items=items, next_cursor=next_cursor)
