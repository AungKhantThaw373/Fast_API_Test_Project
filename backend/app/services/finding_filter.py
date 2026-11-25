"""Deterministic validation of AI continuity findings.

The model proposes; this module decides. Every finding must quote text that
actually exists in the draft line and in the cited earlier passage. That makes
fabricated evidence impossible and keeps the behaviour unit-testable without a
provider in the loop.
"""

from dataclasses import dataclass
from uuid import UUID

# A finding is only useful when both sides quote real, reasonably specific text.
# Short fragments ("i", "dual", a single name) match almost any passage and
# produced false contradictions on nearly every line.
MIN_DRAFT_QUOTE_CHARS = 10
MIN_EARLIER_QUOTE_CHARS = 15
MIN_CONFIDENCE = 50
MAX_FINDINGS_PER_LINE = 3
MAX_CANDIDATES = 20

VALID_REVIEW_STATUSES = {"open", "resolved", "dismissed"}


@dataclass(frozen=True)
class EvidenceRef:
    """The slice of an earlier passage an AI finding can cite."""

    id: str
    chapter_id: UUID
    chapter_number: int
    text: str


@dataclass
class DraftFinding:
    draft_quote: str
    draft_line: int
    earlier_quote: str | None
    earlier_chapter_id: UUID | None
    earlier_chapter_number: int
    explanation: str
    confidence: int
    source: str = "llm"
    rule_id: str | None = None
    scene_index: int | None = None
    evidence_kind: str | None = None
    evidence_id: str | None = None


def filter_findings(
    candidates: object,
    manuscript_lines: list[str],
    evidence_by_id: dict[str, EvidenceRef],
) -> list[DraftFinding]:
    """Keep only findings whose quotes verifiably exist in the manuscript."""
    if not isinstance(candidates, list):
        return []

    findings: list[DraftFinding] = []
    for item in candidates[:MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        try:
            line_number = int(item.get("draft_line", 0))
            confidence = max(0, min(100, int(item.get("confidence", 50))))
        except (TypeError, ValueError):
            continue
        draft_quote = str(item.get("draft_quote", "")).strip()[:500]
        evidence_id = str(item.get("evidence_id", ""))
        earlier_quote = str(item.get("earlier_quote", "")).strip()[:1000]
        source = evidence_by_id.get(evidence_id)
        if not (1 <= line_number <= len(manuscript_lines)) or source is None:
            continue
        if confidence < MIN_CONFIDENCE:
            continue
        if len(draft_quote) < MIN_DRAFT_QUOTE_CHARS or len(earlier_quote) < MIN_EARLIER_QUOTE_CHARS:
            continue
        if draft_quote not in manuscript_lines[line_number - 1]:
            continue
        if earlier_quote not in source.text:
            continue
        explanation = str(item.get("explanation", "")).strip()[:1600]
        if not explanation:
            continue
        findings.append(
            DraftFinding(
                draft_quote=draft_quote,
                draft_line=line_number,
                earlier_quote=earlier_quote,
                earlier_chapter_id=source.chapter_id,
                earlier_chapter_number=source.chapter_number,
                explanation=explanation,
                confidence=confidence,
            )
        )

    # The same claim often comes back once per retrieved chunk. Collapse those to
    # the highest-confidence version before capping how many a single line shows.
    by_explanation: dict[tuple[int, str], DraftFinding] = {}
    for finding in findings:
        key = (finding.draft_line, finding.explanation.casefold())
        current = by_explanation.get(key)
        if current is None or finding.confidence > current.confidence:
            by_explanation[key] = finding

    per_line: dict[int, int] = {}
    unique: dict[tuple[int, str, str], DraftFinding] = {}
    for finding in sorted(by_explanation.values(), key=lambda value: (-value.confidence, value.draft_line)):
        if per_line.get(finding.draft_line, 0) >= MAX_FINDINGS_PER_LINE:
            continue
        per_line[finding.draft_line] = per_line.get(finding.draft_line, 0) + 1
        key = (
            finding.draft_line,
            finding.draft_quote.casefold(),
            (finding.earlier_quote or "").casefold(),
        )
        unique[key] = finding
    return [unique[key] for key in sorted(unique, key=lambda value: value[0])]
