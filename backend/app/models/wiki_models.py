"""Knowledge model v2: entities, facts, relationships, events, threads, mentions.

The old ``story_bible_entries`` table was a list of descriptions. A story wiki is
a graph: entities connected by facts and relationships, events on a timeline,
threads that open and resolve, and mentions that point back to the manuscript.

Every AI-created fact keeps provenance (chapter, line range, and an exact quote),
and nothing first-class is hard-deleted: an entity merge is soft
(``merged_into_id``) so history and old links still resolve.

These tables are additive in Phase 3. ``story_bible_entries`` stays until the new
wiki UI ships.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ENTITY_TYPES = (
    "character",
    "location",
    "item",
    "organization",
    "concept",
    "world_rule",
    "power_system",
    "creature",
    "other",
)

FACT_STATUSES = ("proposed", "accepted", "rejected", "superseded")
THREAD_STATES = ("open", "touched", "resolved", "abandoned")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index(
            "uq_entities_type_canonical_active",
            "story_id",
            "entity_type",
            "canonical_name",
            unique=True,
            postgresql_where=text("merged_into_id IS NULL"),
        ),
        Index("ix_entities_story_type", "story_id", "entity_type"),
        Index("ix_entities_story_status", "story_id", "status"),
        Index(
            "ix_entities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(220), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # Soft merge: a merged entity keeps its row so old ids and links still resolve.
    merged_into_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    first_chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_alias_normalized"),
        Index("ix_entity_aliases_normalized", "normalized_alias"),
        Index(
            "ix_entity_aliases_alias_trgm",
            "alias",
            postgresql_using="gin",
            postgresql_ops={"alias": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(220), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(20), nullable=False, default="name")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityFact(Base):
    """One atomic statement about one entity, with provenance."""

    __tablename__ = "entity_facts"
    __table_args__ = (
        Index("ix_entity_facts_entity_predicate", "entity_id", "predicate"),
        Index("ix_entity_facts_status", "status"),
        Index("ix_entity_facts_chapter", "chapter_id"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(100), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    scene_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    valid_from_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_to_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supersedes_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_facts.id", ondelete="SET NULL"), nullable=True
    )
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    __table_args__ = (
        Index("ix_entity_relationships_from", "from_entity_id"),
        Index("ix_entity_relationships_to", "to_entity_id"),
        Index("ix_entity_relationships_story", "story_id"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    from_entity_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    to_entity_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    since_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    until_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StoryEvent(Base):
    """Something that happened. ``timeline_order`` is separate from chapter order
    so flashbacks can sit where they belong in story time."""

    __tablename__ = "story_events"
    __table_args__ = (
        Index("ix_story_events_story_chapter", "story_id", "chapter_id"),
        Index("ix_story_events_story_timeline", "story_id", "timeline_order"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
    )
    scene_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeline_order: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    location_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    participant_entity_ids: Mapped[list[UUIDType]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StoryThread(Base):
    __tablename__ = "story_threads"
    __table_args__ = (Index("ix_story_threads_story_state", "story_id", "state"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    setup_chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    setup_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    payoff_chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    linked_entity_ids: Mapped[list[UUIDType]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EntityMention(Base):
    """Where an entity appears. Written by the regex matcher, never by an LLM."""

    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "chapter_id", "line_start", "line_end", name="uq_entity_mention_range"
        ),
        Index("ix_entity_mentions_entity_chapter", "entity_id", "chapter_id"),
        Index("ix_entity_mentions_chapter", "chapter_id"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
    )
    scene_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CanonException(Base):
    """Suppresses findings that match: "her eyes change in chapter 7, on purpose"."""

    __tablename__ = "canon_exceptions"
    __table_args__ = (Index("ix_canon_exceptions_story", "story_id", "scope"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    predicate: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChapterMeta(Base):
    __tablename__ = "chapter_meta"

    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("story_chapters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    synopsis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pov_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    location_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    story_time: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class SceneMeta(Base):
    __tablename__ = "scene_meta"
    __table_args__ = (UniqueConstraint("chapter_id", "scene_index", name="uq_scene_meta_index"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pov_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    location_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    story_time: Mapped[str | None] = mapped_column(String(200), nullable=True)
    character_entity_ids: Mapped[list[UUIDType]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )


class AIUsage(Base):
    """One row per model call, so budgets and cost are visible per story."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_story_created", "story_id", "created_at"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    story_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "ENTITY_TYPES",
    "FACT_STATUSES",
    "THREAD_STATES",
    "AIUsage",
    "CanonException",
    "ChapterMeta",
    "Entity",
    "EntityAlias",
    "EntityFact",
    "EntityMention",
    "EntityRelationship",
    "SceneMeta",
    "StoryEvent",
    "StoryThread",
]


class EntityMerge(Base):
    """Audit of a merge, recording exactly which rows moved so it can be undone.

    The merge itself is soft and reversible: ``entities.merged_into_id`` points at
    the target, and this row holds the ids of the facts, mentions, relationships,
    aliases, and array memberships that were rewritten. Undo uses those ids
    instead of guessing from names.
    """

    __tablename__ = "entity_merges"
    __table_args__ = (Index("ix_entity_merges_source", "source_id", "created_at"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    moved: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MergeProposal(Base):
    """Two entities that look like the same thing, waiting for a decision.

    Derived from name similarity (never applied automatically), stored so a
    dismissal sticks instead of reappearing on every inbox load.
    """

    __tablename__ = "merge_proposals"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", name="uq_merge_proposal_pair"),
        Index("ix_merge_proposals_story_status", "story_id", "status"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutoAcceptRules(Base):
    """Per-story rules for accepting extraction proposals without review."""

    __tablename__ = "auto_accept_rules"

    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    require_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    require_existing_entity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    block_conflicts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_per_chapter: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
