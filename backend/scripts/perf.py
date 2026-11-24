"""Phase 2 performance budget, measured against the test database.

    cd backend
    uv run python scripts/perf.py

Runs the ASGI app in-process (no socket), which removes network jitter and makes
the numbers repeatable. Everything happens in ``stillroom_test`` and is cleaned
up afterwards. Nothing here calls Ollama or a provider: the vectors are synthetic.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

os.environ["DBNAME"] = "stillroom_test"
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_SSL", "disable")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("JWT_SECRET", "perf-script-secret-that-is-long-enough")
os.environ.setdefault("host", "127.0.0.1")
os.environ.setdefault("port", "5432")
os.environ.setdefault("user", "postgres")
os.environ.setdefault("password", "death373")
# Bulk fixture setup (10k rows into an HNSW index) is a data load, not a request.
os.environ.setdefault("STATEMENT_TIMEOUT_MS", "600000")

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

from app.app import app  # noqa: E402
from app.db import async_session, engine  # noqa: E402
from app.services import continuity  # noqa: E402


def json_dumps(vectors: list[list[float]]) -> str:
    return json.dumps(vectors, separators=(",", ":"))

CHAPTER_WORDS = 900
CHUNKS = 10_000
REORDER_CHAPTERS = 1_100
SAVE_ITERATIONS = 50
RETRIEVAL_ITERATIONS = 30
RETRIEVAL_WARMUP = 5
PASSWORD = "perf correct horse battery"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def report(name: str, samples: list[float], target_ms: float) -> str:
    p50 = percentile(samples, 0.5) * 1000
    p95 = percentile(samples, 0.95) * 1000
    verdict = "pass" if p95 <= target_ms else "MISS"
    print(f"| {name} | {p50:.1f} ms | {p95:.1f} ms | < {target_ms:.0f} ms | {verdict} |")
    return verdict


async def _login(client: httpx.AsyncClient) -> None:
    email = f"perf-{uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/register",
        json={"username": f"perf{uuid4().hex[:8]}", "email": email, "password": PASSWORD},
    )
    response.raise_for_status()
    response = await client.post("/token", data={"username": email, "password": PASSWORD})
    response.raise_for_status()


async def _timed(call, iterations: int) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        response = await call()
        samples.append(time.perf_counter() - started)
        response.raise_for_status()
    return samples


async def measure_requests(client: httpx.AsyncClient) -> dict[str, list[float]]:
    story = (await client.post("/stories", json={"title": "Perf story"})).json()
    chapter = (
        await client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Chapter one", "content": "word " * CHAPTER_WORDS},
        )
    ).json()

    opens = await _timed(
        lambda: client.get(f"/stories/chapters/{chapter['id']}"), SAVE_ITERATIONS
    )
    list_stories = await _timed(lambda: client.get("/stories"), SAVE_ITERATIONS)

    revision = chapter["revision"]
    saves: list[float] = []
    for index in range(SAVE_ITERATIONS):
        started = time.perf_counter()
        response = await client.put(
            f"/stories/chapters/{chapter['id']}",
            json={"content": f"word {index} " + "word " * CHAPTER_WORDS, "expected_revision": revision},
        )
        saves.append(time.perf_counter() - started)
        response.raise_for_status()
        revision = response.json()["revision"]

    return {
        "chapter open (GET)": opens,
        "chapter save (PUT)": saves,
        "story list (GET /stories)": list_stories,
    }


async def measure_reorder(client: httpx.AsyncClient) -> float:
    story = (await client.post("/stories", json={"title": "Reorder perf"})).json()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO story_chapters
                    (id, story_id, chapter_number, position, title, content, word_count,
                     revision, index_status, created_at, updated_at, indexed_embedding_model)
                SELECT gen_random_uuid(), :story_id, g, g * 1024.0,
                       'Chapter ' || g, 'text ' || g, 2, 1, 'indexed', now(), now(),
                       'nomic-embed-text'
                FROM generate_series(1, :count) AS g
                """
            ),
            {"story_id": story["id"], "count": REORDER_CHAPTERS},
        )
    async with async_session() as session:
        ids = list(
            await session.scalars(
                text(
                    "SELECT id FROM story_chapters WHERE story_id = :story_id "
                    "ORDER BY chapter_number"
                ),
                {"story_id": story["id"]},
            )
        )
    shuffled = [str(chapter_id) for chapter_id in reversed(ids)]
    started = time.perf_counter()
    response = await client.put(
        f"/stories/{story['id']}/chapters/order", json={"chapter_ids": shuffled}
    )
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    assert len(response.json()["chapters"]) == REORDER_CHAPTERS
    return elapsed


