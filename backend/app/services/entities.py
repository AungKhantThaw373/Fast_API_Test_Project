"""Entity resolution: names, aliases, candidates, soft merge, and mentions.

Merging is deliberately soft. A merge sets ``merged_into_id`` and keeps the source
row, so old links and old facts still resolve; ``resolve_entity`` follows the chain
to the live target. Nothing here guesses: similarity only *proposes* candidates,
and a merge is an explicit action.

Mention extraction is pure regex over the alias dictionary. It costs zero tokens,
works offline, and improves every time the writer adds an alias.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter
from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityMention,
    EntityRelationship,
)

ARTICLES = ("the", "a", "an")
HONORIFICS = (
    "lord",
    "lady",
    "sir",
    "dame",
    "captain",
    "king",
    "queen",
    "prince",
    "princess",
    "doctor",
    "professor",
)

# Words that are capitalised often enough to be useless as name matches.
STOPWORDS = frozenset(
    {
        "chapter",
        "part",
        "yes",
        "no",
        "oh",
        "ah",
        "well",
        "then",
        "but",
        "and",
        "however",
        "meanwhile",
        "later",
        "now",
        "she",
        "he",
        "they",
        "it",
        "we",
        "you",
        "i",
        "god",
        "sir",
        "madam",
    }
)

MIN_ALIAS_LENGTH = 3
SIMILARITY_THRESHOLD = 0.55
MAX_MERGE_HOPS = 8


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.casefold()
    value = re.sub(r"[^\w\s'-]", " ", value)
    value = re.sub(r"\b(" + "|".join(ARTICLES) + r")\b", " ", value)
    value = re.sub(r"\b(" + "|".join(HONORIFICS) + r")\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class EntityCandidate:
    entity: Entity
    score: float
    matched_alias: str | None = None


async def resolve_entity(session: AsyncSession, entity_id: UUID) -> Entity | None:
    """Follow a merge chain to the live entity."""
    entity = await session.get(Entity, entity_id)
    hops = 0
    while entity is not None and entity.merged_into_id is not None and hops < MAX_MERGE_HOPS:
        entity = await session.get(Entity, entity.merged_into_id)
        hops += 1
    return entity


async def find_candidates(
    session: AsyncSession, story_id: UUID, name: str, limit: int = 5
) -> list[EntityCandidate]:
    """Exact alias match first, then trigram similarity. Never auto-merges."""
    normalized = normalize_name(name)
    if not normalized:
        return []
    exact = (
        await session.execute(
            select(EntityAlias, Entity)
            .join(Entity, Entity.id == EntityAlias.entity_id)
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                EntityAlias.normalized_alias == normalized,
            )
            .limit(limit)
        )
    ).all()
    if exact:
        return [
            EntityCandidate(entity=entity, score=1.0, matched_alias=alias.alias)
            for alias, entity in exact
        ]

    rows = (
        await session.execute(
            select(Entity, func.similarity(Entity.canonical_name, normalized).label("score"))
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                func.similarity(Entity.canonical_name, normalized) > SIMILARITY_THRESHOLD,
            )
            .order_by(func.similarity(Entity.canonical_name, normalized).desc())
            .limit(limit)
        )
    ).all()
    return [EntityCandidate(entity=entity, score=float(score)) for entity, score in rows]


async def create_entity(
    session: AsyncSession,
    *,
    story_id: UUID,
    entity_type: str,
    name: str,
    summary: str = "",
    aliases: list[tuple[str, str]] | None = None,
    entity_id: UUID | None = None,
    first_chapter_number: int | None = None,
    status: str = "active",
) -> Entity:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="An entity needs a name.")
    entity = Entity(
        id=entity_id,
        story_id=story_id,
        entity_type=entity_type,
        name=clean_name,
        canonical_name=normalize_name(clean_name)[:220],
        summary=summary,
        status=status,
        first_chapter_number=first_chapter_number,
        last_chapter_number=first_chapter_number,
    )
    session.add(entity)
    await session.flush()
    await add_alias(session, entity, clean_name, "name")
    for alias, alias_type in aliases or []:
        await add_alias(session, entity, alias, alias_type)
    return entity


async def add_alias(
    session: AsyncSession, entity: Entity, alias: str, alias_type: str = "name"
) -> bool:
    """Insert an alias if this entity does not already have it."""
    clean = alias.strip()
    if not clean:
        return False
    # Honorific-only aliases ("the captain") normalize to nothing; keep them
    # anyway so mention matching can use the words the writer actually typed.
    normalized = normalize_name(clean) or clean.casefold()
    statement = (
        insert(EntityAlias)
        .values(
            entity_id=entity.id,
            alias=clean[:200],
            normalized_alias=normalized[:220],
            alias_type=alias_type,
        )
        .on_conflict_do_nothing(constraint="uq_entity_alias_normalized")
        .returning(EntityAlias.id)
    )
    return (await session.scalar(statement)) is not None


async def alias_map(session: AsyncSession, story_id: UUID) -> dict[str, UUID]:
    """normalized alias -> entity id, for entities that are not merged away."""
    rows = (
        await session.execute(
            select(EntityAlias.normalized_alias, EntityAlias.entity_id)
            .join(Entity, Entity.id == EntityAlias.entity_id)
            .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
        )
    ).all()
    return {
        normalized: entity_id
        for normalized, entity_id in rows
        if len(normalized) >= MIN_ALIAS_LENGTH and normalized not in STOPWORDS
    }


def _alias_pattern(aliases: list[str]) -> re.Pattern[str] | None:
    if not aliases:
        return None
    # Longest first so "Lady Voss" wins over "Voss" at the same position.
    ordered = sorted(set(aliases), key=len, reverse=True)
    body = "|".join(re.escape(alias) for alias in ordered)
    return re.compile(rf"(?<![\w'])(?:{body})(?![\w'])", re.IGNORECASE)


def find_mentions(
    lines: list[str], display: dict[str, UUID]
) -> list[tuple[UUID, int, int, str]]:
    """Return ``(entity_id, line, line, quote)`` per match, longest alias first."""
    pattern = _alias_pattern(list(display))
    if pattern is None:
        return []
    lookup = {alias.casefold(): entity_id for alias, entity_id in display.items()}
    found: list[tuple[UUID, int, int, str]] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        for match in pattern.finditer(line):
            entity_id = lookup.get(match.group(0).casefold())
            if entity_id is None:
                continue
            quote = line.strip()[:500]
            found.append((entity_id, index, index, quote))
    return found


async def extract_mentions(
    session: AsyncSession, story_id: UUID, chapter_id: UUID, content: str
) -> int:
    """Rebuild this chapter's mentions from the alias dictionary."""
    display_rows = (
        await session.execute(
            select(EntityAlias.alias, EntityAlias.entity_id)
            .join(Entity, Entity.id == EntityAlias.entity_id)
            .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
        )
    ).all()
    # Match on the alias as written. Normalization strips honorifics, so
    # ``normalize_name("the captain")`` is empty even though the alias is useful.
    display = {
        alias.strip(): entity_id
        for alias, entity_id in display_rows
        if len(alias.strip()) >= MIN_ALIAS_LENGTH
        and alias.strip().casefold() not in STOPWORDS
    }
    if not display:
        return 0
    lines = content.splitlines()
    matches = find_mentions(lines, display)
    if not matches:
        return 0
    # The same entity can be named twice on one line; one mention per line is the
    # unit the unique constraint stores.
    unique: dict[tuple[UUID, int, int], str] = {}
    for entity_id, line_start, line_end, quote in matches:
        unique.setdefault((entity_id, line_start, line_end), quote)

    await session.execute(
        delete(EntityMention).where(EntityMention.chapter_id == chapter_id)
    )
    inserted = await session.execute(
        insert(EntityMention)
        .values(
            [
                {
                    "entity_id": entity_id,
                    "chapter_id": chapter_id,
                    "line_start": line_start,
                    "line_end": line_end,
                    "quote": quote,
                }
                for (entity_id, line_start, line_end), quote in unique.items()
            ]
        )
        .on_conflict_do_nothing(constraint="uq_entity_mention_range")
        .returning(EntityMention.entity_id)
    )
    touched = {row[0] for row in inserted.all()}
    await refresh_appearance_range(session, story_id, touched)
    return len(unique)


