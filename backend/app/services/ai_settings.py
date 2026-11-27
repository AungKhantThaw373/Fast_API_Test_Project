from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from app.models.app_models import UserAISettings
from app.services.ai_credentials import decrypt_api_key
from app.services.url_safety import assert_public_url


@dataclass(frozen=True)
class ProviderPreset:
    label: str
    base_url: str
    protocol: str = "openai"


PROVIDERS: dict[str, ProviderPreset] = {
    "ollama": ProviderPreset("Ollama (local, free)", settings.OLLAMA_BASE_URL, "ollama"),
    "openrouter": ProviderPreset("OpenRouter", settings.OPENROUTER_BASE_URL),
    "openai": ProviderPreset("OpenAI", "https://api.openai.com/v1"),
    "anthropic": ProviderPreset("Anthropic", "https://api.anthropic.com", "anthropic"),
    "google": ProviderPreset("Google Gemini", "https://generativelanguage.googleapis.com/v1beta", "google"),
    "cohere": ProviderPreset("Cohere", "https://api.cohere.com/v2", "cohere"),
    "cohere_compat": ProviderPreset(
        "Cohere (OpenAI-compatible)", "https://api.cohere.ai/compatibility/v1", "cohere_compat"
    ),
    "deepseek": ProviderPreset("DeepSeek", "https://api.deepseek.com/v1"),
    "groq": ProviderPreset("Groq", "https://api.groq.com/openai/v1"),
    "mistral": ProviderPreset("Mistral", "https://api.mistral.ai/v1"),
    "together": ProviderPreset("Together AI", "https://api.together.xyz/v1"),
    "fireworks": ProviderPreset("Fireworks AI", "https://api.fireworks.ai/inference/v1"),
    "cerebras": ProviderPreset("Cerebras", "https://api.cerebras.ai/v1"),
    "custom": ProviderPreset("Custom OpenAI-compatible", ""),
}


@dataclass(frozen=True)
class AIConfig:
    provider: str
    model: str
    api_key: str
    base_url: str
    protocol: str


def base_url_for(provider: str, custom_base_url: str | None = None) -> str:
    preset = PROVIDERS[provider]
    if provider == "openrouter":
        return custom_base_url or settings.OPENROUTER_BASE_URL
    return (custom_base_url or preset.base_url).rstrip("/")


async def has_ai_config(session: AsyncSession, user_id: UUID) -> bool:
    row = await session.get(UserAISettings, user_id)
    # Ollama is the offline default, so a fresh workspace is configured even
    # without a saved provider row or a cloud key.
    return bool(row or settings.OPENROUTER_API_KEY or settings.OLLAMA_BASE_URL)


async def load_ai_config(user_id: UUID) -> AIConfig:
    async with async_session() as session:
        row = await session.get(UserAISettings, user_id)

    if row:
        preset = PROVIDERS.get(row.provider)
        if not preset:
            raise RuntimeError("The saved AI provider is no longer supported. Update AI settings.")
        api_key = decrypt_api_key(row.api_key_encrypted) if row.api_key_encrypted else ""
        if row.base_url:
            try:
                await assert_public_url(row.base_url, allow_private=row.provider == "ollama")
            except ValueError as exc:
                raise RuntimeError(f"The saved AI base URL is not allowed: {exc}") from exc
        return AIConfig(
            provider=row.provider,
            model=row.model,
            api_key=api_key,
            base_url=base_url_for(row.provider, row.base_url),
            protocol=preset.protocol,
        )

    if settings.OPENROUTER_API_KEY:
        return AIConfig(
            provider="openrouter",
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL.rstrip("/"),
            protocol="openai",
        )
    return AIConfig(
        provider="ollama",
        model=settings.OLLAMA_CHAT_MODEL,
        api_key="",
        base_url=settings.OLLAMA_BASE_URL.rstrip("/"),
        protocol="ollama",
    )
