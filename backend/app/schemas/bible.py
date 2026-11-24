"""Story Bible request and response models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BibleCategory = Literal[
    "character", "location", "item", "world_rule", "worldbuilding", "power_system", "plot_thread"
]


class BibleScanRange(BaseModel):
    start_chapter: int = Field(ge=1)
    end_chapter: int = Field(ge=1)
    force: bool = False


class BibleEntryUpdate(BaseModel):
    category: BibleCategory
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    details: dict = Field(default_factory=dict)


class BibleEntryCreate(BibleEntryUpdate):
    pass


class BibleDecision(BaseModel):
    status: Literal["accepted", "dismissed"]


class ThreadUpdate(BaseModel):
    thread_state: Literal["open", "resolved"]


class BibleEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: str
    name: str
    description: str
    status: str
    thread_state: str | None
    confidence: int
    source_chapter_id: UUID | None
    source_quote: str | None
    details: dict
    updated_at: datetime


class BibleListOut(BaseModel):
    entries: list[BibleEntryOut]


class ScheduledBibleChapterOut(BaseModel):
    id: UUID
    revision: int


class BibleScanOut(BaseModel):
    scheduled_count: int
    skipped_count: int
    scheduled_chapters: list[ScheduledBibleChapterOut]
