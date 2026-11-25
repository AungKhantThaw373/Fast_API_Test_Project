"""Ask Story endpoint: cited answers only, never free-form generation."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.schemas.ask import AskStoryIn, AskStoryOut
from app.security import get_current_user
from app.services import stories as stories_service
from app.services.ask_story import ask_story

router = APIRouter(prefix="/stories", tags=["ask"])


@router.post("/{story_id}/ask", response_model=AskStoryOut)
async def ask(
    story_id: UUID,
    payload: AskStoryIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AskStoryOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    result = await ask_story(session, story, user.id, payload.question)
    return AskStoryOut(**result)
