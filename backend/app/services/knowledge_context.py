"""Canon notes for the continuity prompt, built from accepted facts.

Vector search finds what the draft *looks like*; this finds what the story
*knows*. Only accepted facts about entities named in the draft, their
relationships, and threads still open before this chapter are included, so the
model gets a short, high-signal block instead of a dump of the whole wiki.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityRelationship,
    StoryThread,
)
from app.services.entities import find_mentions

MAX_FACTS = 40
MAX_THREADS = 12
MAX_RELATIONSHIPS = 20


def _format_fact(fact: EntityFact, name: str) -> str:
    if fact.value_text:
        value = fact.value_text.strip().replace("\n", " ")
    elif fact.value_number is not None:
        value = f"{fact.value_number:g}"
    elif fact.value_date is not None:
        value = fact.value_date.isoformat()
    else:
        value = "(see linked entity)"
    chapter = f" (chapter {fact.valid_from_chapter})" if fact.valid_from_chapter else ""
    return f"- {name} | {fact.predicate.replace('_', ' ')}: {value}{chapter}"


async def mentioned_entity_ids(
    session: AsyncSession, story_id: UUID, draft_text: str
) -> set[UUID]:
    """Entities named in the draft, by alias regex - no model call."""
    rows = await session.execute(
        select(Entity.id, Entity.name, EntityAlias.alias)
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
    )
    display: dict[str, UUID] = {}
    for entity_id, name, alias in rows.all():
        for candidate in (name, alias):
            if len(candidate.strip()) >= 3:
                display[candidate.strip()] = entity_id
    if not display:
        return set()
    direct = find_mentions(draft_text.splitlines(), display)
    return {entity_id for entity_id, _start, _end, _quote in direct}


async def build_fact_context(
    session: AsyncSession, story_id: UUID, draft_text: str, chapter_number: int
) -> tuple[str, dict[str, int]]:
    entity_ids = await mentioned_entity_ids(session, story_id, draft_text)
    stats = {"entities": len(entity_ids), "facts": 0, "threads": 0, "relationships": 0}
    if not entity_ids:
        return "", stats

    facts = list(
        await session.scalars(
            select(EntityFact)
            .where(
                EntityFact.entity_id.in_(entity_ids),
                EntityFact.status == "accepted",
            )
            .order_by(EntityFact.updated_at.desc())
            .limit(MAX_FACTS)
        )
    )
    facts = [
        fact
        for fact in facts
        if fact.valid_from_chapter is None or fact.valid_from_chapter <= chapter_number
    ]
    names = {
        entity_id: name
        for entity_id, name in (
            await session.execute(
                select(Entity.id, Entity.name).where(Entity.id.in_(entity_ids))
            )
        ).all()
    }
    lines: list[str] = [_format_fact(fact, names.get(fact.entity_id, "?")) for fact in facts]
    stats["facts"] = len(lines)

    relationships = list(
        await session.scalars(
            select(EntityRelationship)
            .where(
                EntityRelationship.from_entity_id.in_(entity_ids),
                EntityRelationship.to_entity_id.in_(entity_ids),
                EntityRelationship.status == "accepted",
            )
            .limit(MAX_RELATIONSHIPS)
        )
    )
    for relationship in relationships:
        lines.append(
            f"- {names.get(relationship.from_entity_id, '?')} "
            f"{relationship.relationship_type.replace('_', ' ')} "
            f"{names.get(relationship.to_entity_id, '?')}"
            + (f": {relationship.description}" if relationship.description else "")
        )
    stats["relationships"] = len(relationships)

    threads = list(
        await session.scalars(
            select(StoryThread)
            .where(
                StoryThread.story_id == story_id,
                StoryThread.state.in_(("open", "touched")),
            )
            .order_by(StoryThread.created_at.desc())
            .limit(MAX_THREADS)
        )
    )
    for thread in threads:
        lines.append(f"- Unresolved thread: {thread.title}")
    stats["threads"] = len(threads)

    if not lines:
        return "", stats
    return "\n".join(lines), stats


def fact_system_note() -> str:
    return (
        " CANON NOTES list facts the writer has already accepted for named characters and places. "
        "Treat them as canon unless the draft deliberately changes them; if it does, that is a "
        "legitimate development, not a contradiction."
    )
