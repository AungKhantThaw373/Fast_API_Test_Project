"""Continuity scan request and response models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FindingReviewUpdate(BaseModel):
    review_status: Literal["open", "resolved", "dismissed"]


class IntentionalUpdate(BaseModel):
    intentional: bool = True


class ScanSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_revision: int
    chapter_word_count: int
    prompt_version: str | None = None
    model: str | None = None
    schema_version: str | None = None
    scenes_total: int = 0
    scenes_done: int = 0
    scenes_failed: int = 0
    created_at: datetime


class FindingOut(BaseModel):
    id: UUID
    draft_quote: str
    draft_line: int
    earlier_quote: str | None
    earlier_chapter_id: UUID | None
    earlier_chapter_number: int
    earlier_chapter_title: str
    explanation: str
    confidence: int
    intentional: bool
    review_status: str
    source: str = "llm"
    rule_id: str | None = None
    scene_index: int | None = None
    evidence_kind: str | None = None
    evidence_id: str | None = None


class LatestScanOut(BaseModel):
    scan: ScanSummaryOut | None
    findings: list[FindingOut]
    next_cursor: str | None = None


class ScanJobOut(BaseModel):
    job_id: UUID


class ScanCheckOut(BaseModel):
    scan_id: UUID
    finding_count: int
    chapter_revision: int
    reused: bool


class IntentionalOut(BaseModel):
    id: UUID
    intentional: bool


class FindingReviewOut(BaseModel):
    id: UUID
    review_status: str
    intentional: bool
