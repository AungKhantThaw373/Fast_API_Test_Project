from pydantic import BaseModel, EmailStr, Field, field_validator


def normalize_email(value: str) -> str:
    """Emails are login identifiers; compare them case-insensitively."""
    return value.strip().lower()


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class Token(BaseModel):
    access_token: str
    token_type: str
