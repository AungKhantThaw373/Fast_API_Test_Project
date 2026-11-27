"""Phase 6 limits: huge and CJK chapters stay bounded and never crash rules."""

from time import monotonic
from uuid import uuid4

from app.services.ai_usage import estimate_scan_tokens
from app.services.chunking import detect_scenes
from app.services.deterministic import RuleContext, check_pov, check_scene


def test_two_hundred_thousand_character_chapter_is_split_without_quadratic_work():
    content = ("Mira walked to the gate and waited. " * 5600)[:200_000]
    started = monotonic()
    scenes = detect_scenes(content)
    elapsed = monotonic() - started
    assert scenes
    assert len(content) == 200_000
    assert elapsed < 2.0, elapsed
    assert sum(len(scene.text) for scene in scenes) > 190_000


def test_cjk_chapter_without_latin_punctuation_stays_chunked_and_safe():
    content = "米拉走过院子，门锁着。\n\n" * 5000
    scenes = detect_scenes(content)
    assert scenes
    assert all(scene.text for scene in scenes)
    context = RuleContext(names={uuid4(): "米拉"}, aliases={}, facts=[])
    for scene in scenes:
        assert check_scene(scene.text, scene.start_line, context) == []
    assert check_pov(
        [(index, scene.text, scene.start_line) for index, scene in enumerate(scenes)]
    ) == []


def test_scan_estimate_stays_bounded_for_a_huge_chapter():
    inputs, outputs = estimate_scan_tokens(200_000)
    assert inputs == 50_000
    assert 200 <= outputs <= 1200
