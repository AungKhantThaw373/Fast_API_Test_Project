"""IR metrics for the retrieval evaluation set.

Relevance is binary and evidence-based: a retrieved passage counts when its
chapter matches an expected evidence entry and the expected phrase appears in
the passage. That keeps the labels auditable without asking a second model to
grade the first.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.eval.dataset import ExpectedEvidence, Question


@dataclass(frozen=True)
class Retrieved:
    """The fields the evaluator needs from either retrieval pipeline."""

    chapter_number: int
    text: str


def is_relevant(item: Retrieved, evidence: Iterable[ExpectedEvidence]) -> bool:
    text = item.text.casefold()
    for expected in evidence:
        if expected.chapter_number == item.chapter_number and expected.quote_contains.casefold() in text:
            return True
    return False


def relevance_vector(question: Question, results: Sequence[Retrieved]) -> list[bool]:
    return [is_relevant(item, question.expected_evidence) for item in results]


def first_relevant_rank(relevance: Sequence[bool]) -> int | None:
    for index, relevant in enumerate(relevance, start=1):
        if relevant:
            return index
    return None


def recall_at_k(relevance: Sequence[bool], k: int) -> float:
    return 1.0 if any(relevance[:k]) else 0.0


def reciprocal_rank(relevance: Sequence[bool]) -> float:
    rank = first_relevant_rank(relevance)
    return 0.0 if rank is None else 1.0 / rank


def ndcg_at_k(relevance: Sequence[bool], k: int, *, ideal_relevant: int) -> float:
    """Binary-gain nDCG. ``ideal_relevant`` is the number of distinct expected hits."""
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, relevant in enumerate(relevance[:k], start=1)
        if relevant
    )
    ideal_count = min(max(ideal_relevant, 1), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(rows: Sequence[dict], *, k: int = 10) -> dict:
    """Aggregate per-question rows produced by ``app.eval.run``."""
    if not rows:
        return {"questions": 0}
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "questions": len(rows),
        "recall@5": round(sum(row["recall@5"] for row in rows) / len(rows), 4),
        "recall@10": round(sum(row["recall@10"] for row in rows) / len(rows), 4),
        "mrr": round(sum(row["reciprocal_rank"] for row in rows) / len(rows), 4),
        "ndcg@10": round(sum(row["ndcg@10"] for row in rows) / len(rows), 4),
        "hit_rate": round(sum(1 for row in rows if row["first_relevant_rank"]) / len(rows), 4),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
        "top_k": k,
    }


def summarize_by_type(rows: Sequence[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row["type"]), []).append(row)
    return {kind: summarize(items) for kind, items in sorted(groups.items())}


def continuity_scores(predictions: Sequence[tuple[bool, bool]]) -> dict:
    """Precision/recall/F1 from ``(expected, predicted)`` pairs."""
    true_positive = sum(1 for expected, predicted in predictions if expected and predicted)
    false_positive = sum(1 for expected, predicted in predictions if not expected and predicted)
    false_negative = sum(1 for expected, predicted in predictions if expected and not predicted)
    true_negative = sum(1 for expected, predicted in predictions if not expected and not predicted)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }
