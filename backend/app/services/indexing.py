import asyncio
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select, update
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import async_session
from app.logging_config import fields, get_logger
from app.models.story_models import Chapter, SceneEmbedding, Story, StoryChunk
from app.models.wiki_models import ChapterMeta, SceneMeta
from app.services import jobs
from app.services.ai_service import AIProviderHTTPError, embed_texts
from app.services.ai_usage import check_budget
from app.services.chunking import chunk_chapter
from app.services.entities import alias_map, extract_mentions, find_mentions
from app.services.extraction import extract_chapter

logger = get_logger("index")
SCENE_HEADING = re.compile(r"^(?:#{1,3}\s+\S.*|(?:INT\.|EXT\.|INT/EXT\.).+|\*\s*\*\s*\*\s*)$", re.IGNORECASE)
_BIBLE_MAX_ATTEMPTS = 2

# Job outcomes. "superseded" means the chapter changed while the worker was
# busy, so the worker requeues the same logical job for the newer revision.
DONE = "done"
SUPERSEDED = "superseded"
SKIPPED = "skipped"


async def enqueue_reindex(session, chapter_id: UUID, owner_id: UUID | None = None) -> None:
    """Debounced reindex request; repeated calls collapse onto one queued job."""
    await jobs.enqueue(
        session,
        "reindex_chapter",
        {"chapter_id": str(chapter_id)},
        owner_id=owner_id,
        dedupe_key=f"chapter:{chapter_id}",
        delay_seconds=2.5,
        max_attempts=3,
    )


async def enqueue_bible_scan(
    session,
    chapter_id: UUID,
    *,
    owner_id: UUID | None = None,
    revision: int | None = None,
) -> None:
    await jobs.enqueue(
        session,
        "bible_scan",
        {"chapter_id": str(chapter_id), "revision": revision},
        owner_id=owner_id,
        dedupe_key=f"bible:{chapter_id}",
        max_attempts=3,
    )


async def reconcile_indexing_state() -> dict:
    """Repair chapters left mid-index by a crash or restart.

    ``indexing`` is a transient state owned by the process that set it. If the
    process dies, nothing will ever finish those chapters and the UI waits
    forever. Reset them to ``pending`` and queue everything that is waiting.
    """
    async with async_session() as session:
        stuck = list(
            await session.scalars(
                select(Chapter.id).where(Chapter.index_status == "indexing")
            )
        )
        if stuck:
            await session.execute(
                update(Chapter)
                .where(Chapter.id.in_(stuck))
                .values(index_status="pending", index_error=None)
            )
            await session.commit()
        pending = list(
            await session.scalars(select(Chapter.id).where(Chapter.index_status == "pending"))
        )
    async with async_session() as session:
        for chapter_id in stuck + pending:
            await enqueue_reindex(session, chapter_id)
    summary = {"reset": len(stuck), "queued": len(pending)}
    logger.info("[index] reconcile %s", fields(**summary))
    return summary


async def reindex_stale_embedding_models() -> None:
    """Queue chapters whose stored vectors were built with another model."""
    async with async_session() as session:
        stale_ids = list(await session.scalars(
            select(Chapter.id).where(Chapter.indexed_embedding_model != settings.EMBEDDING_MODEL)
        ))
        if stale_ids:
            await session.execute(
                update(Chapter)
                .where(Chapter.id.in_(stale_ids))
                .values(index_status="pending", index_error=None)
            )
            await session.commit()
    logger.info(
        "[index] stale  %s",
        fields(model=settings.EMBEDDING_MODEL, queued=len(stale_ids)),
    )
    async with async_session() as session:
        for chapter_id in stale_ids:
            await enqueue_reindex(session, chapter_id)


@dataclass
class SceneText:
    text: str
    start_line: int
    end_line: int


