"""Measure read/save latency against a running Stillroom API.

Used by the Phase 9 scale report. It logs in once, picks the scale story,
warms the query path, and reports p50/p95/max for story list, story detail,
chapter load, hybrid search, and (optionally) a changed save on a temporary
probe chapter. The probe is deleted afterward.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from typing import Any

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(percentile(values, 0.95), 1),
        "max_ms": round(max(values), 1),
        "runs": len(values),
    }


def measure(label: str, action: Callable[[], Any], runs: int) -> dict[str, Any]:
    times: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        response = action()
        times.append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise RuntimeError(
                f"{label} returned {response.status_code}: {response.text[:300]}"
            )
    return {"endpoint": label, **summarize(times)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--email", default="scale@example.com")
    parser.add_argument("--password", default="scale fixture only")
    parser.add_argument("--query", default="The Grey Guild")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--save-iterations", type=int, default=10)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base, timeout=120.0) as client:
        bootstrap = client.get("/health")
        bootstrap.raise_for_status()
        csrf = client.cookies.get("csrf") or ""
        login = client.post(
            "/token",
            data={"username": args.email, "password": args.password},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-Token": csrf,
            },
        )
        login.raise_for_status()
        headers: dict[str, str] = {}
        stories = client.get("/stories", headers=headers)
        stories.raise_for_status()
        rows = stories.json()["stories"]
        story = next(
            (row for row in rows if row["title"] == "Synthetic Scale Serial"), rows[0]
        )
        story_id = story["id"]
        detail = client.get(f"/stories/{story_id}", headers=headers)
        detail.raise_for_status()
        chapters = detail.json()["chapters"]
        chapter = client.get(f"/stories/chapters/{chapters[0]['id']}", headers=headers)
        chapter.raise_for_status()

        search_timings: list[dict[str, float]] = []
        search_counter = 0
        run_nonce = str(time.time_ns())[-9:]

        def search_call():
            nonlocal search_counter
            # The API cache makes a repeated query a different measurement. Use
            # a unique query for every sample, including across repeated runs of
            # this script, so each one embeds and scans.
            text = f"{args.query} variant {run_nonce}-{search_counter}"
            search_counter += 1
            response = client.get(
                f"/stories/{story_id}/search",
                params={"q": text, "limit": 20},
                headers=headers,
            )
            if response.status_code == 200:
                search_timings.append(response.json().get("timings_ms", {}))
            return response

        search_call()
        results = [
            measure(
                "stories.list",
                lambda: client.get("/stories", headers=headers),
                args.iterations,
            ),
            measure(
                "story.detail",
                lambda: client.get(f"/stories/{story_id}", headers=headers),
                args.iterations,
            ),
            measure(
                "chapter.load",
                lambda: client.get(
                    f"/stories/chapters/{chapters[0]['id']}", headers=headers
                ),
                args.iterations,
            ),
            measure("search.hybrid", search_call, args.iterations),
        ]
        stages = {
            key: summarize([row[key] for row in search_timings if key in row])
            for key in ("embed", "vector", "lexical", "name", "fusion", "total")
            if any(key in row for row in search_timings)
        }
        save_probe_id = None
        if args.save:
            save_headers = {**headers, "X-CSRF-Token": client.cookies.get("csrf") or ""}
            probe = client.post(
                f"/stories/{story_id}/chapters",
                headers=save_headers,
                json={
                    "title": "Scale save probe",
                    "content": (
                        "The lantern keeper counted the boats and wrote the hour in the ledger. "
                        * 180
                    ),
                },
            )
            probe.raise_for_status()
            probe_body = probe.json()
            save_probe_id = probe_body["id"]

            def changed_save():
                nonlocal probe_body
                probe_body["content"] += "\n\nThe tide turned again."
                response = client.put(
                    f"/stories/chapters/{save_probe_id}",
                    headers=save_headers,
                    json={
                        "title": probe_body["title"],
                        "content": probe_body["content"],
                        "expected_revision": probe_body["revision"],
                    },
                )
                if response.status_code == 200:
                    probe_body = response.json()
                return response

            results.append(
                measure("chapter.save_changed", changed_save, args.save_iterations)
            )
            cleanup = client.delete(
                f"/stories/chapters/{save_probe_id}", headers=save_headers
            )
            cleanup.raise_for_status()
        output = {
            "base": args.base,
            "story_id": story_id,
            "chapters": len(chapters),
            "query": args.query,
            "search_stages_ms": stages,
            "save_probe_id": save_probe_id,
            "results": results,
        }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
