"""Bulk-import the synthetic scale fixture into an isolated database.

This is intentionally a script, not a request handler. It imports one chapter
per transaction, records a checkpoint after each commit, and skips chapters that
already exist. A failed chapter is recorded and the run continues; a pause file
or Ctrl-C stops after the current chapter. No cloud provider is used.

Example (from the repository root):

    $env:DBNAME = "stillroom_scale_test"
    cd backend
    uv run alembic upgrade head
    uv run python ../scripts/import_fixture.py --migrate

Synthetic vectors are the default because a 1M-word local embedding pass takes
hours. Pass --embedding-mode ollama to use the configured local model; the
worker path is never involved, so the API stays responsive.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
DEFAULT_FIXTURE = ROOT / "data" / "scale-fixture"
DEFAULT_STATE = ROOT / "data" / "scale-import-state.json"
SYNTHETIC_MODEL = "synthetic-scale-768"
STORY_TITLE = "Synthetic Scale Serial"
SCALE_EMAIL = "scale@example.com"


@dataclass
class Totals:
    chapters: int = 0
    chunks: int = 0
    words: int = 0
    failed: int = 0
    skipped: int = 0


def synthetic_vector(key: str, dimensions: int = 768) -> list[float]:
    """Deterministic unit vector; identical text gets an identical vector."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    values = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def load_fixture(path: Path) -> dict[str, Any]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    chapters = [
        json.loads(line)
        for line in (path / "chapters.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "manifest": manifest,
        "chapters": chapters,
        "entities": json.loads((path / "entities.json").read_text(encoding="utf-8")),
        "arcs": json.loads((path / "arcs.json").read_text(encoding="utf-8")),
        "threads": json.loads((path / "threads.json").read_text(encoding="utf-8")),
        "contradictions": json.loads(
            (path / "contradictions.json").read_text(encoding="utf-8")
        ),
    }


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


async def _migrate(db: str) -> None:
    environment = {**os.environ, "DBNAME": db}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr[-2000:] or "alembic upgrade head failed")


async def _seed_entities(
    session: Any,
    story_id: Any,
    entities: dict[str, list[dict[str, Any]]],
    chapter_ids: dict[int, Any],
) -> dict[str, Any]:
    from app.models.wiki_models import Entity, EntityAlias
    from app.services.entities import normalize_name

    rows: list[Any] = []
    for kind in ("characters", "locations", "items", "organizations"):
        for item in entities[kind]:
            rows.append(
                Entity(
                    story_id=story_id,
                    entity_type=item["type"],
                    name=item["name"],
                    canonical_name=item["name"],
                    summary=item["summary"],
                    status="active",
                    first_chapter_number=1,
                    last_chapter_number=max(chapter_ids) if chapter_ids else None,
                )
            )
    session.add_all(rows)
    await session.flush()
    by_name = {row.name: row.id for row in rows}
    aliases = []
    for row in rows:
        source = next(
            item
            for kind in ("characters", "locations", "items", "organizations")
            for item in entities[kind]
            if item["name"] == row.name
        )
        for alias in source["aliases"]:
            aliases.append(
                EntityAlias(
                    entity_id=row.id,
                    alias=alias,
                    normalized_alias=normalize_name(alias),
                    alias_type="name",
                )
            )
    session.add_all(aliases)
    await session.commit()
    return by_name


def _character_ids_in(content: str, characters: list[dict[str, Any]], by_name: dict[str, Any]) -> list[Any]:
    found = []
    for character in characters:
        if character["name"] in content:
            entity_id = by_name.get(character["name"])
            if entity_id is not None:
                found.append(entity_id)
    return found


