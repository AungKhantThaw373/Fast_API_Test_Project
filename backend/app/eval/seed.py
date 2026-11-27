"""Create the deterministic evaluation story.

The fixture is rebuilt from ``eval/datasets/manuscript.json`` on every run,
with fixed UUIDs so reports diff cleanly. It seeds accepted facts, aliases,
threads, and mentions as well as chapters, because the entity-first context is
part of what Phase 5 measures.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.dataset import Manuscript
from app.models.app_models import User
from app.models.story_models import Chapter, Story
from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityRelationship,
    StoryEvent,
    StoryThread,
)
from app.security import get_password_hash
from app.services import indexing
from app.services.entities import extract_mentions, normalize_name

EVAL_NAMESPACE = uuid5(NAMESPACE_URL, "https://stillroom.local/eval/v1")
EVAL_USER_ID = uuid5(EVAL_NAMESPACE, "user")
EVAL_STORY_ID = uuid5(EVAL_NAMESPACE, "story")
EVAL_EMAIL = "eval@stillroom.local"


def stable_id(kind: str, key: str) -> UUID:
    return uuid5(EVAL_NAMESPACE, f"{kind}:{key}")


@dataclass(frozen=True)
class SeededStory:
    story_id: UUID
    user_id: UUID
    chapter_ids: dict[int, UUID]
    entity_ids: dict[str, UUID]


def _locate_line(content: str, quote: str) -> int:
    for number, line in enumerate(content.splitlines(), start=1):
        if quote in line:
            return number
    return 1


async def ensure_eval_user(session: AsyncSession) -> User:
    user = await session.get(User, EVAL_USER_ID)
    if user is not None:
        return user
    email_owner = await session.scalar(select(User.id).where(User.email == EVAL_EMAIL))
    if email_owner is not None:
        raise RuntimeError(
            f"{EVAL_EMAIL} already belongs to {email_owner}; remove that user or change EVAL_EMAIL."
        )
    user = User(
        id=EVAL_USER_ID,
        username="eval",
        fullname="Evaluation Harness",
        email=EVAL_EMAIL,
        password=get_password_hash("evaluation-only"),
    )
    session.add(user)
    await session.flush()
    return user


async def seed_eval_story(session: AsyncSession, manuscript: Manuscript) -> SeededStory:
    """Delete and rebuild the evaluation story, then index it.

    The caller owns the session; indexing opens its own sessions, so this
    function commits before returning.
    """
    await ensure_eval_user(session)
    await session.execute(delete(Story).where(Story.id == EVAL_STORY_ID))
    await session.flush()

    story = Story(
        id=EVAL_STORY_ID,
        owner_id=EVAL_USER_ID,
        title=manuscript.title,
        collection_name="evaluation",
        external_analysis_enabled=True,
    )
    session.add(story)
    await session.flush()

    chapter_ids: dict[int, UUID] = {}
    chapters_by_number: dict[int, Chapter] = {}
    for position, seed in enumerate(manuscript.chapters, start=1):
        chapter = Chapter(
            id=stable_id("chapter", str(seed.number)),
            story_id=story.id,
            chapter_number=seed.number,
            position=1024.0 * position,
            title=seed.title,
            content=seed.content,
            word_count=len(seed.content.split()),
            revision=1,
            index_status="pending",
        )
        session.add(chapter)
        chapter_ids[seed.number] = chapter.id
        chapters_by_number[seed.number] = chapter
    await session.flush()

    entity_ids: dict[str, UUID] = {}
    for seed in manuscript.entities:
        entity = Entity(
            id=stable_id("entity", seed.key),
            story_id=story.id,
            entity_type=seed.type,
            name=seed.name,
            canonical_name=normalize_name(seed.name)[:220],
            summary=seed.summary,
            status="active",
        )
        session.add(entity)
        entity_ids[seed.key] = entity.id
        aliases = [(seed.name, "name"), *seed.aliases]
        seen: set[str] = set()
        for alias, kind in aliases:
            normalized = normalize_name(alias)[:220] or alias.casefold()[:220]
            if normalized in seen:
                continue
            seen.add(normalized)
            session.add(
                EntityAlias(
                    entity_id=entity.id,
                    alias=alias[:200],
                    normalized_alias=normalized,
                    alias_type=kind,
                )
            )
    await session.flush()

    for seed in manuscript.facts:
        chapter = chapters_by_number[seed.chapter]
        value_entity_id = entity_ids.get(seed.value_entity) if seed.value_entity else None
        line = _locate_line(chapter.content, seed.quote)
        session.add(
            EntityFact(
                entity_id=entity_ids[seed.entity],
                predicate=seed.predicate,
                value_text=seed.value,
                value_entity_id=value_entity_id,
                value_type="entity" if value_entity_id else "text",
                chapter_id=chapter.id,
                line_start=line,
                line_end=line,
                quote=seed.quote,
                confidence=100,
                status="accepted",
                valid_from_chapter=seed.chapter,
                created_by="human",
            )
        )
    for seed in manuscript.relationships:
        chapter = chapters_by_number[seed.chapter]
        session.add(
            EntityRelationship(
                story_id=story.id,
                from_entity_id=entity_ids[seed.from_entity],
                to_entity_id=entity_ids[seed.to_entity],
                relationship_type=seed.type,
                description=seed.description,
                since_chapter=seed.chapter,
                chapter_id=chapter.id,
                status="accepted",
            )
        )
    for seed in manuscript.threads:
        chapter = chapters_by_number[seed.setup_chapter]
        session.add(
            StoryThread(
                story_id=story.id,
                title=seed.title,
                description=seed.description,
                setup_chapter_id=chapter.id,
                state=seed.state,
                linked_entity_ids=[entity_ids[key] for key in seed.linked if key in entity_ids],
            )
        )
    for seed in manuscript.events:
        chapter = chapters_by_number[seed.chapter]
        session.add(
            StoryEvent(
                story_id=story.id,
                chapter_id=chapter.id,
                summary=seed.summary,
                location_entity_id=entity_ids.get(seed.location or ""),
                participant_entity_ids=[entity_ids[key] for key in seed.participants if key in entity_ids],
            )
        )
    await session.flush()

    for chapter in chapters_by_number.values():
        await extract_mentions(session, story.id, chapter.id, chapter.content)
    await session.commit()

    for chapter_id in chapter_ids.values():
        await indexing.reindex_chapter(chapter_id)

    return SeededStory(
        story_id=story.id,
        user_id=EVAL_USER_ID,
        chapter_ids=chapter_ids,
        entity_ids=entity_ids,
    )
