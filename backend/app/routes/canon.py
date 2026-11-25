"""Canon coverage and lazy arc extraction."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.logging_config import fields, get_logger
from app.models.app_models import User
from app.rate_limits import ai_scan_rate_limit
from app.schemas.canon import ArcCoverageOut, ArcExtractOut, CanonCoverageOut
from app.security import get_current_user
from app.services import canon_coverage as canon_service
from app.services import stories as stories_service

logger = get_logger("api")
router = APIRouter(prefix="/stories", tags=["canon"])


@router.get("/{story_id}/canon/coverage", response_model=CanonCoverageOut)
async def get_canon_coverage(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CanonCoverageOut:
    await stories_service.owned_story(session, story_id, user.id)
    result = await canon_service.coverage(session, story_id)
    return CanonCoverageOut(
        story_id=result.story_id,
        current_arc_id=result.current_arc_id,
        chapters=result.chapters,
        extracted=result.extracted,
        pending=result.chapters - result.extracted,
        unassigned_chapters=result.unassigned_chapters,
        arcs=[
            ArcCoverageOut(
                arc_id=arc.arc_id,
                arc_name=arc.arc_name,
                position=arc.position,
                chapter_count=arc.chapter_count,
                first_chapter_number=arc.first_chapter_number,
                last_chapter_number=arc.last_chapter_number,
                extracted_count=arc.extracted_count,
                pending_count=arc.chapter_count - arc.extracted_count,
                complete=arc.chapter_count > 0 and arc.extracted_count == arc.chapter_count,
            )
            for arc in result.arcs
        ],
    )


@router.post(
    "/{story_id}/canon/arcs/{arc_id}/extract",
    status_code=202,
    response_model=ArcExtractOut,
)
async def extract_arc_canon(
    story_id: UUID,
    arc_id: UUID,
    force: bool = Query(default=False),
    _limit: None = Depends(ai_scan_rate_limit),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ArcExtractOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    scheduled, skipped, chapter_count = await canon_service.queue_arc_extraction(
        session, story, arc_id, user.id, force=force
    )
    logger.info(
        "[canon] queue  %s",
        fields(
            story=str(story.id)[:8],
            arc=str(arc_id)[:8],
            chapters=chapter_count,
            scheduled=scheduled,
            skipped=skipped,
            force=force,
        ),
    )
    return ArcExtractOut(
        arc_id=arc_id,
        scheduled_count=scheduled,
        skipped_count=skipped,
        chapter_count=chapter_count,
    )