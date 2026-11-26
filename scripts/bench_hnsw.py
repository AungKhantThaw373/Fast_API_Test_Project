"""Compare pgvector exact scan with HNSW at Phase 9 scale.

This is a disposable benchmark, not an application path. It creates a
`bench_chunks` table in a separate database, generates deterministic vectors,
measures exact top-30 scans, builds an HNSW index, and measures latency and
recall with and without a story filter.

Example (after creating `stillroom_hnsw_test`):

    uv run --project backend python scripts/bench_hnsw.py --sizes 10000 50000 100000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy import URL

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
# Settings loads `.env` relative to the process, not the package.
os.chdir(BACKEND_ROOT)

from app.config import settings

DIMS = 768
LIMIT = 30
QUERY_POINTS = 5
REPEATS = 4


def _dsn(database: str) -> str:
    return URL.create(
        "postgresql",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=database,
    ).render_as_string(hide_password=False)


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(
            ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))], 1
        ),
        "max_ms": round(ordered[-1], 1),
        "runs": len(ordered),
    }


async def _scalar(conn: asyncpg.Connection, sql: str, *args: object) -> Any:
    return await conn.fetchval(sql, *args)


async def _create(conn: asyncpg.Connection, size: int) -> None:
    await conn.execute("DROP TABLE IF EXISTS bench_chunks")
    await conn.execute(
        "CREATE TABLE bench_chunks ("
        "id integer PRIMARY KEY, story_id uuid NOT NULL, embedding vector(768) NOT NULL)"
    )
    # Real embeddings cluster; uniform random vectors make every distance tie
    # and unfairly destroy HNSW recall. Build 512 noisy clusters instead and
    # keep the vectors deterministic. This measures index mechanics, not
    # semantic retrieval quality.
    await conn.execute(
        """
        INSERT INTO bench_chunks (id, story_id, embedding)
        SELECT i,
               CASE WHEN i <= $1 / 2
                    THEN '11111111-1111-1111-1111-111111111111'::uuid
                    ELSE '22222222-2222-2222-2222-222222222222'::uuid END,
               ARRAY(
                   SELECT (
                       ((hashtext('c' || (i % 512)::text || ':' || g::text) % 2001) - 1000)::float8 / 1000.0
                       + 0.08 * (((hashtext(i::text || ':' || g::text) % 201) - 100)::float8 / 100.0)
                   )
                   FROM generate_series(1, 768) g
               )::vector
        FROM generate_series(1, $1) i
        """,
        size,
    )
    await conn.execute("ANALYZE bench_chunks")


async def _timed(
    conn: asyncpg.Connection, sql: str, args: tuple[Any, ...], repeats: int
) -> list[float]:
    values: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        await conn.fetch(sql, *args)
        values.append((time.perf_counter() - started) * 1000)
        await asyncio.sleep(0.05)
    return values


async def _run_size(
    conn: asyncpg.Connection, size: int, ef_values: list[int]
) -> dict[str, Any]:
    print(f"building {size:,} rows", flush=True)
    started = time.perf_counter()
    await _create(conn, size)
    insert_seconds = time.perf_counter() - started
    table_mb = float(
        await _scalar(conn, "SELECT pg_total_relation_size('bench_chunks') / 1048576.0")
    )

    query_rows = await conn.fetch(
        "SELECT id, embedding::text AS vector FROM bench_chunks WHERE id = ANY($1::int[]) ORDER BY id",
        [1 + (size // 2 - 2) * i // (QUERY_POINTS - 1) for i in range(QUERY_POINTS)],
    )
    vectors = [row["vector"] for row in query_rows]

    exact_sets: list[set[int]] = []
    exact_times: list[float] = []
    for vector in vectors:
        rows = await conn.fetch(
            "SELECT id FROM bench_chunks WHERE story_id = $1 ORDER BY embedding <=> $2::vector LIMIT 30",
            "11111111-1111-1111-1111-111111111111",
            vector,
        )
        exact_sets.append({row["id"] for row in rows})
        exact_times.extend(
            await _timed(
                conn,
                "SELECT id FROM bench_chunks WHERE story_id = $1 ORDER BY embedding <=> $2::vector LIMIT 30",
                ("11111111-1111-1111-1111-111111111111", vector),
                REPEATS,
            )
        )

    print(f"  exact done, building HNSW at {size:,}", flush=True)
    await conn.execute("SET maintenance_work_mem = '1GB'")
    await conn.execute("SET max_parallel_maintenance_workers = 0")
    started = time.perf_counter()
    await conn.execute(
        "CREATE INDEX bench_chunks_hnsw ON bench_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    build_seconds = time.perf_counter() - started
    index_mb = float(
        await _scalar(conn, "SELECT pg_relation_size('bench_chunks_hnsw') / 1048576.0")
    )
    await conn.execute("ANALYZE bench_chunks")

    async def _hnsw_query(
        ef_search: int, iterative: bool
    ) -> tuple[dict[str, float], list[float], list[int]]:
        await conn.execute(f"SET hnsw.ef_search = {ef_search}")
        await conn.execute("SET hnsw.max_scan_tuples = 200000")
        await conn.execute(
            "SET hnsw.iterative_scan = 'relaxed_order'"
            if iterative
            else "SET hnsw.iterative_scan = 'off'"
        )
        times: list[float] = []
        recalls: list[float] = []
        counts: list[int] = []
        sql = "SELECT id FROM bench_chunks WHERE story_id = $1 ORDER BY embedding <=> $2::vector LIMIT 30"
        for index, vector in enumerate(vectors):
            args = ("11111111-1111-1111-1111-111111111111", vector)
            rows = await conn.fetch(sql, *args)
            found = {row["id"] for row in rows}
            recalls.append(len(found & exact_sets[index]) / LIMIT)
            counts.append(len(found))
            times.extend(await _timed(conn, sql, args, REPEATS))
        return _summary(times), recalls, counts

    hnsw_results: dict[str, dict[str, float]] = {}
    for iterative, label in ((False, "plain"), (True, "iterative")):
        for ef_search in ef_values:
            summary, recalls, counts = await _hnsw_query(ef_search, iterative)
            hnsw_results[f"{label}_ef_{ef_search}"] = {
                **summary,
                "recall_at_30": round(statistics.mean(recalls), 3),
                "returned": round(statistics.mean(counts), 1),
            }
    return {
        "rows": size,
        "story_rows": size // 2,
        "insert_seconds": round(insert_seconds, 2),
        "hnsw_build_seconds": round(build_seconds, 2),
        "table_mb": round(table_mb, 1),
        "hnsw_index_mb": round(index_mb, 1),
        "exact_filtered": _summary(exact_times),
        "hnsw": hnsw_results,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="stillroom_hnsw_test")
    parser.add_argument(
        "--sizes", type=int, nargs="+", default=[10_000, 50_000, 100_000]
    )
    parser.add_argument("--ef-search", type=int, nargs="+", default=[40, 100, 200])
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "Docs" / "eval" / "hnsw.json"
    )
    args = parser.parse_args()
    conn = await asyncpg.connect(_dsn(args.database))
    try:
        reports = []
        for size in args.sizes:
            report = await _run_size(conn, size, args.ef_search)
            reports.append(report)
            print(json.dumps(report, indent=2), flush=True)
        payload = {
            "dimensions": DIMS,
            "limit": LIMIT,
            "query_points": QUERY_POINTS,
            "reports": reports,
        }
        out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {out}", flush=True)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
