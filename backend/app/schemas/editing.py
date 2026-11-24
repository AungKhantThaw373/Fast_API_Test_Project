from uuid import UUID

from pydantic import BaseModel, Field


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class FolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DraftFileUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder_id: UUID | None = None
