import hashlib
import logging
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.db import get_async_session
from app.models.app_models import User
from app.models.editing_models import DraftFile, EditingFolder
from app.schemas.editing import DraftFileUpdate, FolderCreate, FolderUpdate
from app.security import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/editing", tags=["editing file library"])
MAX_FILE_SIZE = 25 * 1024 * 1024
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}
PREVIEWABLE = {".pdf", ".txt", ".md", ".markdown"}


def _folder_data(folder: EditingFolder, count: int = 0, size: int = 0) -> dict:
    return {
        "id": str(folder.id),
        "name": folder.name,
        "file_count": count,
        "size_bytes": size,
        "created_at": folder.created_at.isoformat(),
        "updated_at": folder.updated_at.isoformat(),
    }


def _file_data(draft: DraftFile, folder_name: str) -> dict:
    return {
        "id": str(draft.id),
        "folder_id": str(draft.folder_id),
        "folder_name": folder_name,
        "title": draft.title,
        "original_filename": draft.original_filename,
        "extension": draft.extension,
        "media_type": draft.media_type,
        "size_bytes": draft.size_bytes,
        "sha256": draft.sha256,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
        "previewable": draft.extension in PREVIEWABLE,
    }


async def _owned_folder(session: AsyncSession, folder_id: UUID, owner_id: UUID) -> EditingFolder:
    folder = await session.scalar(
        select(EditingFolder).where(EditingFolder.id == folder_id, EditingFolder.owner_id == owner_id)
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return folder


async def _owned_file(
    session: AsyncSession,
    file_id: UUID,
    owner_id: UUID,
    include_content: bool = False,
) -> DraftFile:
    statement = select(DraftFile).where(DraftFile.id == file_id, DraftFile.owner_id == owner_id)
    if not include_content:
        statement = statement.options(load_only(
            DraftFile.id,
            DraftFile.owner_id,
            DraftFile.folder_id,
            DraftFile.title,
            DraftFile.original_filename,
            DraftFile.extension,
            DraftFile.media_type,
            DraftFile.size_bytes,
            DraftFile.sha256,
            DraftFile.created_at,
            DraftFile.updated_at,
        ))
    draft = await session.scalar(statement)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft file not found.")
    return draft


async def _ensure_unsorted(session: AsyncSession, owner_id: UUID) -> EditingFolder:
    folder = await session.scalar(
        select(EditingFolder).where(
            EditingFolder.owner_id == owner_id,
            EditingFolder.canonical_name == "unsorted",
        )
    )
    if folder:
        return folder
    folder = EditingFolder(owner_id=owner_id, name="Unsorted", canonical_name="unsorted")
    session.add(folder)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        folder = await session.scalar(
            select(EditingFolder).where(
                EditingFolder.owner_id == owner_id,
                EditingFolder.canonical_name == "unsorted",
            )
        )
        if folder is None:
            raise
    else:
        await session.refresh(folder)
    return folder


@router.get("/folders")
async def list_folders(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _ensure_unsorted(session, user.id)
    rows = await session.execute(
        select(
            EditingFolder,
            func.count(DraftFile.id).label("file_count"),
            func.coalesce(func.sum(DraftFile.size_bytes), 0).label("size_bytes"),
        )
        .outerjoin(DraftFile, DraftFile.folder_id == EditingFolder.id)
        .where(EditingFolder.owner_id == user.id)
        .group_by(EditingFolder.id)
        .order_by(EditingFolder.canonical_name)
    )
    return {
        "folders": [_folder_data(folder, count, size) for folder, count, size in rows]
    }


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Folder name cannot be blank.")
    folder = EditingFolder(owner_id=user.id, name=name, canonical_name=name.casefold())
    session.add(folder)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A folder with that name already exists.") from None
    await session.refresh(folder)
    return _folder_data(folder)


@router.patch("/folders/{folder_id}")
async def rename_folder(
    folder_id: UUID,
    payload: FolderUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    folder = await _owned_folder(session, folder_id, user.id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Folder name cannot be blank.")
    folder.name = name
    folder.canonical_name = name.casefold()
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A folder with that name already exists.") from None
    await session.refresh(folder)
    count, size = (await session.execute(
        select(func.count(DraftFile.id), func.coalesce(func.sum(DraftFile.size_bytes), 0))
        .where(DraftFile.folder_id == folder.id)
    )).one()
    return _folder_data(folder, count, size)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    folder = await _owned_folder(session, folder_id, user.id)
    file_count = await session.scalar(select(func.count(DraftFile.id)).where(DraftFile.folder_id == folder.id))
    if file_count:
        raise HTTPException(status_code=409, detail="Move or remove the files in this folder first.")
    await session.delete(folder)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/files")
async def list_draft_files(
    folder_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    statement = (
        select(DraftFile, EditingFolder.name)
        .join(EditingFolder, DraftFile.folder_id == EditingFolder.id)
        .where(DraftFile.owner_id == user.id)
        .options(load_only(
            DraftFile.id,
            DraftFile.owner_id,
            DraftFile.folder_id,
            DraftFile.title,
            DraftFile.original_filename,
            DraftFile.extension,
            DraftFile.media_type,
            DraftFile.size_bytes,
            DraftFile.sha256,
            DraftFile.created_at,
            DraftFile.updated_at,
        ))
        .order_by(DraftFile.updated_at.desc())
    )
    if folder_id:
        await _owned_folder(session, folder_id, user.id)
        statement = statement.where(DraftFile.folder_id == folder_id)
    rows = await session.execute(statement)
    return {"files": [_file_data(draft, folder_name) for draft, folder_name in rows]}


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_draft_file(
    file: UploadFile = File(...),
    folder_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    original_filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].replace("\r", "").replace("\n", "").strip()
    if not original_filename:
        raise HTTPException(status_code=400, detail="Choose a file with a valid filename.")
    if len(original_filename) > 255:
        raise HTTPException(status_code=422, detail="Filenames must be 255 characters or fewer.")
    extension = PurePosixPath(original_filename).suffix.lower()
    media_type = ALLOWED_TYPES.get(extension)
    if media_type is None:
        raise HTTPException(status_code=415, detail="Supported draft files: PDF, DOC, DOCX, ODT, RTF, TXT, and Markdown.")

    if folder_id:
        try:
            folder = await _owned_folder(session, UUID(folder_id), user.id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid folder id.") from None
    else:
        folder = await _ensure_unsorted(session, user.id)

    chunks: list[bytes] = []
    total_size = 0
    while chunk := await file.read(1024 * 1024):
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Draft files must be 25 MB or smaller.")
        chunks.append(chunk)
    if not total_size:
        raise HTTPException(status_code=400, detail="The selected file is empty.")
    contents = b"".join(chunks)
    digest = hashlib.sha256(contents).hexdigest()
    duplicate = await session.scalar(select(DraftFile).where(
        DraftFile.owner_id == user.id,
        DraftFile.sha256 == digest,
    ))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"This file is already in your library as ‘{duplicate.title}’. Rename or move that copy instead.")
    display_title = (title or "").strip() or PurePosixPath(original_filename).stem
    if len(display_title) > 200:
        raise HTTPException(status_code=422, detail="Draft title must be 200 characters or fewer.")

    draft = DraftFile(
        owner_id=user.id,
        folder_id=folder.id,
        title=display_title,
        original_filename=original_filename,
        extension=extension,
        media_type=media_type,
        size_bytes=total_size,
        sha256=digest,
        content=contents,
    )
    session.add(draft)
    await session.commit()
    logger.info("User %s uploaded draft file %s (%d bytes)", user.id, draft.id, total_size)
    return _file_data(draft, folder.name)


@router.patch("/files/{file_id}")
async def update_draft_file(
    file_id: UUID,
    payload: DraftFileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    draft = await _owned_file(session, file_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="Draft title cannot be blank.")
        draft.title = title
    if changes.get("folder_id") is not None:
        folder = await _owned_folder(session, changes["folder_id"], user.id)
        draft.folder_id = folder.id
    await session.commit()
    folder = await session.get(EditingFolder, draft.folder_id)
    return _file_data(draft, folder.name if folder else "Unknown folder")


@router.get("/files/{file_id}/content")
async def get_draft_file_content(
    file_id: UUID,
    inline: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    draft = await _owned_file(session, file_id, user.id, include_content=True)
    if inline and draft.extension not in PREVIEWABLE:
        raise HTTPException(status_code=415, detail="This file type does not support browser preview.")
    preview_type = "application/pdf" if draft.extension == ".pdf" else "text/plain; charset=utf-8"
    disposition = "inline" if inline else "attachment"
    filename = quote(draft.original_filename, safe="")
    return Response(
        content=draft.content,
        media_type=preview_type if inline else draft.media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    draft = await _owned_file(session, file_id, user.id)
    await session.delete(draft)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
