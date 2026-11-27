"""Smoke-test a freshly migrated API: auth, create, load, save, delete."""

from __future__ import annotations

import argparse
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    stamp = int(time.time())
    email = f"fresh{stamp}@example.com"
    password = "correct horse battery"
    checks: list[tuple[str, bool, str]] = []

    with httpx.Client(base_url=args.base, timeout=60) as client:
        health = client.get("/health")
        csrf = client.cookies.get("csrf")
        checks.append(("health", health.status_code == 200, str(health.status_code)))
        checks.append(("csrf cookie", bool(csrf), csrf or "missing"))
        ready = client.get("/ready")
        checks.append(("ready", ready.status_code == 200, ready.text[:160]))
        headers = {"X-CSRF-Token": csrf or ""}
        registered = client.post(
            "/register",
            json={"username": f"fresh{stamp}", "email": email, "password": password},
            headers=headers,
        )
        checks.append(("register", registered.status_code == 201, str(registered.status_code)))
        login = client.post(
            "/token",
            data={"username": email, "password": password},
            headers=headers,
        )
        checks.append(("login", login.status_code == 200, str(login.status_code)))
        story_response = client.post(
            "/stories", json={"title": f"Fresh install {stamp}"}, headers=headers
        )
        story = story_response.json()
        checks.append(("create story", story_response.status_code == 201, str(story_response.status_code)))
        chapter_response = client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "First Light", "content": "The first sentence of a fresh database."},
            headers=headers,
        )
        chapter = chapter_response.json()
        checks.append(("create chapter", chapter_response.status_code == 201, str(chapter_response.status_code)))
        detail = client.get(f"/stories/{story['id']}")
        detail_ok = detail.status_code == 200 and detail.json()["chapter_count"] == 1
        checks.append(("story detail", detail_ok, str(detail.status_code)))
        saved = client.put(
            f"/stories/chapters/{chapter['id']}",
            json={
                "content": "The first sentence, revised after a fresh install.",
                "expected_revision": chapter["revision"],
            },
            headers=headers,
        )
        save_ok = (
            saved.status_code == 200
            and saved.json()["revision"] == chapter["revision"] + 1
        )
        checks.append(("save chapter", save_ok, str(saved.status_code)))
        removed = client.delete(f"/stories/{story['id']}", headers=headers)
        checks.append(("trash story", removed.status_code == 204, str(removed.status_code)))

    for name, ok, detail in checks:
        print(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""))
    failed = [row for row in checks if not row[1]]
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())