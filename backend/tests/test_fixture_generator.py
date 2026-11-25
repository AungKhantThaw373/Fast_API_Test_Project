from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_fixture.py"


def _generate(out: Path, chapters: int = 6) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--chapters", str(chapters),
            "--words", "90",
            "--contradictions", "2",
            "--near-misses", "2",
            "--threads", "3",
            "--resolved-threads", "1",
            "--out", str(out),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_fixture_is_deterministic_and_structured(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest = _generate(first)
    _generate(second)

    assert manifest["totals"]["chapters"] == 6
    assert manifest["totals"]["characters"] == 300
    assert manifest["totals"]["locations"] == 150
    assert manifest["totals"]["items"] == 200
    assert manifest["totals"]["organizations"] == 100
    assert manifest["totals"]["contradictions"] == 2
    assert manifest["totals"]["near_misses"] == 2
    for name in ("chapters.jsonl", "entities.json", "contradictions.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    chapters = [
        json.loads(line)
        for line in (first / "chapters.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["number"] for row in chapters] == list(range(1, 7))
    for row in chapters:
        assert row["content"].count("### Scene ") == 3
        assert row["word_count"] == len(row["content"].split())


def test_planted_quotes_exist_in_the_right_chapters(tmp_path: Path) -> None:
    _generate(tmp_path)
    chapters = {
        row["number"]: row["content"]
        for row in (
            json.loads(line)
            for line in (tmp_path / "chapters.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    contradictions = json.loads(
        (tmp_path / "contradictions.json").read_text(encoding="utf-8")
    )
    assert len(contradictions) == 2
    for row in contradictions:
        assert row["canonical_quote"] in chapters[row["canonical_chapter"]]
        assert row["contradiction_quote"] in chapters[row["contradiction_chapter"]]
        assert row["near_quote"] in chapters[row["near_chapter"]]
        assert row["canonical_quote"] != row["contradiction_quote"]
        assert row["near_quote"] != row["contradiction_quote"]

    near = json.loads((tmp_path / "near_misses.json").read_text(encoding="utf-8"))
    assert len(near) == 2
    assert all(row["reason"] for row in near)