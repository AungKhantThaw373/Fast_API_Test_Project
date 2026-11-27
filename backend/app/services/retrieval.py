"""Hybrid retrieval and entity-first context for Phase 5.

The retrieval path is deliberately boring: one indexed vector scan, one
full-text scan, one name scan, then reciprocal rank fusion. No provider call
is needed to answer "where did I say X?", and no loop runs one query per scene.

Entity context is assembled before prose so a fact established five hundred
chapters ago survives even when its passage is nowhere near the current scene.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from starlette.concurrency import run_in_threadpool

from app.models.story_models import Chapter, StoryChunk
from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityMention,
    EntityRelationship,
    StoryThread,
)
from app.services.ai_service import embed_queries
from app.services.chunking import approximate_tokens
from app.services.entities import STOPWORDS, find_mentions, normalize_name

RRF_K = 60
DEFAULT_CONTEXT_TOKENS = 6000
VECTOR_LIMIT = 30
LEXICAL_LIMIT = 30
NAME_LIMIT = 10
MAX_CHUNKS_PER_CHAPTER = 3
# Vector first; lexical and name recover exact phrases and proper nouns.
RRF_WEIGHTS = [8.0, 0.5, 0.2]


@dataclass(frozen=True)
class SearchFilters:
    chapter_min: int | None = None
    chapter_max: int | None = None
    entity_id: UUID | None = None
    pov_entity_id: UUID | None = None
    arc_id: UUID | None = None
    chunk_kind: str | None = None


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: UUID
    chapter_id: UUID
    chapter_number: int
    scene_index: int
    chunk_index: int
    text: str
    start_line: int
    end_line: int
    score: float
    scores: dict[str, float] = field(default_factory=dict)
    entity_ids: list[UUID] = field(default_factory=list)


@dataclass
class EntityContext:
    text: str
    token_count: int
    entity_ids: list[UUID]
    facts: int = 0
    relationships: int = 0
    threads: int = 0
    appearances: int = 0
    context_hash: str = ""


@dataclass
class RetrievalResult:
    chunks: list[ChunkHit]
    entity_ids: list[UUID]
    context: EntityContext
    semantic_query: str
    lexical_query: str
    name_query: str
    cache_hit: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rank_lists: list[list[UUID]],
    k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[tuple[UUID, float]]:
    """Deterministic weighted RRF; ties break on the id, never on insertion.

    The vector list is deliberately weighted above the lexical and name lists.
    Equal weights let one noisy FTS match outrank a correct semantic hit. The
    other retrievers are there to recover names and exact phrases, not to
    replace the embedding.
    """
    if weights is None:
        weights = [1.0] * len(rank_lists)
    scores: dict[UUID, float] = {}
    for index, results in enumerate(rank_lists):
        weight = weights[index] if index < len(weights) else 1.0
        seen: set[UUID] = set()
        for rank, item in enumerate(results, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], str(pair[0])))


def apply_filters(statement, filters: SearchFilters):
    if filters.chapter_min is not None:
        statement = statement.where(StoryChunk.chapter_number >= filters.chapter_min)
    if filters.chapter_max is not None:
        statement = statement.where(StoryChunk.chapter_number <= filters.chapter_max)
    if filters.entity_id is not None:
        statement = statement.where(StoryChunk.entities.op("&&")([filters.entity_id]))
    if filters.pov_entity_id is not None:
        statement = statement.where(StoryChunk.pov_entity_id == filters.pov_entity_id)
    if filters.chunk_kind is not None:
        statement = statement.where(StoryChunk.chunk_kind == filters.chunk_kind)
    if filters.arc_id is not None:
        statement = statement.join(Chapter, Chapter.id == StoryChunk.chapter_id).where(
            Chapter.arc_id == filters.arc_id
        )
    return statement


def lexical_query_for(scene_text: str, entity_names: list[str], limit: int = 14) -> str:
    """AND the distinctive terms; the vector list carries the broad recall."""
    words: list[str] = []
    for name in entity_names:
        words.extend(part for part in name.replace("-", " ").split() if len(part) > 1)
    words.extend(
        word.strip(".,;:!?()[]{}\'\"")
        for word in scene_text.replace("\n", " ").split()
    )
    stop = {
        "the", "and", "she", "her", "his", "him", "they", "them", "that", "this",
        "with", "from", "into", "onto", "were", "was", "had", "have", "not", "but",
        "for", "you", "your", "said", "then", "when", "what", "who", "how", "why",
        "does", "did", "do", "is", "are", "be", "been", "being", "where", "which",
        "whom", "whose", "about", "at", "by", "in", "of", "on", "to", "as", "it",
        "its", "these", "those", "a", "an",
    }
    seen: list[str] = []
    for word in words:
        cleaned = word.strip().strip(".,;:!?()[]{}\'\"")
        if len(cleaned) < 3 or cleaned.casefold() in stop:
            continue
        if cleaned.casefold() in {item.casefold() for item in seen}:
            continue
        seen.append(cleaned)
        if len(seen) >= limit:
            break
    return " ".join(seen)


async def match_entity_ids(
    session: AsyncSession, story_id: UUID, query: str, limit: int = NAME_LIMIT
) -> list[UUID]:
    normalized = normalize_name(query) or query.strip().casefold()
    found: dict[UUID, float] = {}
    exact = (
        await session.execute(
            select(Entity.id).where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                or_(
                    Entity.canonical_name == normalized,
                    Entity.id.in_(
                        select(EntityAlias.entity_id).where(
                            EntityAlias.normalized_alias == normalized
                        )
                    ),
                ),
            )
        )
    ).scalars()
    for entity_id in exact:
        found[entity_id] = 1.0
    if len(normalized) >= 3:
        name_rows = (
            await session.execute(
                select(Entity.id, func.similarity(Entity.name, normalized).label("score"))
                .where(
                    Entity.story_id == story_id,
                    Entity.merged_into_id.is_(None),
                    Entity.name.op("%")(normalized),
                )
                .order_by(func.similarity(Entity.name, normalized).desc(), Entity.id)
                .limit(limit)
            )
        ).all()
        for entity_id, score in name_rows:
            found[entity_id] = max(found.get(entity_id, 0.0), float(score or 0.0))
        alias_rows = (
            await session.execute(
                select(
                    EntityAlias.entity_id,
                    func.similarity(EntityAlias.alias, normalized).label("score"),
                )
                .where(
                    EntityAlias.alias.op("%")(normalized),
                    EntityAlias.entity_id.in_(
                        select(Entity.id).where(
                            Entity.story_id == story_id,
                            Entity.merged_into_id.is_(None),
                        )
                    ),
                )
                .order_by(func.similarity(EntityAlias.alias, normalized).desc())
                .limit(limit)
            )
        ).all()
        for entity_id, score in alias_rows:
            found[entity_id] = max(found.get(entity_id, 0.0), float(score or 0.0))
    return [entity_id for entity_id, _score in sorted(found.items(), key=lambda pair: (-pair[1], str(pair[0])))[:limit]]


async def entity_ids_in_text(
    session: AsyncSession, story_id: UUID, scene_text: str
) -> list[UUID]:
    rows = (
        await session.execute(
            select(EntityAlias.alias, EntityAlias.entity_id)
            .join(Entity, Entity.id == EntityAlias.entity_id)
            .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
        )
    ).all()
    display = {
        alias.strip(): entity_id
        for alias, entity_id in rows
        if len(alias.strip()) >= 3 and alias.strip().casefold() not in STOPWORDS
    }
    found = [
        entity_id
        for entity_id, _start, _end, _quote in find_mentions(scene_text.splitlines(), display)
    ]
    return list(dict.fromkeys(found))


async def vector_search(
    session: AsyncSession,
    story_id: UUID,
    vector: list[float],
    filters: SearchFilters,
    limit: int = VECTOR_LIMIT,
) -> list[tuple[StoryChunk, float]]:
    # HNSW is approximate and a story filter can discard most of its first
    # candidates. ef_search=400 kept 0.993 top-30 recall in the 100k benchmark
    # and is the setting where the planner keeps choosing the HNSW index on the
    # 6.6k-chunk scale story. Relaxed iterative scanning fills a selective limit.
    await session.execute(text("SET LOCAL hnsw.ef_search = 400"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
    await session.execute(text("SET LOCAL hnsw.max_scan_tuples = 200000"))
    distance = StoryChunk.embedding.cosine_distance(vector)
    # Keep the sort tuple narrow. Selecting the ORM entity here makes Postgres
    # detoast every embedding and scene text in the table before the top-N
    # sort; ids plus a score cut the scanned width from kilobytes to bytes.
    ranking = apply_filters(
        select(StoryChunk.id, (1.0 - distance).label("score")).where(
            StoryChunk.story_id == story_id
        ),
        filters,
    )
    rows = (await session.execute(ranking.order_by(distance).limit(limit))).all()
    if not rows:
        return []
    scores = {row[0]: float(row[1]) for row in rows}
    chunks = await session.scalars(
        select(StoryChunk)
        .options(defer(StoryChunk.embedding))
        .where(StoryChunk.id.in_(scores))
    )
    hits = [(chunk, scores[chunk.id]) for chunk in chunks]
    return sorted(hits, key=lambda row: (-row[1], str(row[0].id)))


async def lexical_search(
    session: AsyncSession,
    story_id: UUID,
    query: str,
    filters: SearchFilters,
    limit: int = LEXICAL_LIMIT,
) -> list[tuple[StoryChunk, float]]:
    if not query.strip():
        return []
    tsquery = func.websearch_to_tsquery("simple", query)
    rank = func.ts_rank_cd(StoryChunk.text_search, tsquery)
    statement = apply_filters(
        select(StoryChunk, rank.label("score"))
        .options(defer(StoryChunk.embedding))
        .where(
            StoryChunk.story_id == story_id,
            StoryChunk.text_search.op("@@")(tsquery),
        ),
        filters,
    )
    statement = statement.order_by(rank.desc(), StoryChunk.id).limit(limit)
    return [(row[0], float(row[1] or 0.0)) for row in (await session.execute(statement)).all()]


async def name_chunk_search(
    session: AsyncSession,
    story_id: UUID,
    entity_ids: list[UUID],
    filters: SearchFilters,
    limit: int = NAME_LIMIT,
) -> list[tuple[StoryChunk, float]]:
    if not entity_ids:
        return []
    statement = apply_filters(
        select(StoryChunk)
        .options(defer(StoryChunk.embedding))
        .where(
            StoryChunk.story_id == story_id,
            StoryChunk.entities.op("&&")(entity_ids),
        ),
        filters,
    )
    statement = statement.order_by(StoryChunk.chapter_number.desc(), StoryChunk.chunk_index).limit(limit)
    return [(row[0], 1.0) for row in (await session.execute(statement)).all()]


def _merge_texts(left: str, right: str) -> str:
    max_overlap = min(len(left), len(right), 800)
    for size in range(max_overlap, 0, -1):
        if left[-size:] == right[:size]:
            return left + right[size:]
    return left + "\n\n" + right


def merge_adjacent(hits: list[ChunkHit]) -> list[ChunkHit]:
    ordered = sorted(hits, key=lambda hit: (hit.chapter_number, hit.scene_index, hit.chunk_index))
    merged: list[ChunkHit] = []
    for hit in ordered:
        if (
            merged
            and merged[-1].chapter_id == hit.chapter_id
            and merged[-1].scene_index == hit.scene_index
            and hit.chunk_index <= merged[-1].chunk_index + 1
        ):
            previous = merged[-1]
            merged[-1] = ChunkHit(
                chunk_id=previous.chunk_id,
                chapter_id=previous.chapter_id,
                chapter_number=previous.chapter_number,
                scene_index=previous.scene_index,
                chunk_index=previous.chunk_index,
                text=_merge_texts(previous.text, hit.text),
                start_line=min(previous.start_line, hit.start_line),
                end_line=max(previous.end_line, hit.end_line),
                score=max(previous.score, hit.score),
                scores=previous.scores,
                entity_ids=list(dict.fromkeys([*previous.entity_ids, *hit.entity_ids])),
            )
        else:
            merged.append(hit)
    return sorted(merged, key=lambda hit: (-hit.score, hit.chapter_number, hit.chunk_index))


def cap_per_chapter(hits: list[ChunkHit], cap: int = MAX_CHUNKS_PER_CHAPTER) -> list[ChunkHit]:
    counts: dict[UUID, int] = {}
    kept: list[ChunkHit] = []
    for hit in hits:
        if counts.get(hit.chapter_id, 0) >= cap:
            continue
        counts[hit.chapter_id] = counts.get(hit.chapter_id, 0) + 1
        kept.append(hit)
    return kept


async def _index_version(session: AsyncSession, story_id: UUID) -> str:
    row = await session.execute(
        text(
            "SELECT "
            "COALESCE((SELECT max(created_at)::text FROM story_chunks WHERE story_id = :story), '') "
            "|| '|' || "
            "COALESCE((SELECT max(f.updated_at)::text FROM entity_facts f "
            "JOIN entities e ON e.id = f.entity_id WHERE e.story_id = :story), '')"
        ),
        {"story": str(story_id)},
    )
    return str(row.scalar_one() or "")


class RetrievalCache:
    def __init__(self, maxsize: int = 256, ttl_seconds: float = 60.0) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._data: dict[str, tuple[float, RetrievalResult]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> RetrievalResult | None:
        item = self._data.get(key)
        if item is None or time.monotonic() - item[0] > self.ttl_seconds:
            if item is not None:
                self._data.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return item[1]

    def clear(self) -> None:
        self._data.clear()

    def put(self, key: str, result: RetrievalResult) -> None:
        if len(self._data) >= self.maxsize:
            oldest = min(self._data, key=lambda item: self._data[item][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic(), result)

    def stats(self) -> dict[str, float | int]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


CACHE = RetrievalCache()


def _cache_key(
    story_id: UUID, query: str, filters: SearchFilters, limit: int, version: str
) -> str:
    raw = (
        f"{story_id}|{limit}|{version}|{filters.chapter_min}|{filters.chapter_max}|"
        f"{filters.entity_id}|{filters.pov_entity_id}|{filters.arc_id}|{filters.chunk_kind}|{query}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def search_chunks(
    session: AsyncSession,
    story_id: UUID,
    query: str,
    *,
    limit: int = 10,
    filters: SearchFilters | None = None,
    entity_ids: list[UUID] | None = None,
    use_cache: bool = True,
) -> RetrievalResult:
    started = time.perf_counter()
    filters = filters or SearchFilters()
    query = query.strip()
    if not query:
        empty = EntityContext(text="", token_count=0, entity_ids=[])
        return RetrievalResult(
            chunks=[],
            entity_ids=[],
            context=empty,
            semantic_query="",
            lexical_query="",
            name_query="",
            timings_ms={"embed": 0.0, "total": 0.0},
        )
    version = await _index_version(session, story_id) if use_cache else ""
    key = _cache_key(story_id, query, filters, limit, version)
    if use_cache:
        cached = CACHE.get(key)
        if cached is not None:
            cached.cache_hit = True
            return cached

    if entity_ids is None:
        entity_ids = await entity_ids_in_text(session, story_id, query)
    entities = list(
        await session.scalars(select(Entity).where(Entity.id.in_(entity_ids)))
    ) if entity_ids else []
    names = [entity.name for entity in entities]
    lexical = lexical_query_for(query, names)
    semantic = query[:2400]
    names_query = " ".join(names)

    embed_started = time.perf_counter()
    vector = (await run_in_threadpool(embed_queries, [semantic]))[0]
    embed_ms = (time.perf_counter() - embed_started) * 1000
    vector_started = time.perf_counter()
    vector_rows = await vector_search(session, story_id, vector, filters)
    vector_ms = (time.perf_counter() - vector_started) * 1000
    lexical_started = time.perf_counter()
    lexical_rows = await lexical_search(session, story_id, lexical, filters)
    lexical_ms = (time.perf_counter() - lexical_started) * 1000
    matched_ids = list(entity_ids)
    for entity_id in await match_entity_ids(session, story_id, query or names_query):
        if entity_id not in matched_ids:
            matched_ids.append(entity_id)
    name_started = time.perf_counter()
    name_rows = await name_chunk_search(session, story_id, matched_ids, filters)
    name_ms = (time.perf_counter() - name_started) * 1000

    by_id: dict[UUID, StoryChunk] = {}
    raw_scores: dict[UUID, dict[str, float]] = {}
    rank_lists: list[list[UUID]] = []
    for label, rows in (
        ("vector", vector_rows),
        ("lexical", lexical_rows),
        ("name", name_rows),
    ):
        ids: list[UUID] = []
        for chunk, score in rows:
            by_id[chunk.id] = chunk
            raw_scores.setdefault(chunk.id, {})[label] = round(float(score), 6)
            ids.append(chunk.id)
        rank_lists.append(ids)

    fused = reciprocal_rank_fusion(rank_lists, weights=RRF_WEIGHTS)
    hits: list[ChunkHit] = []
    for chunk_id, score in fused:
        chunk = by_id[chunk_id]
        hits.append(
            ChunkHit(
                chunk_id=chunk.id,
                chapter_id=chunk.chapter_id,
                chapter_number=chunk.chapter_number,
                scene_index=chunk.scene_index,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=round(score, 6),
                scores=raw_scores.get(chunk_id, {}),
                entity_ids=list(chunk.entities),
            )
        )
    hits = cap_per_chapter(merge_adjacent(hits), cap=MAX_CHUNKS_PER_CHAPTER)[:limit]
    elapsed_ms = (time.perf_counter() - started) * 1000
    result = RetrievalResult(
        chunks=hits,
        entity_ids=entity_ids,
        context=EntityContext(text="", token_count=0, entity_ids=entity_ids),
        semantic_query=semantic,
        lexical_query=lexical,
        name_query=names_query,
        timings_ms={
            "embed": round(embed_ms, 2),
            "vector": round(vector_ms, 2),
            "lexical": round(lexical_ms, 2),
            "name": round(name_ms, 2),
            "total": round(elapsed_ms, 2),
        },
    )
    if use_cache:
        CACHE.put(key, result)
    return result


def _excerpt(text: str, max_chars: int = 420) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[:max_chars]
    last = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return cut[: last + 1].strip() if last > 0 else ""


def _append_line(lines: list[str], line: str, budget: int) -> bool:
    candidate = "\n".join([*lines, line])
    if approximate_tokens(candidate) > budget:
        return False
    lines.append(line)
    return True


async def build_entity_context(
    session: AsyncSession,
    story_id: UUID,
    entity_ids: list[UUID],
    *,
    current_chapter: int | None = None,
    prose_hits: list[ChunkHit] | None = None,
    budget_tokens: int = DEFAULT_CONTEXT_TOKENS,
) -> EntityContext:
    """Facts, threads, relationships, appearances, then prose. Hard cap."""
    if not entity_ids:
        return EntityContext(text="", token_count=0, entity_ids=[])
    entities = list(
        await session.scalars(
            select(Entity).where(Entity.story_id == story_id, Entity.id.in_(entity_ids))
        )
    )
    if not entities:
        return EntityContext(text="", token_count=0, entity_ids=[])
    entity_by_id = {entity.id: entity for entity in entities}
    aliases_by_entity: dict[UUID, list[str]] = {entity.id: [] for entity in entities}
    for alias in await session.scalars(
        select(EntityAlias).where(EntityAlias.entity_id.in_(entity_by_id))
    ):
        aliases_by_entity[alias.entity_id].append(alias.alias)

    fact_statement = select(EntityFact).where(
        EntityFact.entity_id.in_(entity_by_id),
        EntityFact.status == "accepted",
    )
    if current_chapter is not None:
        fact_statement = fact_statement.where(
            or_(EntityFact.valid_from_chapter.is_(None), EntityFact.valid_from_chapter <= current_chapter),
            or_(EntityFact.valid_to_chapter.is_(None), EntityFact.valid_to_chapter >= current_chapter),
        )
    facts = list(
        await session.scalars(
            fact_statement.order_by(
                EntityFact.entity_id,
                EntityFact.predicate,
                EntityFact.valid_from_chapter.nullsfirst(),
            ).limit(120)
        )
    )

    relationship_statement = select(EntityRelationship).where(
        EntityRelationship.story_id == story_id,
        EntityRelationship.status == "accepted",
        or_(
            EntityRelationship.from_entity_id.in_(entity_by_id),
            EntityRelationship.to_entity_id.in_(entity_by_id),
        ),
    )
    relationships = list(await session.scalars(relationship_statement.limit(60)))

    thread_statement = (
        select(StoryThread, Chapter.chapter_number.label("setup_chapter_number"))
        .outerjoin(Chapter, Chapter.id == StoryThread.setup_chapter_id)
        .where(
            StoryThread.story_id == story_id,
            StoryThread.state == "open",
            StoryThread.linked_entity_ids.op("&&")(list(entity_by_id)),
        )
        .limit(40)
    )
    threads = (await session.execute(thread_statement)).all()

    ranked_mentions = (
        select(
            EntityMention,
            Chapter.chapter_number.label("chapter_number"),
            func.row_number()
            .over(
                partition_by=EntityMention.entity_id,
                order_by=Chapter.chapter_number.desc(),
            )
            .label("appearance_rank"),
        )
        .join(Chapter, Chapter.id == EntityMention.chapter_id)
        .where(EntityMention.entity_id.in_(entity_by_id))
        .subquery()
    )
    appearances = (
        await session.execute(
            select(
                ranked_mentions.c.entity_id,
                ranked_mentions.c.chapter_number,
                ranked_mentions.c.line_start,
                ranked_mentions.c.quote,
            )
            .where(ranked_mentions.c.appearance_rank <= 3)
            .order_by(ranked_mentions.c.entity_id, ranked_mentions.c.chapter_number.desc())
        )
    ).all()

    lines: list[str] = ["ENTITIES PRESENT"]
    for entity in sorted(entities, key=lambda item: item.name.casefold()):
        aliases = sorted(set(aliases_by_entity.get(entity.id, [])))
        suffix = f", aliases: {', '.join(aliases)}" if aliases else ""
        if not _append_line(lines, f"{entity.name} ({entity.entity_type}{suffix})", budget_tokens):
            break

    used_facts = 0
    if _append_line(lines, "FACTS", budget_tokens):
        for fact in facts:
            value = fact.value_text or (
                str(fact.value_number) if fact.value_number is not None else ""
            )
            if not value:
                continue
            entity = entity_by_id.get(fact.entity_id)
            if entity is None:
                continue
            since = f"ch. {fact.valid_from_chapter}" if fact.valid_from_chapter else "established"
            quote = f" | \"{_excerpt(fact.quote)}\"" if fact.quote else ""
            if _append_line(
                lines,
                f"- {entity.name}: {fact.predicate}: {value} | valid from {since}{quote}",
                budget_tokens,
            ):
                used_facts += 1
            else:
                break

    used_relationships = 0
    if relationships and _append_line(lines, "RELATIONSHIPS", budget_tokens):
        for relationship in relationships:
            left = entity_by_id.get(relationship.from_entity_id)
            right = entity_by_id.get(relationship.to_entity_id)
            left_name = left.name if left else str(relationship.from_entity_id)[:8]
            right_name = right.name if right else str(relationship.to_entity_id)[:8]
            since = f" (since ch. {relationship.since_chapter})" if relationship.since_chapter else ""
            if not _append_line(
                lines,
                f"- {left_name} {relationship.relationship_type} {right_name}{since}",
                budget_tokens,
            ):
                break
            used_relationships += 1

    used_threads = 0
    if threads and _append_line(lines, "THREADS", budget_tokens):
        for thread, setup_chapter_number in threads:
            setup = f"setup ch. {setup_chapter_number}" if setup_chapter_number else "open"
            if not _append_line(
                lines,
                f"- {thread.title} ({thread.state}, {setup})",
                budget_tokens,
            ):
                break
            used_threads += 1

    used_appearances = 0
    if appearances and _append_line(lines, "APPEARANCES", budget_tokens):
        for entity_id, chapter_number, line_start, quote in appearances:
            entity = entity_by_id.get(entity_id)
            if entity is None:
                continue
            excerpt = _excerpt(quote or "", 180)
            if not excerpt:
                continue
            if not _append_line(
                lines,
                f"- {entity.name}, ch. {chapter_number}, line {line_start}: \"{excerpt}\"",
                budget_tokens,
            ):
                break
            used_appearances += 1

    if prose_hits and _append_line(lines, "EARLIER PASSAGES", budget_tokens):
        for hit in prose_hits:
            excerpt = _excerpt(hit.text, 360)
            if not excerpt:
                continue
            if not _append_line(
                lines,
                f"- ch. {hit.chapter_number}, line {hit.start_line}: \"{excerpt}\"",
                budget_tokens,
            ):
                break

    context_text = "\n".join(lines)
    token_count = approximate_tokens(context_text) if context_text else 0
    while token_count > budget_tokens and len(lines) > 1:
        lines.pop()
        context_text = "\n".join(lines)
        token_count = approximate_tokens(context_text)
    return EntityContext(
        text=context_text,
        token_count=token_count,
        entity_ids=sorted(entity_by_id, key=str),
        facts=used_facts,
        relationships=used_relationships,
        threads=used_threads,
        appearances=used_appearances,
        context_hash=hashlib.sha256(context_text.encode("utf-8")).hexdigest()[:16],
    )


async def retrieve_for_scene(
    session: AsyncSession,
    story_id: UUID,
    scene_text: str,
    *,
    current_chapter: int | None = None,
    limit: int = 10,
    filters: SearchFilters | None = None,
    budget_tokens: int = DEFAULT_CONTEXT_TOKENS,
    use_cache: bool = True,
) -> RetrievalResult:
    result = await search_chunks(
        session,
        story_id,
        scene_text,
        limit=limit,
        filters=filters,
        use_cache=use_cache,
    )
    result.context = await build_entity_context(
        session,
        story_id,
        result.entity_ids,
        current_chapter=current_chapter,
        prose_hits=result.chunks,
        budget_tokens=budget_tokens,
    )
    return result
