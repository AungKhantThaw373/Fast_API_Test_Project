"""Queue, claim, and finish durable jobs.

Claiming relies on ``FOR UPDATE SKIP LOCKED``: two workers can poll the same
table and never take the same row. Dedupe keys collapse repeated enqueues onto a
single active row, so a burst of autosaves still produces one reindex.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import CursorResult, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_models import Job, WorkerHeartbeat

# A running job whose lock is older than this was abandoned by a crashed worker.
STUCK_AFTER = timedelta(minutes=15)
BACKOFF_SECONDS = (5, 15, 45)
SUPERSEDED_DELAY_SECONDS = 5
HEARTBEAT_FRESH_SECONDS = 60

ACTIVE_STATUSES = ("queued", "running")


def current_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def enqueue(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any],
    *,
    owner_id: UUID | None = None,
    dedupe_key: str | None = None,
    delay_seconds: float = 0.0,
    max_attempts: int = 3,
) -> UUID | None:
    """Insert a job, or move the matching queued job's `run_at` forward.

    Returns the job id, or ``None`` when an identical job is already running.
    """
    run_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    statement = (
        insert(Job)
        .values(
            id=uuid4(),
            owner_id=owner_id,
            type=job_type,
            payload=payload,
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
            dedupe_key=dedupe_key,
            run_at=run_at,
            progress={},
        )
        .on_conflict_do_update(
            index_elements=["type", "dedupe_key"],
            index_where=text("dedupe_key IS NOT NULL AND status IN ('queued', 'running')"),
            set_={"run_at": run_at, "updated_at": func.now()},
            where=Job.status == "queued",
        )
        .returning(Job.id)
    )
    job_id = await session.scalar(statement)
    await session.commit()
    return job_id


async def claim_next(session: AsyncSession, worker: str) -> Job | None:
    next_id = (
        select(Job.id)
        .where(Job.status == "queued", Job.run_at <= func.now())
        .order_by(Job.run_at, Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
        .scalar_subquery()
    )
    statement = (
        update(Job)
        .where(Job.id == next_id)
        .values(
            status="running",
            locked_at=func.now(),
            locked_by=worker,
            attempts=Job.attempts + 1,
            updated_at=func.now(),
        )
        .returning(Job.id)
        .execution_options(synchronize_session=False)
    )
    job_id = await session.scalar(statement)
    await session.commit()
    if job_id is None:
        return None
    return await session.scalar(
        select(Job)
        .where(Job.id == job_id)
        .execution_options(populate_existing=True)
    )


async def set_progress(
    session: AsyncSession, job_id: UUID, progress: dict[str, Any]
) -> None:
    await session.execute(
        update(Job).where(Job.id == job_id).values(progress=progress, updated_at=func.now())
    )
    await session.commit()


async def record_success(
    session: AsyncSession, job_id: UUID, *, note: str | None = None
) -> None:
    progress: dict[str, Any] = {"stage": "done"}
    if note:
        progress["note"] = note
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status="succeeded",
            locked_at=None,
            locked_by=None,
            last_error=None,
            progress=progress,
            updated_at=func.now(),
        )
    )
    await session.commit()


async def record_failure(session: AsyncSession, job_id: UUID, error: BaseException) -> str:
    """Retry with backoff, or bury the job as ``dead`` once attempts run out."""
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        return "missing"
    job.last_error = f"{type(error).__name__}: {error}"[:4000]
    if job.attempts >= job.max_attempts:
        job.status = "dead"
    else:
        job.status = "queued"
        job.run_at = datetime.now(UTC) + timedelta(seconds=_backoff(job.attempts))
    job.locked_at = None
    job.locked_by = None
    await session.commit()
    return job.status


async def requeue_superseded(session: AsyncSession, job_id: UUID) -> str:
    """The work was overtaken by a newer revision; run it again shortly."""
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        return "missing"
    if job.attempts >= job.max_attempts:
        job.status = "succeeded"
        job.progress = {"stage": "done", "note": "superseded"}
    else:
        job.status = "queued"
        job.run_at = datetime.now(UTC) + timedelta(seconds=SUPERSEDED_DELAY_SECONDS)
    job.locked_at = None
    job.locked_by = None
    await session.commit()
    return job.status


def _backoff(attempts: int) -> int:
    index = min(max(attempts - 1, 0), len(BACKOFF_SECONDS) - 1)
    return BACKOFF_SECONDS[index]


async def recover_stuck(session: AsyncSession) -> int:
    """Reset jobs abandoned by a crashed worker."""
    result = await session.execute(
        update(Job)
        .where(
            Job.status == "running",
            or_(
                Job.locked_at.is_(None),
                Job.locked_at < text("now() - interval '15 minutes'"),
            ),
        )
        .values(status="queued", locked_at=None, locked_by=None, updated_at=func.now())
    )
    await session.commit()
    assert isinstance(result, CursorResult)
    return int(result.rowcount or 0)


async def heartbeat(session: AsyncSession, worker: str) -> None:
    """Mark this worker alive and extend the lock on jobs it is running."""
    await session.execute(
        insert(WorkerHeartbeat)
        .values(worker_id=worker)
        .on_conflict_do_update(
            index_elements=["worker_id"],
            set_={"heartbeat_at": func.now()},
        )
    )
    await session.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_by == worker)
        .values(locked_at=func.now())
    )
    await session.commit()


async def forget_worker(session: AsyncSession, worker: str) -> None:
    await session.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_by == worker)
        .values(status="queued", locked_at=None, locked_by=None, updated_at=func.now())
    )
    await session.execute(
        delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker)
    )
    await session.commit()


async def latest_heartbeat(session: AsyncSession) -> datetime | None:
    return await session.scalar(select(func.max(WorkerHeartbeat.heartbeat_at)))


async def worker_is_alive(session: AsyncSession) -> bool:
    last = await latest_heartbeat(session)
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return datetime.now(UTC) - last <= timedelta(seconds=HEARTBEAT_FRESH_SECONDS)


async def counts_by_status(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Job.status, func.count(Job.id)).group_by(Job.status))
    counts = {status: 0 for status in ("queued", "running", "succeeded", "failed", "dead")}
    for status, count in rows:
        counts[str(status)] = int(count)
    return counts


async def owned_job(session: AsyncSession, job_id: UUID, user_id: UUID) -> Job:
    job = await session.scalar(
        select(Job).where(Job.id == job_id, Job.owner_id == user_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job
