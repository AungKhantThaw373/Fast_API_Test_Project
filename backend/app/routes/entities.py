"""Wiki endpoints: entities, aliases, merge, appearances, search, facts, relations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.wiki_models import Entity, EntityFact
from app.schemas.wiki import (
    AliasCreate,
    AliasOut,
    AppearanceListOut,
    AppearanceOut,
    EntityCreate,
    EntityListOut,
    EntityOut,
    EntitySearchOut,
    EntityUpdate,
    FactCreate,
    FactListOut,
    FactOut,
    FactUpdate,
    MergeRequest,
    MergeResultOut,
    RelationshipCreate,
    RelationshipListOut,
    RelationshipOut,
    RelationshipUpdate,
    UnmergeOut,
)
from app.security import get_current_user
from app.services import entities as entity_service
from app.services import facts as fact_service
from app.services import stories as stories_service
from app.services.audit import record_audit

router = APIRouter(tags=["entities"])


async def _owned_entity(
    session: AsyncSession, entity_id: UUID, user: User
) -> Entity:
    entity = await entity_service.get_entity(session, entity_id)
    await stories_service.owned_story(session, entity.story_id, user.id)
    if entity.status == "merged" or entity.merged_into_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This entity was merged; use its target instead.",
        )
    return entity


async def _out(session: AsyncSession, entities: list[Entity]) -> list[EntityOut]:
    aliases = await entity_service.aliases_for(session, [entity.id for entity in entities])
    return [
        EntityOut.model_validate(entity).model_copy(
            update={"aliases": [AliasOut.model_validate(a) for a in aliases.get(entity.id, [])]}
        )
        for entity in entities
    ]


@router.get("/stories/{story_id}/entities", response_model=EntityListOut)
async def list_entities(
    story_id: UUID,
    entity_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    arc_id: UUID | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntityListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows, next_cursor = await entity_service.list_entities(
        session,
        story_id,
        entity_type=entity_type,
        status=status_filter,
        query=q,
        arc_id=arc_id,
        limit=limit,
        cursor=cursor,
    )
    return EntityListOut(entities=await _out(session, rows), next_cursor=next_cursor)


@router.post(
    "/stories/{story_id}/entities",
    status_code=status.HTTP_201_CREATED,
    response_model=EntityOut,
)
async def create_entity(
    story_id: UUID,
    payload: EntityCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntityOut:
    await stories_service.owned_story(session, story_id, user.id)
    candidates = await entity_service.find_candidates(session, story_id, payload.name)
    exact = [c for c in candidates if c.score == 1.0]
    if exact:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "An entity with that name or alias already exists.",
                "entity_id": str(exact[0].entity.id),
            },
        )
    entity = await entity_service.create_entity(
        session,
        story_id=story_id,
        entity_type=payload.entity_type,
        name=payload.name,
        summary=payload.summary,
        aliases=[(alias.alias, alias.alias_type) for alias in payload.aliases],
    )
    await session.commit()
    await session.refresh(entity)
    return (await _out(session, [entity]))[0]


@router.get("/entities/search", response_model=EntitySearchOut)
async def search_entities(
    story_id: UUID = Query(...),
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntitySearchOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await entity_service.search_entities(session, story_id, q, limit=limit)
    return EntitySearchOut(entities=await _out(session, rows), next_cursor=None)


@router.get("/entities/{entity_id}", response_model=EntityOut)
async def get_entity(
    entity_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntityOut:
    entity = await _owned_entity(session, entity_id, user)
    return (await _out(session, [entity]))[0]


@router.put("/entities/{entity_id}", response_model=EntityOut)
async def update_entity(
    entity_id: UUID,
    payload: EntityUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntityOut:
    entity = await _owned_entity(session, entity_id, user)
    await entity_service.update_entity(
        session,
        entity,
        name=payload.name,
        entity_type=payload.entity_type,
        summary=payload.summary,
    )
    await session.commit()
    await session.refresh(entity)
    return (await _out(session, [entity]))[0]


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_entity(
    entity_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    entity = await _owned_entity(session, entity_id, user)
    await entity_service.archive_entity(session, entity)
    await session.commit()


@router.post(
    "/entities/{entity_id}/aliases",
    status_code=status.HTTP_201_CREATED,
    response_model=AliasOut,
)
async def add_alias(
    entity_id: UUID,
    payload: AliasCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AliasOut:
    entity = await _owned_entity(session, entity_id, user)
    added = await entity_service.add_alias(session, entity, payload.alias, payload.alias_type)
    if not added:
        raise HTTPException(status_code=409, detail="That alias already exists.")
    await session.commit()
    aliases = await entity_service.aliases_for(session, [entity.id])
    match = next(
        (
            alias
            for alias in aliases.get(entity.id, [])
            if alias.alias == payload.alias.strip()
        ),
        None,
    )
    if match is None:
        raise HTTPException(status_code=500, detail="Alias was not stored.")
    return AliasOut.model_validate(match)


@router.delete(
    "/entities/{entity_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_alias(
    entity_id: UUID,
    alias_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await _owned_entity(session, entity_id, user)
    if not await entity_service.delete_alias(session, entity_id, alias_id):
        raise HTTPException(status_code=404, detail="Alias not found.")
    await session.commit()


@router.post("/entities/{entity_id}/merge", response_model=MergeResultOut)
async def merge_entity(
    entity_id: UUID,
    payload: MergeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> MergeResultOut:
    entity = await _owned_entity(session, entity_id, user)
    result = await entity_service.merge_entities(
        session,
        story_id=entity.story_id,
        source_id=entity_id,
        target_id=payload.target_id,
        dry_run=payload.dry_run,
    )
    if payload.dry_run:
        await session.rollback()
    else:
        record_audit(
            session,
            "entity_merged",
            user_id=user.id,
            email=user.email,
            target_type="entity",
            target_id=str(entity_id),
            detail={"target_id": str(payload.target_id), "moved": result},
            request=request,
        )
        await session.commit()
    return MergeResultOut(
        source_id=entity_id,
        target_id=payload.target_id,
        dry_run=payload.dry_run,
        moved=result,
    )


@router.post("/entities/{entity_id}/unmerge", response_model=UnmergeOut)
async def undo_merge(
    entity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnmergeOut:
    entity = await entity_service.get_entity(session, entity_id)
    await stories_service.owned_story(session, entity.story_id, user.id)
    merge = await entity_service.undo_merge(
        session, story_id=entity.story_id, source_id=entity_id
    )
    # Build the response before committing: ``commit`` expires every attribute.
    result = UnmergeOut(
        source_id=merge.source_id,
        target_id=merge.target_id,
        merge_id=merge.id,
        reverted_at=merge.reverted_at,
    )
    record_audit(
        session,
        "entity_unmerged",
        user_id=user.id,
        email=user.email,
        target_type="entity",
        target_id=str(entity_id),
        detail={"merge_id": str(merge.id)},
        request=request,
    )
    await session.commit()
    return result


@router.get("/entities/{entity_id}/appearances", response_model=AppearanceListOut)
async def list_appearances(
    entity_id: UUID,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AppearanceListOut:
    entity = await _owned_entity(session, entity_id, user)
    rows, next_cursor = await entity_service.appearances(
        session, entity.story_id, entity_id, limit=limit, cursor=cursor
    )
    return AppearanceListOut(
        appearances=[
            AppearanceOut(
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title or f"Chapter {chapter.chapter_number}",
                line_start=mention.line_start,
                line_end=mention.line_end,
                quote=mention.quote,
            )
            for mention, chapter in rows
        ],
        next_cursor=next_cursor,
    )


@router.get("/entities/{entity_id}/facts", response_model=FactListOut)
async def list_facts(
    entity_id: UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    predicate: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FactListOut:
    await _owned_entity(session, entity_id, user)
    rows = await fact_service.list_facts(
        session, entity_id, status=status_filter, predicate=predicate
    )
    return FactListOut(facts=[FactOut.model_validate(fact) for fact in rows])


@router.post(
    "/entities/{entity_id}/facts",
    status_code=status.HTTP_201_CREATED,
    response_model=FactOut,
)
async def create_fact(
    entity_id: UUID,
    payload: FactCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FactOut:
    entity = await _owned_entity(session, entity_id, user)
    fact = await fact_service.create_fact(session, entity, payload)
    await session.commit()
    await session.refresh(fact)
    return FactOut.model_validate(fact)


@router.put("/facts/{fact_id}", response_model=FactOut)
async def update_fact(
    fact_id: UUID,
    payload: FactUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FactOut:
    fact = await fact_service.get_fact(session, fact_id)
    await _owned_entity(session, fact.entity_id, user)
    await fact_service.update_fact(session, fact, payload)
    await session.commit()
    await session.refresh(fact)
    return FactOut.model_validate(fact)


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(
    fact_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    fact = await fact_service.get_fact(session, fact_id)
    await _owned_entity(session, fact.entity_id, user)
    await fact_service.delete_fact(session, fact)
    await session.commit()


async def _decide(
    session: AsyncSession, fact: EntityFact, *, accept: bool
) -> EntityFact:
    fact = await (fact_service.accept_fact(session, fact) if accept else fact_service.reject_fact(session, fact))
    await session.commit()
    await session.refresh(fact)
    return fact


@router.post("/facts/{fact_id}/accept", response_model=FactOut)
async def accept_fact(
    fact_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FactOut:
    fact = await fact_service.get_fact(session, fact_id)
    await _owned_entity(session, fact.entity_id, user)
    return FactOut.model_validate(await _decide(session, fact, accept=True))


@router.post("/facts/{fact_id}/reject", response_model=FactOut)
async def reject_fact(
    fact_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FactOut:
    fact = await fact_service.get_fact(session, fact_id)
    await _owned_entity(session, fact.entity_id, user)
    return FactOut.model_validate(await _decide(session, fact, accept=False))


@router.get("/entities/{entity_id}/relationships", response_model=RelationshipListOut)
async def list_relationships(
    entity_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RelationshipListOut:
    await _owned_entity(session, entity_id, user)
    outgoing, incoming = await fact_service.list_relationships(session, entity_id)
    return RelationshipListOut(
        outgoing=[RelationshipOut.model_validate(row) for row in outgoing],
        incoming=[RelationshipOut.model_validate(row) for row in incoming],
    )


@router.post(
    "/entities/{entity_id}/relationships",
    status_code=status.HTTP_201_CREATED,
    response_model=RelationshipOut,
)
async def create_relationship(
    entity_id: UUID,
    payload: RelationshipCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RelationshipOut:
    entity = await _owned_entity(session, entity_id, user)
    relationship = await fact_service.create_relationship(session, entity, payload)
    await session.commit()
    await session.refresh(relationship)
    return RelationshipOut.model_validate(relationship)


@router.patch("/relationships/{relationship_id}", response_model=RelationshipOut)
async def update_relationship(
    relationship_id: UUID,
    payload: RelationshipUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> RelationshipOut:
    relationship = await fact_service.get_relationship(session, relationship_id)
    entity = await entity_service.get_entity(session, relationship.from_entity_id)
    await stories_service.owned_story(session, entity.story_id, user.id)
    updated = await fact_service.update_relationship(session, relationship, payload)
    await session.commit()
    await session.refresh(updated)
    return RelationshipOut.model_validate(updated)


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    relationship_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    relationship = await fact_service.get_relationship(session, relationship_id)
    entity = await entity_service.get_entity(session, relationship.from_entity_id)
    await stories_service.owned_story(session, entity.story_id, user.id)
    await fact_service.delete_relationship(session, relationship)
    await session.commit()
