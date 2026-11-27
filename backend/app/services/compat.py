"""Compatibility view of the knowledge model for the Phase 1/2 Bible clients.

The studio UI still calls ``GET /stories/{id}/bible`` and expects the old entry
shape. The canonical data now lives in entities, summary facts, and threads, so
this module projects those back into the old fields and appends any legacy
``story_bible_entries`` rows that have no entity yet (the pre-P6 extraction still
writes those). When a row exists in both places the entity wins.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, Story, StoryBibleEntry
from app.models.wiki_models import Entity, EntityFact, StoryThread
from app.services.entities import normalize_name
from app.services.pagination import (
    clamp_limit,
    cursor_text,
    cursor_uuid,
    decode_cursor,
    encode_cursor,
)

# entity_type -> legacy category. Several new types have no old equivalent and
# fall back to the catch-all bucket the old UI renders as "worldbuilding".
TYPE_TO_CATEGORY = {
    "character": "character",
    "location": "location",
    "item": "item",
    "world_rule": "world_rule",
    "power_system": "power_system",
    "concept": "worldbuilding",
    "organization": "worldbuilding",
    "creature": "worldbuilding",
    "other": "worldbuilding",
}

# legacy category -> entity_type, for writes that still arrive in the old shape.
CATEGORY_TO_TYPE = {
    "character": "character",
    "location": "location",
    "item": "item",
    "world_rule": "world_rule",
    "power_system": "power_system",
    "worldbuilding": "concept",
    "plot_thread": "concept",
}

FACT_TO_STATUS = {
    "proposed": "suggested",
    "accepted": "accepted",
    "rejected": "dismissed",
    "superseded": "accepted",
}

THREAD_TO_STATE = {"open": "open", "touched": "open", "resolved": "resolved", "abandoned": "resolved"}
STATE_TO_THREAD = {"open": "open", "resolved": "resolved"}


async def bible_view(
    session: AsyncSession,
    story_id: UUID,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    page_size = clamp_limit(limit, default=500, maximum=2000)
    entities = list(
        await session.scalars(
            select(Entity)
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                Entity.status.notin_(("merged", "archived")),
            )
            .order_by(Entity.created_at)
        )
    )
    threads = list(
        await session.scalars(select(StoryThread).where(StoryThread.story_id == story_id))
    )
    facts = list(
        await session.scalars(
            select(EntityFact)
            .where(
                EntityFact.entity_id.in_([entity.id for entity in entities]),
                EntityFact.predicate == "summary",
            )
            .order_by(EntityFact.created_at)
        )
    )
    latest: dict[UUID, EntityFact] = {}
    for fact in facts:
        latest[fact.entity_id] = fact

    rows: list[dict[str, Any]] = []
    for entity in entities:
        fact = latest.get(entity.id)
        category = TYPE_TO_CATEGORY.get(entity.entity_type, "worldbuilding")
        rows.append(
            {
                "id": entity.id,
                "category": category,
                "name": entity.name,
                "description": (fact.value_text if fact and fact.value_text else entity.summary)
                or entity.name,
                "status": FACT_TO_STATUS.get(fact.status, "accepted") if fact else "accepted",
                "thread_state": None,
                "confidence": fact.confidence if fact else 50,
                "source_chapter_id": fact.chapter_id if fact else None,
                "source_quote": fact.quote if fact else None,
                "details": {},
                "updated_at": max(
                    entity.updated_at, fact.updated_at if fact else entity.updated_at
                ),
            }
        )

    for thread in threads:
        rows.append(
            {
                "id": thread.id,
                "category": "plot_thread",
                "name": thread.title,
                "description": thread.description or thread.title,
                "status": "accepted",
                "thread_state": THREAD_TO_STATE.get(thread.state, "open"),
                "confidence": 100,
                "source_chapter_id": thread.setup_chapter_id,
                "source_quote": thread.setup_quote,
                "details": {},
                "updated_at": thread.updated_at,
            }
        )

    legacy = list(
        await session.scalars(
            select(StoryBibleEntry).where(StoryBibleEntry.story_id == story_id)
        )
    )
    seen = {row["id"] for row in rows}
    for entry in legacy:
        if entry.id in seen:
            continue
        rows.append(
            {
                "id": entry.id,
                "category": entry.category,
                "name": entry.name,
                "description": entry.description,
                "status": entry.status,
                "thread_state": entry.thread_state,
                "confidence": entry.confidence,
                "source_chapter_id": entry.source_chapter_id,
                "source_quote": entry.source_quote,
                "details": entry.details or {},
                "updated_at": entry.updated_at,
            }
        )

    rows.sort(key=lambda row: (row["status"], row["category"], row["name"], str(row["id"])))
    if cursor:
        status, category, name, row_id = decode_cursor(
            cursor, (cursor_text, cursor_text, cursor_text, cursor_uuid)
        )
        marker = (status, category, name, str(row_id))
        rows = [
            row
            for row in rows
            if (row["status"], row["category"], row["name"], str(row["id"])) > marker
        ]
    page = rows[:page_size]
    next_cursor = None
    if len(rows) > page_size and page:
        last = page[-1]
        next_cursor = encode_cursor(
            (last["status"], last["category"], last["name"], str(last["id"]))
        )
    return page, next_cursor


async def legacy_ids(session: AsyncSession, story_id: UUID) -> set[UUID]:
    """Legacy rows that have not been migrated into the new model yet."""
    entity_ids = set(
        await session.scalars(
            select(StoryBibleEntry.id).where(
                StoryBibleEntry.story_id == story_id,
                StoryBibleEntry.id.in_(
                    select(Entity.id).where(Entity.story_id == story_id)
                ),
            )
        )
    )
    all_ids = set(
        await session.scalars(
            select(StoryBibleEntry.id).where(StoryBibleEntry.story_id == story_id)
        )
    )
    return all_ids - entity_ids


async def chapter_number(session: AsyncSession, chapter_id: UUID | None) -> int | None:
    if chapter_id is None:
        return None
    return await session.scalar(
        select(Chapter.chapter_number).where(Chapter.id == chapter_id)
    )


__all__ = ["bible_view", "legacy_ids", "chapter_number", "TYPE_TO_CATEGORY"]


async def entity_entry(session: AsyncSession, entry_id: UUID, user_id: UUID) -> Entity | None:
    """The entity behind a Bible id, if this id came from the knowledge model."""
    entity = await session.get(Entity, entry_id)
    if entity is None:
        return None
    story = await session.scalar(
        select(Story).where(Story.id == entity.story_id, Story.owner_id == user_id)
    )
    if story is None:
        raise HTTPException(status_code=404, detail="Story Bible entry not found.")
    return entity


async def thread_entry(session: AsyncSession, entry_id: UUID, user_id: UUID) -> StoryThread | None:
    thread = await session.get(StoryThread, entry_id)
    if thread is None:
        return None
    story = await session.scalar(
        select(Story).where(Story.id == thread.story_id, Story.owner_id == user_id)
    )
    if story is None:
        raise HTTPException(status_code=404, detail="Story Bible entry not found.")
    return thread


async def _summary_fact(session: AsyncSession, entity_id: UUID) -> EntityFact | None:
    return await session.scalar(
        select(EntityFact)
        .where(EntityFact.entity_id == entity_id, EntityFact.predicate == "summary")
        .order_by(EntityFact.created_at.desc())
        .limit(1)
    )


async def _entity_row(session: AsyncSession, entity: Entity) -> dict[str, Any]:
    rows, _next = await bible_view_rows(session, entity.story_id, only_ids=[entity.id])
    return rows[0]


async def bible_view_rows(
    session: AsyncSession, story_id: UUID, *, only_ids: list[UUID] | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    rows, next_cursor = await bible_view(session, story_id)
    if only_ids is None:
        return rows, next_cursor
    wanted = {str(value) for value in only_ids}
    return [row for row in rows if str(row["id"]) in wanted], None


async def update_entity_entry(
    session: AsyncSession, entity: Entity, payload: Any
) -> dict[str, Any]:
    """Apply an old-shape edit to the entity and its summary fact."""
    entity.entity_type = CATEGORY_TO_TYPE.get(payload.category, "concept")
    entity.name = payload.name.strip()
    entity.canonical_name = normalize_name(entity.name)[:220]
    entity.summary = payload.description.strip()
    fact = await _summary_fact(session, entity.id)
    if fact is None:
        fact = EntityFact(
            entity_id=entity.id,
            predicate="summary",
            value_type="text",
            confidence=100,
            status="accepted",
            created_by="human",
            context={},
        )
        session.add(fact)
    fact.value_text = payload.description.strip()
    await session.flush()
    return await _entity_row(session, entity)


async def decide_entity_entry(
    session: AsyncSession, entity: Entity, status: str
) -> dict[str, Any]:
    fact = await _summary_fact(session, entity.id)
    if fact is None:
        raise HTTPException(status_code=409, detail="This entry has no summary to review.")
    if fact.status != "proposed":
        raise HTTPException(
            status_code=409, detail="This suggestion has already been reviewed."
        )
    fact.status = "accepted" if status == "accepted" else "rejected"
    await session.flush()
    return await _entity_row(session, entity)


async def archive_entity_entry(session: AsyncSession, entity: Entity) -> None:
    entity.status = "archived"
    await session.flush()


async def set_thread_state_entry(
    session: AsyncSession, thread: StoryThread, state: str
) -> dict[str, Any]:
    thread.state = "open" if state == "open" else "resolved"
    await session.flush()
    rows, _next = await bible_view_rows(session, thread.story_id, only_ids=[thread.id])
    return rows[0]
