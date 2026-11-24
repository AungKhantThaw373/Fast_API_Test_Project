from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID as UUIDType

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship("User", back_populates="stories")
    chapters: Mapped[list[Chapter]] = relationship(
        "Chapter", back_populates="story", cascade="all, delete-orphan", order_by="Chapter.chapter_number"
    )
    bible_entries: Mapped[list[StoryBibleEntry]] = relationship(
        "StoryBibleEntry", back_populates="story", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "story_chapters"
    __table_args__ = (UniqueConstraint("story_id", "chapter_number", name="uq_story_chapter_number"),)

    id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
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

    story: Mapped[Story] = relationship("Story", back_populates="chapters")
    scenes: Mapped[list[SceneEmbedding]] = relationship(
        "SceneEmbedding", back_populates="chapter", cascade="all, delete-orphan"
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
    earlier_quote: Mapped[str] = mapped_column(Text, nullable=False)
    earlier_chapter_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
    )
    earlier_chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    intentional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    scan: Mapped[ContinuityScan] = relationship("ContinuityScan", back_populates="findings")
