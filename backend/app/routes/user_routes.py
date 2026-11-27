from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User, UserAISettings
from app.schemas.user import AISettingsUpdate
from app.security import get_current_user
from app.services.ai_credentials import encrypt_api_key
from app.services.ai_settings import PROVIDERS, base_url_for
from app.services.audit import record_audit
from app.services.url_safety import assert_public_url

router = APIRouter(tags=["account"])


@router.get("/me")
async def current_user(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }


def _ai_settings_data(row: UserAISettings | None) -> dict:
    if row is None:
        if settings.OPENROUTER_API_KEY:
            return {
                "provider": "openrouter",
                "model": settings.OPENROUTER_MODEL,
                "base_url": settings.OPENROUTER_BASE_URL,
                "api_key_configured": True,
                "using_server_default": True,
            }
        return {
            "provider": "ollama",
            "model": settings.OLLAMA_CHAT_MODEL,
            "base_url": settings.OLLAMA_BASE_URL,
            "api_key_configured": True,
            "using_server_default": True,
        }
    return {
        "provider": row.provider,
        "model": row.model,
        "base_url": base_url_for(row.provider, row.base_url),
        "api_key_configured": True,
        "using_server_default": False,
    }


@router.get("/ai-settings")
async def get_ai_settings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    row = await session.get(UserAISettings, user.id)
    return _ai_settings_data(row)


@router.get("/ai-providers")
async def list_ai_providers():
    return {
        "providers": [
            {"id": provider, "label": preset.label, "base_url": preset.base_url}
            for provider, preset in PROVIDERS.items()
        ]
    }


@router.put("/ai-settings")
async def save_ai_settings(
    payload: AISettingsUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    existing = await session.get(UserAISettings, user.id)
    model = payload.model.strip()
    if not model:
        raise HTTPException(status_code=422, detail="Enter a model ID.")

    base_url = payload.base_url.strip() if payload.base_url else None
    if base_url:
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError:
            raise HTTPException(status_code=422, detail="Enter a valid API base URL.") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (port is not None and not 1 <= port <= 65535)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise HTTPException(status_code=422, detail="Enter a valid API base URL without credentials, query parameters, or a fragment.")
        base_url = base_url.rstrip("/")
        try:
            await assert_public_url(base_url, allow_private=payload.provider == "ollama")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    if payload.provider == "custom" and not base_url:
        raise HTTPException(status_code=422, detail="A base URL is required for a custom provider.")

    submitted_key = payload.api_key.strip() if payload.api_key else ""
    same_provider = existing is not None and existing.provider == payload.provider
    if payload.provider == "ollama":
        # Local Ollama has no key; store a stable empty value so the column
        # stays non-null and switching back to a cloud provider prompts again.
        encrypted_key = encrypt_api_key("")
    elif submitted_key:
        encrypted_key = encrypt_api_key(submitted_key)
    elif same_provider and existing is not None:
        encrypted_key = existing.api_key_encrypted
    else:
        raise HTTPException(status_code=422, detail="Enter an API key for this provider.")


    if existing is None:
        existing = UserAISettings(user_id=user.id)
        session.add(existing)
    existing.provider = payload.provider
    existing.model = model
    existing.base_url = base_url
    existing.api_key_encrypted = encrypted_key
    record_audit(
        session,
        "provider_changed",
        user_id=user.id,
        email=user.email,
        target_type="ai_settings",
        target_id=str(user.id),
        detail={"provider": payload.provider, "model": model, "base_url": base_url},
        request=request,
    )
    await session.commit()
    await session.refresh(existing)
    return _ai_settings_data(existing)


@router.delete("/ai-settings")
async def reset_ai_settings(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    existing = await session.get(UserAISettings, user.id)
    if existing is not None:
        await session.delete(existing)
        record_audit(
            session,
            "provider_reset",
            user_id=user.id,
            email=user.email,
            target_type="ai_settings",
            target_id=str(user.id),
            request=request,
        )
        await session.commit()
    return _ai_settings_data(None)
