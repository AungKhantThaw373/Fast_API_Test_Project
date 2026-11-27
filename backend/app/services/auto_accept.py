"""Auto-accept rules for extraction proposals.

The defaults are deliberately conservative: a quote must exist, confidence must be
high, and a value that contradicts accepted canon is never accepted silently. The
dry-run count exists so the trade-off is visible before the writer turns it on.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki_models import AutoAcceptRules, Entity, EntityFact

DEFAULTS = {
    "require_quote": True,
    "min_confidence": 80,
    "require_existing_entity": False,
    "block_conflicts": True,
    "max_per_chapter": 20,
}


async def get_rules(session: AsyncSession, story_id: UUID) -> AutoAcceptRules:
    rules = await session.get(AutoAcceptRules, story_id)
    if rules is not None:
        return rules
    rules = AutoAcceptRules(story_id=story_id, **DEFAULTS)
    session.add(rules)
    await session.flush()
    return rules


async def save_rules(
    session: AsyncSession,
    story_id: UUID,
    *,
    require_quote: bool | None = None,
    min_confidence: int | None = None,
    require_existing_entity: bool | None = None,
    block_conflicts: bool | None = None,
    max_per_chapter: int | None = None,
) -> AutoAcceptRules:
    rules = await get_rules(session, story_id)
    if require_quote is not None:
        rules.require_quote = require_quote
    if min_confidence is not None:
        if not 0 <= min_confidence <= 100:
            raise HTTPException(status_code=422, detail="Confidence must be between 0 and 100.")
        rules.min_confidence = min_confidence
    if require_existing_entity is not None:
        rules.require_existing_entity = require_existing_entity
    if block_conflicts is not None:
        rules.block_conflicts = block_conflicts
    if max_per_chapter is not None:
        if max_per_chapter < 1:
            raise HTTPException(status_code=422, detail="Keep at least one accept per chapter.")
        rules.max_per_chapter = max_per_chapter
    await session.flush()
    return rules


async def _accepted_by_entity(session: AsyncSession, story_id: UUID) -> dict[UUID, dict[str, str]]:
    rows = (
        await session.execute(
            select(EntityFact.entity_id, EntityFact.predicate, EntityFact.value_text)
            .join(Entity, Entity.id == EntityFact.entity_id)
            .where(
                Entity.story_id == story_id,
                Entity.status != "merged",
                EntityFact.status == "accepted",
            )
        )
    ).all()
    accepted: dict[UUID, dict[str, str]] = {}
    for entity_id, predicate, value in rows:
        accepted.setdefault(entity_id, {})[predicate] = (value or "").strip()
    return accepted


async def eligible(
    session: AsyncSession, story_id: UUID
) -> tuple[list[EntityFact], list[tuple[EntityFact, str]], AutoAcceptRules]:
    """Return (facts that would be accepted, held facts with a reason, rules)."""
    rules = await get_rules(session, story_id)
    proposed = list(
        await session.scalars(
            select(EntityFact)
            .join(Entity, Entity.id == EntityFact.entity_id)
            .where(
                Entity.story_id == story_id,
                Entity.merged_into_id.is_(None),
                Entity.status != "archived",
                EntityFact.status == "proposed",
            )
            .order_by(EntityFact.created_at.desc())
        )
    )
    accepted = await _accepted_by_entity(session, story_id)
    by_chapter: dict[UUID | None, int] = {}
    take: list[EntityFact] = []
    held: list[tuple[EntityFact, str]] = []
    for fact in proposed:
        reason = ""
        if rules.require_quote and not fact.quote:
            reason = "No quote in the chapter."
        elif fact.confidence < rules.min_confidence:
            reason = f"Confidence {fact.confidence} is below {rules.min_confidence}."
        elif rules.require_existing_entity and fact.entity_id is None:
            reason = "The entity must already exist."
        elif rules.block_conflicts:
            current = accepted.get(fact.entity_id, {}).get(fact.predicate)
            if current and current != (fact.value_text or "").strip():
                reason = f"Already recorded as '{current}'."
        else:
            reason = ""
        if not reason:
            used = by_chapter.get(fact.chapter_id, 0)
            if used >= rules.max_per_chapter:
                reason = f"Limit of {rules.max_per_chapter} per chapter reached."
        if reason:
            held.append((fact, reason))
        else:
            by_chapter[fact.chapter_id] = by_chapter.get(fact.chapter_id, 0) + 1
            take.append(fact)
    return take, held, rules


@dataclass
class Preview:
    would_accept: int
    held: int
    total: int
    rules: RulesView


@dataclass
class RulesView:
    require_quote: bool
    min_confidence: int
    require_existing_entity: bool
    block_conflicts: bool
    max_per_chapter: int


async def preview(session: AsyncSession, story_id: UUID) -> Preview:
    take, held, rules = await eligible(session, story_id)
    return Preview(
        would_accept=len(take),
        held=len(held),
        total=len(take) + len(held),
        rules=_rules_out(rules),
    )


async def run(session: AsyncSession, story_id: UUID) -> dict[str, int]:
    take, held, _rules = await eligible(session, story_id)
    for fact in take:
        _accept(fact)
    await session.flush()
    return {"accepted": len(take), "held": len(held)}


def _accept(fact: EntityFact) -> None:
    fact.status = "accepted"


def _rules_out(rules: AutoAcceptRules) -> RulesView:
    return RulesView(
        require_quote=rules.require_quote,
        min_confidence=rules.min_confidence,
        require_existing_entity=rules.require_existing_entity,
        block_conflicts=rules.block_conflicts,
        max_per_chapter=rules.max_per_chapter,
    )
