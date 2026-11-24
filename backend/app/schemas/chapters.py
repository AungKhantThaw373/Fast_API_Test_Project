"""Chapter request and response models.

Request models validate what the client sends. Response models are the contract
for ``/openapi.json``; they are built from ORM rows with ``from_attributes``.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class ChapterReorder(BaseModel):
    chapter_ids: list[UUID] = Field(min_length=1, max_length=5000)


class ChapterMove(BaseModel):
    destination_story_id: UUID


class ManuscriptImport(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5_000_000)


class ChapterSummaryOut(BaseModel):
    """A chapter without its manuscript text."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    chapter_number: int
    arc_id: UUID | None = None
    title: str
    word_count: int
    revision: int
    bible_scan_revision: int | None
    bible_scan_error: str | None
    index_status: str
    index_error: str | None
    updated_at: datetime
    deleted_at: datetime | None


class ChapterOut(ChapterSummaryOut):
    content: str


class ChapterListOut(BaseModel):
    chapters: list[ChapterSummaryOut]


class ChapterMoveOut(BaseModel):
    story_id: UUID
    chapter: ChapterOut


class ChapterStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision: int
    bible_scan_revision: int | None
    bible_scan_error: str | None
    word_count: int
    index_status: str
    index_error: str | None


class ChapterIndexRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision: int
    word_count: int
    index_status: str
    index_error: str | None
    bible_scan_revision: int | None
    bible_scan_error: str | None


class ChapterIndexStatusOut(BaseModel):
    chapters: list[ChapterIndexRowOut]


class RetryIndexOut(BaseModel):
    id: UUID
    index_status: str


class RevisionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_number: int
    title: str
    word_count: int
    kind: str
    char_count: int
    created_at: datetime


class RevisionListOut(BaseModel):
    revisions: list[RevisionSummaryOut]


class CheckpointOut(BaseModel):
    revision_number: int
    kind: str
    word_count: int
    char_count: int
    created_at: datetime
    label: str | None


class DiffSideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_number: int
    word_count: int
    kind: str
    created_at: datetime


class DiffHunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str]


class RevisionDiffOut(BaseModel):
    older: DiffSideOut
    newer: DiffSideOut
    hunks: list[DiffHunkOut]


class ArcCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=20_000)


class ArcUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20_000)
    position: float | None = None


class ArcOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    name: str
    summary: str
    position: float
    chapter_count: int = 0
    first_chapter_number: int | None = None
    last_chapter_number: int | None = None


class ArcAssignment(BaseModel):
    arc_id: UUID | None = None
    chapter_ids: list[UUID] = Field(min_length=1, max_length=5000)
