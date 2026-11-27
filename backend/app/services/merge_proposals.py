"""Merge proposals: similar names, proposed once, decided forever.

Similarity never merges anything. It only suggests a pair, and the suggestion is
stored so a dismissal sticks instead of reappearing every time the inbox loads.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.wiki_models import Entity, MergeProposal
from app.services.entities import merge_entities

SIMILARITY_THRESHOLD = 0.6
MAX_PROPOSALS = 20


async def propose(session: AsyncSession, story_id: UUID) -> list[tuple[MergeProposal, Entity, Entity]]:
    """Derive similar-name pairs in one statement and keep the unseen ones."""
    left = aliased(Entity)
    right = aliased(Entity)
    score = func.similarity(left.canonical_name, right.canonical_name)
    rows = (
        await session.execute(
            select(left.id, right.id, score)
            .where(
                left.story_id == story_id,
                right.story_id == story_id,
                left.id < right.id,
                left.merged_into_id.is_(None),
                right.merged_into_id.is_(None),
                left.status == "active",
                right.status == "active",
                left.canonical_name != "",
                right.canonical_name != "",
                score > SIMILARITY_THRESHOLD,
            )
            .order_by(score.desc())
            .limit(MAX_PROPOSALS * 2)
        )
    ).all()

    decided = {
        (row[0], row[1])
        for row in (
            await session.execute(
                select(MergeProposal.source_id, MergeProposal.target_id).where(
                    MergeProposal.story_id == story_id
                )
            )
        ).all()
    }
    created = False
    for source_id, target_id, similarity in rows:
        if (source_id, target_id) in decided or (target_id, source_id) in decided:
            continue
        session.add(
            MergeProposal(
                story_id=story_id,
                source_id=source_id,
                target_id=target_id,
                score=round(float(similarity), 3),
            )
        )
        created = True
    if created:
        await session.flush()

    proposals = list(
        await session.scalars(
            select(MergeProposal)
            .where(MergeProposal.story_id == story_id, MergeProposal.status == "pending")
            .order_by(MergeProposal.score.desc())
            .limit(MAX_PROPOSALS)
        )
    )
    out: list[tuple[MergeProposal, Entity, Entity]] = []
    for proposal in proposals:
        source = await session.get(Entity, proposal.source_id)
        target = await session.get(Entity, proposal.target_id)
        if source is None or target is None:
            continue
        if source.merged_into_id is not None or target.merged_into_id is not None:
            proposal.status = "stale"
            continue
        out.append((proposal, source, target))
    return out


async def dismiss(
    session: AsyncSession, story_id: UUID, proposal_id: UUID, *, reason: str = ""
) -> MergeProposal:
    proposal = await session.get(MergeProposal, proposal_id)
    if proposal is None or proposal.story_id != story_id:
        raise HTTPException(status_code=404, detail="Merge proposal not found.")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="That proposal was already decided.")
    proposal.status = "dismissed"
    proposal.decided_at = func.now()
    await session.flush()
    return proposal


async def apply(
    session: AsyncSession, story_id: UUID, proposal_id: UUID, *, created_by: str = "human"
) -> Entity:
    proposal = await session.get(MergeProposal, proposal_id)
    if proposal is None or proposal.story_id != story_id:
        raise HTTPException(status_code=404, detail="Merge proposal not found.")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="That proposal was already decided.")
    target = await session.get(Entity, proposal.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="The target entry no longer exists.")
    await merge_entities(
        session,
        story_id=story_id,
        source_id=proposal.source_id,
        target_id=proposal.target_id,
        created_by=created_by,
    )
    proposal.status = "merged"
    proposal.decided_at = func.now()
    await session.flush()
    return target


async def mark_stale_for_entity(session: AsyncSession, entity_id: UUID) -> None:
    """A merge or deletion makes every proposal touching the entity stale."""
    rows = await session.scalars(
        select(MergeProposal).where(
            MergeProposal.status == "pending",
            (MergeProposal.source_id == entity_id) | (MergeProposal.target_id == entity_id),
        )
    )
    for proposal in rows:
        proposal.status = "stale"
    await session.flush()
