"""Canon exceptions: reasons a known contradiction is intentional.

A writer who changes a detail on purpose records an exception with a reason. A
finding whose text matches an exception's pattern is dropped before the writer
ever sees it, so the inbox stops repeating the same accepted deviation.

Patterns are plain case-insensitive substrings, not regexes: an exception should
never be able to suppress half the manuscript through a typo.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki_models import CanonException, Entity, EntityFact
from app.services.finding_filter import DraftFinding

SCOPES = ("pattern", "entity", "predicate")


@dataclass(frozen=True)
class ExceptionCreate:
    scope: str
    reason: str
    pattern: str | None = None
    entity_id: UUID | None = None
    predicate: str | None = None


async def list_exceptions(
    session: AsyncSession, story_id: UUID
) -> list[CanonException]:
    return list(
        await session.scalars(
            select(CanonException)
            .where(CanonException.story_id == story_id)
            .order_by(CanonException.created_at.desc())
        )
    )


async def create_exception(
    session: AsyncSession, story_id: UUID, payload: ExceptionCreate
) -> CanonException:
    if payload.scope not in SCOPES:
        raise HTTPException(status_code=422, detail="Unknown exception scope.")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="An exception needs a reason.")
    pattern = (payload.pattern or "").strip() or None
    if payload.scope == "pattern" and pattern is None:
        raise HTTPException(status_code=422, detail="A pattern exception needs a pattern.")
    predicate = (payload.predicate or "").strip() or None
    if payload.scope == "entity":
        entity = await session.get(Entity, payload.entity_id) if payload.entity_id else None
        if entity is None or entity.story_id != story_id:
            raise HTTPException(status_code=422, detail="Entity is not in this story.")
    if payload.scope == "predicate":
        if predicate is None:
            raise HTTPException(status_code=422, detail="A predicate exception needs a predicate.")
        fact = await session.scalar(
            select(EntityFact.id)
            .join(Entity, Entity.id == EntityFact.entity_id)
            .where(
                Entity.story_id == story_id,
                EntityFact.predicate == predicate,
            )
            .limit(1)
        )
        if fact is None:
            raise HTTPException(
                status_code=422, detail="No fact in this story uses that predicate."
            )
    exception = CanonException(
        story_id=story_id,
        scope=payload.scope,
        entity_id=payload.entity_id,
        predicate=predicate,
        pattern=pattern,
        reason=reason,
    )
    session.add(exception)
    await session.flush()
    return exception


async def delete_exception(
    session: AsyncSession, story_id: UUID, exception_id: UUID
) -> None:
    exception = await session.scalar(
        select(CanonException).where(
            CanonException.id == exception_id, CanonException.story_id == story_id
        )
    )
    if exception is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    await session.delete(exception)
    await session.flush()


def matches(exception: CanonException, finding: DraftFinding) -> bool:
    pattern = (exception.pattern or "").strip().casefold()
    if not pattern:
        return False
    haystack = " ".join(
        (finding.draft_quote, finding.earlier_quote or "", finding.explanation)
    ).casefold()
    return pattern in haystack


async def filter_exceptions(
    session: AsyncSession, story_id: UUID, findings: list[DraftFinding]
) -> tuple[list[DraftFinding], int]:
    exceptions = [item for item in await list_exceptions(session, story_id) if item.pattern]
    if not exceptions:
        return findings, 0
    kept = [
        finding
        for finding in findings
        if not any(matches(exception, finding) for exception in exceptions)
    ]
    return kept, len(findings) - len(kept)
