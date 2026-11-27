"""Portable export of everything an account owns: JSON, Markdown, and drafts."""

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_models import User, UserAISettings
from app.models.editing_models import DraftFile, EditingFolder
from app.models.story_models import Story
from app.services.backup import build_backup


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", PurePosixPath(value).name).strip(" .")
    return cleaned[:120] or fallback


def _story_markdown(backup) -> str:
    story = backup.story
    lines = [f"# {story.title}", ""]
    if story.collection_name:
        lines.extend([f"*{story.collection_name}*", ""])
    for chapter in sorted(backup.chapters, key=lambda item: item.chapter_number):
        lines.extend([f"## Chapter {chapter.chapter_number}: {chapter.title}", ""])
        lines.extend([chapter.content.rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


async def build_account_export(session: AsyncSession, user: User) -> tuple[bytes, str]:
    stories = list(await session.scalars(
        select(Story).where(Story.owner_id == user.id).order_by(Story.created_at)
    ))
    backups = [await build_backup(session, story) for story in stories]
    folders = list(await session.scalars(
        select(EditingFolder).where(EditingFolder.owner_id == user.id).order_by(EditingFolder.name)
    ))
    drafts = list(await session.scalars(
        select(DraftFile).where(DraftFile.owner_id == user.id).order_by(DraftFile.created_at)
    ))
    ai = await session.get(UserAISettings, user.id)

    archive = io.BytesIO()
    draft_manifest = []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for index, backup in enumerate(backups, start=1):
            safe = _safe_name(backup.story.title, f"story-{index}")
            bundle.writestr(f"stories/{index:02d}-{safe}.md", _story_markdown(backup))
        for draft in drafts:
            safe = _safe_name(draft.original_filename, f"draft-{draft.id}")
            path = f"drafts/{draft.id}-{safe}"
            bundle.writestr(path, draft.content)
            draft_manifest.append({
                "id": str(draft.id),
                "folder_id": str(draft.folder_id),
                "title": draft.title,
                "original_filename": draft.original_filename,
                "media_type": draft.media_type,
                "size_bytes": draft.size_bytes,
                "sha256": draft.sha256,
                "path": path,
            })

        manifest = {
            "format_version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat(),
            },
            "stories": [item.model_dump(mode="json") for item in backups],
            "draft_folders": [
                {"id": str(folder.id), "name": folder.name, "created_at": folder.created_at.isoformat()}
                for folder in folders
            ],
            "draft_files": draft_manifest,
            "ai_settings": None if ai is None else {
                "provider": ai.provider,
                "model": ai.model,
                "base_url": ai.base_url,
                # Never export the stored secret itself.
                "api_key_configured": bool(ai.api_key_encrypted),
            },
        }
        bundle.writestr("stillroom-export.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        bundle.writestr("README.txt", (
            "This archive contains every story, chapter, wiki record, draft file, and "
            "account preference Stillroom holds for you. stillroom-export.json is the "
            "portable data file; the Markdown files are reading copies. API keys are "
            "never included.\n"
        ))
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return archive.getvalue(), f"stillroom-export-{stamp}.zip"