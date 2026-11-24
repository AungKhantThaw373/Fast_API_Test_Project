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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, StoryBibleEntry
from app.models.wiki_models import Entity, EntityFact, StoryThread
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
                Entity.status != "merged",
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
