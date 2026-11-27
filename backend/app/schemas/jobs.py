"""Background job response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    progress: dict[str, Any]
    last_error: str | None
    run_at: datetime
    created_at: datetime
    updated_at: datetime