async def _seed_facts(
    story_id: Any,
    by_name: dict[str, Any],
    contradictions: list[dict[str, Any]],
) -> int:
    from sqlalchemy import select

    from app.db import async_session
    from app.models.story_models import Chapter
    from app.models.wiki_models import Entity, EntityFact

    async with async_session() as session:
        chapter_lookup = {
            row.chapter_number: row.id
            for row in await session.scalars(select(Chapter).where(Chapter.story_id == story_id))
        }
        existing = set(
            await session.scalars(
                select(EntityFact.quote)
                .join(Entity, Entity.id == EntityFact.entity_id)
                .where(Entity.story_id == story_id)
            )
        )
        facts = []
        for planted in contradictions:
            quote = planted["canonical_quote"]
            entity_id = by_name.get(planted["entity"])
            chapter_id = chapter_lookup.get(planted["canonical_chapter"])
            if quote in existing or entity_id is None or chapter_id is None:
                continue
            facts.append(
                EntityFact(
                    entity_id=entity_id,
                    predicate=planted["predicate"],
                    value_text=quote,
                    value_type="text",
                    chapter_id=chapter_id,
                    line_start=1,
                    line_end=1,
                    quote=quote,
                    confidence=100,
                    status="accepted",
                    valid_from_chapter=planted["canonical_chapter"],
                    created_by="human",
                    context={"fixture": "scale", "planted": True},
                )
            )
        session.add_all(facts)
        await session.commit()
        return len(facts)


async def _import_chapter(
    number: int,
    row: dict[str, Any],
    story_id: Any,
    arc_ids: dict[str, Any],
    by_name: dict[str, Any],
    entities: dict[str, list[dict[str, Any]]],
    embedding_mode: str,
    target_tokens_per_second: float | None,
) -> tuple[int, int]:
    from app.config import settings
    from app.db import async_session
    from app.models.story_models import Chapter, StoryChunk
    from app.services.chunking import chunk_chapter

    chunks = chunk_chapter(row["content"])
    if not chunks:
        raise RuntimeError(f"chapter {number} produced no chunks")
    character_ids = _character_ids_in(row["content"], entities["characters"], by_name)
    if embedding_mode == "ollama":
        from app.services.ai_service import embed_texts

        vectors = await asyncio.to_thread(embed_texts, [chunk.text for chunk in chunks], "document")
    else:
        vectors = [
            synthetic_vector(f"{number}:{chunk.chunk_index}:{chunk.content_hash}")
            for chunk in chunks
        ]
    started = time.perf_counter()
    async with async_session() as session:
        chapter = Chapter(
            story_id=story_id,
            chapter_number=number,
            arc_id=arc_ids.get(row["arc"]),
            position=float(number * 1024),
            title=row["title"],
            content=row["content"],
            word_count=len(row["content"].split()),
            revision=1,
            index_status="indexed",
            indexed_embedding_model=settings.EMBEDDING_MODEL,
            bible_scan_revision=None,
        )
        session.add(chapter)
        await session.flush()
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                StoryChunk(
                    story_id=story_id,
                    chapter_id=chapter.id,
                    chapter_number=number,
                    scene_index=chunk.scene_index,
                    chunk_index=chunk.chunk_index,
                    chunk_kind="scene",
                    text=chunk.text,
                    token_count=chunk.token_count,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    entities=character_ids,
                    content_hash=chunk.content_hash,
                    embedding=vector,
                    embedding_model=SYNTHETIC_MODEL if embedding_mode == "synthetic" else "nomic-embed-text",
                )
            )
        await session.commit()
    elapsed = time.perf_counter() - started
    if target_tokens_per_second and embedding_mode == "ollama":
        tokens = sum(chunk.token_count for chunk in chunks)
        budget = tokens / target_tokens_per_second
        if elapsed < budget:
            await asyncio.sleep(budget - elapsed)
    return len(chunks), len(row["content"].split())


