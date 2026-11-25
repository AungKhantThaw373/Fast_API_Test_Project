"""End-to-end lazy canon drill against the local API and Ollama worker."""

import json
import time

import httpx

BASE = "http://127.0.0.1:8000"
STAMP = int(time.time() * 1000)
EMAIL = f"canondrill{STAMP}@example.com"
PASSWORD = "correct horse battery"

with httpx.Client(base_url=BASE, timeout=60) as client:
    client.get("/health").raise_for_status()
    csrf = client.cookies.get("csrf") or ""
    headers = {"X-CSRF-Token": csrf}
    response = client.post(
        "/register",
        json={"username": f"canondrill{STAMP}", "email": EMAIL, "password": PASSWORD},
        headers=headers,
    )
    response.raise_for_status()
    response = client.post(
        "/token",
        data={"username": EMAIL, "password": PASSWORD},
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    headers["X-CSRF-Token"] = client.cookies.get("csrf") or csrf

    response = client.put(
        "/ai-settings",
        json={
            "provider": "ollama",
            "model": "qwen3:4b-instruct",
            "base_url": "http://127.0.0.1:11434",
        },
        headers=headers,
    )
    response.raise_for_status()

    story = client.post(
        "/stories", json={"title": f"Canon extraction drill {STAMP}"}, headers=headers
    ).json()
    chapter = client.post(
        f"/stories/{story['id']}/chapters",
        json={
            "title": "The gate",
            "content": "Mira Voss crossed the yard at dawn. The gatekeeper watched her go and said nothing.",
        },
        headers=headers,
    ).json()
    arc = client.post(
        f"/stories/{story['id']}/arcs", json={"name": "Opening"}, headers=headers
    ).json()
    client.put(
        f"/stories/{story['id']}/arcs",
        json={"arc_id": arc["id"], "chapter_ids": [chapter["id"]]},
        headers=headers,
    ).raise_for_status()

    queued = client.post(
        f"/stories/{story['id']}/canon/arcs/{arc['id']}/extract", headers=headers
    )
    queued.raise_for_status()
    print("queued", queued.status_code, queued.json())

    deadline = time.time() + 180
    last = None
    while time.time() < deadline:
        coverage = client.get(f"/stories/{story['id']}/canon/coverage").json()
        last = coverage["arcs"][0]
        print(
            "coverage",
            last["extracted_count"],
            "/",
            last["chapter_count"],
            "pending",
            last["pending_count"],
        )
        if last["extracted_count"] == last["chapter_count"]:
            break
        time.sleep(3)
    else:
        raise SystemExit("extraction did not finish: " + json.dumps(last))
    print("STORY", story["id"])
    print("ARC", arc["id"])
    print("EMAIL", EMAIL)
