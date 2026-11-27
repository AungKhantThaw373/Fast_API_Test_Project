from uuid import uuid4

from app.services.finding_filter import EvidenceRef, filter_findings

EARLIER = EvidenceRef(
    id="evidence-1",
    chapter_id=uuid4(),
    chapter_number=2,
    text="Her grey eyes caught the lamplight as she turned away.",
)


def _candidate(**overrides):
    payload = {
        "draft_line": 1,
        "draft_quote": "his blue eyes narrowed",
        "evidence_id": "evidence-1",
        "earlier_quote": "Her grey eyes caught the lamplight",
        "explanation": "Eye colour contradicts chapter 2.",
        "confidence": 88,
    }
    payload.update(overrides)
    return payload


def test_a_verifiable_finding_is_kept():
    lines = ["his blue eyes narrowed at the door"]
    findings = filter_findings([_candidate()], lines, {"evidence-1": EARLIER})
    assert len(findings) == 1
    assert findings[0].draft_line == 1
    assert findings[0].earlier_chapter_number == 2


def test_a_fabricated_draft_quote_is_rejected():
    lines = ["his blue eyes narrowed at the door"]
    candidate = _candidate(draft_quote="his green eyes widened")
    assert filter_findings([candidate], lines, {"evidence-1": EARLIER}) == []


def test_a_fabricated_earlier_quote_is_rejected():
    lines = ["his blue eyes narrowed at the door"]
    candidate = _candidate(earlier_quote="Her violet eyes caught the lamplight")
    assert filter_findings([candidate], lines, {"evidence-1": EARLIER}) == []


def test_an_unknown_evidence_id_is_rejected():
    lines = ["his blue eyes narrowed at the door"]
    candidate = _candidate(evidence_id="not-supplied")
    assert filter_findings([candidate], lines, {"evidence-1": EARLIER}) == []


def test_short_quotes_are_rejected():
    lines = ["his blue eyes narrowed at the door"]
    candidate = _candidate(draft_quote="eyes", earlier_quote="grey eyes")
    assert filter_findings([candidate], lines, {"evidence-1": EARLIER}) == []


def test_low_confidence_findings_are_rejected():
    lines = ["his blue eyes narrowed at the door"]
    assert filter_findings([_candidate(confidence=20)], lines, {"evidence-1": EARLIER}) == []


def test_out_of_range_line_numbers_are_rejected():
    lines = ["his blue eyes narrowed at the door"]
    assert filter_findings([_candidate(draft_line=4)], lines, {"evidence-1": EARLIER}) == []


def test_duplicate_findings_collapse_to_the_highest_confidence():
    lines = ["his blue eyes narrowed at the door"]
    findings = filter_findings(
        [_candidate(confidence=60), _candidate(confidence=95)],
        lines,
        {"evidence-1": EARLIER},
    )
    assert len(findings) == 1
    assert findings[0].confidence == 95


def test_per_line_cap_is_enforced():
    lines = ["his blue eyes narrowed at the door while the lantern guttered and he waited"]
    quotes = [
        "his blue eyes narrowed",
        "at the door while",
        "the lantern guttered",
        "and he waited",
        "blue eyes narrowed at",
        "while the lantern",
    ]
    candidates = [
        _candidate(draft_quote=quote, explanation=f"Contradiction number {index}")
        for index, quote in enumerate(quotes)
    ]
    assert len(filter_findings(candidates, lines, {"evidence-1": EARLIER})) == 3


def test_non_list_payload_is_ignored():
    assert filter_findings({"findings": []}, ["text"], {}) == []
