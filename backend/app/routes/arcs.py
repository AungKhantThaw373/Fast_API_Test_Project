"""Arc endpoints: the chapter rail group headings and the wiki arc filter."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.story_models import Arc
from app.schemas.chapters import ArcAssignment, ArcCreate, ArcOut, ArcUpdate
from app.security import get_current_user
from app.services import arcs as arcs_service
from app.services import stories as stories_service

router = APIRouter(prefix="/stories/{story_id}/arcs", tags=["arcs"])
arc_router = APIRouter(prefix="/arcs", tags=["arcs"])


@router.get("", response_model=list[ArcOut])
async def list_arcs(
    story_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await stories_service.owned_story(session, story_id, user.id)
    return await arcs_service.list_arcs(session, story_id)


@router.post("", response_model=ArcOut, status_code=status.HTTP_201_CREATED)
async def create_arc(
    story_id: UUID,
    payload: ArcCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> dict:
    await stories_service.owned_story(session, story_id, user.id)
    arc = await arcs_service.create_arc(session, story_id, payload.name, payload.summary)
    await session.commit()
    return {
        "id": arc.id,
        "story_id": arc.story_id,
        "name": arc.name,
        "summary": arc.summary,
        "position": arc.position,
        "chapter_count": 0,
        "first_chapter_number": None,
        "last_chapter_number": None,
    }


@router.put("", response_model=dict)
async def assign_chapters(
    story_id: UUID,
    payload: ArcAssignment,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> dict:
    await stories_service.owned_story(session, story_id, user.id)
    try:
        moved = await arcs_service.assign_chapters(session, story_id, payload.arc_id, payload.chapter_ids)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    await session.commit()
    return {"updated": moved}


@arc_router.patch("/{arc_id}", response_model=ArcOut)
async def update_arc(
    arc_id: UUID,
    payload: ArcUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> dict:
    arc = await _owned_arc(session, arc_id, user.id)
    await arcs_service.update_arc(session, arc, **payload.model_dump(exclude_none=True))
    await session.commit()
    rows = await arcs_service.list_arcs(session, arc.story_id)
    return next(row for row in rows if row["id"] == arc.id)


@arc_router.delete("/{arc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_arc(
    arc_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> None:
    arc = await _owned_arc(session, arc_id, user.id)
    await arcs_service.delete_arc(session, arc)
    await session.commit()


async def _owned_arc(session: AsyncSession, arc_id: UUID, user_id: UUID) -> Arc:
    arc = await arcs_service.get_arc(session, arc_id)
    if arc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arc not found.")
    await stories_service.owned_story(session, arc.story_id, user_id)
    return arc
