"""Mixed read/write soak against the synthetic scale story.

Runs search, chapter load, story detail, and periodic saves while a worker
reindexes the saved chapter. It records actual elapsed time, latency, and
failures; it does not turn a short run into a 24-hour claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

QUERIES = [
    "Grey Guild",
    "lighthouse keeper",
    "the archive",
    "Kestrel",
    "broken oath",
    "northern road",
    "the silent bell",
    "ash and salt",
]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 1)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--email", default="scale@example.com")
    parser.add_argument("--password", default="scale fixture only")
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--save-every", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("Docs/eval/soak.json"))
    args = parser.parse_args()

    latencies: dict[str, list[float]] = defaultdict(list)
    errors: list[str] = []
    counts: dict[str, int] = defaultdict(int)
    started = time.monotonic()
    deadline = started + args.minutes * 60
    random.seed(9)

    async with httpx.AsyncClient(base_url=args.base, timeout=120) as client:
        health = await client.get("/health")
        health.raise_for_status()
        csrf = client.cookies.get("csrf")
        if not csrf:
            raise RuntimeError("no csrf cookie from /health")
        login = await client.post(
            "/token",
            data={"username": args.email, "password": args.password},
            headers={"X-CSRF-Token": csrf},
        )
        login.raise_for_status()

        stories = (await client.get("/stories", params={"limit": 200})).json()["stories"]
        story = next((row for row in stories if row["title"] == "Synthetic Scale Serial"), None)
        if story is None:
            raise RuntimeError("Synthetic Scale Serial is not in this account")
        story_id = story["id"]

        detail = await client.get(f"/stories/{story_id}")
        detail.raise_for_status()
        chapters = detail.json()["chapters"]
        probe = next((row for row in chapters if row["title"] == "Soak probe"), None)
        if probe is None:
            response = await client.post(
                f"/stories/{story_id}/chapters",
                json={"title": "Soak probe", "content": "A quiet probe chapter for the Phase 9 soak. " * 120},
                headers={"X-CSRF-Token": csrf},
            )
            response.raise_for_status()
            probe = response.json()
        probe_id = probe["id"]

        async def measured(name: str, request):
            nonlocal errors
            counts[name] += 1
            before = time.perf_counter()
            try:
                response = await request
                if response.status_code >= 500:
                    errors.append(f"{name}: HTTP {response.status_code}")
                response.raise_for_status()
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                return None
            finally:
                latencies[name].append((time.perf_counter() - before) * 1000)
            return response

        last_save = 0.0
        iteration = 0
        while time.monotonic() < deadline:
            iteration += 1
            remaining = max(1, int(deadline - time.monotonic()))
            print(f"[{iteration}] {remaining}s left; ops={sum(counts.values())}; errors={len(errors)}", flush=True)
            await measured("stories.list", client.get("/stories", params={"limit": 200}))
            await measured("story.detail", client.get(f"/stories/{story_id}"))
            await measured("chapter.load", client.get(f"/stories/chapters/{probe_id}"))
            query = random.choice(QUERIES) + f" run {iteration}-{int(time.time())}"
            await measured(
                "search.hybrid",
                client.get(f"/stories/{story_id}/search", params={"q": query, "limit": 10}),
            )

            now = time.monotonic()
            if now - last_save >= args.save_every:
                last_save = now
                current = await measured("chapter.read_for_save", client.get(f"/stories/chapters/{probe_id}"))
                if current is not None:
                    body = current.json()
                    content = body["content"] + f"\n\nSoak marker {iteration} at {datetime.now(UTC).isoformat()}. " * 20
                    saved = await measured(
                        "chapter.save",
                        client.put(
                            f"/stories/chapters/{probe_id}",
                            json={"content": content, "expected_revision": body["revision"]},
                            headers={"X-CSRF-Token": csrf},
                        ),
                    )
                    if saved is not None and saved.status_code not in (200, 409):
                        errors.append(f"chapter.save: unexpected HTTP {saved.status_code}")

            await asyncio.sleep(max(0.1, min(args.interval, deadline - time.monotonic())))

    elapsed = time.monotonic() - started
    summary = {
        "started_at": datetime.fromtimestamp(time.time() - elapsed, UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "requested_minutes": args.minutes,
        "elapsed_seconds": round(elapsed, 1),
        "interval_seconds": args.interval,
        "save_every_seconds": args.save_every,
        "counts": dict(counts),
        "latency_ms": {
            name: {
                "p50": percentile(values, 0.50),
                "p95": percentile(values, 0.95),
                "max": round(max(values), 1) if values else 0.0,
                "n": len(values),
            }
            for name, values in latencies.items()
        },
        "errors": errors,
    }
    out = args.output if args.output.is_absolute() else Path.cwd() / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))