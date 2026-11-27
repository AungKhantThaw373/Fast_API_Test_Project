"""Portable JSON backup: every story-owned row that is not derived or advisory."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BackupModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class BackupStory(BackupModel):
    title: str = Field(min_length=1, max_length=200)
    collection_name: str = Field(default="", max_length=100)
    scan_interval_words: int = Field(default=1500, ge=0)
    external_analysis_enabled: bool = False
    monthly_ai_budget: float = Field(default=0, ge=0)
    wiki_format: dict[str, Any] | None = None


class BackupArc(BackupModel):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    position: float = 1024.0
    summary: str = ""


class BackupRevision(BackupModel):
    revision_number: int = Field(ge=1)
    title: str = Field(max_length=200)
    content: str = ""
    word_count: int = Field(default=0, ge=0)
    kind: str = Field(default="autosave", max_length=20)
    content_hash: str = Field(default="", max_length=64)
    char_count: int = Field(default=0, ge=0)


class BackupChapter(BackupModel):
    id: UUID
    chapter_number: int = Field(ge=1)
    position: float = 1024.0
    arc_id: UUID | None = None
    title: str = Field(max_length=200)
    content: str = ""
    word_count: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    revisions: list[BackupRevision] = Field(default_factory=list)


class BackupAlias(BackupModel):
    alias: str = Field(min_length=1, max_length=200)
    alias_type: str = Field(default="name", max_length=20)


class BackupFact(BackupModel):
    predicate: str = Field(min_length=1, max_length=100)
    value_text: str | None = None
    value_number: float | None = None
    value_date: str | None = None
    value_entity_id: UUID | None = None
    value_type: str = "text"
    chapter_id: UUID | None = None
    scene_index: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    quote: str | None = None
    confidence: int = Field(default=50, ge=0, le=100)
    status: str = "proposed"
    valid_from_chapter: int | None = None
    valid_to_chapter: int | None = None
    context: dict = Field(default_factory=dict)
    created_by: str = "human"


class BackupEntity(BackupModel):
    id: UUID
    entity_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    canonical_name: str = Field(default="", max_length=220)
    summary: str = ""
    status: str = "active"
    merged_into_id: UUID | None = None
    first_chapter_number: int | None = None
    last_chapter_number: int | None = None
    aliases: list[BackupAlias] = Field(default_factory=list)
    facts: list[BackupFact] = Field(default_factory=list)


class BackupRelationship(BackupModel):
    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str = Field(min_length=1, max_length=60)
    description: str = ""
    since_chapter: int | None = None
    until_chapter: int | None = None
    chapter_id: UUID | None = None
    quote: str | None = None
    status: str = "accepted"


class BackupThread(BackupModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    setup_chapter_id: UUID | None = None
    setup_quote: str | None = None
    payoff_chapter_id: UUID | None = None
    state: str = "open"
    linked_entity_ids: list[UUID] = Field(default_factory=list)


class BackupEvent(BackupModel):
    chapter_id: UUID
    scene_index: int | None = None
    timeline_order: float | None = None
    summary: str = Field(min_length=1)
    location_entity_id: UUID | None = None
    participant_entity_ids: list[UUID] = Field(default_factory=list)
    quote: str | None = None


class BackupChapterMeta(BackupModel):
    chapter_id: UUID
    synopsis: str = ""
    pov_entity_id: UUID | None = None
    location_entity_id: UUID | None = None
    story_time: str | None = Field(default=None, max_length=200)
    status: str = "draft"


class BackupCanonException(BackupModel):
    scope: str
    entity_id: UUID | None = None
    predicate: str | None = None
    pattern: str | None = None
    reason: str = Field(min_length=1)


class StoryBackup(BackupModel):
    format_version: int = 1
    exported_at: datetime
    story: BackupStory
    arcs: list[BackupArc] = Field(default_factory=list)
    chapters: list[BackupChapter] = Field(default_factory=list)
    entities: list[BackupEntity] = Field(default_factory=list)
    relationships: list[BackupRelationship] = Field(default_factory=list)
    threads: list[BackupThread] = Field(default_factory=list)
    events: list[BackupEvent] = Field(default_factory=list)
    chapter_meta: list[BackupChapterMeta] = Field(default_factory=list)
    canon_exceptions: list[BackupCanonException] = Field(default_factory=list)


class BackupImportOut(BackupModel):
    story_id: UUID
    chapters: int
    entities: int
    facts: int
    relationships: int
    threads: int
    events: int