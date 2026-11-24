"""Chapter snapshot policy, retention, and diffs.

A snapshot pins the text of a chapter *before* it changes. The old rule took one
every five minutes when the revision had no snapshot yet, which could swallow a
lot of intermediate work. This module implements the Phase 1 policy:

* always snapshot on an explicit checkpoint or a restore,
* otherwise snapshot after 60 seconds of editing, or a 500-word change,
* never store the same content twice,
* prune history with a tiered retention window.
"""

from __future__ import annotations

import difflib
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, ChapterRevision

EDIT_WINDOW_SECONDS = 60
WORD_DELTA_THRESHOLD = 500

AUTOSAVE_KEEP_ALL = timedelta(hours=48)
HOURLY_KEEP_FOR = timedelta(days=7)
DAILY_KEEP_FOR = timedelta(days=90)

SNAPSHOT_KINDS = {"autosave", "checkpoint", "restore"}
ALWAYS_KEEP_KINDS = {"checkpoint", "restore"}


def content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Treat naive timestamps from PostgreSQL as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def latest_snapshot(session: AsyncSession, chapter_id) -> ChapterRevision | None:
    return await session.scalar(
        select(ChapterRevision)
        .where(ChapterRevision.chapter_id == chapter_id)
        .order_by(ChapterRevision.created_at.desc())
        .limit(1)
    )


async def snapshot_exists_for_revision(
    session: AsyncSession, chapter_id, revision_number: int
) -> bool:
    return (
        await session.scalar(
            select(ChapterRevision.id).where(
                ChapterRevision.chapter_id == chapter_id,
                ChapterRevision.revision_number == revision_number,
            )
        )
    ) is not None


async def should_snapshot(
    session: AsyncSession,
    chapter: Chapter,
    *,
    kind: str,
    new_content: str,
) -> bool:
    if kind not in SNAPSHOT_KINDS:
        raise ValueError(f"Unknown snapshot kind: {kind}")
    if kind in ALWAYS_KEEP_KINDS:
        return True

    latest = await latest_snapshot(session, chapter.id)
    if latest is None:
        return True
    if latest.content_hash == content_hash(new_content):
        return False
    if abs(chapter.word_count - latest.word_count) >= WORD_DELTA_THRESHOLD:
        return True
    return _now() - _aware(latest.created_at) >= EDIT_WINDOW_SECONDS * timedelta(seconds=1)


async def record_snapshot(
    session: AsyncSession,
    chapter: Chapter,
    *,
    kind: str = "autosave",
    content: str | None = None,
    title: str | None = None,
    word_count: int | None = None,
) -> ChapterRevision | None:
    """Store the chapter's current state as a revision.

    Called before the chapter row is mutated, or by an explicit checkpoint. The
    snapshot is de-duplicated by revision number so a revision is never stored
    twice.
    """
    snapshot_content = chapter.content if content is None else content
    snapshot_title = chapter.title if title is None else title
    snapshot_words = chapter.word_count if word_count is None else word_count

    if await snapshot_exists_for_revision(session, chapter.id, chapter.revision):
        return None
    if await should_snapshot(
        session, chapter, kind=kind, new_content=snapshot_content
    ) is False:
        return None

    revision = ChapterRevision(
        chapter_id=chapter.id,
        revision_number=chapter.revision,
        title=snapshot_title,
        content=snapshot_content,
        word_count=snapshot_words,
        kind=kind,
        content_hash=content_hash(snapshot_content),
        char_count=len(snapshot_content),
    )
    session.add(revision)
    await session.flush()
    await apply_retention(session, chapter.id)
    return revision


async def apply_retention(session: AsyncSession, chapter_id) -> int:
    """Delete history outside the retention window.

    * keep everything younger than 48 hours,
    * keep one snapshot per hour up to 7 days,
    * keep one snapshot per day up to 90 days,
    * keep checkpoints and restores forever.
    """
    now = _now()
    revisions = list(
        await session.scalars(
            select(ChapterRevision)
            .where(ChapterRevision.chapter_id == chapter_id)
            .order_by(ChapterRevision.created_at.desc())
        )
    )
    keep: set = set()
    seen_hours: set[tuple[int, int, int]] = set()
    seen_days: set[tuple[int, int, int]] = set()

    for revision in revisions:
        if revision.kind in ALWAYS_KEEP_KINDS:
            keep.add(revision.id)
            continue
        created = _aware(revision.created_at)
        age = now - created
        if age <= AUTOSAVE_KEEP_ALL:
            keep.add(revision.id)
            continue
        if age <= HOURLY_KEEP_FOR:
            bucket = (created.year, created.month, created.day * 24 + created.hour)
            if bucket not in seen_hours:
                seen_hours.add(bucket)
                keep.add(revision.id)
            continue
        if age <= DAILY_KEEP_FOR:
            bucket = (created.year, created.month, created.day)
            if bucket not in seen_days:
                seen_days.add(bucket)
                keep.add(revision.id)
            continue
        # Older than the daily window: only the checkpoints above survive.

    drop_ids = [revision.id for revision in revisions if revision.id not in keep]
    if drop_ids:
        await session.execute(delete(ChapterRevision).where(ChapterRevision.id.in_(drop_ids)))
    return len(drop_ids)


def diff_revisions(
    older: ChapterRevision, newer: ChapterRevision
) -> list[dict]:
    """Return unified-diff hunks with 1-based line numbers.

    Only hunks are returned, never the full chapter twice.
    """
    old_lines = older.content.splitlines()
    new_lines = newer.content.splitlines()
    hunks: list[dict] = []

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    for group in matcher.get_grouped_opcodes(3):
        lines = list(difflib.unified_diff(
            old_lines[group[0][1]:group[-1][2]],
            new_lines[group[0][3]:group[-1][4]],
            lineterm="",
            n=3,
        ))
        # unified_diff repeats the header for this slice only; strip it.
        lines = [line for line in lines if not line.startswith(("---", "+++"))]
        hunks.append(
            {
                "old_start": group[0][1] + 1,
                "old_lines": group[-1][2] - group[0][1],
                "new_start": group[0][3] + 1,
                "new_lines": group[-1][4] - group[0][3],
                "lines": lines,
            }
        )
    return hunks


async def record_checkpoint(session: AsyncSession, chapter: Chapter) -> ChapterRevision:
    """Pin the current revision as a checkpoint.

    A checkpoint is never pruned. If an autosave already covers this revision,
    it is upgraded in place so the checkpoint does not duplicate storage.
    """
    existing = await session.scalar(
        select(ChapterRevision).where(
            ChapterRevision.chapter_id == chapter.id,
            ChapterRevision.revision_number == chapter.revision,
        )
    )
    if existing is not None:
        existing.kind = "checkpoint"
        existing.title = chapter.title
        existing.content = chapter.content
        existing.word_count = chapter.word_count
        existing.content_hash = content_hash(chapter.content)
        existing.char_count = len(chapter.content)
        existing.created_at = _now()
        await session.flush()
        return existing

    revision = ChapterRevision(
        chapter_id=chapter.id,
        revision_number=chapter.revision,
        title=chapter.title,
        content=chapter.content,
        word_count=chapter.word_count,
        kind="checkpoint",
        content_hash=content_hash(chapter.content),
        char_count=len(chapter.content),
    )
    session.add(revision)
    await session.flush()
    return revision
