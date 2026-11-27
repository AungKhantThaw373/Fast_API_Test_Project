"""Deterministic continuity rules: free, exact, and deliberately quiet.

Every rule returns a finding only for a complete sentence that names a canon
entity and clearly contradicts an accepted fact. A near-miss (negation, another
entity, a title without the name) must stay silent; false positives train writers
to ignore the feature.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki_models import Entity, EntityAlias, EntityFact

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
TITLES = (
    "Captain", "Commander", "Lieutenant", "Sergeant", "Corporal", "Admiral",
    "General", "Colonel", "Major", "Doctor", "Professor", "Lord", "Lady",
    "King", "Queen", "Prince", "Princess", "Master", "Mistress", "Father",
    "Mother", "Sister", "Brother",
)
COLORS = (
    "black", "blue", "brown", "green", "grey", "gray", "hazel", "amber",
    "violet", "red", "white", "silver", "gold", "golden",
)
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}
PHYSICAL = {
    "eye_color": ("eyes", "eye"),
    "hair_color": ("hair",),
}


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    severity: str
    line: int
    quote: str
    message: str
    explanation: str
    confidence: int = 100


@dataclass(frozen=True)
class FactRecord:
    entity_id: UUID
    predicate: str
    value: str


@dataclass
class RuleContext:
    names: dict[UUID, str]
    aliases: dict[UUID, list[str]]
    facts: list[FactRecord]


def _sentences(text: str, start_line: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for offset, line in enumerate(text.splitlines()):
        line_number = start_line + offset
        for sentence in SENTENCE_RE.split(line.strip()):
            clean = sentence.strip()
            if clean:
                out.append((line_number, clean))
    return out


def _has_name(sentence: str, names: list[str]) -> bool:
    return any(
        re.search(rf"(?<![\w']){re.escape(name)}(?![\w'])" , sentence, re.IGNORECASE)
        for name in names
        if len(name) >= 3
    )


def _sentence_ok(sentence: str) -> bool:
    words = re.findall(r"[A-Za-z']+", sentence)
    return len(words) >= 5 and bool(re.search(r"""[.!?]["')\]]*$""", sentence))


def _number(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return int(match.group(1))
    for word in re.findall(r"[a-z]+", text.casefold()):
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]
    return None


def _negated(lower: str, position: int) -> bool:
    prefix = lower[:position].split()[-4:]
    return any(word in {"not", "never", "no"} for word in prefix)


def _age_rule(
    line: int, sentence: str, entity_id: UUID, names: list[str], fact: FactRecord
) -> RuleFinding | None:
    if not _has_name(sentence, names) or not re.search(r"years?[- ]old|years? of age", sentence, re.I):
        return None
    stated = _number(sentence)
    expected = _number(fact.value)
    if stated is None or expected is None or stated == expected:
        return None
    number_match = re.search(r"\b(?:\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\b", sentence.casefold())
    if number_match and _negated(sentence.casefold(), number_match.start()):
        return None
    return RuleFinding(
        rule_id="age_mismatch",
        severity="warning",
        line=line,
        quote=sentence,
        message=f"Age: canon says {expected}, this sentence says {stated}.",
        explanation=f"The accepted age for {names[0]} is {fact.value}; this sentence gives a different number.",
    )


def _physical_rule(
    line: int, sentence: str, entity_id: UUID, names: list[str], fact: FactRecord
) -> RuleFinding | None:
    keywords = PHYSICAL.get(fact.predicate)
    if not keywords or not _has_name(sentence, names):
        return None
    lower = sentence.casefold()
    if not any(re.search(rf"\b{word}\b", lower) for word in keywords):
        return None
    expected = fact.value.casefold().strip()
    stated = [color for color in COLORS if re.search(rf"\b{color}\b", lower)]
    if not stated:
        return None
    # "not blue" is a denial, not a statement that the eyes are blue.
    stated = [
        color
        for color in stated
        if not _negated(lower, lower.find(color))
    ]
    if not stated or any(color in expected for color in stated):
        return None
    actual = stated[0]
    label = "eye colour" if fact.predicate == "eye_color" else "hair colour"
    return RuleFinding(
        rule_id="physical_mismatch",
        severity="warning",
        line=line,
        quote=sentence,
        message=f"{label.capitalize()}: canon says {fact.value}, this sentence says {actual}.",
        explanation=f"The accepted {label} for {names[0]} is {fact.value}.",
    )


