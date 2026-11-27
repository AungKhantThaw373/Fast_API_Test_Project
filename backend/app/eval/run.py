"""Phase 5 evaluation CLI.

Examples::

    cd backend
    uv run python -m app.eval.run --mode legacy \
        --out ../Docs/eval/baseline.json

Retrieval runs need PostgreSQL and Ollama (``nomic-embed-text`` by default).
The report records zero provider calls and zero tokens for retrieval-only runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from app.config import settings
from app.db import async_session, engine
from app.eval.dataset import load_continuity, load_manuscript, load_questions
from app.eval.metrics import (
    Retrieved,
    continuity_scores,
    first_relevant_rank,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    relevance_vector,
    summarize,
    summarize_by_type,
)
from app.eval.seed import seed_eval_story
from app.services.ai_service import embed_queries
from app.services.retrieval import search_chunks

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = BACKEND_ROOT / "eval" / "datasets"

LEGACY_SQL = text(
    """
    SELECT e.chapter_number, e.text, e.embedding <=> CAST(:vector AS vector) AS distance
    FROM story_scene_embeddings e
    JOIN story_chapters c
      ON c.id = e.chapter_id
     AND c.index_status = 'indexed'
    WHERE e.story_id = :story_id
    ORDER BY e.embedding <=> CAST(:vector AS vector)
    LIMIT :limit
    """
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stillroom retrieval and continuity evaluation")
    parser.add_argument("--dataset", type=Path, default=DATASET_ROOT / "stillroom.json")
    parser.add_argument("--manuscript", type=Path, default=DATASET_ROOT / "manuscript.json")
    parser.add_argument("--continuity", action="store_true", help="also run the seeded contradiction set")
    parser.add_argument("--continuity-dataset", type=Path, default=DATASET_ROOT / "continuity.json")
    parser.add_argument("--continuity-judge", choices=("none", "ollama"), default="none")
    parser.add_argument("--continuity-limit", type=int, default=None)
    parser.add_argument("--continuity-model", default="qwen2.5-coder:7b-instruct-q4_K_M")
    parser.add_argument("--mode", choices=("legacy", "hybrid"), default="legacy")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None, help="run only the first N questions")
    parser.add_argument("--skip-seed", action="store_true", help="reuse the existing evaluation story")
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def vector_literal(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


async def legacy_search(session, story_id, vector: list[float], limit: int) -> list[Retrieved]:
    rows = (
        await session.execute(
            LEGACY_SQL,
            {"story_id": story_id, "vector": vector_literal(vector), "limit": limit},
        )
    ).all()
    return [Retrieved(chapter_number=int(row.chapter_number), text=str(row.text)) for row in rows]


async def evaluate_retrieval(args: argparse.Namespace, questions) -> list[dict]:
    rows: list[dict] = []
    async with async_session() as session:
        for question in questions:
            started = time.perf_counter()
            if args.mode == "legacy":
                vector = embed_queries([question.question])[0]
                embedded_ms = (time.perf_counter() - started) * 1000
                results = await legacy_search(session, args.story_id, vector, args.top_k)
            else:
                hybrid = await search_chunks(
                    session, args.story_id, question.question, limit=args.top_k, use_cache=False
                )
                embedded_ms = hybrid.timings_ms.get("embed", 0.0)
                results = [
                    Retrieved(chapter_number=hit.chapter_number, text=hit.text)
                    for hit in hybrid.chunks
                ]
            elapsed_ms = (time.perf_counter() - started) * 1000
            relevance = relevance_vector(question, results)
            rank = first_relevant_rank(relevance)
            rows.append(
                {
                    "id": question.id,
                    "type": question.type,
                    "question": question.question,
                    "latency_ms": round(elapsed_ms, 2),
                    "embedding_ms": round(embedded_ms, 2),
                    "first_relevant_rank": rank,
                    "recall@5": recall_at_k(relevance, 5),
                    "recall@10": recall_at_k(relevance, 10),
                    "reciprocal_rank": round(reciprocal_rank(relevance), 4),
                    "ndcg@10": round(
                        ndcg_at_k(relevance, 10, ideal_relevant=len(question.expected_evidence)), 4
                    ),
                    "retrieved": [
                        {
                            "chapter_number": item.chapter_number,
                            "relevant": relevant,
                            "preview": " ".join(item.text.split())[:220],
                        }
                        for item, relevant in zip(results, relevance, strict=True)
                    ],
                }
            )
    return rows


async def ollama_judge(case, model: str) -> tuple[bool, str]:
    system = (
        "You are a continuity editor. Decide whether the DRAFT line contradicts the ESTABLISHED fact. "
        "A character lying, a belief, uncertainty, a deliberate later change explained in the line, or a new "
        "detail that does not conflict is NOT a contradiction. Answer with JSON only: "
        "{\"contradiction\": true or false, \"reason\": \"brief\"}"
    )
    prompt = f"ESTABLISHED: {case.established}\nDRAFT: {case.draft}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10)) as client:
        response = await client.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    content = data.get("message", {}).get("content", "{}")
    try:
        verdict = json.loads(content)
    except json.JSONDecodeError:
        return False, f"unparseable judge response: {content[:200]}"
    return bool(verdict.get("contradiction")), str(verdict.get("reason", ""))


async def evaluate_continuity(args: argparse.Namespace) -> dict:
    cases = load_continuity(args.continuity_dataset)
    if args.continuity_limit:
        cases = cases[: args.continuity_limit]
    positives = sum(1 for case in cases if case.expected_flag)
    report: dict[str, Any] = {
        "dataset": str(args.continuity_dataset),
        "cases": len(cases),
        "positives": positives,
        "negatives": len(cases) - positives,
    }
    if args.continuity_judge == "none":
        report["skipped"] = "no judge selected; dataset validated only"
        return report
    predictions: list[tuple[bool, bool]] = []
    results: list[dict] = []
    for case in cases:
        started = time.perf_counter()
        predicted, reason = await ollama_judge(case, args.continuity_model)
        predictions.append((case.expected_flag, predicted))
        results.append(
            {
                "id": case.id,
                "expected": case.expected_flag,
                "predicted": predicted,
                "note": case.note,
                "reason": reason,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    report.update(continuity_scores(predictions))
    report["judge"] = f"ollama:{args.continuity_model}"
    report["provider_calls"] = len(cases)
    report["results"] = results
    return report


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> dict:
    questions = load_questions(args.dataset)
    if args.limit:
        questions = questions[: args.limit]
    if not args.skip_seed:
        manuscript = load_manuscript(args.manuscript)
        async with async_session() as session:
            seeded = await seed_eval_story(session, manuscript)
            args.story_id = seeded.story_id
    else:
        from app.eval.seed import EVAL_STORY_ID

        args.story_id = EVAL_STORY_ID

    # A cold embedding model would otherwise land in the first measured query.
    embed_queries(["warm up"])
    rows = await evaluate_retrieval(args, questions)
    report: dict[str, Any] = {
        "phase": 5,
        "harness": "retrieval-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "embedding_model": settings.EMBEDDING_MODEL,
        "dataset": str(args.dataset),
        "top_k": args.top_k,
        "provider_calls": 0,
        "tokens": {"input": 0, "output": 0},
        "metrics": summarize(rows, k=args.top_k),
        "by_type": summarize_by_type(rows),
        "results": rows,
    }
    if args.continuity:
        report["continuity"] = await evaluate_continuity(args)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    async def _main() -> dict:
        try:
            return await run(args)
        finally:
            await engine.dispose()

    report = asyncio.run(_main())
    metrics = report["metrics"]
    summary = [
        "mode=" + str(report["mode"]),
        "questions=" + str(metrics["questions"]),
        "recall@5=" + str(metrics.get("recall@5")),
        "recall@10=" + str(metrics.get("recall@10")),
        "mrr=" + str(metrics.get("mrr")),
        "ndcg@10=" + str(metrics.get("ndcg@10")),
        "p50=" + str(metrics.get("latency_ms", {}).get("p50")) + "ms",
        "p95=" + str(metrics.get("latency_ms", {}).get("p95")) + "ms",
    ]
    print(" ".join(summary))
    if "continuity" in report:
        continuity = report["continuity"]
        print(
            "continuity cases=" + str(continuity["cases"]),
            "precision=" + str(continuity.get("precision")),
            "recall=" + str(continuity.get("recall")),
            "f1=" + str(continuity.get("f1")),
        )
    if args.out:
        write_report(args.out, report)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
