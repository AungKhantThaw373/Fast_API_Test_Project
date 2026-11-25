"""Facts and relationships: provenance, review decisions, and supersession.

A fact without provenance is a rumour. Every AI-written row must carry a chapter
and a quote, and the quote's line numbers are located here rather than trusted
from the caller. Accepted facts are the only ones the continuity context uses.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter
from app.models.wiki_models import Entity, EntityFact, EntityRelationship
from app.schemas.wiki import FactCreate, FactUpdate, RelationshipCreate
from app.services.entities import resolve_entity

FACT_STATUSES = ("proposed", "accepted", "rejected", "superseded")


async def chapter_numbers(session: AsyncSession, chapter_ids: set[UUID]) -> dict[UUID, int]:
    if not chapter_ids:
        return {}
    rows = (
        await session.execute(
            select(Chapter.id, Chapter.chapter_number).where(Chapter.id.in_(chapter_ids))
        )
    ).all()
    return {chapter_id: number for chapter_id, number in rows}


def _quote_in_chapter(chapter: Chapter, quote: str) -> bool:
    return " ".join(quote.split()) in " ".join(chapter.content.split())


async def _owned_chapter(session: AsyncSession, story_id: UUID, chapter_id: UUID) -> Chapter:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id or chapter.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


def _locate(chapter: Chapter, quote: str | None) -> tuple[int | None, int | None]:
    if not quote:
        return None, None
    for index, line in enumerate(chapter.content.splitlines(), start=1):
        if quote in line:
            return index, index
    return None, None


async def list_facts(
    session: AsyncSession,
    entity_id: UUID,
    *,
    status: str | None = None,
    predicate: str | None = None,
) -> list[EntityFact]:
    statement = select(EntityFact).where(EntityFact.entity_id == entity_id)
    if status:
        statement = statement.where(EntityFact.status == status)
    if predicate:
        statement = statement.where(EntityFact.predicate == predicate)
    return list(
        await session.scalars(
            statement.order_by(EntityFact.created_at.desc(), EntityFact.id.desc())
        )
    )


async def get_fact(session: AsyncSession, fact_id: UUID) -> EntityFact:
    fact = await session.get(EntityFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return fact


async def create_fact(
    session: AsyncSession, entity: Entity, payload: FactCreate, *, created_by: str = "human"
) -> EntityFact:
    # A fact without a chapter is an opinion. Human and AI facts both carry one;
    # AI facts must also carry a quote that is really in that chapter.
    if payload.chapter_id is None:
        raise HTTPException(
            status_code=422, detail="A fact needs the chapter it comes from."
        )
    chapter = await _owned_chapter(session, entity.story_id, payload.chapter_id)
    chapter_number = chapter.chapter_number
    line_start, line_end = payload.line_start, payload.line_end
    if payload.quote and line_start is None:
        line_start, line_end = _locate(chapter, payload.quote)
    if created_by == "ai":
        if not payload.quote:
            raise HTTPException(
                status_code=422, detail="AI facts need a chapter and a quote for provenance."
            )
        if not _quote_in_chapter(chapter, payload.quote) or line_start is None:
            raise HTTPException(
                status_code=422,
                detail="The quote does not appear in that chapter.",
            )
    if payload.value_entity_id is not None:
        other = await resolve_entity(session, payload.value_entity_id)
        if other is None or other.story_id != entity.story_id:
            raise HTTPException(status_code=422, detail="Linked entity is not in this story.")

    fact = EntityFact(
        entity_id=entity.id,
        predicate=payload.predicate.strip(),
        value_text=payload.value_text,
        value_number=payload.value_number,
        value_date=payload.value_date,
        value_entity_id=payload.value_entity_id,
        value_type=payload.value_type,
        chapter_id=payload.chapter_id,
        scene_index=payload.scene_index,
        line_start=line_start,
        line_end=line_end,
        quote=payload.quote,
        confidence=payload.confidence,
        status=payload.status,
        valid_from_chapter=payload.valid_from_chapter or chapter_number,
        valid_to_chapter=payload.valid_to_chapter,
        supersedes_id=payload.supersedes_id,
        context=payload.context,
        created_by=created_by,
    )
    session.add(fact)
    await session.flush()
    return fact


async def update_fact(session: AsyncSession, fact: EntityFact, payload: FactUpdate) -> EntityFact:
    data = payload.model_dump(exclude_unset=True)
    if "chapter_id" in data and data["chapter_id"] is not None:
        chapter = await session.get(Chapter, data["chapter_id"])
        if chapter is None or chapter.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Chapter not found.")
        entity = await session.get(Entity, fact.entity_id)
        if entity is None or chapter.story_id != entity.story_id:
            raise HTTPException(status_code=404, detail="Chapter not found.")
        if data.get("quote") and "line_start" not in data:
            data["line_start"], data["line_end"] = _locate(chapter, data["quote"])
    for key, value in data.items():
        setattr(fact, key, value)
    await session.flush()
    return fact


async def accept_fact(session: AsyncSession, fact: EntityFact) -> EntityFact:
    """Accept a fact and supersede the accepted value it replaces."""
    if fact.status == "accepted":
        return fact
    stale = await session.scalar(
        select(EntityFact)
        .where(
            EntityFact.entity_id == fact.entity_id,
            EntityFact.predicate == fact.predicate,
            EntityFact.status == "accepted",
            EntityFact.id != fact.id,
        )
        .order_by(EntityFact.created_at.desc())
        .limit(1)
    )
    if stale is not None:
        stale.status = "superseded"
        if fact.supersedes_id is None:
            fact.supersedes_id = stale.id
    fact.status = "accepted"
    await session.flush()
    return fact


async def reject_fact(session: AsyncSession, fact: EntityFact) -> EntityFact:
    fact.status = "rejected"
    await session.flush()
    return fact


async def delete_fact(session: AsyncSession, fact: EntityFact) -> None:
    await session.delete(fact)
    await session.flush()


async def list_relationships(
    session: AsyncSession, entity_id: UUID
) -> tuple[list[EntityRelationship], list[EntityRelationship]]:
    outgoing = list(
        await session.scalars(
            select(EntityRelationship)
            .where(EntityRelationship.from_entity_id == entity_id)
            .order_by(EntityRelationship.created_at)
        )
    )
    incoming = list(
        await session.scalars(
            select(EntityRelationship)
            .where(EntityRelationship.to_entity_id == entity_id)
            .order_by(EntityRelationship.created_at)
        )
    )
    return outgoing, incoming


async def create_relationship(
    session: AsyncSession, entity: Entity, payload: RelationshipCreate
) -> EntityRelationship:
    if payload.to_entity_id == entity.id:
        raise HTTPException(status_code=422, detail="An entity cannot relate to itself.")
    target = await resolve_entity(session, payload.to_entity_id)
    if target is None or target.story_id != entity.story_id:
        raise HTTPException(status_code=422, detail="Target entity is not in this story.")
    if payload.chapter_id is not None:
        await _owned_chapter(session, entity.story_id, payload.chapter_id)
    duplicate = await session.scalar(
        select(EntityRelationship.id).where(
            EntityRelationship.story_id == entity.story_id,
            EntityRelationship.from_entity_id == entity.id,
            EntityRelationship.to_entity_id == payload.to_entity_id,
            EntityRelationship.relationship_type == payload.relationship_type,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="That relationship already exists.")
    relationship = EntityRelationship(
        story_id=entity.story_id,
        from_entity_id=entity.id,
        to_entity_id=payload.to_entity_id,
        relationship_type=payload.relationship_type.strip(),
        description=payload.description,
        since_chapter=payload.since_chapter,
        until_chapter=payload.until_chapter,
        chapter_id=payload.chapter_id,
        quote=payload.quote,
    )
    session.add(relationship)
    await session.flush()
    return relationship


async def get_relationship(session: AsyncSession, relationship_id: UUID) -> EntityRelationship:
    relationship = await session.get(EntityRelationship, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found.")
    return relationship


async def delete_relationship(session: AsyncSession, relationship: EntityRelationship) -> None:
    await session.delete(relationship)
    await session.flush()


async def superseded_by(session: AsyncSession, fact_ids: list[UUID]) -> dict[UUID, UUID]:
    if not fact_ids:
        return {}
    rows = (
        await session.execute(
            select(EntityFact.id, EntityFact.supersedes_id).where(
                EntityFact.supersedes_id.in_(fact_ids)
            )
        )
    ).all()
    return {old_id: new_id for new_id, old_id in rows if old_id is not None}


async def accepted_facts_for(
    session: AsyncSession, story_id: UUID, entity_ids: list[UUID] | None = None
) -> list[EntityFact]:
    statement = (
        select(EntityFact)
        .join(Entity, Entity.id == EntityFact.entity_id)
        .where(
            Entity.story_id == story_id,
            Entity.merged_into_id.is_(None),
            EntityFact.status == "accepted",
        )
    )
    if entity_ids:
        statement = statement.where(EntityFact.entity_id.in_(entity_ids))
    return list(await session.scalars(statement.order_by(EntityFact.predicate)))
