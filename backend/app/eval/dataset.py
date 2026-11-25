"""Dataset loaders for the Phase 5 evaluation harness.

The manual allows YAML or JSON. JSON keeps the harness dependency-free; the
files live in ``backend/eval/datasets`` so a reviewer can read the questions and
the seeded manuscript side by side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExpectedEvidence:
    chapter_number: int
    quote_contains: str


@dataclass(frozen=True)
class Question:
    id: str
    type: str
    question: str
    expected_entities: list[str] = field(default_factory=list)
    expected_evidence: list[ExpectedEvidence] = field(default_factory=list)
    answer_contains: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContinuityCase:
    id: str
    established: str
    draft: str
    expected_flag: bool
    note: str = ""


@dataclass(frozen=True)
class ChapterSeed:
    number: int
    title: str
    content: str


@dataclass(frozen=True)
class EntitySeed:
    key: str
    name: str
    type: str
    summary: str
    aliases: list[tuple[str, str]]


@dataclass(frozen=True)
class FactSeed:
    entity: str
    predicate: str
    value: str | None
    chapter: int
    quote: str
    value_entity: str | None = None


@dataclass(frozen=True)
class RelationshipSeed:
    from_entity: str
    to_entity: str
    type: str
    description: str
    chapter: int


@dataclass(frozen=True)
class ThreadSeed:
    title: str
    description: str
    setup_chapter: int
    state: str
    linked: list[str]


@dataclass(frozen=True)
class EventSeed:
    chapter: int
    summary: str
    participants: list[str]
    location: str | None


@dataclass(frozen=True)
class Manuscript:
    title: str
    chapters: list[ChapterSeed]
    entities: list[EntitySeed]
    facts: list[FactSeed]
    relationships: list[RelationshipSeed]
    threads: list[ThreadSeed]
    events: list[EventSeed]


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def load_manuscript(path: Path) -> Manuscript:
    payload = _read_json(path)
    chapters = [
        ChapterSeed(
            number=int(item["number"]),
            title=str(item["title"]),
            content="\n\n".join(str(line) for line in item["lines"]).strip(),
        )
        for item in payload["chapters"]
    ]
    entities = [
        EntitySeed(
            key=str(item["key"]),
            name=str(item["name"]),
            type=str(item["type"]),
            summary=str(item.get("summary", "")),
            aliases=[(str(alias), str(kind)) for alias, kind in item.get("aliases", [])],
        )
        for item in payload.get("entities", [])
    ]
    facts = [
        FactSeed(
            entity=str(item["entity"]),
            predicate=str(item["predicate"]),
            value=item.get("value"),
            chapter=int(item["chapter"]),
            quote=str(item["quote"]),
            value_entity=item.get("value_entity"),
        )
        for item in payload.get("facts", [])
    ]
    relationships = [
        RelationshipSeed(
            from_entity=str(item["from"]),
            to_entity=str(item["to"]),
            type=str(item["type"]),
            description=str(item.get("description", "")),
            chapter=int(item["chapter"]),
        )
        for item in payload.get("relationships", [])
    ]
    threads = [
        ThreadSeed(
            title=str(item["title"]),
            description=str(item.get("description", "")),
            setup_chapter=int(item["setup_chapter"]),
            state=str(item.get("state", "open")),
            linked=[str(key) for key in item.get("linked", [])],
        )
        for item in payload.get("threads", [])
    ]
    events = [
        EventSeed(
            chapter=int(item["chapter"]),
            summary=str(item["summary"]),
            participants=[str(key) for key in item.get("participants", [])],
            location=item.get("location"),
        )
        for item in payload.get("events", [])
    ]
    return Manuscript(
        title=str(payload.get("title", "Evaluation story")),
        chapters=chapters,
        entities=entities,
        facts=facts,
        relationships=relationships,
        threads=threads,
        events=events,
    )


def load_questions(path: Path) -> list[Question]:
    payload = _read_json(path)
    questions: list[Question] = []
    for item in payload["questions"]:
        questions.append(
            Question(
                id=str(item["id"]),
                type=str(item["type"]),
                question=str(item["question"]),
                expected_entities=[str(value) for value in item.get("expected_entities", [])],
                expected_evidence=[
                    ExpectedEvidence(
                        chapter_number=int(evidence["chapter_number"]),
                        quote_contains=str(evidence["quote_contains"]),
                    )
                    for evidence in item.get("expected_evidence", [])
                ],
                answer_contains=[str(value) for value in item.get("answer_contains", [])],
            )
        )
    if len({question.id for question in questions}) != len(questions):
        raise ValueError(f"{path} contains duplicate question ids.")
    return questions


def load_continuity(path: Path) -> list[ContinuityCase]:
    payload = _read_json(path)
    cases = [
        ContinuityCase(
            id=str(item["id"]),
            established=str(item["established"]),
            draft=str(item["draft"]),
            expected_flag=bool(item["expected_flag"]),
            note=str(item.get("note", "")),
        )
        for item in payload["cases"]
    ]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError(f"{path} contains duplicate case ids.")
    return cases
