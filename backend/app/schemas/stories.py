"""Story request and response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chapters import ChapterSummaryOut


class StoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    collection_name: str | None = Field(default=None, max_length=100)
    scan_interval_words: int | None = Field(default=None, ge=0, le=1_000_000)
    external_analysis_enabled: bool | None = None


class StoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    collection_name: str
    scan_interval_words: int
    external_analysis_enabled: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class StorySummaryOut(StoryOut):
    chapter_count: int
    word_count: int


class StoryListOut(BaseModel):
    stories: list[StorySummaryOut]
    next_cursor: str | None = None


class StoryDetailsOut(StorySummaryOut):
    chapters: list[ChapterSummaryOut]
    # The chapter list is not paginated by default; it is capped instead.
    chapters_truncated: bool = False
