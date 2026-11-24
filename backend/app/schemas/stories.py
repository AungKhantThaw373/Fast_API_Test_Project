from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    collection_name: str | None = Field(default=None, max_length=100)
    scan_interval_words: int | None = Field(default=None, ge=0, le=1_000_000)
    external_analysis_enabled: bool | None = None


class ChapterCreate(BaseModel):
    title: str = Field(default="Untitled chapter", min_length=1, max_length=200)
    content: str = Field(default="", max_length=1_000_000)


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=1_000_000)
    expected_revision: int = Field(ge=1)
    # Optional idempotency key: replaying the same save after a timeout returns
    # the stored chapter instead of creating another revision.
    client_save_id: UUID | None = None


class CheckpointCreate(BaseModel):
    label: str | None = Field(default=None, max_length=200)


class BibleScanRange(BaseModel):
    start_chapter: int = Field(ge=1)
    end_chapter: int = Field(ge=1)
    force: bool = False


class BibleEntryUpdate(BaseModel):
    category: Literal["character", "location", "item", "world_rule", "worldbuilding", "power_system", "plot_thread"]
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    details: dict = Field(default_factory=dict)


class BibleEntryCreate(BibleEntryUpdate):
    pass


class ChapterReorder(BaseModel):
    chapter_ids: list[UUID] = Field(min_length=1, max_length=5000)


class ChapterMove(BaseModel):
    destination_story_id: UUID


class FindingReviewUpdate(BaseModel):
    review_status: Literal["open", "resolved", "dismissed"]


class ManuscriptImport(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5_000_000)


class BibleDecision(BaseModel):
    status: Literal["accepted", "dismissed"]


class ThreadUpdate(BaseModel):
    thread_state: Literal["open", "resolved"]


class IntentionalUpdate(BaseModel):
    intentional: bool = True
