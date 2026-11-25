"""Response models for story-wide retrieval."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchEntityOut(BaseModel):
    id: UUID
    name: str
    entity_type: str


class SearchHitOut(BaseModel):
    chunk_id: UUID
    chapter_id: UUID
    chapter_number: int
    chapter_title: str
    scene_index: int
    chunk_index: int
    start_line: int
    end_line: int
    quote: str
    score: float
    scores: dict[str, float] = Field(default_factory=dict)
    entities: list[SearchEntityOut] = Field(default_factory=list)


class SearchOut(BaseModel):
    query: str
    semantic_query: str
    lexical_query: str
    name_query: str
    entity_ids: list[UUID] = Field(default_factory=list)
    cache_hit: bool
    timings_ms: dict[str, float] = Field(default_factory=dict)
    results: list[SearchHitOut] = Field(default_factory=list)
