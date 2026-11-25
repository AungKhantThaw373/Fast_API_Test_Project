"""Story-wide search: the same hybrid path the evaluator uses."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.story_models import Chapter
from app.models.wiki_models import Entity
from app.schemas.search import SearchEntityOut, SearchHitOut, SearchOut
from app.security import get_current_user
from app.services import stories as stories_service
from app.services.retrieval import SearchFilters, search_chunks

router = APIRouter(prefix="/stories", tags=["search"])


@router.get("/{story_id}/search", response_model=SearchOut)
async def search_story(
    story_id: UUID,
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=20, ge=1, le=50),
    chapter_min: int | None = Query(default=None, ge=1),
    chapter_max: int | None = Query(default=None, ge=1),
    entity_id: UUID | None = Query(default=None),
    arc_id: UUID | None = Query(default=None),
    chunk_kind: str | None = Query(default=None, pattern="^(scene|summary|note)$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> SearchOut:
    await stories_service.owned_story(session, story_id, user.id)
    result = await search_chunks(
        session,
        story_id,
        q,
        limit=limit,
        filters=SearchFilters(
            chapter_min=chapter_min,
            chapter_max=chapter_max,
            entity_id=entity_id,
            arc_id=arc_id,
            chunk_kind=chunk_kind,
        ),
    )
    chapter_ids = {hit.chapter_id for hit in result.chunks}
    titles: dict[UUID, str] = {}
    if chapter_ids:
        titles = {
            chapter_id: title
            for chapter_id, title in (
                await session.execute(
                    select(Chapter.id, Chapter.title).where(Chapter.id.in_(chapter_ids))
                )
            ).all()
        }
    entity_ids = {entity_id for hit in result.chunks for entity_id in hit.entity_ids}
    entities: dict[UUID, Entity] = {}
    if entity_ids:
        entities = {
            entity.id: entity
            for entity in await session.scalars(select(Entity).where(Entity.id.in_(entity_ids)))
        }
    return SearchOut(
        query=q.strip(),
        semantic_query=result.semantic_query,
        lexical_query=result.lexical_query,
        name_query=result.name_query,
        entity_ids=result.entity_ids,
        cache_hit=result.cache_hit,
        timings_ms=result.timings_ms,
        results=[
            SearchHitOut(
                chunk_id=hit.chunk_id,
                chapter_id=hit.chapter_id,
                chapter_number=hit.chapter_number,
                chapter_title=titles.get(hit.chapter_id, f"Chapter {hit.chapter_number}"),
                scene_index=hit.scene_index,
                chunk_index=hit.chunk_index,
                start_line=hit.start_line,
                end_line=hit.end_line,
                quote=hit.text,
                score=hit.score,
                scores=hit.scores,
                entities=[
                    SearchEntityOut(
                        id=entity.id, name=entity.name, entity_type=entity.entity_type
                    )
                    for entity_id in hit.entity_ids
                    if (entity := entities.get(entity_id)) is not None
                ],
            )
            for hit in result.chunks
        ],
    )
