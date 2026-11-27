"""Recap request and response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChapterSynopsisUpdate(BaseModel):
    synopsis: str = Field(max_length=20_000)


class ChapterSynopsisOut(BaseModel):
    chapter_id: UUID
    synopsis: str
    editable: bool
    generated: bool


class ArcSummaryOut(BaseModel):
    arc_id: UUID
    summary: str
    chapter_count: int


class RecapCitationOut(BaseModel):
    chapter_id: UUID
    chapter_number: int
    chapter_title: str
    quote: str
    line: int


class RecapChapterOut(BaseModel):
    chapter_id: UUID
    chapter_number: int
    title: str
    synopsis: str
    citation: RecapCitationOut


class ArcRecapOut(BaseModel):
    arc_id: UUID
    name: str
    summary: str


class StorySoFarOut(BaseModel):
    story_id: UUID
    range_label: str
    chapters: list[RecapChapterOut]
    arcs: list[ArcRecapOut]
    read_only: bool = True
    generated_at: datetime