async def measure_retrieval() -> tuple[list[float], int, str]:
    async with async_session() as session:
        story_id = uuid4()
        chapter_id = uuid4()
        await session.execute(
            text(
                """
                INSERT INTO stories (id, owner_id, title, collection_name, scan_interval_words,
                                     external_analysis_enabled, created_at, updated_at)
                SELECT :story_id, id, 'Retrieval perf', '', 1500, true, now(), now()
                FROM users LIMIT 1
                """
            ),
            {"story_id": story_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO story_chapters
                    (id, story_id, chapter_number, position, title, content, word_count,
                     revision, index_status, created_at, updated_at, indexed_embedding_model)
                VALUES (:chapter_id, :story_id, 1, 1024.0, 'Evidence', 'text', 1, 1,
                        'indexed', now(), now(), 'nomic-embed-text')
                """
            ),
            {"chapter_id": chapter_id, "story_id": story_id},
        )
        await session.execute(
            text(
                """
                WITH vector AS (
                    SELECT ('[' || (
                        SELECT string_agg(random()::text, ',')
                        FROM generate_series(1, 768)
                    ) || ']')::vector AS value
                )
                INSERT INTO story_scene_embeddings
                    (id, story_id, chapter_id, chapter_number, chunk_index, text,
                     start_line, end_line, chunk_metadata, embedding, created_at)
                SELECT gen_random_uuid(), :story_id, :chapter_id, 1, g,
                       'evidence chunk ' || g, 1, 2, '{}'::jsonb, vector.value, now()
                FROM generate_series(1, :count) AS g, vector
                """
            ),
            {"story_id": story_id, "chapter_id": chapter_id, "count": CHUNKS},
        )
        await session.commit()

    # Bulk-loading 10k rows leaves the planner with no statistics and autovacuum
    # decides when to catch up; do it now so the measurement is not a coin flip.
    async with engine.connect() as connection:
        autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("VACUUM (ANALYZE) story_scene_embeddings"))

    async with async_session() as session:
        vectors = [[0.01] * 768 for _ in range(3)]
        for _ in range(RETRIEVAL_WARMUP):
            await continuity.retrieve_evidence(session, story_id, 2, vectors, top_k=4)

        plan_rows = (
            await session.execute(
                text("EXPLAIN " + str(continuity._EVIDENCE_SQL)),  # noqa: SLF001
                {
                    "vectors": json_dumps(vectors),
                    "story_id": story_id,
                    "chapter_number": 2,
                    "embedding_model": "nomic-embed-text",
                    "top_k": 4,
                },
            )
        ).all()
        plan = " ".join(str(row[0]) for row in plan_rows)
        plan_kind = (
            "hnsw" if "ix_story_scene_embedding_hnsw" in plan else "sequential scan"
        )
        statements: list[str] = []

        def record(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            samples: list[float] = []
            for _ in range(RETRIEVAL_ITERATIONS):
                started = time.perf_counter()
                found = await continuity.retrieve_evidence(
                    session, story_id, 2, vectors, top_k=4
                )
                samples.append(time.perf_counter() - started)
                assert found
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
        query_count = len(statements) // RETRIEVAL_ITERATIONS

        await session.execute(
            text("DELETE FROM stories WHERE id = :story_id"), {"story_id": story_id}
        )
        await session.commit()
    return samples, query_count, plan_kind


async def main() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://perf") as client:
        await _login(client)
        print(f"# Stillroom performance budget ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)")
        print()
        print("In-process ASGI, local PostgreSQL 18, no network, synthetic vectors.")
        print()
        print("| Operation | p50 | p95 | Target | Result |")
        print("|---|---|---|---|---|")

        results = await measure_requests(client)
        failures = [
            report(name, samples, target)
            for name, target in (
                ("chapter open (GET)", 150),
                ("chapter save (PUT)", 150),
                ("story list (GET /stories)", 100),
            )
            for samples in [results[name]]
        ]
        print(f"| chapter saves measured | | | {SAVE_ITERATIONS} iterations | |")

        reorder_seconds = await measure_reorder(client)
        verdict = "pass" if reorder_seconds * 1000 <= 500 else "MISS"
        failures.append(verdict)
        print(
            f"| reorder {REORDER_CHAPTERS} chapters | | {reorder_seconds * 1000:.1f} ms "
            f"| < 500 ms | {verdict} |"
        )

        samples, query_count, plan_kind = await measure_retrieval()
        failures.append(report(f"retrieval {CHUNKS} chunks", samples, 300))
        query_verdict = "pass" if query_count <= 5 else "MISS"
        failures.append(query_verdict)
        print(
            f"| one-chapter retrieval DB queries | {query_count} | | <= 5 "
            f"| {query_verdict} |"
        )

        print()
        print(f"Vector plan for the retrieval query: {plan_kind}.")
        print()
        print("MISS" in failures and "**One or more targets missed.**" or "All targets met.")

    async with async_session() as session:
        await session.execute(text("DELETE FROM stories WHERE title IN ('Perf story', 'Reorder perf')"))
        await session.execute(text("DELETE FROM users WHERE email LIKE 'perf-%@example.com'"))
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
