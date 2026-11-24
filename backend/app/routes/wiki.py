"""Story thread, event, and inbox endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.wiki_models import CanonException
from app.schemas.inbox import (
    AutoAcceptPreviewOut,
    AutoAcceptRulesIn,
    AutoAcceptRulesOut,
    AutoAcceptRunOut,
    InboxDecision,
    InboxDecisionResult,
    MergeProposalOut,
)
from app.schemas.wiki import (
    AliasOut,
    EntityOut,
    EventCreate,
    EventListOut,
    EventOut,
    EventUpdate,
    ExceptionCreate,
    ExceptionListOut,
    ExceptionOut,
    InboxOut,
    NameCandidateAccept,
    NameCandidateListOut,
    NameCandidateOut,
    ThreadCreate,
    ThreadListOut,
    ThreadOut,
    ThreadUpdate,
)
from app.security import get_current_user
from app.services import auto_accept as auto_accept_service
from app.services import canon_exceptions as exceptions_service
from app.services import entities as entity_service
from app.services import inbox as inbox_service
from app.services import merge_proposals as proposals_service
from app.services import name_candidates as candidates_service
from app.services import stories as stories_service
from app.services import threads as threads_service

router = APIRouter(tags=["wiki"])


async def _owned_thread_story(session: AsyncSession, thread_id: UUID, user: User) -> UUID:
    thread = await threads_service.get_thread(session, thread_id)
    await stories_service.owned_story(session, thread.story_id, user.id)
    return thread.story_id


@router.get("/stories/{story_id}/threads", response_model=ThreadListOut)
async def list_threads(
    story_id: UUID,
    state_filter: str | None = Query(default=None, alias="state"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await threads_service.list_threads(session, story_id, state=state_filter)
    return ThreadListOut(threads=[ThreadOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/threads",
    status_code=status.HTTP_201_CREATED,
    response_model=ThreadOut,
)
async def create_thread(
    story_id: UUID,
    payload: ThreadCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadOut:
    await stories_service.owned_story(session, story_id, user.id)
    thread = await threads_service.create_thread(session, story_id, payload)
    await session.commit()
    await session.refresh(thread)
    return ThreadOut.model_validate(thread)


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def update_thread(
    thread_id: UUID,
    payload: ThreadUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadOut:
    await _owned_thread_story(session, thread_id, user)
    thread = await threads_service.get_thread(session, thread_id)
    await threads_service.update_thread(session, thread, payload)
    await session.commit()
    await session.refresh(thread)
    return ThreadOut.model_validate(thread)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await _owned_thread_story(session, thread_id, user)
    thread = await threads_service.get_thread(session, thread_id)
    await threads_service.delete_thread(session, thread)
    await session.commit()


@router.get("/stories/{story_id}/events", response_model=EventListOut)
async def list_events(
    story_id: UUID,
    chapter_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await threads_service.list_events(session, story_id, chapter_id=chapter_id)
    return EventListOut(events=[EventOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/events",
    status_code=status.HTTP_201_CREATED,
    response_model=EventOut,
)
async def create_event(
    story_id: UUID,
    payload: EventCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventOut:
    await stories_service.owned_story(session, story_id, user.id)
    event = await threads_service.create_event(session, story_id, payload)
    await session.commit()
    await session.refresh(event)
    return EventOut.model_validate(event)


@router.put("/events/{event_id}", response_model=EventOut)
async def update_event(
    event_id: UUID,
    payload: EventUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EventOut:
    event = await threads_service.get_event(session, event_id)
    await stories_service.owned_story(session, event.story_id, user.id)
    await threads_service.update_event(session, event, payload)
    await session.commit()
    await session.refresh(event)
    return EventOut.model_validate(event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    event = await threads_service.get_event(session, event_id)
    await stories_service.owned_story(session, event.story_id, user.id)
    await threads_service.delete_event(session, event)
    await session.commit()


@router.get(
    "/stories/{story_id}/chapters/{chapter_id}/name-candidates",
    response_model=NameCandidateListOut,
)
async def list_name_candidates(
    story_id: UUID,
    chapter_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> NameCandidateListOut:
    await stories_service.owned_story(session, story_id, user.id)
    chapter, candidates = await candidates_service.candidates_for_chapter(
        session, story_id, chapter_id
    )
    return NameCandidateListOut(
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
        candidates=[
            NameCandidateOut(
                name=item.name,
                count=item.count,
                first_line=item.first_line,
                sample=item.sample,
            )
            for item in candidates
        ],
    )


@router.post(
    "/stories/{story_id}/name-candidates/accept",
    status_code=status.HTTP_201_CREATED,
    response_model=EntityOut,
)
async def accept_name_candidate(
    story_id: UUID,
    payload: NameCandidateAccept,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> EntityOut:
    await stories_service.owned_story(session, story_id, user.id)
    entity = await candidates_service.accept_candidate(
        session,
        story_id=story_id,
        chapter_id=payload.chapter_id,
        name=payload.name,
        entity_type=payload.entity_type,
        line_start=payload.line_start,
        quote=payload.quote,
    )
    await session.commit()
    await session.refresh(entity)
    aliases = await entity_service.aliases_for(session, [entity.id])
    out = EntityOut.model_validate(entity).model_copy(
        update={"aliases": [AliasOut.model_validate(alias) for alias in aliases.get(entity.id, [])]}
    )
    return out


@router.get("/stories/{story_id}/exceptions", response_model=ExceptionListOut)
async def list_exceptions(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ExceptionListOut:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await exceptions_service.list_exceptions(session, story_id)
    return ExceptionListOut(exceptions=[ExceptionOut.model_validate(row) for row in rows])


@router.post(
    "/stories/{story_id}/exceptions",
    status_code=status.HTTP_201_CREATED,
    response_model=ExceptionOut,
)
async def create_exception(
    story_id: UUID,
    payload: ExceptionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ExceptionOut:
    await stories_service.owned_story(session, story_id, user.id)
    exception = await exceptions_service.create_exception(
        session,
        story_id,
        exceptions_service.ExceptionCreate(
            scope=payload.scope,
            reason=payload.reason,
            pattern=payload.pattern,
            entity_id=payload.entity_id,
            predicate=payload.predicate,
        ),
    )
    await session.commit()
    await session.refresh(exception)
    return ExceptionOut.model_validate(exception)


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(
    exception_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    exception = await session.get(CanonException, exception_id)
    if exception is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    await stories_service.owned_story(session, exception.story_id, user.id)
    await exceptions_service.delete_exception(session, exception.story_id, exception_id)
    await session.commit()


@router.post("/stories/{story_id}/inbox/decide", response_model=InboxDecisionResult)
async def decide_inbox_items(
    story_id: UUID,
    payload: InboxDecision,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> InboxDecisionResult:
    await stories_service.owned_story(session, story_id, user.id)
    counts = await inbox_service.decide_many(session, story_id, payload.ids, payload.action)
    await session.commit()
    return InboxDecisionResult(action=payload.action, **counts)


@router.get("/stories/{story_id}/inbox/rules", response_model=AutoAcceptRulesOut)
async def get_auto_accept_rules(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AutoAcceptRulesOut:
    await stories_service.owned_story(session, story_id, user.id)
    rules = await auto_accept_service.get_rules(session, story_id)
    await session.commit()
    return AutoAcceptRulesOut(
        require_quote=rules.require_quote,
        min_confidence=rules.min_confidence,
        require_existing_entity=rules.require_existing_entity,
        block_conflicts=rules.block_conflicts,
        max_per_chapter=rules.max_per_chapter,
    )


@router.put("/stories/{story_id}/inbox/rules", response_model=AutoAcceptRulesOut)
async def save_auto_accept_rules(
    story_id: UUID,
    payload: AutoAcceptRulesIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AutoAcceptRulesOut:
    await stories_service.owned_story(session, story_id, user.id)
    rules = await auto_accept_service.save_rules(
        session,
        story_id,
        require_quote=payload.require_quote,
        min_confidence=payload.min_confidence,
        require_existing_entity=payload.require_existing_entity,
        block_conflicts=payload.block_conflicts,
        max_per_chapter=payload.max_per_chapter,
    )
    await session.commit()
    return AutoAcceptRulesOut(
        require_quote=rules.require_quote,
        min_confidence=rules.min_confidence,
        require_existing_entity=rules.require_existing_entity,
        block_conflicts=rules.block_conflicts,
        max_per_chapter=rules.max_per_chapter,
    )


@router.get("/stories/{story_id}/inbox/rules/preview", response_model=AutoAcceptPreviewOut)
async def preview_auto_accept(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AutoAcceptPreviewOut:
    await stories_service.owned_story(session, story_id, user.id)
    preview = await auto_accept_service.preview(session, story_id)
    await session.commit()
    return AutoAcceptPreviewOut(
        would_accept=preview.would_accept,
        held=preview.held,
        total=preview.total,
        rules=AutoAcceptRulesOut(**preview.rules.__dict__),
    )


@router.post("/stories/{story_id}/inbox/auto-accept", response_model=AutoAcceptRunOut)
async def run_auto_accept(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> AutoAcceptRunOut:
    await stories_service.owned_story(session, story_id, user.id)
    result = await auto_accept_service.run(session, story_id)
    await session.commit()
    return AutoAcceptRunOut(accepted=result["accepted"], held=result["held"])


@router.get("/stories/{story_id}/merge-proposals", response_model=list[MergeProposalOut])
async def list_merge_proposals(
    story_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[MergeProposalOut]:
    await stories_service.owned_story(session, story_id, user.id)
    rows = await proposals_service.propose(session, story_id)
    await session.commit()
    return [
        MergeProposalOut(
            id=proposal.id,
            story_id=story_id,
            source_id=source.id,
            target_id=target.id,
            source_name=source.name,
            target_name=target.name,
            score=proposal.score,
            status=proposal.status,
            created_at=proposal.created_at,
        )
        for proposal, source, target in rows
    ]


@router.get("/stories/{story_id}/inbox", response_model=InboxOut)
async def get_inbox(
    story_id: UUID,
    kind: str | None = Query(default=None, description="Comma separated: fact,finding"),
    status_filter: str = Query(default="open", alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> InboxOut:
    await stories_service.owned_story(session, story_id, user.id)
    kinds = [part.strip() for part in kind.split(",")] if kind else None
    items, next_cursor = await inbox_service.collect(
        session, story_id, kinds=kinds, status=status_filter, limit=limit, cursor=cursor
    )
    return InboxOut(items=items, next_cursor=next_cursor)
