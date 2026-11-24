"""Backfill knowledge model v2 from ``story_bible_entries``.

```bash
uv run python -m app.backfill.bible                 # entities, aliases, facts, threads
uv run python -m app.backfill.bible --mentions      # also rebuild mentions
uv run python -m app.backfill.bible --story <uuid>  # one story
```

Safe to run twice: entities keep their original UUID (so old links resolve), facts
are matched on ``(entity, predicate, quote)``, threads on ``(story, title)``, and
aliases use ``ON CONFLICT DO NOTHING``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session, engine
from app.logging_config import configure_app_logging, get_logger
from app.models.story_models import Chapter, StoryBibleEntry
from app.models.wiki_models import Entity, EntityFact, StoryThread
from app.services.entities import add_alias, create_entity, extract_mentions, normalize_name

logger = get_logger("backfill")

CATEGORY_TO_TYPE = {
    "character": "character",
    "location": "location",
    "item": "item",
    "world_rule": "world_rule",
    "worldbuilding": "concept",
    "power_system": "power_system",
}

STATUS_TO_FACT = {"suggested": "proposed", "accepted": "accepted", "dismissed": "rejected"}
THREAD_STATE = {"open": "open", "resolved": "resolved"}


def locate_quote(content: str, quote: str) -> tuple[int | None, int | None]:
    """1-based first and last line of ``quote`` inside ``content``."""
    offset = content.find(quote)
    if offset < 0:
        return None, None
    start = content.count("\n", 0, offset) + 1
    return start, start + quote.count("\n")


async def _chapter_numbers(session: AsyncSession, chapter_ids: set[UUID]) -> dict[UUID, tuple[int, str]]:
    if not chapter_ids:
        return {}
    rows = (
        await session.execute(
            select(Chapter.id, Chapter.chapter_number, Chapter.content).where(
                Chapter.id.in_(chapter_ids)
            )
        )
    ).all()
    return {chapter_id: (number, content) for chapter_id, number, content in rows}


async def backfill_story(
    session: AsyncSession, story_id: UUID, *, mentions: bool = False
) -> Counter:
    counts: Counter = Counter()
    entries = list(
        await session.scalars(
            select(StoryBibleEntry)
            .where(StoryBibleEntry.story_id == story_id)
            .order_by(StoryBibleEntry.created_at)
        )
    )
    chapter_ids = {entry.source_chapter_id for entry in entries if entry.source_chapter_id}
    chapters = await _chapter_numbers(session, chapter_ids)

    for entry in entries:
        if entry.category == "plot_thread":
            existing_thread = await session.scalar(
                select(StoryThread.id).where(
                    StoryThread.story_id == story_id, StoryThread.title == entry.name
                )
            )
            if existing_thread is not None:
                counts["threads_skipped"] += 1
                continue
            session.add(
                StoryThread(
                    story_id=story_id,
                    title=entry.name[:300],
                    description=entry.description,
                    setup_chapter_id=entry.source_chapter_id,
                    setup_quote=entry.source_quote,
                    state=THREAD_STATE.get(entry.thread_state or "open", "open"),
                    linked_entity_ids=[],
                )
            )
            counts["threads"] += 1
            continue

        source_id = entry.source_chapter_id
        source_number, source_content = (
            chapters.get(source_id, (None, "")) if source_id is not None else (None, "")
        )

        entity = await session.get(Entity, entry.id)
        if entity is not None:
            counts["entities_skipped"] += 1
        else:
            entity = await create_entity(
                session,
                story_id=story_id,
                entity_type=CATEGORY_TO_TYPE.get(entry.category, "other"),
                name=entry.name,
                summary=entry.description,
                entity_id=entry.id,
                first_chapter_number=source_number,
            )
            counts["entities"] += 1
            # ``create_entity`` always adds the display name as the first alias.
            counts["aliases"] += 1

        counts["aliases"] += await add_alias(session, entity, entry.name, "name")
        normalized = normalize_name(entry.name)
        if normalized and normalized != entry.name.casefold():
            counts["aliases"] += await add_alias(session, entity, normalized, "other")

        if not entry.source_quote:
            continue
        existing_fact = await session.scalar(
            select(EntityFact.id).where(
                EntityFact.entity_id == entity.id,
                EntityFact.predicate == "summary",
                EntityFact.quote == entry.source_quote,
            )
        )
        if existing_fact is not None:
            counts["facts_skipped"] += 1
            continue
        line_start, line_end = locate_quote(source_content, entry.source_quote)
        session.add(
            EntityFact(
                entity_id=entity.id,
                predicate="summary",
                value_text=entry.description,
                value_type="text",
                chapter_id=entry.source_chapter_id,
                line_start=line_start,
                line_end=line_end,
                quote=entry.source_quote,
                confidence=entry.confidence,
                status=STATUS_TO_FACT.get(entry.status, "proposed"),
                valid_from_chapter=source_number,
                created_by="human" if entry.status in {"accepted", "dismissed"} else "ai",
            )
        )
        counts["facts"] += 1

    if mentions:
        chapters_to_scan = list(
            await session.scalars(select(Chapter).where(Chapter.story_id == story_id))
        )
        for chapter in chapters_to_scan:
            found = await extract_mentions(session, story_id, chapter.id, chapter.content)
            counts["mentions"] += found

    await session.commit()
    return counts


async def run(story_id: UUID | None = None, *, mentions: bool = False) -> Counter:
    totals: Counter = Counter()
    async with async_session() as session:
        story_ids = (
            [story_id]
            if story_id is not None
            else list(await session.scalars(select(StoryBibleEntry.story_id).distinct()))
        )
    logger.info("[backfill] start  stories=%s mentions=%s", len(story_ids), mentions)
    for index, current in enumerate(story_ids, start=1):
        async with async_session() as session:
            counts = await backfill_story(session, current, mentions=mentions)
        totals.update(counts)
        logger.info(
            "[backfill] story  %s/%s %s | %s",
            index,
            len(story_ids),
            current,
            dict(counts),
        )
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill the stillroom knowledge model")
    parser.add_argument("--story", type=UUID, default=None, help="only this story id")
    parser.add_argument(
        "--mentions", action="store_true", help="also rebuild mentions for every chapter"
    )
    args = parser.parse_args(argv)
    configure_app_logging()

    async def _main() -> Counter:
        try:
            return await run(args.story, mentions=args.mentions)
        finally:
            await engine.dispose()

    totals = asyncio.run(_main())
    print("backfill summary:")
    for key in sorted(totals):
        print(f"  {key:18} {totals[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
