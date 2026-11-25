"""Deterministic rules: each fires on a clear contradiction and stays quiet otherwise."""

from uuid import uuid4

from app.services.deterministic import FactRecord, RuleContext, check_pov, check_scene

ENTITY = uuid4()


def _context(*, age: str | None = None, eye: str | None = None, title: str | None = None) -> RuleContext:
    facts = []
    if age:
        facts.append(FactRecord(ENTITY, "age", age))
    if eye:
        facts.append(FactRecord(ENTITY, "eye_color", eye))
    if title:
        facts.append(FactRecord(ENTITY, "title", title))
    return RuleContext(
        names={ENTITY: "Mira Voss"},
        aliases={ENTITY: ["Mira"]},
        facts=facts,
    )


def test_age_contradiction_fires_with_full_sentence():
    findings = check_scene("Mira Voss was fifteen years old that winter.", 4, _context(age="17"))
    assert [finding.rule_id for finding in findings] == ["age_mismatch"]
    assert findings[0].line == 4
    assert findings[0].quote == "Mira Voss was fifteen years old that winter."


def test_age_near_misses_stay_quiet():
    context = _context(age="17")
    assert check_scene("Kael was fifteen years old that winter.", 1, context) == []
    assert check_scene("Mira was seventeen years old.", 1, context) == []
    assert check_scene("Mira was not fifteen years old.", 1, context) == []


def test_eye_colour_contradiction_and_negation():
    context = _context(eye="grey")
    findings = check_scene("Mira Voss watched him with her green eyes.", 2, context)
    assert len(findings) == 1
    assert findings[0].rule_id == "physical_mismatch"
    assert check_scene("Mira Voss did not have blue eyes.", 2, context) == []
    assert check_scene("Mira Voss had grey eyes.", 2, context) == []


def test_title_contradiction_needs_the_name_in_the_sentence():
    context = _context(title="Captain")
    findings = check_scene("Commander Mira Voss took the report.", 3, context)
    assert [finding.rule_id for finding in findings] == ["title_mismatch"]
    assert check_scene("The commander took the report.", 3, context) == []
    assert check_scene("Captain Mira Voss took the report.", 3, context) == []


def test_pov_flags_only_a_single_outlier_scene():
    first = "I walked to the yard and saw my brother waiting there for us.\nWe said nothing for a long moment."
    third = "She walked to the yard and saw her brother waiting there for them.\nThey said nothing for a long moment."
    findings = check_pov([(0, first, 1), (1, first, 5), (2, third, 9)])
    assert [finding.rule_id for finding in findings] == ["pov_shift"]
    assert findings[0].line == 9
    assert check_pov([(0, first, 1), (1, first, 5)]) == []


def test_short_sentence_never_fires():
    findings = check_scene("Mira is fifteen.", 1, _context(age="17"))
    assert findings == []
