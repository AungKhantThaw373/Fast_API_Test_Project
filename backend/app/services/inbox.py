"""The review inbox: one ordered list of things that want a human decision.

Two kinds arrive today: proposed facts (from AI extraction or a merge) and open
continuity findings. Everything carries the source it came from, the actions the
client may offer, and - when a decision is being held back - the reason. The
cursor is a stable key so the list can be polled while the writer works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Chapter, ContinuityFinding, ContinuityScan
from app.models.wiki_models import Entity, EntityFact, MergeProposal
from app.schemas.wiki import InboxItemOut, InboxSourceOut
from app.services.pagination import (
    clamp_limit,
    cursor_timestamp,
    cursor_uuid,
    decode_cursor,
    encode_cursor,
)

KINDS = ("fact", "merge", "finding")
FACT_ACTIONS = ["accept", "reject", "edit"]
FINDING_ACTIONS = ["resolve", "dismiss"]
MERGE_ACTIONS = ["merge", "dismiss"]


@dataclass(frozen=True)
class RawItem:
    id: UUID
    kind: str
    sort_at: datetime
    title: str
    summary: str
    confidence: int
    source: InboxSourceOut
    actions: list[str]
    why_held: str | None
    entity_id: UUID | None
    chapter_id: UUID | None


def _fact_value(fact: EntityFact) -> str:
    if fact.value_text:
        return fact.value_text
    if fact.value_number is not None:
        return f"{fact.value_number:g}"
    if fact.value_date is not None:
        return fact.value_date.isoformat()
    if fact.value_entity_id is not None:
        return str(fact.value_entity_id)
    return "(empty)"


async def _conflict_reason(session: AsyncSession, fact: EntityFact) -> str | None:
    """Explain why a proposal is held: an accepted value already exists."""
    accepted = await session.scalar(
        select(EntityFact)
        .where(
            EntityFact.entity_id == fact.entity_id,
            EntityFact.predicate == fact.predicate,
            EntityFact.status == "accepted",
            EntityFact.id != fact.id,
        )
        .order_by(EntityFact.created_at.desc())
        .limit(1)
    )
    if accepted is None:
        return None
    if _fact_value(accepted) == _fact_value(fact):
        return None
    return f"Already recorded as '{_fact_value(accepted)}'."


def _default_reason(fact: EntityFact) -> str:
    """Every pending item says why it is pending, even without a conflict."""
    if fact.created_by == "ai":
        return "Found while reading a chapter; no one has accepted it yet."
    return "Added by hand and left as a proposal."


async def collect(
    session: AsyncSession,
    story_id: UUID,
    *,
    kinds: list[str] | None = None,
    status: str = "open",
    limit: int | None = None,
    cursor: str | None = None,
) -> tuple[list[InboxItemOut], str | None]:
    selected = [kind for kind in (kinds or KINDS) if kind in KINDS]
    if not selected:
        return [], None
    page_size = clamp_limit(limit, default=50, maximum=200)

    items: list[RawItem] = []
    if "fact" in selected and status in {"open", "proposed", "all"}:
        items.extend(await _facts(session, story_id))
    if "merge" in selected and status in {"open", "all"}:
        items.extend(await _merges(session, story_id))
    if "finding" in selected and status in {"open", "all"}:
        items.extend(await _findings(session, story_id))

    items.sort(key=lambda item: (item.sort_at, str(item.id)), reverse=True)
    if cursor:
        at, item_id = decode_cursor(cursor, (cursor_timestamp, cursor_uuid))
        items = [item for item in items if (item.sort_at, item.id) < (at, item_id)]

    page = items[:page_size]
    next_cursor = None
    if len(items) > page_size and page:
        next_cursor = encode_cursor((page[-1].sort_at, page[-1].id))
    return [
        InboxItemOut(
            id=item.id,
            kind=item.kind,
            title=item.title,
            summary=item.summary,
            confidence=item.confidence,
            source=item.source,
            actions=item.actions,
            why_held=item.why_held,
            entity_id=item.entity_id,
            chapter_id=item.chapter_id,
        )
        for item in page
    ], next_cursor


async def _facts(session: AsyncSession, story_id: UUID) -> list[RawItem]:
    rows = (
        await session.execute(
            select(EntityFact, Entity, Chapter)
            .join(Entity, Entity.id == EntityFact.entity_id)
            .outerjoin(Chapter, Chapter.id == EntityFact.chapter_id)
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                EntityFact.status == "proposed",
            )
            .order_by(EntityFact.created_at.desc())
            .limit(500)
        )
    ).all()
    out: list[RawItem] = []
    for fact, entity, chapter in rows:
        out.append(
            RawItem(
                id=fact.id,
                kind="fact",
                sort_at=fact.created_at,
                title=f"{entity.name}: {fact.predicate.replace('_', ' ')}",
                summary=_fact_value(fact),
                confidence=fact.confidence,
                source=InboxSourceOut(
                    chapter_id=fact.chapter_id,
                    chapter_number=chapter.chapter_number if chapter else fact.valid_from_chapter,
                    line=fact.line_start,
                    quote=fact.quote,
                ),
                actions=FACT_ACTIONS,
                why_held=await _conflict_reason(session, fact) or _default_reason(fact),
                entity_id=entity.id,
                chapter_id=fact.chapter_id,
            )
        )
    return out


async def _findings(session: AsyncSession, story_id: UUID) -> list[RawItem]:
    rows = (
        await session.execute(
            select(ContinuityFinding, ContinuityScan, Chapter)
            .join(ContinuityScan, ContinuityScan.id == ContinuityFinding.scan_id)
            .join(Chapter, Chapter.id == ContinuityScan.chapter_id)
            .where(
                ContinuityScan.story_id == story_id,
                ContinuityFinding.review_status == "open",
            )
            .order_by(ContinuityFinding.created_at.desc())
            .limit(500)
        )
    ).all()
    return [
        RawItem(
            id=finding.id,
            kind="finding",
            sort_at=finding.created_at,
            title=f"Continuity: line {finding.draft_line} of {chapter.title or 'chapter'}",
            summary=finding.explanation,
            confidence=finding.confidence,
            source=InboxSourceOut(
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                line=finding.draft_line,
                quote=finding.draft_quote,
            ),
            actions=FINDING_ACTIONS,
            why_held=f"Conflicts with chapter {finding.earlier_chapter_number}.",
            entity_id=None,
            chapter_id=chapter.id,
        )
        for finding, _scan, chapter in rows
    ]


async def _merges(session: AsyncSession, story_id: UUID) -> list[RawItem]:
    from app.services.merge_proposals import propose

    proposals = await propose(session, story_id)
    out: list[RawItem] = []
    for proposal, source, target in proposals:
        out.append(
            RawItem(
                id=proposal.id,
                kind="merge",
                sort_at=proposal.created_at,
                title=f"{source.name} and {target.name}: the same thing?",
                summary=(
                    f"Names are {round(proposal.score * 100)}% similar. Merging moves "
                    f"{source.name}'s facts and mentions into {target.name}."
                ),
                confidence=int(round(proposal.score * 100)),
                source=InboxSourceOut(),
                actions=MERGE_ACTIONS,
                why_held="Similar names, but nothing has been merged automatically.",
                entity_id=source.id,
                chapter_id=None,
            )
        )
    return out


async def decide_many(
    session: AsyncSession, story_id: UUID, ids: list[UUID], action: str
) -> dict[str, int]:
    """Apply one decision to many items: the "clear this chapter" path."""
    from app.services.merge_proposals import apply as apply_merge
    from app.services.merge_proposals import dismiss as dismiss_merge

    counts = {"facts": 0, "findings": 0, "merges": 0, "skipped": 0}
    if action not in {"accept", "reject", "resolve", "dismiss"}:
        raise HTTPException(status_code=422, detail="Unknown inbox action.")
    for item_id in ids:
        fact = await session.get(EntityFact, item_id)
        if fact is not None:
            owner = await session.scalar(select(Entity.story_id).where(Entity.id == fact.entity_id))
            if owner != story_id:
                counts["skipped"] += 1
                continue
            fact.status = "accepted" if action == "accept" else "rejected"
            counts["facts"] += 1
            continue
        merge = await session.get(MergeProposal, item_id)
        if merge is not None:
            if merge.story_id != story_id or merge.status != "pending":
                counts["skipped"] += 1
                continue
            if action == "accept":
                await apply_merge(session, story_id, item_id)
                counts["merges"] += 1
            else:
                await dismiss_merge(session, story_id, item_id)
                counts["merges"] += 1
            continue
        finding = await session.get(ContinuityFinding, item_id)
        if finding is not None:
            scan = await session.get(ContinuityScan, finding.scan_id)
            if scan is None or scan.story_id != story_id:
                counts["skipped"] += 1
                continue
            finding.review_status = "resolved" if action in {"accept", "resolve"} else "dismissed"
            counts["findings"] += 1
            continue
        counts["skipped"] += 1
    await session.flush()
    return counts


async def counts(session: AsyncSession, story_id: UUID) -> dict[str, int]:
    fact_count = int(
        await session.scalar(
            select(func.count(EntityFact.id))
            .join(Entity, Entity.id == EntityFact.entity_id)
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                EntityFact.status == "proposed",
            )
        )
        or 0
    )
    finding_count = int(
        await session.scalar(
            select(func.count(ContinuityFinding.id))
            .join(ContinuityScan, ContinuityScan.id == ContinuityFinding.scan_id)
            .where(
                ContinuityScan.story_id == story_id,
                ContinuityFinding.review_status == "open",
            )
        )
        or 0
    )
    merge_count = int(
        await session.scalar(
            select(func.count(MergeProposal.id)).where(
                MergeProposal.story_id == story_id, MergeProposal.status == "pending"
            )
        )
        or 0
    )
    return {
        "fact": fact_count,
        "merge": merge_count,
        "finding": finding_count,
        "total": fact_count + merge_count + finding_count,
    }
