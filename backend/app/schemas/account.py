from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import normalize_email


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=40)


class MessageOut(BaseModel):
    message: str


class SessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_agent: str
    ip: str
    created_at: datetime
    last_seen_at: datetime
    current: bool = False


class SessionListOut(BaseModel):
    sessions: list[SessionView]


class AuditEventView(BaseModel):
    id: UUID
    action: str
    target_type: str
    target_id: str
    detail: dict[str, Any]
    ip: str
    created_at: datetime


class AuditListOut(BaseModel):
    events: list[AuditEventView]