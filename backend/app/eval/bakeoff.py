"""Embedding bake-off on the fixed Phase 5 evaluation story.

The chunk set is held constant so the only variable is the embedding model.
Run the seed once first (``python -m app.eval.run --limit 1``); then::

    cd backend
    uv run python -m app.eval.bakeoff --out ../Docs/eval/bakeoff.json

Quality is measured with the same binary evidence labels as the main harness.
Latency is warm query latency after documents are indexed. Storage is the raw
float32 payload for the test corpus, not a PostgreSQL table estimate.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import ollama
from sqlalchemy import select

from app.config import settings
from app.db import async_session
from app.eval.dataset import load_questions
from app.eval.metrics import (
    Retrieved,
    first_relevant_rank,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
    relevance_vector,
    summarize,
)
from app.models.story_models import Story, StoryChunk

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = BACKEND_ROOT / "eval" / "datasets"
STORY_TITLE = "The Lantern Coast"


@dataclass(frozen=True)
class Candidate:
    label: str
    model: str
    dimensions: int | None
    query_prefix: str = ""
    document_prefix: str = ""


CANDIDATES = (
    Candidate(
        label="nomic-embed-text",
        model="nomic-embed-text:latest",
        dimensions=768,
        query_prefix="search_query: ",
        document_prefix="search_document: ",
    ),
    Candidate(
        label="qwen3-embedding:0.6b",
        model="qwen3-embedding:0.6b",
        dimensions=768,
        query_prefix=(
            "Instruct: Retrieve earlier story passages that establish facts relevant to this scene.\nQuery: "
        ),
    ),
    Candidate(label="bge-m3", model="bge-m3:latest", dimensions=1024),
)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _embed_batch(
    client: ollama.Client, candidate: Candidate, texts: list[str], *, task: str
) -> list[list[float]]:
    prefixed = [
        (candidate.query_prefix if task == "query" else candidate.document_prefix) + text
        for text in texts
    ]
    kwargs: dict[str, Any] = {"model": candidate.model, "input": prefixed}
    if candidate.dimensions is not None:
        kwargs["dimensions"] = candidate.dimensions
    response = client.embed(**kwargs)
    vectors = getattr(response, "embeddings", None)
    if vectors is None:
        vectors = response.get("embeddings", [])
    if len(vectors) != len(prefixed):
        raise RuntimeError(f"{candidate.label} returned {len(vectors)} vectors for {len(prefixed)} inputs")
    return [[float(value) for value in vector] for vector in vectors]


def _model_size_mb(client: ollama.Client, model: str) -> float | None:
    try:
        response = client.list()
    except Exception:
        return None
    for item in getattr(response, "models", []):
        name = getattr(item, "model", getattr(item, "name", ""))
        if name == model or name.startswith(model.split(":")[0]):
            size = getattr(item, "size", None)
            return round(size / (1024 * 1024), 1) if size else None
    return None


def _vram_mb(model: str) -> float | None:
    try:
        response = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/ps", timeout=5.0)
        response.raise_for_status()
    except Exception:
        return None
    for item in response.json().get("models", []):
        if item.get("name") == model or item.get("model") == model:
            value = item.get("size_vram")
            return round(value / (1024 * 1024), 1) if value else None
    return None


async def _load_corpus() -> tuple[list[StoryChunk], Any]:
    async with async_session() as session:
        story = await session.scalar(select(Story).where(Story.title == STORY_TITLE))
        if story is None:
            raise SystemExit("Evaluation story not found. Run `uv run python -m app.eval.run --limit 1` first.")
        chunks = list(
            await session.scalars(
                select(StoryChunk)
                .where(StoryChunk.story_id == story.id)
                .order_by(StoryChunk.chapter_number, StoryChunk.chunk_index)
            )
        )
        if not chunks:
            raise SystemExit("Evaluation story has no chunks. Run the main harness with indexing first.")
        return chunks, story.id


def evaluate_candidate(
    candidate: Candidate, chunks: list[StoryChunk], questions, client: ollama.Client
) -> dict[str, Any]:
    started = time.perf_counter()
    first_batch = _embed_batch(client, candidate, [chunk.text for chunk in chunks[:8]], task="document")
    cold_ms = (time.perf_counter() - started) * 1000
    document_vectors = list(first_batch)
    for offset in range(8, len(chunks), 8):
        document_vectors.extend(
            _embed_batch(client, candidate, [chunk.text for chunk in chunks[offset : offset + 8]], task="document")
        )
    document_vectors = [_normalize(vector) for vector in document_vectors]
    dimensions = len(document_vectors[0])

    rows: list[dict[str, Any]] = []
    query_latencies: list[float] = []
    for question in questions:
        query_started = time.perf_counter()
        query_vector = _normalize(_embed_batch(client, candidate, [question.question], task="query")[0])
        scored = sorted(
            enumerate(document_vectors),
            key=lambda pair: _cosine(query_vector, pair[1]),
            reverse=True,
        )[:10]
        elapsed_ms = (time.perf_counter() - query_started) * 1000
        query_latencies.append(elapsed_ms)
        results = [
            Retrieved(chapter_number=chunks[index].chapter_number, text=chunks[index].text)
            for index, _score in scored
        ]
        relevance = relevance_vector(question, results)
        rows.append(
            {
                "id": question.id,
                "type": question.type,
                "latency_ms": round(elapsed_ms, 2),
                "first_relevant_rank": first_relevant_rank(relevance),
                "recall@5": recall_at_k(relevance, 5),
                "recall@10": recall_at_k(relevance, 10),
                "reciprocal_rank": round(reciprocal_rank(relevance), 4),
                "ndcg@10": round(
                    ndcg_at_k(relevance, 10, ideal_relevant=len(question.expected_evidence)), 4
                ),
            }
        )

    quality = summarize(rows, k=10)
    return {
        "label": candidate.label,
        "model": candidate.model,
        "dimensions": dimensions,
        "documents": len(chunks),
        "questions": len(questions),
        "quality": quality,
        "cold_start_ms": round(cold_ms, 2),
        "warm_latency_ms": {
            "p50": round(percentile(query_latencies, 0.5), 2),
            "p95": round(percentile(query_latencies, 0.95), 2),
            "max": round(max(query_latencies), 2),
        },
        "vram_mb": _vram_mb(candidate.model),
        "model_size_mb": _model_size_mb(client, candidate.model),
        "storage_mb_raw_float32": round(len(chunks) * dimensions * 4 / (1024 * 1024), 3),
        "results": rows,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Embedding bake-off on the Phase 5 eval story")
    parser.add_argument("--dataset", type=Path, default=DATASET_ROOT / "stillroom.json")
    parser.add_argument("--out", type=Path, default=BACKEND_ROOT.parent / "Docs" / "eval" / "bakeoff.json")
    args = parser.parse_args(argv)

    import asyncio

    chunks, _story_id = asyncio.run(_load_corpus())
    questions = load_questions(args.dataset)
    client = ollama.Client(host=settings.OLLAMA_BASE_URL)
    results = []
    for candidate in CANDIDATES:
        try:
            result = evaluate_candidate(candidate, chunks, questions, client)
        except Exception as exc:
            results.append({"label": candidate.label, "model": candidate.model, "error": str(exc)})
            continue
        results.append(result)
        print(
            f"{result['label']}: dims={result['dimensions']} "
            f"recall@5={result['quality']['recall@5']} "
            f"mrr={result['quality']['mrr']} "
            f"p95={result['warm_latency_ms']['p95']}ms"
        )

    payload = {
        "phase": 5,
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset.relative_to(BACKEND_ROOT.parent)).replace("\\", "/"),
        "documents": len(chunks),
        "candidates": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
