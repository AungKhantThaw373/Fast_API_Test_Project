from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "import_fixture.py"


def _module():
    spec = importlib.util.spec_from_file_location("scale_import", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_synthetic_vectors_are_deterministic_unit_vectors() -> None:
    module = _module()
    first = module.synthetic_vector("chapter:1:0")
    second = module.synthetic_vector("chapter:1:0")
    other = module.synthetic_vector("chapter:1:1")
    assert first == second
    assert first != other
    assert len(first) == 768
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-9)
    assert all(-1.0 <= value <= 1.0 for value in first)


def test_fixture_loader_and_token_estimate(tmp_path: Path) -> None:
    (tmp_path / "chapters.jsonl").write_text(
        json.dumps({"number": 1, "title": "One", "arc": "Arc 1", "word_count": 3,
                    "content": "one two three"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(json.dumps({"seed": 1}), encoding="utf-8")
    for name, payload in (
        ("entities", {"characters": [], "locations": [], "items": [], "organizations": []}),
        ("arcs", []),
        ("threads", []),
        ("contradictions", []),
    ):
        (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = _module().load_fixture(tmp_path)
    assert loaded["manifest"]["seed"] == 1
    assert loaded["chapters"][0]["number"] == 1
    assert _module().estimate_tokens("one two three") == 4


def test_importer_refuses_the_real_database() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", "stillroom", "--limit", "1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "non-scale database" in (result.stdout + result.stderr)