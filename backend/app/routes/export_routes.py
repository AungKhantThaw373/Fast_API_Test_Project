"""Export manuscript files and move a whole story through JSON backup."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.schemas.backup import BackupImportOut, StoryBackup
from app.security import get_current_user
from app.services import stories as stories_service
from app.services.backup import build_backup, import_backup
from app.services.export import ExportFormat, render_export

router = APIRouter(prefix="/stories", tags=["export"])


@router.get("/{story_id}/export")
async def export_story(
    story_id: UUID,
    format: ExportFormat = Query(default="docx"),
    include_wiki: bool = Query(default=True),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    story = await stories_service.owned_story(session, story_id, user.id)
    body, media_type, filename = await render_export(session, story, format, include_wiki)
    fallback = filename.encode("ascii", "ignore").decode("ascii") or "manuscript"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'
        )
    }
    return Response(content=body, media_type=media_type, headers=headers)


@router.get("/{story_id}/backup", response_model=StoryBackup)
async def export_backup(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StoryBackup:
    story = await stories_service.owned_story(session, story_id, user.id)
    return await build_backup(session, story)


@router.post("/import-backup", status_code=status.HTTP_201_CREATED, response_model=BackupImportOut)
async def import_story_backup(
    payload: StoryBackup,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> BackupImportOut:
    return await import_backup(session, user.id, payload)