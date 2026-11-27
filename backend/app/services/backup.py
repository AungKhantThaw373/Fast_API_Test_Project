"""Full JSON backup and restore for one story.

Backups are deliberately boring: every row that belongs to the story, ids intact,
so a restore can rebuild the graph without guessing. Derived data (chunks, scene
embeddings, mentions, auto-accept decisions) is rebuilt by the normal workers.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Arc, Chapter, ChapterRevision, Story
from app.models.wiki_models import (
    CanonException,
    ChapterMeta,
    Entity,
    EntityAlias,
    EntityFact,
    EntityRelationship,
    StoryEvent,
    StoryThread,
)
from app.schemas.backup import (
    BackupAlias,
    BackupArc,
    BackupCanonException,
    BackupChapter,
    BackupChapterMeta,
    BackupEntity,
    BackupEvent,
    BackupFact,
    BackupImportOut,
    BackupRelationship,
    BackupRevision,
    BackupStory,
    BackupThread,
    StoryBackup,
)
from app.services.entities import normalize_name

FORMAT_VERSION = 1


def _revision_snapshot(row: ChapterRevision) -> BackupRevision:
    return BackupRevision(
        revision_number=row.revision_number,
        title=row.title,
        content=row.content,
        word_count=row.word_count,
        kind=row.kind,
        content_hash=row.content_hash,
        char_count=row.char_count,
    )


async def build_backup(session: AsyncSession, story: Story) -> StoryBackup:
    chapters = list(
        (
            await session.scalars(
                select(Chapter)
                .where(Chapter.story_id == story.id, Chapter.deleted_at.is_(None))
                .order_by(Chapter.position, Chapter.chapter_number)
            )
        ).all()
    )
    chapter_ids = [row.id for row in chapters]
    arcs = list(
        (await session.scalars(select(Arc).where(Arc.story_id == story.id).order_by(Arc.position))).all()
    )
    revisions: dict[UUID, list[BackupRevision]] = {chapter_id: [] for chapter_id in chapter_ids}
    if chapter_ids:
        for row in (
            await session.scalars(
                select(ChapterRevision)
                .where(ChapterRevision.chapter_id.in_(chapter_ids))
                .order_by(ChapterRevision.revision_number)
            )
        ).all():
            revisions[row.chapter_id].append(_revision_snapshot(row))

    entities = list(
        (await session.scalars(select(Entity).where(Entity.story_id == story.id).order_by(Entity.name))).all()
    )
    entity_ids = [row.id for row in entities]
    aliases: dict[UUID, list[Any]] = {entity_id: [] for entity_id in entity_ids}
    facts: dict[UUID, list[BackupFact]] = {entity_id: [] for entity_id in entity_ids}
    if entity_ids:
        for row in (
            await session.scalars(
                select(EntityAlias).where(EntityAlias.entity_id.in_(entity_ids)).order_by(EntityAlias.alias)
            )
        ).all():
            aliases[row.entity_id].append(row)
        for row in (
            await session.scalars(
                select(EntityFact)
                .where(EntityFact.entity_id.in_(entity_ids))
                .order_by(EntityFact.created_at, EntityFact.predicate)
            )
        ).all():
            facts[row.entity_id].append(
                BackupFact(
                    predicate=row.predicate,
                    value_text=row.value_text,
                    value_number=row.value_number,
                    value_date=row.value_date.isoformat() if row.value_date else None,
                    value_entity_id=row.value_entity_id,
                    value_type=row.value_type,
                    chapter_id=row.chapter_id,
                    scene_index=row.scene_index,
                    line_start=row.line_start,
                    line_end=row.line_end,
                    quote=row.quote,
                    confidence=row.confidence,
                    status=row.status,
                    valid_from_chapter=row.valid_from_chapter,
                    valid_to_chapter=row.valid_to_chapter,
                    context=row.context or {},
                    created_by=row.created_by,
                )
            )

    relationships = list(
        (
            await session.scalars(
                select(EntityRelationship)
                .where(EntityRelationship.story_id == story.id)
                .order_by(EntityRelationship.created_at)
            )
        ).all()
    )
    threads = list(
        (
            await session.scalars(
                select(StoryThread)
                .where(StoryThread.story_id == story.id)
                .order_by(StoryThread.created_at)
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(StoryEvent)
                .where(StoryEvent.story_id == story.id)
                .order_by(StoryEvent.timeline_order, StoryEvent.created_at)
            )
        ).all()
    )
    metas = []
    if chapter_ids:
        metas = list(
            (await session.scalars(select(ChapterMeta).where(ChapterMeta.chapter_id.in_(chapter_ids)))).all()
        )
    exceptions = list(
        (
            await session.scalars(
                select(CanonException).where(CanonException.story_id == story.id).order_by(CanonException.created_at)
            )
        ).all()
    )

    return StoryBackup(
        format_version=FORMAT_VERSION,
        exported_at=datetime.now(UTC),
        story=BackupStory(
            title=story.title,
            collection_name=story.collection_name,
            scan_interval_words=story.scan_interval_words,
            external_analysis_enabled=story.external_analysis_enabled,
            monthly_ai_budget=float(story.monthly_ai_budget),
            wiki_format=story.wiki_format,
        ),
        arcs=[
            BackupArc(id=row.id, name=row.name, position=row.position, summary=row.summary)
            for row in arcs
        ],
        chapters=[
            BackupChapter(
                id=row.id,
                chapter_number=row.chapter_number,
                position=row.position,
                arc_id=row.arc_id,
                title=row.title,
                content=row.content,
                word_count=row.word_count,
                revision=row.revision,
                revisions=revisions[row.id],
            )
            for row in chapters
        ],
        entities=[
            BackupEntity(
                id=row.id,
                entity_type=row.entity_type,
                name=row.name,
                canonical_name=row.canonical_name,
                summary=row.summary,
                status=row.status,
                merged_into_id=row.merged_into_id,
                first_chapter_number=row.first_chapter_number,
                last_chapter_number=row.last_chapter_number,
                aliases=[
                    BackupAlias(alias=alias.alias, alias_type=alias.alias_type) for alias in aliases[row.id]
                ],
                facts=facts[row.id],
            )
            for row in entities
        ],
        relationships=[
            BackupRelationship(
                from_entity_id=row.from_entity_id,
                to_entity_id=row.to_entity_id,
                relationship_type=row.relationship_type,
                description=row.description,
                since_chapter=row.since_chapter,
                until_chapter=row.until_chapter,
                chapter_id=row.chapter_id,
                quote=row.quote,
                status=row.status,
            )
            for row in relationships
        ],
        threads=[
            BackupThread(
                title=row.title,
                description=row.description,
                setup_chapter_id=row.setup_chapter_id,
                setup_quote=row.setup_quote,
                payoff_chapter_id=row.payoff_chapter_id,
                state=row.state,
                linked_entity_ids=list(row.linked_entity_ids),
            )
            for row in threads
        ],
        events=[
            BackupEvent(
                chapter_id=row.chapter_id,
                scene_index=row.scene_index,
                timeline_order=row.timeline_order,
                summary=row.summary,
                location_entity_id=row.location_entity_id,
                participant_entity_ids=list(row.participant_entity_ids),
                quote=row.quote,
            )
            for row in events
        ],
        chapter_meta=[
            BackupChapterMeta(
                chapter_id=row.chapter_id,
                synopsis=row.synopsis or "",
                pov_entity_id=row.pov_entity_id,
                location_entity_id=row.location_entity_id,
                story_time=row.story_time,
                status=row.status,
            )
            for row in metas
        ],
        canon_exceptions=[
            BackupCanonException(
                scope=row.scope,
                entity_id=row.entity_id,
                predicate=row.predicate,
                pattern=row.pattern,
                reason=row.reason,
            )
            for row in exceptions
        ],
    )


async def import_backup(
    session: AsyncSession, owner_id: UUID, payload: StoryBackup
) -> BackupImportOut:
    if payload.format_version != FORMAT_VERSION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Backup format version {payload.format_version} is not supported.",
        )
    story = Story(
        owner_id=owner_id,
        title=payload.story.title,
        collection_name=payload.story.collection_name,
        scan_interval_words=payload.story.scan_interval_words,
        external_analysis_enabled=payload.story.external_analysis_enabled,
        monthly_ai_budget=payload.story.monthly_ai_budget,
        wiki_format=payload.story.wiki_format,
    )
    session.add(story)
    await session.flush()

    arc_map = {}
    for item in payload.arcs:
        arc = Arc(story_id=story.id, name=item.name, position=item.position, summary=item.summary)
        session.add(arc)
        arc_map[item.id] = arc
    await session.flush()

    chapter_map: dict[UUID, Chapter] = {}
    for item in payload.chapters:
        chapter = Chapter(
            story_id=story.id,
            chapter_number=item.chapter_number,
            position=item.position,
            arc_id=arc_map[item.arc_id].id if item.arc_id and item.arc_id in arc_map else None,
            title=item.title or "Untitled chapter",
            content=item.content,
            word_count=item.word_count,
            revision=item.revision,
            index_status="pending",
        )
        session.add(chapter)
        chapter_map[item.id] = chapter
    await session.flush()

    for item in payload.chapters:
        chapter = chapter_map[item.id]
        seen_numbers = set()
        for revision in item.revisions:
            if revision.revision_number in seen_numbers:
                continue
            seen_numbers.add(revision.revision_number)
            content = revision.content
            session.add(
                ChapterRevision(
                    chapter_id=chapter.id,
                    revision_number=revision.revision_number,
                    title=revision.title or chapter.title,
                    content=content,
                    word_count=revision.word_count,
                    kind=revision.kind,
                    content_hash=revision.content_hash or hashlib.sha256(content.encode()).hexdigest(),
                    char_count=revision.char_count or len(content),
                )
            )

    entity_map: dict[UUID, Entity] = {}
    for item in payload.entities:
        canonical = item.canonical_name or normalize_name(item.name)
        entity = Entity(
            story_id=story.id,
            entity_type=item.entity_type,
            name=item.name,
            canonical_name=canonical[:220],
            summary=item.summary,
            status=item.status,
            first_chapter_number=item.first_chapter_number,
            last_chapter_number=item.last_chapter_number,
        )
        session.add(entity)
        entity_map[item.id] = entity
    await session.flush()
    for item in payload.entities:
        if item.merged_into_id and item.merged_into_id in entity_map:
            entity_map[item.id].merged_into_id = entity_map[item.merged_into_id].id
        for alias in item.aliases:
            session.add(
                EntityAlias(
                    entity_id=entity_map[item.id].id,
                    alias=alias.alias,
                    normalized_alias=normalize_name(alias.alias)[:220],
                    alias_type=alias.alias_type,
                )
            )

    fact_count = 0
    for item in payload.entities:
        entity = entity_map[item.id]
        for fact in item.facts:
            session.add(
                EntityFact(
                    entity_id=entity.id,
                    predicate=fact.predicate,
                    value_text=fact.value_text,
                    value_number=fact.value_number,
                    value_date=date.fromisoformat(fact.value_date) if fact.value_date else None,
                    value_entity_id=entity_map[fact.value_entity_id].id if fact.value_entity_id and fact.value_entity_id in entity_map else None,
                    value_type=fact.value_type,
                    chapter_id=chapter_map[fact.chapter_id].id if fact.chapter_id and fact.chapter_id in chapter_map else None,
                    scene_index=fact.scene_index,
                    line_start=fact.line_start,
                    line_end=fact.line_end,
                    quote=fact.quote,
                    confidence=fact.confidence,
                    status=fact.status,
                    valid_from_chapter=fact.valid_from_chapter,
                    valid_to_chapter=fact.valid_to_chapter,
                    context=fact.context,
                    created_by=fact.created_by,
                )
            )
            fact_count += 1

    for item in payload.relationships:
        if item.from_entity_id not in entity_map or item.to_entity_id not in entity_map:
            continue
        session.add(
            EntityRelationship(
                story_id=story.id,
                from_entity_id=entity_map[item.from_entity_id].id,
                to_entity_id=entity_map[item.to_entity_id].id,
                relationship_type=item.relationship_type,
                description=item.description,
                since_chapter=item.since_chapter,
                until_chapter=item.until_chapter,
                chapter_id=chapter_map[item.chapter_id].id if item.chapter_id and item.chapter_id in chapter_map else None,
                quote=item.quote,
                status=item.status,
            )
        )

    for item in payload.threads:
        session.add(
            StoryThread(
                story_id=story.id,
                title=item.title,
                description=item.description,
                setup_chapter_id=chapter_map[item.setup_chapter_id].id
                if item.setup_chapter_id and item.setup_chapter_id in chapter_map
                else None,
                setup_quote=item.setup_quote,
                payoff_chapter_id=chapter_map[item.payoff_chapter_id].id
                if item.payoff_chapter_id and item.payoff_chapter_id in chapter_map
                else None,
                state=item.state,
                linked_entity_ids=[
                    entity_map[entity_id].id for entity_id in item.linked_entity_ids if entity_id in entity_map
                ],
            )
        )

    for item in payload.events:
        if item.chapter_id not in chapter_map:
            continue
        session.add(
            StoryEvent(
                story_id=story.id,
                chapter_id=chapter_map[item.chapter_id].id,
                scene_index=item.scene_index,
                timeline_order=item.timeline_order,
                summary=item.summary,
                location_entity_id=entity_map[item.location_entity_id].id
                if item.location_entity_id and item.location_entity_id in entity_map
                else None,
                participant_entity_ids=[
                    entity_map[entity_id].id
                    for entity_id in item.participant_entity_ids
                    if entity_id in entity_map
                ],
                quote=item.quote,
            )
        )

    for item in payload.chapter_meta:
        if item.chapter_id not in chapter_map:
            continue
        session.add(
            ChapterMeta(
                chapter_id=chapter_map[item.chapter_id].id,
                synopsis=item.synopsis,
                pov_entity_id=entity_map[item.pov_entity_id].id if item.pov_entity_id and item.pov_entity_id in entity_map else None,
                location_entity_id=entity_map[item.location_entity_id].id
                if item.location_entity_id and item.location_entity_id in entity_map
                else None,
                story_time=item.story_time,
                status=item.status,
            )
        )

    for item in payload.canon_exceptions:
        session.add(
            CanonException(
                story_id=story.id,
                scope=item.scope,
                entity_id=entity_map[item.entity_id].id if item.entity_id and item.entity_id in entity_map else None,
                predicate=item.predicate,
                pattern=item.pattern,
                reason=item.reason,
                created_by="human",
            )
        )

    await session.commit()
    return BackupImportOut(
        story_id=story.id,
        chapters=len(payload.chapters),
        entities=len(payload.entities),
        facts=fact_count,
        relationships=len(payload.relationships),
        threads=len(payload.threads),
        events=len(payload.events),
    )