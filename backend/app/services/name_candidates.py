"""Name candidates: capitalised words the alias dictionary has never seen.

Zero tokens, no model. The point is speed: a writer finishes a chapter and within
a second sees "Tessa", "Hollow Gate", "the Ninth" waiting to become entries. Each
acceptance trains the alias dictionary that mention extraction and resolution both
depend on, so the heuristic gets more useful the more it is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter
from app.models.wiki_models import Entity, EntityAlias, EntityMention
from app.services.entities import MIN_ALIAS_LENGTH, STOPWORDS, normalize_name, refresh_appearance_range

# Capitalised words that are almost always grammar or stage directions, not names.
COMMON_CAPITALISED = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "if",
        "so",
        "then",
        "when",
        "while",
        "after",
        "before",
        "because",
        "however",
        "still",
        "just",
        "even",
        "now",
        "later",
        "today",
        "tomorrow",
        "yesterday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "god",
        "lord",
        "yes",
        "no",
        "okay",
        "well",
        "oh",
        "ah",
        "hey",
        "hello",
        "goodbye",
        "please",
        "thank",
        "thanks",
        "sorry",
        "chapter",
        "part",
        "scene",
    }
)

WORD = re.compile(r"\b[A-Z][a-zA-Z'’\-]{2,}\b")
SENTENCE_END = re.compile(r"[.!?…]")
MAX_CANDIDATES = 40


@dataclass(frozen=True)
class NameCandidate:
    name: str
    count: int
    first_line: int
    sample: str


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in SENTENCE_END.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def find_name_candidates(
    content: str,
    known: set[str],
    *,
    limit: int = MAX_CANDIDATES,
) -> list[NameCandidate]:
    """Capitalised tokens that repeat mid-sentence and are not known aliases."""
    sentences = _sentence_spans(content)
    token_counts: dict[str, int] = {}
    pair_counts: dict[str, int] = {}
    covered_tokens: set[str] = set()
    first_line: dict[str, int] = {}
    samples: dict[str, str] = {}

    for start, end in sentences:
        sentence = content[start:end]
        if not sentence.strip():
            continue
        line_number = content.count("\n", 0, start) + 1
        words = list(WORD.finditer(sentence))
        lead = sentence[: len(sentence) - len(sentence.lstrip())]
        for index, match in enumerate(words):
            word = match.group(0)
            normalized = normalize_name(word) or word.casefold()
            if len(word) < MIN_ALIAS_LENGTH or normalized in known or word.casefold() in COMMON_CAPITALISED:
                continue
            # A sentence-initial capital is grammar, unless the name is capitalised
            # again later in the sentence (handled by counting the token again).
            at_sentence_start = match.start() == len(lead)
            if not at_sentence_start:
                token_counts[word] = token_counts.get(word, 0) + 1
                first_line.setdefault(word, line_number)
                samples.setdefault(word, sentence.strip())
            if index + 1 < len(words):
                following = words[index + 1]
                gap = sentence[match.end() : following.start()]
                if gap.strip() in {"", "-", "’", "'"} and following.group(0)[0].isupper():
                    pair = f"{word} {following.group(0)}"
                    pair_key = pair.casefold()
                    if len(pair) < MIN_ALIAS_LENGTH:
                        continue
                    if pair_key in known:
                        # The pair is already an alias, so neither half is news.
                        covered_tokens.update(part.casefold() for part in pair.split())
                        continue
                    # A pair is a name even at a sentence start: "Mira Voss crossed
                    # the yard." is the commonest way a character is introduced.
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    first_line.setdefault(pair, line_number)
                    samples.setdefault(pair, sentence.strip())

    # A repeated pair is a better candidate than either half of it.
    covered = {part.casefold() for pair in pair_counts for part in pair.split()} | covered_tokens
    candidates: list[NameCandidate] = []
    for name, count in pair_counts.items():
        if count < 2:
            continue
        candidates.append(
            NameCandidate(name=name, count=count, first_line=first_line[name], sample=samples[name])
        )
    for name, count in token_counts.items():
        if count < 2 or name.casefold() in covered:
            continue
        candidates.append(
            NameCandidate(name=name, count=count, first_line=first_line[name], sample=samples[name])
        )
    candidates.sort(key=lambda item: (-item.count, item.name.casefold()))
    return candidates[:limit]


async def known_names(session: AsyncSession, story_id: UUID) -> set[str]:
    """Every normalised name and alias the story already knows."""
    rows = await session.execute(
        select(Entity.name, Entity.canonical_name)
        .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
    )
    known: set[str] = set()
    for name, canonical_name in rows.all():
        known.add(canonical_name or normalize_name(name) or name.casefold())
    aliases = await session.execute(
        select(EntityAlias.normalized_alias)
        .join(Entity, Entity.id == EntityAlias.entity_id)
        .where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
    )
    known.update(row for row in aliases.scalars() if row)
    known.update(STOPWORDS)
    known.update(COMMON_CAPITALISED)
    return known


async def candidates_for_chapter(
    session: AsyncSession, story_id: UUID, chapter_id: UUID, *, limit: int = MAX_CANDIDATES
) -> tuple[Chapter, list[NameCandidate]]:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id or chapter.deleted_at is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Chapter not found.")
    known = await known_names(session, story_id)
    return chapter, find_name_candidates(chapter.content, known, limit=limit)


async def accept_candidate(
    session: AsyncSession,
    *,
    story_id: UUID,
    chapter_id: UUID,
    name: str,
    entity_type: str,
    line_start: int | None = None,
    quote: str | None = None,
) -> Entity:
    """Create the entity, its name alias, and the mention in one transaction."""
    from app.services.entities import create_entity

    chapter, _candidates = await candidates_for_chapter(session, story_id, chapter_id)
    clean = name.strip()
    if not clean:
        raise ValueError("A candidate needs a name.")
    entity = await create_entity(
        session,
        story_id=story_id,
        entity_type=entity_type,
        name=clean,
        first_chapter_number=chapter.chapter_number,
    )
    if quote:
        entity_line, _end = _locate(chapter, quote) if line_start is None else (line_start, line_start)
        if entity_line is not None:
            await session.execute(
                insert(EntityMention)
                .values(
                    entity_id=entity.id,
                    chapter_id=chapter.id,
                    line_start=entity_line,
                    line_end=entity_line,
                    quote=quote,
                )
                .on_conflict_do_nothing(constraint="uq_entity_mention_range")
            )
            await refresh_appearance_range(session, story_id, {entity.id})
    await session.flush()
    return entity


def _locate(chapter: Chapter, quote: str) -> tuple[int | None, int | None]:
    for index, line in enumerate(chapter.content.splitlines(), start=1):
        if quote in line:
            return index, index
    return None, None
