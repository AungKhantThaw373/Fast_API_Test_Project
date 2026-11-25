"""Backfill sentence-aware chunks for chapters indexed before Phase 5.

Run after deploying the chunker:

    python -m app.backfill.chunks              # enqueue every chapter missing chunks
    python -m app.backfill.chunks --story ID   # one story
    python -m app.backfill.chunks --run        # index inline instead of queueing

One job per chapter, deduped by the existing ``chapter:<id>`` key, so the
worker can make progress without holding a request open.
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import exists, select

from app.db import async_session
from app.models.story_models import Chapter, Story, StoryChunk
from app.services import indexing


async def backfill_chunks(
    *,
    story_id: UUID | None = None,
    force: bool = False,
    run_inline: bool = False,
) -> dict[str, int]:
    async with async_session() as session:
        statement = (
            select(Chapter.id, Story.owner_id)
            .join(Story, Story.id == Chapter.story_id)
            .where(Chapter.deleted_at.is_(None))
        )
        if story_id is not None:
            statement = statement.where(Chapter.story_id == story_id)
        if not force:
            statement = statement.where(
                ~exists().where(StoryChunk.chapter_id == Chapter.id)
            )
        rows = (await session.execute(statement.order_by(Chapter.story_id, Chapter.position))).all()
        for chapter_id, owner_id in rows:
            if run_inline:
                await indexing.reindex_chapter(chapter_id)
            else:
                await indexing.enqueue_reindex(session, chapter_id, owner_id)
        await session.commit()
    return {"chapters": len(rows), "inline": int(run_inline)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", type=UUID, default=None, help="limit to one story id")
    parser.add_argument("--force", action="store_true", help="reindex chapters that already have chunks")
    parser.add_argument("--run", action="store_true", help="index inline instead of enqueueing jobs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = asyncio.run(
        backfill_chunks(story_id=args.story, force=args.force, run_inline=args.run)
    )
    print(f"chapters={result['chapters']} mode={'inline' if args.run else 'queued'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
