"""AI usage response models."""

from pydantic import BaseModel


class AIUsagePurposeOut(BaseModel):
    purpose: str
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    average_duration_ms: int


class AIUsageOut(BaseModel):
    month: str
    calls: int
    input_tokens: int
    output_tokens: int
    spent_usd: float
    by_purpose: list[AIUsagePurposeOut]
