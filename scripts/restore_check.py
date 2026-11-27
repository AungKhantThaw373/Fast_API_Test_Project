"""Read-only check that a restored database still serves the scale story."""

from __future__ import annotations

import argparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8003")
    parser.add_argument("--email", default="scale@example.com")
    parser.add_argument("--password", default="scale fixture only")
    parser.add_argument("--title", default="Synthetic Scale Serial")
    args = parser.parse_args()
    checks: list[tuple[str, bool, str]] = []

    with httpx.Client(base_url=args.base, timeout=120) as client:
        client.get("/health")
        csrf = client.cookies.get("csrf") or ""
        login = client.post(
            "/token",
            data={"username": args.email, "password": args.password},
            headers={"X-CSRF-Token": csrf},
        )
        checks.append(("login", login.status_code == 200, str(login.status_code)))
        stories = client.get("/stories", params={"limit": 200})
        checks.append(("story list", stories.status_code == 200, str(stories.status_code)))
        story = next(
            (row for row in stories.json().get("stories", []) if row["title"] == args.title),
            None,
        )
        checks.append(("scale story present", story is not None, args.title))
        if story is None:
            story_id = ""
            chapter_id = ""
            detail = None
        else:
            story_id = story["id"]
            detail = client.get(f"/stories/{story_id}")
            checks.append(("story detail", detail.status_code == 200, str(detail.status_code)))
            chapters = detail.json().get("chapters", []) if detail is not None else []
            checks.append(("chapters readable", len(chapters) >= 1100, str(len(chapters))))
            chapter_id = chapters[0]["id"] if chapters else ""
        if chapter_id:
            chapter = client.get(f"/stories/chapters/{chapter_id}")
            load_ok = (
                chapter.status_code == 200
                and len(chapter.json().get("content", "")) > 0
            )
            checks.append(("chapter load", load_ok, str(chapter.status_code)))
        if story_id:
            search = client.get(
                f"/stories/{story_id}/search", params={"q": "Grey Guild restored copy", "limit": 5}
            )
            search_ok = (
                search.status_code == 200
                and len(search.json().get("results", [])) > 0
            )
            checks.append(("hybrid search", search_ok, str(search.status_code)))

    for name, ok, detail_text in checks:
        print(("PASS " if ok else "FAIL ") + name + (" - " + detail_text if detail_text else ""))
    failed = [row for row in checks if not row[1]]
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())