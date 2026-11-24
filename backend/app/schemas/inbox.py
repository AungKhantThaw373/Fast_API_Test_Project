"""Review inbox, merge proposals, and auto-accept rules."""

from uuid import UUID

from pydantic import BaseModel, Field


class InboxDecision(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(accept|reject|resolve|dismiss)$")


class InboxDecisionResult(BaseModel):
    facts: int
    findings: int
    merges: int
    skipped: int
    action: str


class MergeProposalOut(BaseModel):
    id: UUID
    story_id: UUID
    source_id: UUID
    target_id: UUID
    source_name: str
    target_name: str
    score: float
    status: str
    created_at: object | None = None


class AutoAcceptRulesIn(BaseModel):
    require_quote: bool | None = None
    min_confidence: int | None = Field(default=None, ge=0, le=100)
    require_existing_entity: bool | None = None
    block_conflicts: bool | None = None
    max_per_chapter: int | None = Field(default=None, ge=1, le=500)


class AutoAcceptRulesOut(BaseModel):
    require_quote: bool
    min_confidence: int
    require_existing_entity: bool
    block_conflicts: bool
    max_per_chapter: int


class AutoAcceptPreviewOut(BaseModel):
    would_accept: int
    held: int
    total: int
    rules: AutoAcceptRulesOut


class AutoAcceptRunOut(BaseModel):
    accepted: int
    held: int
