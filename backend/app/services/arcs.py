"""Arcs: named spans of chapters.

The rail groups chapters by arc once a story outgrows a flat list. Assignment is
explicit rather than computed from numbering, so a writer can regroup freely.
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Arc, Chapter


def _bounds() -> tuple[object, ...]:
    return (func.min(Chapter.chapter_number), func.max(Chapter.chapter_number), func.count(Chapter.id))


async def list_arcs(session: AsyncSession, story_id: UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Arc, *_bounds())
            .outerjoin(
                Chapter,
                (Chapter.arc_id == Arc.id) & Chapter.deleted_at.is_(None),
            )
            .where(Arc.story_id == story_id)
            .group_by(Arc.id)
            .order_by(Arc.position, Arc.name)
        )
    ).all()
    return [_arc_dict(arc, low, high, count) for arc, low, high, count in rows]


def _arc_dict(arc: Arc, low: int | None, high: int | None, count: int | None) -> dict:
    return {
        "id": arc.id,
        "story_id": arc.story_id,
        "name": arc.name,
        "summary": arc.summary,
        "position": arc.position,
        "chapter_count": int(count or 0),
        "first_chapter_number": low,
        "last_chapter_number": high,
    }


async def get_arc(session: AsyncSession, arc_id: UUID) -> Arc | None:
    return await session.get(Arc, arc_id)


async def create_arc(session: AsyncSession, story_id: UUID, name: str, summary: str) -> Arc:
    position = (
        await session.execute(select(func.coalesce(func.max(Arc.position), 0.0)).where(Arc.story_id == story_id))
    ).scalar_one()
    arc = Arc(story_id=story_id, name=name.strip(), summary=summary, position=float(position) + 1024)
    session.add(arc)
    await session.flush()
    return arc


async def update_arc(session: AsyncSession, arc: Arc, **fields: object) -> Arc:
    for key, value in fields.items():
        if value is not None:
            setattr(arc, key, value)
    await session.flush()
    return arc


async def delete_arc(session: AsyncSession, arc: Arc) -> None:
    """Chapter links are cleared by the FK; the chapters themselves stay."""
    await session.delete(arc)
    await session.flush()


async def assign_chapters(
    session: AsyncSession, story_id: UUID, arc_id: UUID | None, chapter_ids: list[UUID]
) -> int:
    if arc_id is not None:
        owns = (
            await session.execute(select(Arc.id).where(Arc.id == arc_id, Arc.story_id == story_id))
        ).scalar_one_or_none()
        if owns is None:
            raise ValueError("Unknown arc for this story.")
    result = await session.execute(
        update(Chapter)
        .where(Chapter.story_id == story_id, Chapter.id.in_(chapter_ids))
        .values(arc_id=arc_id)
        .returning(Chapter.id)
    )
    await session.flush()
    return len(result.scalars().all())
