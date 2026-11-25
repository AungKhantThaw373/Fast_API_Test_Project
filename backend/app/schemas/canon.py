"""Canon extraction coverage for lazy arc-by-arc backfill."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ArcCoverageOut(BaseModel):
    arc_id: UUID
    arc_name: str
    position: float
    chapter_count: int
    first_chapter_number: int | None
    last_chapter_number: int | None
    extracted_count: int
    pending_count: int
    complete: bool


class CanonCoverageOut(BaseModel):
    story_id: UUID
    current_arc_id: UUID | None
    chapters: int
    extracted: int
    pending: int
    unassigned_chapters: int
    arcs: list[ArcCoverageOut]


class ArcExtractOut(BaseModel):
    arc_id: UUID
    scheduled_count: int
    skipped_count: int
    chapter_count: int