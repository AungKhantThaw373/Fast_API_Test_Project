"""Wiki API models: entities, aliases, facts, relationships, threads, events."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal[
    "character",
    "location",
    "item",
    "organization",
    "concept",
    "world_rule",
    "power_system",
    "creature",
    "other",
]
AliasType = Literal["name", "title", "epithet", "disguise", "translation", "other"]
FactStatus = Literal["proposed", "accepted", "rejected", "superseded"]
ValueType = Literal["text", "number", "date", "entity", "boolean"]
ThreadState = Literal["open", "touched", "resolved", "abandoned"]


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    alias_type: AliasType = "name"


class AliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alias: str
    normalized_alias: str
    alias_type: str


class EntityCreate(BaseModel):
    entity_type: EntityType
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=20000)
    aliases: list[AliasCreate] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    entity_type: EntityType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20000)


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    entity_type: str
    name: str
    summary: str
    status: str
    merged_into_id: UUID | None
    first_chapter_number: int | None
    last_chapter_number: int | None
    created_at: datetime
    updated_at: datetime
    aliases: list[AliasOut] = Field(default_factory=list)


class EntityListOut(BaseModel):
    entities: list[EntityOut]
    next_cursor: str | None = None


class EntitySearchOut(BaseModel):
    entities: list[EntityOut]
    next_cursor: str | None = None


class MergeRequest(BaseModel):
    target_id: UUID
    dry_run: bool = False


class MergeResultOut(BaseModel):
    source_id: UUID
    target_id: UUID
    dry_run: bool
    moved: dict[str, int]


class UnmergeOut(BaseModel):
    source_id: UUID
    target_id: UUID
    merge_id: UUID
    reverted_at: datetime | None


class AppearanceOut(BaseModel):
    chapter_id: UUID
    chapter_number: int
    chapter_title: str
    line_start: int
    line_end: int
    quote: str


class AppearanceListOut(BaseModel):
    appearances: list[AppearanceOut]
    next_cursor: str | None = None


class FactCreate(BaseModel):
    predicate: str = Field(min_length=1, max_length=100)
    value_text: str | None = Field(default=None, max_length=20000)
    value_number: float | None = None
    value_date: date | None = None
    value_entity_id: UUID | None = None
    value_type: ValueType = "text"
    chapter_id: UUID | None = None
    scene_index: int | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=4000)
    confidence: int = Field(default=50, ge=0, le=100)
    status: FactStatus = "accepted"
    valid_from_chapter: int | None = Field(default=None, ge=1)
    valid_to_chapter: int | None = Field(default=None, ge=1)
    supersedes_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_a_value(self) -> "FactCreate":
        if (
            self.value_text is None
            and self.value_number is None
            and self.value_date is None
            and self.value_entity_id is None
        ):
            raise ValueError("A fact needs a value.")
        if self.valid_from_chapter and self.valid_to_chapter:
            if self.valid_from_chapter > self.valid_to_chapter:
                raise ValueError("valid_from_chapter must not be after valid_to_chapter.")
        return self


class FactUpdate(BaseModel):
    predicate: str | None = Field(default=None, min_length=1, max_length=100)
    value_text: str | None = Field(default=None, max_length=20000)
    value_number: float | None = None
    value_date: date | None = None
    value_entity_id: UUID | None = None
    value_type: ValueType | None = None
    chapter_id: UUID | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=4000)
    confidence: int | None = Field(default=None, ge=0, le=100)
    valid_from_chapter: int | None = Field(default=None, ge=1)
    valid_to_chapter: int | None = Field(default=None, ge=1)
    context: dict[str, Any] | None = None


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    predicate: str
    value_text: str | None
    value_number: float | None
    value_date: date | None
    value_entity_id: UUID | None
    value_type: str
    chapter_id: UUID | None
    scene_index: int | None
    line_start: int | None
    line_end: int | None
    quote: str | None
    confidence: int
    status: str
    valid_from_chapter: int | None
    valid_to_chapter: int | None
    supersedes_id: UUID | None
    context: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class FactListOut(BaseModel):
    facts: list[FactOut]


class RelationshipCreate(BaseModel):
    to_entity_id: UUID
    relationship_type: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=4000)
    since_chapter: int | None = Field(default=None, ge=1)
    until_chapter: int | None = Field(default=None, ge=1)
    chapter_id: UUID | None = None
    quote: str | None = Field(default=None, max_length=4000)


class RelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    description: str
    since_chapter: int | None
    until_chapter: int | None
    chapter_id: UUID | None
    quote: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class RelationshipListOut(BaseModel):
    outgoing: list[RelationshipOut]
    incoming: list[RelationshipOut]


class ThreadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    setup_chapter_id: UUID | None = None
    setup_quote: str | None = Field(default=None, max_length=4000)
    payoff_chapter_id: UUID | None = None
    state: ThreadState = "open"
    linked_entity_ids: list[UUID] = Field(default_factory=list)


class ThreadUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    payoff_chapter_id: UUID | None = None
    state: ThreadState | None = None
    linked_entity_ids: list[UUID] | None = None


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    title: str
    description: str
    setup_chapter_id: UUID | None
    setup_quote: str | None
    payoff_chapter_id: UUID | None
    state: str
    linked_entity_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class ThreadListOut(BaseModel):
    threads: list[ThreadOut]


class EventCreate(BaseModel):
    chapter_id: UUID
    scene_index: int | None = None
    timeline_order: float | None = None
    summary: str = Field(min_length=1, max_length=4000)
    location_entity_id: UUID | None = None
    participant_entity_ids: list[UUID] = Field(default_factory=list)
    quote: str | None = Field(default=None, max_length=4000)


class EventUpdate(BaseModel):
    scene_index: int | None = None
    timeline_order: float | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=4000)
    location_entity_id: UUID | None = None
    participant_entity_ids: list[UUID] | None = None
    quote: str | None = Field(default=None, max_length=4000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    chapter_id: UUID
    scene_index: int | None
    timeline_order: float | None
    summary: str
    location_entity_id: UUID | None
    participant_entity_ids: list[UUID]
    quote: str | None
    created_at: datetime
    updated_at: datetime


class EventListOut(BaseModel):
    events: list[EventOut]


class InboxSourceOut(BaseModel):
    chapter_id: UUID | None = None
    chapter_number: int | None = None
    line: int | None = None
    quote: str | None = None


class InboxItemOut(BaseModel):
    id: UUID
    kind: str
    title: str
    summary: str
    confidence: int
    source: InboxSourceOut
    actions: list[str]
    why_held: str | None = None
    entity_id: UUID | None = None
    chapter_id: UUID | None = None


class InboxOut(BaseModel):
    items: list[InboxItemOut]
    next_cursor: str | None = None
