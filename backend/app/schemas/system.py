"""Diagnostics response models."""

from datetime import datetime

from pydantic import BaseModel


class JobStatusCounts(BaseModel):
    queued: int
    running: int
    succeeded: int
    failed: int
    dead: int


class AIUsageMetric(BaseModel):
    purpose: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float


class BackupStatus(BaseModel):
    filename: str
    size_bytes: int
    modified_at: datetime


class DiagnosticsOut(BaseModel):
    generated_at: datetime
    database: str
    database_size_bytes: int
    pgvector: str
    schema_status: str
    worker: str
    ollama: str
    jobs: JobStatusCounts
    ai_provider: str
    ai_model: str
    ai_usage_30d: list[AIUsageMetric]
    last_backup: BackupStatus | None
    slow_query_ms: int