"""Recaps: editable chapter synopses, arc summaries, and Story so far."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Arc, Chapter, Story
from app.models.wiki_models import ChapterMeta
from app.schemas.recaps import (
    ArcRecapOut,
    ArcSummaryOut,
    ChapterSynopsisOut,
    RecapChapterOut,
    RecapCitationOut,
    StorySoFarOut,
)
from app.services import stories as stories_service

MAX_SYNOPSIS = 20_000


def _sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    parts: list[str] = []
    start = 0
    for index, char in enumerate(cleaned):
        if char in ".!?" and (index + 1 == len(cleaned) or cleaned[index + 1].isspace()):
            sentence = cleaned[start : index + 1].strip()
            if sentence:
                parts.append(sentence)
            start = index + 1
    tail = cleaned[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def extractive_synopsis(text: str, max_chars: int = 700) -> str:
    """A deterministic, local summary: opening, a strong middle sentence, and the last beat."""
    sentences = _sentences(text)
    if not sentences:
        return ""
    if len(sentences) <= 3:
        return _clip(" ".join(sentences), max_chars)
    middle = max(
        sentences[1:-1],
        key=lambda sentence: (
            0 if any(marker in sentence.lower() for marker in ("but", "however", "instead", "finally")) else 1,
            min(len(sentence), 180),
        ),
    )
    chosen = [sentences[0], middle, sentences[-1]]
    seen: set[str] = set()
    unique = [sentence for sentence in chosen if not (sentence in seen or seen.add(sentence))]
    return _clip(" ".join(unique), max_chars)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def citation_for(chapter: Chapter) -> RecapCitationOut:
    line_number = 1
    quote = ""
    for index, line in enumerate(chapter.content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        line_number = index
        quote = _clip(" ".join(stripped.split()), 280)
        break
    if not quote:
        quote = chapter.title
    return RecapCitationOut(
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        quote=quote,
        line=line_number,
    )


async def _chapter_meta(session: AsyncSession, chapter_id: UUID) -> ChapterMeta | None:
    return await session.get(ChapterMeta, chapter_id)


async def chapter_synopsis(session: AsyncSession, chapter: Chapter) -> ChapterSynopsisOut:
    meta = await _chapter_meta(session, chapter.id)
    manual = (meta.synopsis if meta else "").strip()
    generated = not manual
    synopsis = manual or extractive_synopsis(chapter.content)
    return ChapterSynopsisOut(
        chapter_id=chapter.id,
        synopsis=synopsis,
        editable=True,
        generated=generated,
    )


async def save_synopsis(session: AsyncSession, chapter: Chapter, synopsis: str) -> ChapterSynopsisOut:
    cleaned = synopsis.strip()
    if len(cleaned) > MAX_SYNOPSIS:
        raise HTTPException(status_code=422, detail="A synopsis must be 20,000 characters or fewer.")
    meta = await _chapter_meta(session, chapter.id)
    if meta is None:
        meta = ChapterMeta(chapter_id=chapter.id)
        session.add(meta)
    meta.synopsis = cleaned
    await session.commit()
    return ChapterSynopsisOut(chapter_id=chapter.id, synopsis=cleaned, editable=True, generated=False)


async def generate_synopsis(
    session: AsyncSession, chapter: Chapter, *, overwrite: bool
) -> ChapterSynopsisOut:
    if not chapter.content.strip():
        raise HTTPException(status_code=409, detail="This chapter has no text to summarize yet.")
    meta = await _chapter_meta(session, chapter.id)
    existing = (meta.synopsis if meta else "").strip()
    if existing and not overwrite:
        return ChapterSynopsisOut(
            chapter_id=chapter.id, synopsis=existing, editable=True, generated=False
        )
    synopsis = extractive_synopsis(chapter.content)
    if meta is None:
        meta = ChapterMeta(chapter_id=chapter.id)
        session.add(meta)
    meta.synopsis = synopsis
    await session.commit()
    return ChapterSynopsisOut(chapter_id=chapter.id, synopsis=synopsis, editable=True, generated=True)


async def owned_arc(session: AsyncSession, arc_id: UUID, story_id: UUID, user_id: UUID) -> Arc:
    await stories_service.owned_story(session, story_id, user_id)
    arc = await session.get(Arc, arc_id)
    if arc is None or arc.story_id != story_id:
        raise HTTPException(status_code=404, detail="Arc not found.")
    return arc


async def arc_chapters(session: AsyncSession, arc: Arc) -> list[Chapter]:
    return list(
        await session.scalars(
            select(Chapter)
            .where(Chapter.arc_id == arc.id, Chapter.deleted_at.is_(None))
            .order_by(Chapter.chapter_number)
        )
    )


async def generate_arc_summary(session: AsyncSession, arc: Arc) -> ArcSummaryOut:
    chapters = await arc_chapters(session, arc)
    if not chapters:
        raise HTTPException(status_code=409, detail="Add chapters to this arc before summarizing it.")
    metas = {
        meta.chapter_id: meta
        for meta in await session.scalars(
            select(ChapterMeta).where(ChapterMeta.chapter_id.in_([chapter.id for chapter in chapters]))
        )
    }
    lines: list[str] = []
    for chapter in chapters:
        meta = metas.get(chapter.id)
        synopsis = (meta.synopsis if meta else "").strip() or extractive_synopsis(chapter.content)
        if synopsis:
            lines.append(f"Chapter {chapter.chapter_number} — {chapter.title}: {synopsis}")
    summary = _clip("\n\n".join(lines), MAX_SYNOPSIS)
    arc.summary = summary
    await session.commit()
    return ArcSummaryOut(arc_id=arc.id, summary=summary, chapter_count=len(chapters))


async def story_so_far(
    session: AsyncSession, story: Story, *, limit: int, arc_id: UUID | None
) -> StorySoFarOut:
    selected_arc: Arc | None = None
    if arc_id is not None:
        selected_arc = await owned_arc(session, arc_id, story.id, story.owner_id)
    query = select(Chapter).where(Chapter.story_id == story.id, Chapter.deleted_at.is_(None))
    if selected_arc is not None:
        query = query.where(Chapter.arc_id == selected_arc.id)
    chapters = list(
        await session.scalars(query.order_by(Chapter.chapter_number.desc()).limit(limit))
    )
    chapters.reverse()
    metas = {
        meta.chapter_id: meta
        for meta in await session.scalars(
            select(ChapterMeta).where(ChapterMeta.chapter_id.in_([chapter.id for chapter in chapters]))
        )
    } if chapters else {}
    rows: list[RecapChapterOut] = []
    for chapter in chapters:
        meta = metas.get(chapter.id)
        synopsis = (meta.synopsis if meta else "").strip() or extractive_synopsis(chapter.content)
        rows.append(
            RecapChapterOut(
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                synopsis=synopsis,
                citation=citation_for(chapter),
            )
        )
    arc_ids = {chapter.arc_id for chapter in chapters if chapter.arc_id}
    arcs: list[ArcRecapOut] = []
    if arc_ids:
        arc_rows = list(await session.scalars(select(Arc).where(Arc.id.in_(arc_ids))))
        arcs = [ArcRecapOut(arc_id=arc.id, name=arc.name, summary=arc.summary) for arc in arc_rows]
    label = ""
    if rows:
        first, last = rows[0].chapter_number, rows[-1].chapter_number
        label = f"Chapter {first}" if first == last else f"Chapters {first}–{last}"
    return StorySoFarOut(
        story_id=story.id,
        range_label=label,
        chapters=rows,
        arcs=arcs,
        read_only=True,
        generated_at=datetime.now(UTC),
    )