def _title_rule(
    line: int, sentence: str, entity_id: UUID, names: list[str], fact: FactRecord
) -> RuleFinding | None:
    if not _has_name(sentence, names):
        return None
    used = [title for title in TITLES if re.search(rf"\b{title}\b", sentence, re.I)]
    expected = fact.value.strip()
    if not used or not expected:
        return None
    if any(title.casefold() == expected.casefold() for title in used):
        return None
    actual = used[0]
    return RuleFinding(
        rule_id="title_mismatch",
        severity="warning",
        line=line,
        quote=sentence,
        message=f"Title: canon says {expected}, this sentence says {actual}.",
        explanation=f"The accepted title for {names[0]} is {expected}.",
    )


Rule = Callable[[int, str, UUID, list[str], FactRecord], RuleFinding | None]
RULES: tuple[tuple[str, Rule], ...] = (
    ("age_mismatch", _age_rule),
    ("physical_mismatch", _physical_rule),
    ("title_mismatch", _title_rule),
)


def check_scene(scene_text: str, start_line: int, context: RuleContext) -> list[RuleFinding]:
    by_entity: dict[UUID, list[FactRecord]] = {}
    for fact in context.facts:
        by_entity.setdefault(fact.entity_id, []).append(fact)
    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for line, sentence in _sentences(scene_text, start_line):
        if not _sentence_ok(sentence):
            continue
        for entity_id, facts in by_entity.items():
            names = [context.names.get(entity_id, ""), *context.aliases.get(entity_id, [])]
            names = [name for name in names if name and len(name) >= 3]
            if not _has_name(sentence, names):
                continue
            for fact in facts:
                for rule_id, rule in RULES:
                    if rule_id != _rule_for_fact(fact.predicate):
                        continue
                    finding = rule(line, sentence, entity_id, names, fact)
                    if finding is None:
                        continue
                    key = (finding.rule_id, finding.line, finding.quote.casefold())
                    if key not in seen:
                        seen.add(key)
                        findings.append(finding)
    return findings


def _rule_for_fact(predicate: str) -> str:
    if predicate == "age":
        return "age_mismatch"
    if predicate in PHYSICAL:
        return "physical_mismatch"
    if predicate == "title":
        return "title_mismatch"
    return ""


def _pov(sentence: str) -> str:
    words = re.findall(r"[A-Za-z']+", sentence.casefold())
    first = sum(word in {"i", "we", "my", "our", "me", "us"} for word in words)
    third = sum(word in {"he", "she", "they", "his", "her", "their", "him", "them"} for word in words)
    if len(words) < 20:
        return "neutral"
    if first >= 3 and first > third * 1.5:
        return "first"
    if third >= 3 and third > first * 1.5:
        return "third"
    return "neutral"


def check_pov(scenes: list[tuple[int, str, int]]) -> list[RuleFinding]:
    """Flag one scene that switches point of view inside a chapter.

    ``scenes`` is ``(scene_index, text, start_line)``. A chapter with a genuine
    mix is left alone: only a single outlier scene is reported.
    """
    classified: list[tuple[int, str, int, str]] = []
    for scene_index, text, start_line in scenes:
        if any(sentence for _, sentence in _sentences(text, start_line)):
            classified.append((scene_index, text, start_line, _pov(text)))
    first = [item for item in classified if item[3] == "first"]
    third = [item for item in classified if item[3] == "third"]
    if not first or not third:
        return []
    minority = first if len(first) < len(third) else third
    if len(minority) != 1:
        return []
    scene_index, text, start_line, kind = minority[0]
    line, sentence = next(iter(_sentences(text, start_line)), (start_line, text[:200]))
    other = "first" if kind == "third" else "third"
    return [
        RuleFinding(
            rule_id="pov_shift",
            severity="info",
            line=line,
            quote=sentence,
            message=f"Point of view: this scene is {kind} person; the rest is {other} person.",
            explanation="A single scene switches narrative person inside the chapter.",
            confidence=80,
        )
    ]


async def load_context(session: AsyncSession, story_id: UUID) -> RuleContext:
    entities = list(
        await session.scalars(
            select(Entity).where(Entity.story_id == story_id, Entity.merged_into_id.is_(None))
        )
    )
    aliases: dict[UUID, list[str]] = {entity.id: [] for entity in entities}
    for entity_id, alias in (
        await session.execute(
            select(EntityAlias.entity_id, EntityAlias.alias).where(
                EntityAlias.entity_id.in_([entity.id for entity in entities])
            )
        )
    ).all():
        aliases.setdefault(entity_id, []).append(alias)
    facts = [
        FactRecord(entity_id=fact.entity_id, predicate=fact.predicate, value=fact.value_text or "")
        for fact in await session.scalars(
            select(EntityFact).where(
                EntityFact.entity_id.in_([entity.id for entity in entities]),
                EntityFact.status == "accepted",
            )
        )
    ]
    return RuleContext(
        names={entity.id: entity.name for entity in entities},
        aliases=aliases,
        facts=[fact for fact in facts if fact.value],
    )
