from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class CurrentUser(BaseModel):
    id: int | None = None
    username: str
    email: EmailStr | None = None


AIProviderName = Literal[
    "ollama", "openrouter", "openai", "anthropic", "google", "cohere", "cohere_compat", "deepseek", "groq",
    "mistral", "together", "fireworks", "cerebras", "custom",
]


class AISettingsUpdate(BaseModel):
    provider: AIProviderName
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=1000)
    base_url: str | None = Field(default=None, max_length=500)


class AISettingsView(BaseModel):
    provider: AIProviderName | None
    model: str | None
    base_url: str | None
    api_key_configured: bool
    using_server_default: bool
