"""Authoritative chapter ordering.

``position`` is a double: new chapters go at the end (+1024), a reorder rewrites
all positions in one round trip, and display numbers are recomputed with two bulk
statements instead of one UPDATE per chapter. ``chapter_number`` is only what the
writer sees.

The two-pass display renumbering exists because the unique index on
``(story_id, chapter_number)`` is checked per row; a permutation must pass through
a set of temporary negative values first.
"""

from __future__ import annotations

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter

POSITION_STEP = 1024.0
REBALANCE_THRESHOLD = 1e-6


async def next_position(session: AsyncSession, story_id) -> float:
    current = await session.scalar(
        select(func.max(Chapter.position)).where(
            Chapter.story_id == story_id, Chapter.deleted_at.is_(None)
        )
    )
    return (current or 0.0) + POSITION_STEP


async def position_between(before: float, after: float) -> float | None:
    """Midpoint for an insert; ``None`` means the caller should rebalance first."""
    gap = after - before
    if gap < REBALANCE_THRESHOLD:
        return None
    return before + gap / 2


async def assign_positions(session: AsyncSession, ordered_chapters: list[Chapter]) -> None:
    """Rewrite positions from an explicit order in one executemany round trip."""
    if not ordered_chapters:
        return
    payload = [
        {"id": chapter.id, "position": (index + 1) * POSITION_STEP}
        for index, chapter in enumerate(ordered_chapters)
    ]
    # ORM bulk UPDATE ... WHERE id = :id, one executemany round trip.
    await session.execute(update(Chapter), payload)


async def rebalance_story(session: AsyncSession, story_id) -> int:
    """Spread positions evenly when a gap has shrunk below the threshold."""
    chapters = list(
        await session.scalars(
            select(Chapter)
            .where(Chapter.story_id == story_id, Chapter.deleted_at.is_(None))
            .order_by(Chapter.position)
        )
    )
    await assign_positions(session, chapters)
    return len(chapters)


async def renumber_display(session: AsyncSession, story_id) -> None:
    """Recompute chapter_number from position, plus the rows that cache it."""
    order = "ORDER BY position, chapter_number"
    scope = "story_id = :story_id AND deleted_at IS NULL"

    # Pass 1: move everything to a disjoint negative range.
    await session.execute(
        text(
            f"""
            WITH ordered AS (
                SELECT id, row_number() OVER ({order}) AS rn
                FROM story_chapters
                WHERE {scope}
            )
            UPDATE story_chapters AS c
            SET chapter_number = -ordered.rn
            FROM ordered
            WHERE c.id = ordered.id
            """
        ),
        {"story_id": story_id},
    )
    # Pass 2: assign the positive display numbers.
    await session.execute(
        text(
            f"""
            WITH ordered AS (
                SELECT id, row_number() OVER ({order}) AS rn
                FROM story_chapters
                WHERE {scope}
            )
            UPDATE story_chapters AS c
            SET chapter_number = ordered.rn
            FROM ordered
            WHERE c.id = ordered.id
            """
        ),
        {"story_id": story_id},
    )

    # Denormalized copies used by retrieval and findings.
    await session.execute(
        text(
            """
            UPDATE story_scene_embeddings AS e
            SET chapter_number = c.chapter_number
            FROM story_chapters AS c
            WHERE e.chapter_id = c.id AND c.story_id = :story_id
            """
        ),
        {"story_id": story_id},
    )
    await session.execute(
        text(
            """
            UPDATE continuity_findings AS f
            SET earlier_chapter_number = c.chapter_number
            FROM story_chapters AS c
            WHERE f.earlier_chapter_id = c.id AND c.story_id = :story_id
            """
        ),
        {"story_id": story_id},
    )
