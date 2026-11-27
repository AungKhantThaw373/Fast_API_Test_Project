"""Fail when a relative Markdown link points at a missing local file."""

from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    missing: list[tuple[Path, str]] = []
    checked = 0
    for markdown in sorted(root.glob("Docs/*.md")) + [root / "README.md", root / "AGENTS.md"]:
        if not markdown.exists():
            continue
        for target in LINK.findall(markdown.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            checked += 1
            if not (markdown.parent / target).resolve().exists():
                missing.append((markdown, target))
    for markdown, target in missing:
        print(f"MISSING {markdown.relative_to(root)} -> {target}")
    print(f"{checked} relative links checked, {len(missing)} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())