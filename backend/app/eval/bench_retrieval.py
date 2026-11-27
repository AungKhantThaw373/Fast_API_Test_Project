"""Synthetic retrieval latency benchmark.

Creates a disposable story with N scene chunks, runs the real hybrid search
path (embedding + SQL + fusion), and reports warm p50/p95. Use it to check the
Phase 5 p95 target before a release; it is not part of the test suite::

    cd backend
    uv run python -m app.eval.bench_retrieval --chunks 10000 --queries 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, insert, select, text

from app.config import settings
from app.db import async_session, engine
from app.eval.dataset import load_questions
from app.eval.metrics import percentile
from app.models.app_models import User
from app.models.story_models import Chapter, Story, StoryChunk
from app.services.ai_service import embed_texts
from app.services.retrieval import CACHE, search_chunks

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET = BACKEND_ROOT / "eval" / "datasets" / "stillroom.json"


NAMES = ["Mira", "Hollis", "Kael", "Sera", "Ivo", "Nell", "Tomas", "Rhea", "Bram", "Edda"]
PLACES = ["lantern coast", "northern quay", "abbey", "lighthouse", "salt market", "old bridge", "harbour gate"]
OBJECTS = ["ledger", "chart", "rope", "bell", "compass", "letter", "coat", "lantern", "boat", "key"]
VERBS = ["counted", "carried", "mended", "questioned", "followed", "left", "found", "hid", "traded", "watched"]
ADJECTIVES = ["grey", "salt-stained", "quiet", "broken", "borrowed", "cold", "narrow", "bright", "empty", "old"]


def _chunk_text(index: int) -> str:
	# Each chunk gets its own deterministic scene. Reusing one template made
	# every embedding almost identical and turned the HNSW graph into a list.
	rng = random.Random(index)
	sentences = []
	if index % 12 == 0:
		sentences.extend(
			[
				f"Scene {index}: Mira Voss counted the boats at the lantern coast while Hollis watched the tide.",
				"The harbour bell rang twice and the gulls turned over the grey water.",
				"Kael wrote the hour in the ledger and did not look back toward the gate.",
				"Sera carried a chart past the lighthouse and the storm followed her in.",
			]
		)
	for _ in range(10):
		sentences.append(
			f"{rng.choice(NAMES)} {rng.choice(VERBS)} the {rng.choice(ADJECTIVES)} "
			f"{rng.choice(OBJECTS)} near the {rng.choice(PLACES)}, and {rng.choice(NAMES)} said nothing."
		)
	return " ".join(sentences)[:1200]


async def _create_story(chunks: int) -> UUID:
	async with async_session() as cleanup:
		old = await cleanup.scalars(select(Story).where(Story.title.like("Retrieval benchmark%")))
		for story in old:
			await cleanup.delete(story)
		await cleanup.commit()
	async with engine.connect() as connection:
		connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
		# Reclaim the previous run before inserting, otherwise the table grows
		# every run and the exact scan measures dead pages instead of rows.
		await connection.execute(text("VACUUM FULL story_chunks"))
	async with async_session() as session:
		user = await session.scalar(select(User).order_by(User.created_at))
		if user is None:
			raise SystemExit("No local user exists. Register once before benchmarking.")
		story = Story(owner_id=user.id, title=f"Retrieval benchmark ({chunks})")
		session.add(story)
		await session.flush()
		chapter_count = max(1, min(100, chunks // 100))
		chapters = [
			Chapter(
				story_id=story.id,
				chapter_number=number,
				position=float(number * 1024),
				title=f"Benchmark chapter {number}",
				content="",
				word_count=0,
				revision=1,
				index_status="indexed",
			)
			for number in range(1, chapter_count + 1)
		]
		session.add_all(chapters)
		await session.flush()

		async def _flush_batch(rows: list[dict]) -> None:
			vectors = await asyncio.to_thread(embed_texts, [row["text"] for row in rows], "document")
			for row, vector in zip(rows, vectors, strict=True):
				row["embedding"] = vector
			await session.execute(insert(StoryChunk), rows)
			rows.clear()

		batch: list[dict] = []
		for index in range(chunks):
			chapter = chapters[index % chapter_count]
			batch.append(
				{
					"story_id": story.id,
					"chapter_id": chapter.id,
					"chapter_number": chapter.chapter_number,
					"scene_index": index // chapter_count,
					"chunk_index": index // chapter_count,
					"chunk_kind": "scene",
					"text": _chunk_text(index),
					"token_count": 300,
					"start_line": 1,
					"end_line": 20,
					"entities": [],
					"content_hash": f"{index:064x}",
					"embedding_model": settings.EMBEDDING_MODEL,
				}
			)
			if len(batch) == 256:
				await _flush_batch(batch)
		if batch:
			await _flush_batch(batch)
		await session.commit()
		story_id = story.id
	async with engine.connect() as connection:
		connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
		await connection.execute(text("VACUUM ANALYZE story_chunks"))
		await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_prewarm"))
		await connection.execute(text("SELECT pg_prewarm('story_chunks')"))
	return story_id


async def _drop_story(story_id: UUID) -> None:
	async with async_session() as session:
		await session.execute(delete(Story).where(Story.id == story_id))
		await session.commit()


async def _measure(story_id: UUID, queries: list[str]) -> list[dict]:
	CACHE.clear()
	records: list[dict] = []
	for query in queries:
		# A person does not submit fifty searches back to back. Give the CPU and
		# Ollama the same gap an interactive session has before each sample.
		await asyncio.sleep(0.25)
		# A real HTTP request gets its own session. Reusing one session for the
		# whole run kept a transaction and identity map alive long enough to
		# distort the latency of the later queries.
		async with async_session() as session:
			started = time.perf_counter()
			result = await search_chunks(session, story_id, query, use_cache=False)
			duration = (time.perf_counter() - started) * 1000
		records.append({"query": query, "latency_ms": round(duration, 2), "timings_ms": result.timings_ms})
		if not result.chunks:
			raise SystemExit("Benchmark query returned no chunks; the synthetic corpus is broken.")
	return records


async def main_async(args: argparse.Namespace) -> None:
	questions = [question.question for question in load_questions(args.dataset)][: args.queries]
	if args.measure_only:
		async with async_session() as session:
			story = await session.scalar(
				select(Story).where(Story.title == f"Retrieval benchmark ({args.chunks})")
			)
		if story is None:
			raise SystemExit("No retained benchmark corpus. Run once with --keep first.")
		story_id = story.id
	else:
		story_id = await _create_story(args.chunks)
	try:
		records = await _measure(story_id, questions)
		latencies = [record["latency_ms"] for record in records]
		size_mb = None
		async with async_session() as session:
			size_mb = await session.scalar(
				text("SELECT round(pg_total_relation_size('story_chunks') / 1048576.0, 1)")
			)
		payload = {
			"generated_at": datetime.now(UTC).isoformat(),
			"chunks": args.chunks,
			"queries": len(latencies),
			"embedding_model": settings.EMBEDDING_MODEL,
			"story_chunks_table_mb": float(size_mb or 0),
			"latency_ms": {
				"p50": round(percentile(latencies, 0.5), 2),
				"p95": round(percentile(latencies, 0.95), 2),
				"max": round(max(latencies), 2),
			},
			"results": records,
		}
		args.out.parent.mkdir(parents=True, exist_ok=True)
		args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
		print(json.dumps(payload, indent=2))
	finally:
		if not args.keep:
			await _drop_story(story_id)


def main() -> None:
	parser = argparse.ArgumentParser(description="Benchmark hybrid retrieval latency")
	parser.add_argument("--chunks", type=int, default=10_000)
	parser.add_argument("--queries", type=int, default=40)
	parser.add_argument("--dataset", type=Path, default=DATASET)
	parser.add_argument("--out", type=Path, default=BACKEND_ROOT.parent / "Docs" / "eval" / "latency.json")
	parser.add_argument("--keep", action="store_true")
	parser.add_argument("--measure-only", action="store_true", help="measure a retained corpus in a fresh process")
	args = parser.parse_args()
	asyncio.run(main_async(args))


if __name__ == "__main__":
	main()
