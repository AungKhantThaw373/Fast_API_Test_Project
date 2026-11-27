"""Coverage and lazy extraction for arcs.

Importing a million words should not immediately spend a million words of
extraction. Text and chunk vectors are written first; canon extraction runs
only for the arc a writer asks about, and older arcs remain available for an
explicit backfill.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Arc, Chapter, Story
from app.services import indexing
from app.services.ai_settings import has_ai_config


@dataclass(frozen=True)
class ArcCoverage:
    arc_id: UUID
    arc_name: str
    position: float
    chapter_count: int
    first_chapter_number: int | None
    last_chapter_number: int | None
    extracted_count: int


@dataclass(frozen=True)
class CanonCoverage:
    story_id: UUID
    current_arc_id: UUID | None
    chapters: int
    extracted: int
    unassigned_chapters: int
    arcs: list[ArcCoverage]


async def coverage(session: AsyncSession, story_id: UUID) -> CanonCoverage:
    """Count chapters whose current revision has been extracted, per arc."""
    rows = (
        await session.execute(
            select(
                Arc.id,
                Arc.name,
                Arc.position,
                func.count(Chapter.id),
                func.min(Chapter.chapter_number),
                func.max(Chapter.chapter_number),
                func.count(Chapter.id).filter(
                    Chapter.bible_scan_revision.is_not(None),
                    Chapter.bible_scan_revision == Chapter.revision,
                ),
            )
            .outerjoin(
                Chapter,
                and_(Chapter.arc_id == Arc.id, Chapter.deleted_at.is_(None)),
            )
            .where(Arc.story_id == story_id)
            .group_by(Arc.id)
            .order_by(Arc.position, Arc.name)
        )
    ).all()
    arcs = [
        ArcCoverage(
            arc_id=row[0],
            arc_name=row[1],
            position=float(row[2]),
            chapter_count=int(row[3] or 0),
            first_chapter_number=row[4],
            last_chapter_number=row[5],
            extracted_count=int(row[6] or 0),
        )
        for row in rows
    ]
    current_arc_id = await session.scalar(
        select(Chapter.arc_id)
        .where(Chapter.story_id == story_id, Chapter.deleted_at.is_(None))
        .order_by(Chapter.chapter_number.desc())
        .limit(1)
    )
    chapters = sum(arc.chapter_count for arc in arcs)
    extracted = sum(arc.extracted_count for arc in arcs)
    total_for_story = int(
        await session.scalar(
            select(func.count(Chapter.id)).where(
                Chapter.story_id == story_id, Chapter.deleted_at.is_(None)
            )
        )
        or 0
    )
    return CanonCoverage(
        story_id=story_id,
        current_arc_id=current_arc_id,
        chapters=chapters,
        extracted=extracted,
        unassigned_chapters=max(0, total_for_story - chapters),
        arcs=arcs,
    )


async def queue_arc_extraction(
    session: AsyncSession,
    story: Story,
    arc_id: UUID,
    user_id: UUID,
    *,
    force: bool = False,
) -> tuple[int, int, int]:
    """Queue only the chapters in one arc that still need extraction."""
    arc = await session.scalar(
        select(Arc).where(Arc.id == arc_id, Arc.story_id == story.id)
    )
    if arc is None:
        raise HTTPException(status_code=404, detail="Arc not found.")
    rows = (
        await session.execute(
            select(Chapter.id, Chapter.revision, Chapter.bible_scan_revision)
            .where(
                Chapter.story_id == story.id,
                Chapter.arc_id == arc.id,
                Chapter.deleted_at.is_(None),
                func.length(func.trim(Chapter.content)) > 0,
            )
            .order_by(Chapter.position)
        )
    ).all()
    if force:
        selected = rows
    else:
        selected = [row for row in rows if row[2] != row[1]]
    if selected and not await has_ai_config(session, user_id):
        raise HTTPException(
            status_code=503,
            detail="Configure an AI provider before extracting canon for an arc.",
        )
    if selected:
        values: dict[str, object] = {"bible_scan_error": None}
        if force:
            values["bible_scan_revision"] = None
        await session.execute(
            update(Chapter)
            .where(Chapter.id.in_([row[0] for row in selected]))
            .values(**values)
        )
        await session.commit()
    for row in selected:
        await indexing.enqueue_bible_scan(
            session,
            row[0],
            owner_id=user_id,
            revision=row[1],
        )
    return len(selected), len(rows) - len(selected), len(rows)