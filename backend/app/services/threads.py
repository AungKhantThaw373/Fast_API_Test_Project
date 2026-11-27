"""Story threads and story events.

Threads carry unresolved questions; events carry what actually happened in a
chapter. Both are plain CRUD with story ownership checks, and both are read by
the continuity context and the chapter review cards.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter
from app.models.wiki_models import Entity, EntityMention, StoryEvent, StoryThread
from app.schemas.wiki import (
    EventCreate,
    EventUpdate,
    ThreadCreate,
    ThreadEntityOut,
    ThreadMentionOut,
    ThreadOut,
    ThreadUpdate,
)
from app.services.entities import resolve_entity


async def _owned_chapter(session: AsyncSession, story_id: UUID, chapter_id: UUID) -> Chapter:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id or chapter.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


async def _validate_entities(session: AsyncSession, story_id: UUID, entity_ids: list[UUID]) -> None:
    if not entity_ids:
        return
    found = set(
        await session.scalars(
            select(Entity.id).where(
                Entity.id.in_(entity_ids),
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
            )
        )
    )
    missing = [str(entity_id) for entity_id in entity_ids if entity_id not in found]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Unknown entities in this story: {', '.join(missing)}"
        )


async def list_threads(
    session: AsyncSession, story_id: UUID, *, state: str | None = None
) -> list[StoryThread]:
    statement = select(StoryThread).where(StoryThread.story_id == story_id)
    if state:
        statement = statement.where(StoryThread.state == state)
    return list(
        await session.scalars(statement.order_by(StoryThread.created_at, StoryThread.id))
    )


async def enrich_threads(
    session: AsyncSession, threads: list[StoryThread]
) -> list[ThreadOut]:
    """Add the names and latest mention the board shows, in three queries total."""
    if not threads:
        return []
    chapter_ids = {
        chapter_id
        for thread in threads
        for chapter_id in (thread.setup_chapter_id, thread.payoff_chapter_id)
        if chapter_id is not None
    }
    entity_ids = {entity_id for thread in threads for entity_id in thread.linked_entity_ids}
    chapters = {
        chapter.id: chapter
        for chapter in await session.scalars(select(Chapter).where(Chapter.id.in_(chapter_ids)))
    } if chapter_ids else {}
    entities = {
        entity.id: entity
        for entity in await session.scalars(select(Entity).where(Entity.id.in_(entity_ids)))
    } if entity_ids else {}
    latest: dict[UUID, dict[str, Any]] = {}
    if entity_ids:
        ranked = (
            select(
                EntityMention.entity_id,
                EntityMention.chapter_id,
                EntityMention.line_start,
                EntityMention.quote,
                Chapter.chapter_number,
                Chapter.title.label("chapter_title"),
                func.row_number()
                .over(
                    partition_by=EntityMention.entity_id,
                    order_by=(Chapter.chapter_number.desc(), EntityMention.line_start.desc()),
                )
                .label("rank"),
            )
            .join(Chapter, Chapter.id == EntityMention.chapter_id)
            .where(
                EntityMention.entity_id.in_(entity_ids),
                Chapter.deleted_at.is_(None),
            )
            .subquery()
        )
        rows = await session.execute(select(ranked).where(ranked.c.rank == 1))
        latest = {row.entity_id: dict(row._mapping) for row in rows}

    result: list[ThreadOut] = []
    for thread in threads:
        out = ThreadOut.model_validate(thread)
        linked = [
            ThreadEntityOut(
                id=entity.id, name=entity.name, entity_type=entity.entity_type
            )
            for entity_id in thread.linked_entity_ids
            if (entity := entities.get(entity_id)) is not None
        ]
        setup = chapters.get(thread.setup_chapter_id) if thread.setup_chapter_id else None
        payoff = chapters.get(thread.payoff_chapter_id) if thread.payoff_chapter_id else None
        mention = None
        candidates = [
            latest[entity_id]
            for entity_id in thread.linked_entity_ids
            if entity_id in latest
        ]
        if candidates:
            best = max(candidates, key=lambda row: (row["chapter_number"], row["line_start"]))
            mention = ThreadMentionOut(
                chapter_id=best["chapter_id"],
                chapter_number=best["chapter_number"],
                chapter_title=best["chapter_title"],
                line=best["line_start"],
                quote=best["quote"],
            )
        out.linked_entities = linked
        out.setup_chapter_number = setup.chapter_number if setup else None
        out.setup_chapter_title = setup.title if setup else None
        out.payoff_chapter_number = payoff.chapter_number if payoff else None
        out.payoff_chapter_title = payoff.title if payoff else None
        out.last_mention = mention
        result.append(out)
    return result


async def get_thread(session: AsyncSession, thread_id: UUID) -> StoryThread:
    thread = await session.get(StoryThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return thread


async def thread_count(session: AsyncSession, story_id: UUID, *, states: tuple[str, ...]) -> int:
    return int(
        await session.scalar(
            select(func.count(StoryThread.id)).where(
                StoryThread.story_id == story_id, StoryThread.state.in_(states)
            )
        )
        or 0
    )


async def create_thread(session: AsyncSession, story_id: UUID, payload: ThreadCreate) -> StoryThread:
    if payload.setup_chapter_id is not None:
        await _owned_chapter(session, story_id, payload.setup_chapter_id)
    if payload.payoff_chapter_id is not None:
        await _owned_chapter(session, story_id, payload.payoff_chapter_id)
    await _validate_entities(session, story_id, payload.linked_entity_ids)
    thread = StoryThread(
        story_id=story_id,
        title=payload.title.strip(),
        description=payload.description,
        setup_chapter_id=payload.setup_chapter_id,
        setup_quote=payload.setup_quote,
        payoff_chapter_id=payload.payoff_chapter_id,
        state=payload.state,
        linked_entity_ids=payload.linked_entity_ids,
    )
    session.add(thread)
    await session.flush()
    return thread


async def update_thread(
    session: AsyncSession, thread: StoryThread, payload: ThreadUpdate
) -> StoryThread:
    data = payload.model_dump(exclude_unset=True)
    if data.get("setup_chapter_id") is not None:
        await _owned_chapter(session, thread.story_id, data["setup_chapter_id"])
    if data.get("payoff_chapter_id") is not None:
        await _owned_chapter(session, thread.story_id, data["payoff_chapter_id"])
    if data.get("linked_entity_ids") is not None:
        await _validate_entities(session, thread.story_id, data["linked_entity_ids"])
    if data.get("title") is not None:
        data["title"] = data["title"].strip()
    for key, value in data.items():
        setattr(thread, key, value)
    if thread.state == "resolved" and thread.payoff_chapter_id is None:
        raise HTTPException(
            status_code=422, detail="A resolved thread needs the chapter that paid it off."
        )
    await session.flush()
    return thread


async def delete_thread(session: AsyncSession, thread: StoryThread) -> None:
    await session.delete(thread)
    await session.flush()


async def list_events(
    session: AsyncSession, story_id: UUID, *, chapter_id: UUID | None = None
) -> list[StoryEvent]:
    statement = select(StoryEvent).where(StoryEvent.story_id == story_id)
    if chapter_id is not None:
        statement = statement.where(StoryEvent.chapter_id == chapter_id)
    return list(
        await session.scalars(
            statement.order_by(StoryEvent.timeline_order, StoryEvent.created_at, StoryEvent.id)
        )
    )


async def get_event(session: AsyncSession, event_id: UUID) -> StoryEvent:
    event = await session.get(StoryEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


async def create_event(session: AsyncSession, story_id: UUID, payload: EventCreate) -> StoryEvent:
    chapter = await _owned_chapter(session, story_id, payload.chapter_id)
    if payload.location_entity_id is not None:
        location = await resolve_entity(session, payload.location_entity_id)
        if location is None or location.story_id != story_id:
            raise HTTPException(status_code=422, detail="Location entity is not in this story.")
    await _validate_entities(session, story_id, payload.participant_entity_ids)
    event = StoryEvent(
        story_id=story_id,
        chapter_id=payload.chapter_id,
        scene_index=payload.scene_index,
        timeline_order=payload.timeline_order
        if payload.timeline_order is not None
        else float(chapter.chapter_number * 1000),
        summary=payload.summary.strip(),
        location_entity_id=payload.location_entity_id,
        participant_entity_ids=payload.participant_entity_ids,
        quote=payload.quote,
    )
    session.add(event)
    await session.flush()
    return event


async def update_event(session: AsyncSession, event: StoryEvent, payload: EventUpdate) -> StoryEvent:
    data = payload.model_dump(exclude_unset=True)
    if data.get("participant_entity_ids") is not None:
        await _validate_entities(session, event.story_id, data["participant_entity_ids"])
    if data.get("location_entity_id") is not None:
        location = await resolve_entity(session, data["location_entity_id"])
        if location is None or location.story_id != event.story_id:
            raise HTTPException(status_code=422, detail="Location entity is not in this story.")
    if data.get("summary") is not None:
        data["summary"] = data["summary"].strip()
    for key, value in data.items():
        setattr(event, key, value)
    await session.flush()
    return event


async def delete_event(session: AsyncSession, event: StoryEvent) -> None:
    await session.delete(event)
    await session.flush()
