"""Read-only AI usage view for one story."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.schemas.ai_usage import AIUsageOut, AIUsagePurposeOut
from app.security import get_current_user
from app.services import stories as stories_service
from app.services.ai_usage import usage_summary

router = APIRouter(prefix="/stories", tags=["ai-usage"])


@router.get("/{story_id}/ai-usage", response_model=AIUsageOut)
async def get_ai_usage(
    story_id: UUID,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AIUsageOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    summary = await usage_summary(session, story.id, month=month)
    purposes = summary.pop("by_purpose")
    return AIUsageOut(
        **summary,
        by_purpose=[AIUsagePurposeOut(**row) for row in purposes],
    )
