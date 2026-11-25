"""Durable worker: claims jobs from Postgres and runs them.

Run exactly one worker next to the API process:

```bash
uv run python -m app.worker          # serve forever
uv run python -m app.worker --once   # drain the queue and exit (CI, tests)
```

One worker with a concurrency of one is the correct default for a 6 GB GPU: two
models cannot be resident at once. Scaling out means more VRAM, not more rows.

Worker connections raise the statement timeout to 5 minutes because a bulk
reindex or a slow provider call is legitimately long. ``STATEMENT_TIMEOUT_MS``
has to be set before ``app.db`` is imported, so it sits above the imports below.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID

os.environ.setdefault("STATEMENT_TIMEOUT_MS", "300000")

from app.db import async_session, engine  # noqa: E402
from app.logging_config import configure_app_logging, fields, get_logger  # noqa: E402
from app.models.job_models import Job  # noqa: E402
from app.services import indexing  # noqa: E402
from app.services import jobs as jobs_service  # noqa: E402

logger = get_logger("worker")

POLL_INTERVAL_SECONDS = 2.0
HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_CONCURRENT_JOBS = 1


async def _run_reindex(payload: dict[str, Any]) -> str:
    chapter_id = UUID(str(payload.get("chapter_id")))
    raw_job_id = payload.get("job_id")
    return await indexing.reindex_chapter(
        chapter_id, UUID(str(raw_job_id)) if raw_job_id else None
    )


async def _run_bible_scan(payload: dict[str, Any]) -> str:
    chapter_id = UUID(str(payload.get("chapter_id")))
    revision = payload.get("revision")
    expected = int(revision) if revision is not None else None
    return await indexing.extract_story_bible(chapter_id, expected)


HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[str]]] = {
    "reindex_chapter": _run_reindex,
    "bible_scan": _run_bible_scan,
}


async def run_job(job: Job) -> str:
    """Execute one claimed job and record its outcome. Never raises."""
    handler = HANDLERS.get(job.type)
    started = time.monotonic()
    async with async_session() as session:
        if handler is None:
            logger.warning(
                "[jobs] unknown %s", fields(job=str(job.id)[:8], type=job.type)
            )
            await jobs_service.record_success(
                session, job.id, note=f"no handler for {job.type}"
            )
            return "unknown"
        try:
            payload = dict(job.payload or {})
            payload.setdefault("job_id", str(job.id))
            outcome = await handler(payload)
        except Exception as exc:
            status = await jobs_service.record_failure(session, job.id, exc)
            logger.warning(
                "[jobs] failed %s",
                fields(
                    job=str(job.id)[:8],
                    type=job.type,
                    status=status,
                    attempts=job.attempts,
                    error=f"{type(exc).__name__}: {exc}"[:300],
                    elapsed=f"{time.monotonic() - started:.2f}s",
                ),
            )
            return status
        if outcome == indexing.SUPERSEDED:
            status = await jobs_service.requeue_superseded(session, job.id)
            logger.info(
                "[jobs] requeue %s",
                fields(job=str(job.id)[:8], type=job.type, status=status),
            )
            return status
        await jobs_service.record_success(session, job.id)
        logger.info(
            "[jobs] done   %s",
            fields(
                job=str(job.id)[:8],
                type=job.type,
                outcome=outcome,
                elapsed=f"{time.monotonic() - started:.2f}s",
            ),
        )
        return outcome


async def _claim(worker: str) -> Job | None:
    async with async_session() as session:
        return await jobs_service.claim_next(session, worker)


async def _heartbeat_loop(worker: str, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with async_session() as session:
                await jobs_service.heartbeat(session, worker)
        except Exception:  # pragma: no cover - depends on a broken database
            logger.exception("[jobs] heartbeat failed")
        await _sleep_or_stop(stop_event, HEARTBEAT_INTERVAL_SECONDS)


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)


async def _recover(worker: str) -> int:
    async with async_session() as session:
        recovered = await jobs_service.recover_stuck(session)
        await jobs_service.heartbeat(session, worker)
    return recovered


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows event loops do not support add_signal_handler.
            try:
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop_event.set))
            except (ValueError, OSError):  # pragma: no cover - platform specific
                continue


async def run_worker(*, once: bool = False) -> None:
    worker = jobs_service.current_worker_id()
    recovered = await _recover(worker)
    logger.info("[jobs] start  %s", fields(worker=worker, recovered=recovered, once=once))

    stop_event = asyncio.Event()
    if not once:
        _install_signal_handlers(stop_event)
    heartbeat = asyncio.create_task(_heartbeat_loop(worker, stop_event))
    in_flight: set[asyncio.Task] = set()

    try:
        while not stop_event.is_set():
            if len(in_flight) < MAX_CONCURRENT_JOBS:
                job = await _claim(worker)
                if job is not None:
                    task = asyncio.create_task(run_job(job))
                    in_flight.add(task)
                    task.add_done_callback(in_flight.discard)
                    continue
            if not in_flight:
                if once:
                    break
                await _sleep_or_stop(stop_event, POLL_INTERVAL_SECONDS)
                continue
            await asyncio.wait(
                set(in_flight),
                timeout=POLL_INTERVAL_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
    finally:
        stop_event.set()
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
        if in_flight:
            # Finish the job in hand instead of leaving a row locked for 15 minutes.
            await asyncio.gather(*in_flight, return_exceptions=True)
        async with async_session() as session:
            await jobs_service.forget_worker(session, worker)
        logger.info("[jobs] stop   %s", fields(worker=worker))
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stillroom background worker")
    parser.add_argument(
        "--once", action="store_true", help="drain the queue, then exit"
    )
    args = parser.parse_args(argv)
    configure_app_logging()
    asyncio.run(run_worker(once=args.once))
    return 0


if __name__ == "__main__":
    sys.exit(main())