def split_into_scenes(content: str, max_characters: int = 2800) -> list[SceneText]:
    lines = content.splitlines()
    scenes: list[SceneText] = []
    current: list[tuple[int, str]] = []

    def flush() -> None:
        if not current:
            return
        text = "\n".join(value for _, value in current).strip()
        if text:
            scenes.append(SceneText(text, current[0][0], current[-1][0]))
        current.clear()

    for line_number, line in enumerate(lines, start=1):
        if SCENE_HEADING.match(line.strip()):
            flush()
        if not line.strip():
            if current and len("\n".join(value for _, value in current)) > max_characters // 2:
                flush()
            elif current:
                current.append((line_number, line))
            continue
        current.append((line_number, line))
        if len("\n".join(value for _, value in current)) >= max_characters:
            flush()
    flush()
    return scenes


async def _suggest_story_bible(
    story_id: UUID,
    chapter_id: UUID,
    owner_id: UUID,
    chapter_title: str,
    content: str,
) -> str:
    started = time.monotonic()
    chapter_ref = str(chapter_id)[:8]
    async with async_session() as consent_session:
        existing = await consent_session.execute(
            select(
                Chapter.content,
                Chapter.title,
                Chapter.revision,
                Chapter.bible_scan_revision,
                Story.owner_id,
            )
            .join(Story, Story.id == Chapter.story_id)
            .where(Chapter.id == chapter_id, Story.id == story_id)
        )
        row = existing.one_or_none()
    if row is None or row.owner_id != owner_id:
        logger.info("[bible] skip   %s", fields(chapter=chapter_ref, reason="missing_or_unowned"))
        return SKIPPED
    if row.content != content or row.title != chapter_title:
        logger.info("[bible] skip   %s", fields(chapter=chapter_ref, reason="edited_during_scan"))
        return SUPERSEDED
    if row.bible_scan_revision == row.revision:
        logger.info("[bible] skip   %s", fields(chapter=chapter_ref, revision=row.revision, reason="already_scanned"))
        return DONE
    logger.info(
        "[bible] extract %s",
        fields(
            chapter=chapter_ref,
            revision=row.revision,
            title=chapter_title[:48],
            chars=len(content),
        ),
    )
    async with async_session() as session:
        current_chapter = await session.scalar(
            select(Chapter).where(Chapter.id == chapter_id).with_for_update()
        )
        if current_chapter is None or current_chapter.content != content or current_chapter.title != chapter_title:
            return SUPERSEDED
        if current_chapter.bible_scan_revision == current_chapter.revision:
            return DONE
        story = await session.get(Story, story_id)
        if story is not None:
            await check_budget(
                session,
                story,
                owner_id,
                chars=len(current_chapter.content),
                purpose="Bible extraction",
            )
        stats = await extract_chapter(session, current_chapter, owner_id)
        current_chapter.bible_scan_revision = current_chapter.revision
        current_chapter.bible_scan_error = None
        await session.commit()
        logger.info(
            "[bible] done   %s",
            fields(
                chapter=chapter_ref,
                revision=current_chapter.revision,
                scenes=stats.scenes_total,
                skipped=stats.scenes_skipped,
                calls=stats.model_calls,
                facts=stats.facts,
                entities=stats.entities,
                rejected=stats.rejected,
                elapsed=f"{time.monotonic() - started:.2f}s",
            ),
        )
        return DONE


async def _job_progress(job_id: UUID | None, progress: dict) -> None:
    if job_id is None:
        return
    async with async_session() as session:
        await jobs.set_progress(session, job_id, progress)
        await session.commit()


