"""Ask Story request and citation response models."""

from pydantic import BaseModel, Field


class AskStoryIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskCitationOut(BaseModel):
    chunk_id: str
    chapter_number: int
    line: int
    quote: str
    explanation: str


class AskStoryOut(BaseModel):
    answer: str
    unsure: bool
    citations: list[AskCitationOut]
