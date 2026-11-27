"""Evaluation harness metrics and dataset contracts."""

from pathlib import Path

import pytest

from app.eval.dataset import load_continuity, load_manuscript, load_questions
from app.eval.metrics import (
    Retrieved,
    continuity_scores,
    first_relevant_rank,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    relevance_vector,
)

DATASETS = Path(__file__).resolve().parent.parent / "eval" / "datasets"


def test_relevance_requires_the_right_chapter_and_phrase():
    questions = load_questions(DATASETS / "stillroom.json")
    question = next(item for item in questions if item.id == "q001")
    results = [
        Retrieved(1, "Her eyes were blue."),
        Retrieved(3, "Her eyes were grey."),
        Retrieved(1, "Her eyes were grey in the lamplight."),
    ]
    assert relevance_vector(question, results) == [False, False, True]


def test_ranks_and_metrics():
    relevance = [False, False, True, False, True]
    assert first_relevant_rank(relevance) == 3
    assert reciprocal_rank(relevance) == pytest.approx(1 / 3)
    assert recall_at_k(relevance, 2) == 0.0
    assert recall_at_k(relevance, 3) == 1.0
    assert 0 < ndcg_at_k(relevance, 5, ideal_relevant=2) <= 1.0
    assert ndcg_at_k([], 10, ideal_relevant=1) == 0.0


def test_continuity_scores_count_false_positives():
    scores = continuity_scores([(True, True), (True, False), (False, True), (False, False)])
    assert scores["precision"] == 0.5
    assert scores["recall"] == 0.5
    assert scores["f1"] == 0.5
    assert scores["true_negative"] == 1


def test_datasets_are_well_formed():
    manuscript = load_manuscript(DATASETS / "manuscript.json")
    questions = load_questions(DATASETS / "stillroom.json")
    cases = load_continuity(DATASETS / "continuity.json")
    assert len(manuscript.chapters) == 12
    assert len(questions) >= 50
    assert len(cases) == 30
    positives = sum(1 for case in cases if case.expected_flag)
    assert positives == 15
    chapter_numbers = {chapter.number for chapter in manuscript.chapters}
    for question in questions:
        assert question.expected_evidence
        for evidence in question.expected_evidence:
            assert evidence.chapter_number in chapter_numbers
            chapter = next(item for item in manuscript.chapters if item.number == evidence.chapter_number)
            assert evidence.quote_contains in chapter.content