async def reindex_chapter(chapter_id: UUID, job_id: UUID | None = None) -> str:
    revision: int | None = None
    started = time.monotonic()
    try:
        async with async_session() as session:
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None:
                return SKIPPED
            revision = chapter.revision
            story_id = chapter.story_id
            content = chapter.content
            can_reuse_vectors = chapter.indexed_embedding_model == settings.EMBEDDING_MODEL
            chapter.index_status = "indexing"
            chapter.index_error = None
            await session.commit()

        chunks = chunk_chapter(content)
        await _job_progress(job_id, {"stage": "chunking", "chunks": len(chunks)})
        async with async_session() as session:
            previous = (
                list(
                    await session.scalars(
                        select(StoryChunk).where(StoryChunk.chapter_id == chapter_id)
                    )
                )
                if can_reuse_vectors
                else []
            )
        reusable: dict[str, deque[list[float]]] = defaultdict(deque)
        for item in previous:
            reusable[item.content_hash].append(item.embedding)
        vectors: dict[str, list[float]] = {}
        for chunk in chunks:
            if reusable[chunk.content_hash]:
                vectors[chunk.content_hash] = reusable[chunk.content_hash].popleft()
        missing = {
            chunk.content_hash: chunk.text
            for chunk in chunks
            if chunk.content_hash not in vectors
        }
        embedded = await run_in_threadpool(embed_texts, list(missing.values()))
        for content_digest, vector in zip(missing, embedded, strict=True):
            vectors[content_digest] = vector
        await _job_progress(
            job_id,
            {
                "stage": "embedding",
                "chunks": len(chunks),
                "embedded": len(missing),
                "reused": len(chunks) - len(missing),
            },
        )

        async with async_session() as session:
            current = await session.scalar(
                select(Chapter).where(Chapter.id == chapter_id).with_for_update()
            )
            if current is None or current.revision != revision:
                logger.debug(
                    "[index] dropped %s",
                    fields(chapter=str(chapter_id)[:8], expected=revision, actual=current.revision if current else "deleted"),
                )
                # A newer revision is queued; stay pending so the UI keeps saying
                # "Updating memory" and the requeued job picks up the new text.
                if current is not None:
                    current.index_status = "pending"
                    await session.commit()
                return SUPERSEDED

            chapter_meta = await session.get(ChapterMeta, chapter_id)
            scene_meta = {
                row.scene_index: row
                for row in await session.scalars(
                    select(SceneMeta).where(SceneMeta.chapter_id == chapter_id)
                )
            }
            display = await alias_map(session, story_id)
            await session.execute(delete(StoryChunk).where(StoryChunk.chapter_id == chapter_id))
            # Keep the legacy table in step until Phase 6 retires it; continuity
            # still reads SceneEmbedding and should see the same passages.
            await session.execute(delete(SceneEmbedding).where(SceneEmbedding.chapter_id == chapter_id))
            for chunk in chunks:
                mentioned = list(
                    dict.fromkeys(
                        entity_id
                        for entity_id, _start, _end, _quote in find_mentions(
                            chunk.text.splitlines(), display
                        )
                    )
                )
                scene = scene_meta.get(chunk.scene_index)
                pov_entity_id = (
                    (scene.pov_entity_id if scene else None)
                    or (chapter_meta.pov_entity_id if chapter_meta else None)
                )
                location_entity_id = (
                    (scene.location_entity_id if scene else None)
                    or (chapter_meta.location_entity_id if chapter_meta else None)
                )
                session.add(
                    StoryChunk(
                        story_id=story_id,
                        chapter_id=chapter_id,
                        chapter_number=current.chapter_number,
                        scene_index=chunk.scene_index,
                        chunk_index=chunk.chunk_index,
                        chunk_kind="scene",
                        text=chunk.text,
                        token_count=chunk.token_count,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        entities=mentioned,
                        pov_entity_id=pov_entity_id,
                        location_entity_id=location_entity_id,
                        content_hash=chunk.content_hash,
                        embedding=vectors[chunk.content_hash],
                        embedding_model=settings.EMBEDDING_MODEL,
                    )
                )
                session.add(
                    SceneEmbedding(
                        story_id=story_id,
                        chapter_id=chapter_id,
                        chapter_number=current.chapter_number,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        chunk_metadata={},
                        embedding=vectors[chunk.content_hash],
                    )
                )
            # New chapters now record mentions on save, not only in the backfill.
            await extract_mentions(session, story_id, chapter_id, content)
            current.index_status = "indexed"
            current.index_error = None
            current.indexed_embedding_model = settings.EMBEDDING_MODEL
            await session.commit()
            logger.info(
                "[index] done   %s",
                fields(
                    chapter=str(chapter_id)[:8],
                    revision=revision,
                    chunks=len(chunks),
                    reused=len(chunks) - len(missing),
                    embedded=len(missing),
                    elapsed=f"{time.monotonic() - started:.2f}s",
                ),
            )
        return DONE
    except Exception as exc:
        logger.exception("[index] failed %s", fields(chapter=str(chapter_id)[:8], revision=revision, error=type(exc).__name__))
        if revision is not None:
            try:
                async with async_session() as session:
                    current = await session.get(Chapter, chapter_id)
                    if current is not None and current.revision == revision:
                        current.index_status = "failed"
                        current.index_error = str(exc)[:1000]
                        await session.commit()
            except Exception:
                logger.exception("Could not persist the indexing error for chapter %s", chapter_id)
        # Let the worker retry with backoff; the chapter row already explains the
        # failure if every attempt is exhausted.
        raise


