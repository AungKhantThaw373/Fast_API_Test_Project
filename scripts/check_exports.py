"""Exercise story and account exports against a running API."""

from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--email", default="scale@example.com")
    parser.add_argument("--password", default="scale fixture only")
    parser.add_argument("--title", default="Synthetic Scale Serial")
    parser.add_argument("--output", type=Path, default=Path("backups/scale-exports"))
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []

    with httpx.Client(base_url=args.base, timeout=600) as client:
        client.get("/health")
        csrf = client.cookies.get("csrf") or ""
        login = client.post(
            "/token",
            data={"username": args.email, "password": args.password},
            headers={"X-CSRF-Token": csrf},
        )
        checks.append(("login", login.status_code == 200, str(login.status_code)))
        stories = client.get("/stories", params={"limit": 200}).json()["stories"]
        story = next((row for row in stories if row["title"] == args.title), None)
        checks.append(("story present", story is not None, args.title))
        if story is None:
            raise SystemExit(1)
        story_id = story["id"]

        started = time.perf_counter()
        backup = client.get(f"/stories/{story_id}/backup")
        elapsed = time.perf_counter() - started
        payload = backup.json()
        backup_path = args.output / "story-backup.json"
        backup_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        chapters = payload.get("chapters", [])
        checks.append(
            (
                "story backup",
                backup.status_code == 200 and len(chapters) >= 1100,
                f"{len(chapters)} chapters, {elapsed:.1f}s",
            )
        )

        for fmt, ext in (("markdown", "md"), ("docx", "docx"), ("epub", "epub")):
            started = time.perf_counter()
            response = client.get(f"/stories/{story_id}/export", params={"format": fmt, "include_wiki": True})
            elapsed = time.perf_counter() - started
            path = args.output / f"story.{ext}"
            path.write_bytes(response.content)
            ok = response.status_code == 200 and len(response.content) > 10_000
            if ext in ("docx", "epub"):
                ok = ok and response.content[:2] == b"PK"
            checks.append((f"export {fmt}", ok, f"{len(response.content)} bytes, {elapsed:.1f}s"))

        if args.pdf:
            started = time.perf_counter()
            response = client.get(f"/stories/{story_id}/export", params={"format": "pdf", "include_wiki": True})
            elapsed = time.perf_counter() - started
            path = args.output / "story.pdf"
            path.write_bytes(response.content)
            checks.append(
                (
                    "export pdf",
                    response.status_code == 200 and response.content.startswith(b"%PDF"),
                    f"{len(response.content)} bytes, {elapsed:.1f}s",
                )
            )

        started = time.perf_counter()
        account = client.get("/account/export")
        elapsed = time.perf_counter() - started
        account_path = args.output / "account.zip"
        account_path.write_bytes(account.content)
        names = zipfile.ZipFile(io.BytesIO(account.content)).namelist() if account.status_code == 200 else []
        has_stories = any(name.endswith("stories.json") or "stories" in name for name in names)
        checks.append(
            (
                "account export",
                account.status_code == 200 and has_stories,
                f"{len(names)} members, {elapsed:.1f}s",
            )
        )

    for name, ok, detail in checks:
        print(("PASS " if ok else "FAIL ") + name + (" - " + detail if detail else ""))
    for path in sorted(args.output.iterdir()):
        print(f"{path.name}: {path.stat().st_size} bytes")
    failed = [row for row in checks if not row[1]]
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())