from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID as UUIDType

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base

if TYPE_CHECKING:
    from app.models.app_models import User


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    scan_interval_words: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    external_analysis_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Dollars per calendar month; zero means local-only and allows free Ollama calls.
    monthly_ai_budget: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship("User", back_populates="stories")
    chapters: Mapped[list[Chapter]] = relationship(
        "Chapter", back_populates="story", cascade="all, delete-orphan", order_by="Chapter.position"
    )
    bible_entries: Mapped[list[StoryBibleEntry]] = relationship(
        "StoryBibleEntry", back_populates="story", cascade="all, delete-orphan"
    )


class Arc(Base):
    """A named span of chapters. At 270+ chapters, a flat list stops working."""

    __tablename__ = "arcs"
    __table_args__ = (UniqueConstraint("story_id", "name", name="uq_arc_story_name"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=1024.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Chapter(Base):
    __tablename__ = "story_chapters"
    __table_args__ = (
        Index(
            "uq_story_chapter_number_active",
            "story_id",
            "chapter_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_chapters_story_deleted", "story_id", "deleted_at"),
        Index("ix_chapters_story_position", "story_id", "position"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    arc_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("arcs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Ordering source. chapter_number is only what the writer sees.
    position: Mapped[float] = mapped_column(Float, nullable=False, default=1024.0)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Untitled chapter")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    bible_scan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bible_scan_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_embedding_model: Mapped[str] = mapped_column(
        String(200), nullable=False, default=settings.EMBEDDING_MODEL, server_default="nomic-embed-text"
    )
    index_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Idempotency for retried autosaves: the last accepted client save id.
    last_client_save_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    story: Mapped[Story] = relationship("Story", back_populates="chapters")
    scenes: Mapped[list[SceneEmbedding]] = relationship(
        "SceneEmbedding", back_populates="chapter", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[StoryChunk]] = relationship(
        "StoryChunk", back_populates="chapter", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[ChapterRevision]] = relationship(
        "ChapterRevision", back_populates="chapter", cascade="all, delete-orphan",
        order_by="ChapterRevision.revision_number.desc()",
    )


class ChapterRevision(Base):
    __tablename__ = "story_chapter_revisions"
    __table_args__ = (UniqueConstraint("chapter_id", "revision_number", name="uq_chapter_revision_number"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="autosave", server_default="autosave")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chapter: Mapped[Chapter] = relationship("Chapter", back_populates="revisions")


class SceneEmbedding(Base):
    __tablename__ = "story_scene_embeddings"
    __table_args__ = (
        Index("ix_story_scene_story_chapter", "story_id", "chapter_number"),
        Index(
            "ix_story_scene_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chapter: Mapped[Chapter] = relationship("Chapter", back_populates="scenes")


class StoryChunk(Base):
    """A retrieval chunk built by the Phase 5 sentence-aware chunker."""

    __tablename__ = "story_chunks"
    __table_args__ = (
        UniqueConstraint("chapter_id", "chunk_kind", "chunk_index", name="uq_story_chunk_index"),
        Index("ix_story_chunks_story_chapter", "story_id", "chapter_number"),
        Index("ix_story_chunks_entities", "entities", postgresql_using="gin"),
        Index("ix_story_chunks_fts", "text_search", postgresql_using="gin"),
        Index(
            "ix_story_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="scene")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    entities: Mapped[list[UUIDType]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    pov_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    location_entity_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=False)
    embedding_model: Mapped[str] = mapped_column(
        String(200), nullable=False, default=settings.EMBEDDING_MODEL
    )
    text_search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chapter: Mapped[Chapter] = relationship("Chapter", back_populates="chunks")

class StoryBibleEntry(Base):
    __tablename__ = "story_bible_entries"
    __table_args__ = (
        UniqueConstraint("story_id", "category", "canonical_name", name="uq_story_bible_canonical_entry"),
        Index("ix_story_bible_story_status", "story_id", "status"),
    )

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="suggested")
    thread_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    source_chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    story: Mapped[Story] = relationship("Story", back_populates="bible_entries")


class ContinuityScan(Base):
    __tablename__ = "continuity_scans"
    __table_args__ = (Index("ix_scans_chapter_created", "chapter_id", "created_at"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="complete")
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Pipeline metadata: comparing two scans is only meaningful when the prompt,
    # schema, model, and context set are visible.
    prompt_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenes_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scenes_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scenes_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    findings: Mapped[list[ContinuityFinding]] = relationship(
        "ContinuityFinding", back_populates="scan", cascade="all, delete-orphan"
    )


class ContinuityFinding(Base):
    __tablename__ = "continuity_findings"

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("continuity_scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_quote: Mapped[str] = mapped_column(Text, nullable=False)
    draft_line: Mapped[int] = mapped_column(Integer, nullable=False)
    # Deterministic findings have no earlier passage; LLM findings do.
    earlier_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    earlier_chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    earlier_chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="llm")
    rule_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    scene_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    intentional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    scan: Mapped[ContinuityScan] = relationship("ContinuityScan", back_populates="findings")