async def import_fixture(args: argparse.Namespace) -> dict[str, Any]:
    if args.db:
        if not (args.db.endswith("_test") or "scale" in args.db):
            raise SystemExit("refusing to import into a non-scale database")
        os.environ["DBNAME"] = args.db
    os.environ.setdefault("DBNAME", "stillroom_scale_test")

    fixture_path = args.fixture.resolve()
    fixture = load_fixture(fixture_path)
    state_path = args.state.resolve()
    state: dict[str, Any] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    from sqlalchemy import delete, func, select, text

    from app.db import async_session, engine
    from app.models.app_models import User
    from app.models.story_models import Arc, Chapter, Story, StoryChunk
    from app.models.wiki_models import StoryThread
    from app.security import get_password_hash

    if args.migrate:
        await _migrate(os.environ["DBNAME"])

    started = time.perf_counter()
    totals = Totals()
    failures: list[dict[str, Any]] = []
    stop = False

    def request_stop(*_: Any) -> None:
        nonlocal stop
        stop = True

    try:
        signal.signal(signal.SIGINT, request_stop)
    except (ValueError, OSError):
        pass

    async with async_session() as session:
        schema = await session.scalar(text("SELECT to_regclass('story_chunks')"))
        if schema is None:
            raise SystemExit(
                "schema missing; run: uv run alembic upgrade head with DBNAME set"
            )
        story = await session.get(Story, state["story_id"]) if state.get("story_id") else None
        if args.force:
            if story is None:
                story = await session.scalar(select(Story).where(Story.title == STORY_TITLE))
            if story is not None:
                await session.execute(delete(Story).where(Story.id == story.id))
                await session.commit()
            story = None
            state = {}
        if story is None:
            story = await session.scalar(select(Story).where(Story.title == STORY_TITLE))
        if story is None:
            user = await session.scalar(select(User).where(User.email == SCALE_EMAIL))
            if user is None:
                user = User(
                    username="scale",
                    email=SCALE_EMAIL,
                    password=get_password_hash("scale fixture only"),
                    fullname="Scale Fixture",
                )
                session.add(user)
                await session.flush()
            story = Story(
                owner_id=user.id,
                title=STORY_TITLE,
                collection_name="scale",
                scan_interval_words=0,
                external_analysis_enabled=False,
                monthly_ai_budget=0,
            )
            session.add(story)
            await session.flush()
            for index, arc_row in enumerate(fixture["arcs"]):
                session.add(
                    Arc(
                        story_id=story.id,
                        name=arc_row["name"],
                        position=float(index * 1024),
                        summary=f"Chapters {arc_row['start']}-{arc_row['end']}.",
                    )
                )
            await session.commit()
        story_id = story.id
        arcs = list(await session.scalars(select(Arc).where(Arc.story_id == story_id)))
        arc_ids = {arc.name: arc.id for arc in arcs}
        existing_numbers = set(
            await session.scalars(
                select(Chapter.chapter_number).where(
                    Chapter.story_id == story_id, Chapter.deleted_at.is_(None)
                )
            )
        )
        existing_chapters = {
            row.chapter_number: row.id
            for row in await session.scalars(select(Chapter).where(Chapter.story_id == story_id))
        }

    db_size_before = await _relation_size("story_chunks")
    entity_map: dict[str, Any] = {}
    async with async_session() as session:
        from app.models.wiki_models import Entity

        entity_count = await session.scalar(
            select(func.count()).select_from(Entity).where(Entity.story_id == story_id)
        )
        if not entity_count:
            entity_map = await _seed_entities(
                session, story_id, fixture["entities"], existing_chapters
            )
    if not entity_map:
        async with async_session() as session:
            entity_map = {
                row.name: row.id
                for row in await session.scalars(select(Entity).where(Entity.story_id == story_id))
            }

    chapter_total = len(fixture["chapters"])
    imported_numbers: list[int] = []
    for index, row in enumerate(fixture["chapters"], start=1):
        if args.limit is not None and totals.chapters >= args.limit:
            break
        if stop or (args.pause_file and args.pause_file.exists()):
            state["paused"] = True
            break
        if index in existing_numbers:
            totals.skipped += 1
            continue
        try:
            if args.fail_at == index:
                raise RuntimeError("simulated chapter failure")
            chunks, words = await _import_chapter(
                index,
                row,
                story_id,
                arc_ids,
                entity_map,
                fixture["entities"],
                args.embedding_mode,
                args.target_tokens_per_second,
            )
        except Exception as exc:
            totals.failed += 1
            failures.append({"chapter": index, "error": f"{type(exc).__name__}: {exc}"})
            print(f"FAIL chapter {index}: {type(exc).__name__}: {exc}", flush=True)
            continue
        totals.chapters += 1
        totals.chunks += chunks
        totals.words += words
        imported_numbers.append(index)
        existing_numbers.add(index)
        state.update(
            {
                "story_id": str(story_id),
                "db": os.environ["DBNAME"],
                "completed_through": index,
                "chapters_total": chapter_total,
                "chapters_imported": len(existing_numbers),
                "chunks": totals.chunks,
                "words": totals.words,
                "failures": failures,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_state(state_path, state)
        if totals.chapters % 25 == 0:
            elapsed = time.perf_counter() - started
            print(
                f"{index}/{chapter_total} chapters | {totals.chunks} chunks | "
                f"{totals.words:,} words | {totals.words / elapsed:,.0f} words/s",
                flush=True,
            )

    async with async_session() as session:
        if imported_numbers:
            await session.execute(text("ANALYZE story_chunks"))
        facts_added = await _seed_facts(
            story_id, entity_map, fixture["contradictions"]
        )
        thread_rows = list(
            await session.scalars(select(StoryThread).where(StoryThread.story_id == story_id))
        )
        existing_thread_titles = {thread.title for thread in thread_rows}
        chapter_lookup = {
            row.chapter_number: row.id
            for row in await session.scalars(select(Chapter).where(Chapter.story_id == story_id))
        }
        for thread in fixture["threads"]:
            if thread["title"] in existing_thread_titles:
                continue
            session.add(
                StoryThread(
                    story_id=story_id,
                    title=thread["title"],
                    description=thread["summary"],
                    setup_chapter_id=chapter_lookup.get(thread["setup_chapter"]),
                    payoff_chapter_id=(
                        chapter_lookup.get(thread["payoff_chapter"])
                        if thread["payoff_chapter"]
                        else None
                    ),
                    state=thread["state"],
                )
            )
        await session.commit()

    db_size_after = await _relation_size("story_chunks")
    elapsed = time.perf_counter() - started
    async with async_session() as session:
        total_chapters = await session.scalar(
            select(func.count()).select_from(Chapter).where(
                Chapter.story_id == story_id, Chapter.deleted_at.is_(None)
            )
        )
        total_chunks = await session.scalar(
            select(func.count()).select_from(StoryChunk).where(StoryChunk.story_id == story_id)
        )
        database_size = await session.scalar(
            text("SELECT pg_database_size(current_database())")
        )
    result = {
        "story_id": str(story_id),
        "db": os.environ["DBNAME"],
        "embedding_mode": args.embedding_mode,
        "run": {**asdict(totals), "seconds": round(elapsed, 2),
                "words_per_second": round(totals.words / elapsed, 2) if elapsed else 0},
        "corpus": {
            "chapters": int(total_chapters or 0),
            "chunks": int(total_chunks or 0),
            "story_chunks_mb": round((await _relation_size("story_chunks")) / 1048576, 2),
            "story_chunks_growth_mb": round((db_size_after - db_size_before) / 1048576, 2),
            "database_mb": round((database_size or 0) / 1048576, 2),
        },
        "facts_added": facts_added,
        "failures": failures,
        "state_path": str(state_path),
    }
    state.update({"last_run": result, "paused": stop or bool(args.pause_file and args.pause_file.exists())})
    _write_state(state_path, state)
    await engine.dispose()
    return result


async def _relation_size(table: str) -> int:
    from sqlalchemy import text

    from app.db import async_session

    async with async_session() as session:
        return int(await session.scalar(text(f"SELECT pg_total_relation_size('{table}')")) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the synthetic scale fixture")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--pause-file", type=Path, default=None)
    parser.add_argument("--fail-at", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--embedding-mode", choices=("synthetic", "ollama"), default="synthetic")
    parser.add_argument("--target-tokens-per-second", type=float, default=None)
    args = parser.parse_args()
    if args.db is None:
        args.db = os.environ.get("DBNAME", "stillroom_scale_test")
    if not (args.db.endswith("_test") or "scale" in args.db):
        raise SystemExit("refusing to import into a non-scale database")
    os.environ["DBNAME"] = args.db
    result = asyncio.run(import_fixture(args))
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())