def _retryable_provider_error(exc: AIProviderHTTPError) -> bool:
    if exc.status_code in {429, 502, 503}:
        return True
    # Groq (and some other hosts) answer 400 when a model emits a malformed
    # tool call; the same prompt usually succeeds on the next attempt.
    return (exc.code or "").casefold() == "tool_use_failed"


async def extract_story_bible(
    chapter_id: UUID,
    expected_revision: int | None = None,
) -> str:
    """Extract Story Bible suggestions for one chapter.

    The job dedupe key keeps two workers off the same chapter, so no in-process
    lock is needed here.
    """
    revision: int | None = None
    try:
        async with async_session() as session:
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None or not chapter.content.strip():
                logger.info("[bible] skip   %s", fields(chapter=str(chapter_id)[:8], reason="empty_or_missing"))
                return SKIPPED
            if expected_revision is not None and chapter.revision != expected_revision:
                logger.info(
                    "[bible] skip   %s",
                    fields(chapter=str(chapter_id)[:8], reason="revision_moved", expected=expected_revision, actual=chapter.revision),
                )
                return SUPERSEDED
            if chapter.bible_scan_revision == chapter.revision:
                logger.info(
                    "[bible] skip   %s",
                    fields(chapter=str(chapter_id)[:8], revision=chapter.revision, reason="already_scanned"),
                )
                return DONE
            revision = chapter.revision
            story_id = chapter.story_id
            title = chapter.title
            content = chapter.content
            owner_id = await session.scalar(select(Story.owner_id).where(Story.id == story_id))
        if owner_id is None:
            return SKIPPED
        for attempt in range(1, _BIBLE_MAX_ATTEMPTS + 1):
            try:
                return await _suggest_story_bible(story_id, chapter_id, owner_id, title, content)
            except AIProviderHTTPError as exc:
                    if attempt >= _BIBLE_MAX_ATTEMPTS or not _retryable_provider_error(exc):
                        raise
                    if (exc.code or "").casefold() == "tool_use_failed":
                        delay = 1
                    else:
                        delay = max(5, min(exc.retry_after_seconds or 15, 60))
                    logger.info(
                        "[bible] retry   %s",
                        fields(
                            chapter=str(chapter_id)[:8],
                            revision=revision,
                            attempt=attempt,
                            delay=f"{delay}s",
                            status=exc.status_code,
                            code=exc.code,
                        ),
                    )
                    await asyncio.sleep(delay)
        return SKIPPED
    except Exception as exc:
        if isinstance(exc, AIProviderHTTPError):
            logger.warning(
                "[bible] failed %s",
                fields(chapter=str(chapter_id)[:8], revision=revision, status=exc.status_code, message=str(exc)),
            )
        else:
            logger.exception("[bible] failed %s", fields(chapter=str(chapter_id)[:8], revision=revision))
        try:
            async with async_session() as session:
                chapter = await session.scalar(
                    select(Chapter).where(Chapter.id == chapter_id).with_for_update()
                )
                if chapter is not None and chapter.revision == revision:
                    chapter.bible_scan_error = str(exc)[:1000]
                    await session.commit()
        except Exception:
            logger.exception("Could not persist the Story Bible scan error for chapter %s", chapter_id)
        # Retry through the queue; the chapter row explains a permanent failure.
        raise