async def refresh_appearance_range(
    session: AsyncSession, story_id: UUID, entity_ids: set[UUID]
) -> None:
    """Recompute first/last chapter from mentions, in one aggregate query."""
    if not entity_ids:
        return
    rows = (
        await session.execute(
            select(
                EntityMention.entity_id,
                func.min(Chapter.chapter_number),
                func.max(Chapter.chapter_number),
            )
            .join(Chapter, Chapter.id == EntityMention.chapter_id)
            .where(EntityMention.entity_id.in_(entity_ids))
            .group_by(EntityMention.entity_id)
        )
    ).all()
    for entity_id, first, last in rows:
        await session.execute(
            update(Entity)
            .where(Entity.id == entity_id)
            .values(first_chapter_number=first, last_chapter_number=last)
        )


async def merge_entities(
    session: AsyncSession,
    *,
    story_id: UUID,
    source_id: UUID,
    target_id: UUID,
    dry_run: bool = False,
) -> dict[str, int]:
    """Move everything from ``source`` onto ``target``; keep the source row."""
    if source_id == target_id:
        raise HTTPException(status_code=422, detail="An entity cannot be merged into itself.")
    source = await session.scalar(
        select(Entity).where(Entity.id == source_id).with_for_update()
    )
    target = await session.scalar(
        select(Entity).where(Entity.id == target_id).with_for_update()
    )
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    if source.story_id != story_id or target.story_id != story_id:
        raise HTTPException(status_code=422, detail="Entities belong to different stories.")
    if source.merged_into_id is not None:
        raise HTTPException(
            status_code=409,
            detail="That entity has already been merged. Resolve it to its target first.",
        )

    counts = {
        "facts": await _alias_count_for(session, EntityFact, source_id),
        "mentions": await _alias_count_for(session, EntityMention, source_id),
        "relationships": await _relationship_counts(session, source_id),
        "events": await _event_counts(session, source_id),
        "threads": await _thread_counts(session, source_id),
        "aliases": await _alias_count(session, source_id),
    }
    if dry_run:
        return counts

    await session.execute(
        update(EntityFact).where(EntityFact.entity_id == source_id).values(entity_id=target_id)
    )
    await session.execute(
        update(EntityMention)
        .where(EntityMention.entity_id == source_id)
        .values(entity_id=target_id)
    )
    await session.execute(
        update(EntityRelationship)
        .where(EntityRelationship.from_entity_id == source_id)
        .values(from_entity_id=target_id)
    )
    await session.execute(
        update(EntityRelationship)
        .where(EntityRelationship.to_entity_id == source_id)
        .values(to_entity_id=target_id)
    )
    # Arrays and metadata are moved with raw SQL: it keeps the ANY() checks and
    # the de-duplication in one statement each.
    array_tables = (
        ("story_events", "participant_entity_ids"),
        ("story_threads", "linked_entity_ids"),
        ("scene_meta", "character_entity_ids"),
    )
    for table, column in array_tables:
        await session.execute(
            text(
                f"UPDATE {table} SET {column} = array_replace({column}, :source, :target) "
                f"WHERE :source = ANY({column})"
            ),
            {"source": source_id, "target": target_id},
        )
        await session.execute(
            text(
                f"UPDATE {table} SET {column} = ("
                f"SELECT coalesce(array_agg(DISTINCT value), '{{}}') "
                f"FROM unnest({column}) AS value) WHERE :target = ANY({column})"
            ),
            {"target": target_id},
        )
    for table in ("chapter_meta", "scene_meta"):
        await session.execute(
            text(
                f"UPDATE {table} SET pov_entity_id = :target WHERE pov_entity_id = :source"
            ),
            {"source": source_id, "target": target_id},
        )
        await session.execute(
            text(
                f"UPDATE {table} SET location_entity_id = :target "
                "WHERE location_entity_id = :source"
            ),
            {"source": source_id, "target": target_id},
        )

    aliases = list(
        await session.scalars(select(EntityAlias).where(EntityAlias.entity_id == source_id))
    )
    for alias in aliases:
        await session.execute(delete(EntityAlias).where(EntityAlias.id == alias.id))
        await add_alias(session, target, alias.alias, alias.alias_type)
    await add_alias(session, target, source.name, "other")

    source.status = "merged"
    source.merged_into_id = target.id
    if source.first_chapter_number is not None:
        target.first_chapter_number = min(
            target.first_chapter_number or source.first_chapter_number,
            source.first_chapter_number,
        )
    if source.last_chapter_number is not None:
        target.last_chapter_number = max(
            target.last_chapter_number or source.last_chapter_number,
            source.last_chapter_number,
        )
    await session.flush()
    return counts


async def _alias_count_for(session, model, source_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(model.entity_id == source_id)
        )
        or 0
    )


async def _relationship_counts(session: AsyncSession, source_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(EntityRelationship)
            .where(
                or_(
                    EntityRelationship.from_entity_id == source_id,
                    EntityRelationship.to_entity_id == source_id,
                )
            )
        )
        or 0
    )


async def _array_counts(session: AsyncSession, table: str, column: str, source_id: UUID) -> int:
    return int(
        await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE :source = ANY({column})"),
            {"source": source_id},
        )
        or 0
    )


async def _event_counts(session: AsyncSession, source_id: UUID) -> int:
    return await _array_counts(session, "story_events", "participant_entity_ids", source_id)


async def _thread_counts(session: AsyncSession, source_id: UUID) -> int:
    return await _array_counts(session, "story_threads", "linked_entity_ids", source_id)


async def _alias_count(session: AsyncSession, source_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(EntityAlias).where(EntityAlias.entity_id == source_id)
        )
        or 0
    )
