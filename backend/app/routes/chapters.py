"""Chapter endpoints: create, import, save, order, move, history, and index state."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.story_models import Chapter
from app.schemas.chapters import (
    ChapterCreate,
    ChapterListOut,
    ChapterMove,
    ChapterMoveOut,
    ChapterOut,
    ChapterReorder,
    ChapterStatusOut,
    ChapterSummaryOut,
    ChapterUpdate,
    CheckpointCreate,
    CheckpointOut,
    DiffHunkOut,
    DiffSideOut,
    ManuscriptImport,
    RetryIndexOut,
    RevisionDiffOut,
    RevisionListOut,
    RevisionSummaryOut,
)
from app.security import get_current_user
from app.services import chapters as chapters_service
from app.services import indexing
from app.services import stories as stories_service

router = APIRouter(prefix="/stories", tags=["chapters"])


def _out(chapter: Chapter) -> ChapterOut:
    return ChapterOut.model_validate(chapter)


def _summary(chapter: Chapter) -> ChapterSummaryOut:
    return ChapterSummaryOut.model_validate(chapter)


def _chapter_etag(chapter: Chapter) -> str:
    """Revision plus save time: cheap to compute and changes on every save."""
    return f'"{chapter.revision}-{int(chapter.updated_at.timestamp())}"'


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = {value.strip() for value in if_none_match.split(",")}
    return "*" in candidates or etag in candidates or f"W/{etag}" in candidates


@router.post("/{story_id}/chapters", status_code=status.HTTP_201_CREATED, response_model=ChapterOut)
async def create_chapter(
    story_id: UUID,
    payload: ChapterCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Chapter:
    story = await stories_service.owned_story(session, story_id, user.id)
    chapter = await chapters_service.create_chapter(session, story, payload.title, payload.content)
    background_tasks.add_task(indexing.schedule_chapter_reindex, chapter.id)
    return chapter


@router.post("/{story_id}/import", status_code=status.HTTP_201_CREATED, response_model=ChapterListOut)
async def import_manuscript(
    story_id: UUID,
    payload: ManuscriptImport,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterListOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    created = await chapters_service.import_manuscript(session, story, payload)
    for chapter in created:
        background_tasks.add_task(indexing.schedule_chapter_reindex, chapter.id)
    return ChapterListOut(chapters=[_summary(chapter) for chapter in created])


@router.put("/{story_id}/chapters/order", response_model=ChapterListOut)
async def reorder_chapters(
    story_id: UUID,
    payload: ChapterReorder,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterListOut:
    story = await stories_service.owned_story(session, story_id, user.id)
    ordered = await chapters_service.reorder_chapters(session, story, payload)
    return ChapterListOut(chapters=[_summary(chapter) for chapter in ordered])


@router.put("/chapters/{chapter_id}", response_model=ChapterOut)
async def update_chapter(
    chapter_id: UUID,
    payload: ChapterUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        chapter, changed = await chapters_service.save_chapter(
            session, chapter_id, user.id, payload
        )
    except chapters_service.SaveConflict as conflict:
        # Return everything the conflict dialog needs so the writer does not wait
        # for another round trip to see the saved version.
        stale = conflict.chapter
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This chapter changed since it was loaded. Reload before saving.",
                "current_revision": stale.revision,
                "current_title": stale.title,
                "current_content": stale.content,
                "updated_at": stale.updated_at.isoformat(),
            },
        )
    if changed:
        background_tasks.add_task(indexing.schedule_chapter_reindex, chapter.id)
    return chapter


@router.get(
    "/chapters/{chapter_id}",
    response_model=ChapterOut,
    responses={304: {"description": "Not modified"}},
)
async def get_chapter(
    chapter_id: UUID,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    etag = _chapter_etag(chapter)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if _etag_matches(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    # Returning a Response directly: this FastAPI version does not copy headers
    # from an injected Response, and the ETag is the whole point of the route.
    return JSONResponse(content=_out(chapter).model_dump(mode="json"), headers=headers)


@router.get("/chapters/{chapter_id}/status", response_model=ChapterStatusOut)
async def get_chapter_status(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterStatusOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    return ChapterStatusOut.model_validate(chapter)


@router.get("/chapters/{chapter_id}/revisions", response_model=RevisionListOut)
async def list_chapter_revisions(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RevisionListOut:
    await chapters_service.owned_chapter(session, chapter_id, user.id)
    revisions = await chapters_service.list_revisions(session, chapter_id)
    return RevisionListOut(
        revisions=[RevisionSummaryOut.model_validate(item) for item in revisions]
    )


@router.post(
    "/chapters/{chapter_id}/checkpoint",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckpointOut,
)
async def create_chapter_checkpoint(
    chapter_id: UUID,
    payload: CheckpointCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CheckpointOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    revision = await chapters_service.create_checkpoint(session, chapter)
    return CheckpointOut(
        revision_number=revision.revision_number,
        kind=revision.kind,
        word_count=revision.word_count,
        char_count=revision.char_count,
        created_at=revision.created_at,
        label=payload.label,
    )


@router.get(
    "/chapters/{chapter_id}/revisions/{older}/diff/{newer}",
    response_model=RevisionDiffOut,
)
async def diff_chapter_revisions(
    chapter_id: UUID,
    older: int,
    newer: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RevisionDiffOut:
    await chapters_service.owned_chapter(session, chapter_id, user.id)
    older_revision, newer_revision, hunks = await chapters_service.revision_diff(
        session, chapter_id, older, newer
    )
    return RevisionDiffOut(
        older=DiffSideOut.model_validate(older_revision),
        newer=DiffSideOut.model_validate(newer_revision),
        hunks=[DiffHunkOut.model_validate(hunk) for hunk in hunks],
    )


@router.post(
    "/chapters/{chapter_id}/revisions/{revision_number}/restore",
    response_model=ChapterOut,
)
async def restore_chapter_revision(
    chapter_id: UUID,
    revision_number: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Chapter:
    chapter = await chapters_service.owned_chapter(
        session, chapter_id, user.id, for_update=True
    )
    restored = await chapters_service.restore_revision(session, chapter, revision_number)
    background_tasks.add_task(indexing.schedule_chapter_reindex, restored.id)
    return restored


@router.post("/chapters/{chapter_id}/move", response_model=ChapterMoveOut)
async def move_chapter(
    chapter_id: UUID,
    payload: ChapterMove,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterMoveOut:
    destination, chapter = await chapters_service.move_chapter(
        session, chapter_id, user.id, payload.destination_story_id
    )
    return ChapterMoveOut(story_id=destination.id, chapter=_out(chapter))


@router.delete("/chapters/{chapter_id}", response_model=ChapterListOut)
async def delete_chapter(
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ChapterListOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    remaining = await chapters_service.delete_chapter(session, chapter)
    return ChapterListOut(chapters=[_summary(item) for item in remaining])


@router.post(
    "/chapters/{chapter_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RetryIndexOut,
)
async def retry_chapter_index(
    chapter_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RetryIndexOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    chapter = await chapters_service.mark_for_reindex(session, chapter)
    background_tasks.add_task(indexing.schedule_chapter_reindex, chapter.id)
    return RetryIndexOut(id=chapter.id, index_status=chapter.index_status)
