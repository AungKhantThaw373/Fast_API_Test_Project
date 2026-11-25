"""Durable job queue: dedupe, claim, retry, recovery, and the worker loop."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.models.job_models import Job
from app.services import indexing
from app.services import jobs as jobs_service


async def _queued(session, dedupe_key: str) -> Job | None:
    return await session.scalar(
        select(Job).where(Job.dedupe_key == dedupe_key, Job.status == "queued")
    )


async def test_enqueue_dedupes_an_active_job(session):
    first = await jobs_service.enqueue(
        session, "reindex_chapter", {"chapter_id": "a"}, dedupe_key="chapter:a"
    )
    second = await jobs_service.enqueue(
        session, "reindex_chapter", {"chapter_id": "a"}, dedupe_key="chapter:a"
    )
    assert first is not None
    # The second call moves the existing row's run time instead of adding a row.
    assert second == first
    rows = list(await session.scalars(select(Job).where(Job.dedupe_key == "chapter:a")))
    assert len(rows) == 1

    # Once it is running, an identical enqueue is dropped entirely.
    claimed = await jobs_service.claim_next(session, "worker-1")
    assert claimed is not None
    assert (
        await jobs_service.enqueue(
            session, "reindex_chapter", {"chapter_id": "a"}, dedupe_key="chapter:a"
        )
        is None
    )


async def test_cancel_stops_a_queued_job_and_flags_a_running_one(session):
    job_id = await jobs_service.enqueue(session, "continuity_scan", {})
    assert job_id is not None
    cancelled = await jobs_service.request_cancel(session, job_id)
    assert cancelled is not None and cancelled.status == "cancelled"

    running_id = await jobs_service.enqueue(session, "continuity_scan", {})
    assert running_id is not None
    claimed = await jobs_service.claim_next(session, "worker-1")
    assert claimed is not None and claimed.id == running_id
    assert await jobs_service.is_cancel_requested(session, claimed.id) is False
    await jobs_service.request_cancel(session, claimed.id)
    assert await jobs_service.is_cancel_requested(session, claimed.id) is True
    await jobs_service.record_cancelled(session, claimed.id)
    stored = await session.get(Job, claimed.id)
    assert stored is not None and stored.status == "cancelled"


async def test_enqueue_creates_a_new_job_after_the_first_finishes(session):
    await jobs_service.enqueue(session, "reindex_chapter", {}, dedupe_key="chapter:b")
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None
    await jobs_service.record_success(session, job.id)

    again = await jobs_service.enqueue(
        session, "reindex_chapter", {}, dedupe_key="chapter:b"
    )
    assert again is not None
    assert again != job.id


async def test_claim_marks_running_and_counts_the_attempt(session):
    await jobs_service.enqueue(session, "reindex_chapter", {"chapter_id": "c"})
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None
    assert job.status == "running"
    assert job.locked_by == "worker-1"
    assert job.attempts == 1
    assert job.locked_at is not None
    # Nothing else is queued.
    assert await jobs_service.claim_next(session, "worker-1") is None


async def test_two_workers_claim_different_jobs(session):
    await jobs_service.enqueue(session, "reindex_chapter", {"chapter_id": "one"})
    await jobs_service.enqueue(session, "reindex_chapter", {"chapter_id": "two"})

    first = await jobs_service.claim_next(session, "worker-1")
    second = await jobs_service.claim_next(session, "worker-2")
    assert first is not None and second is not None
    assert first.id != second.id
    assert {first.locked_by, second.locked_by} == {"worker-1", "worker-2"}


async def test_failure_retries_with_backoff_then_goes_dead(session):
    await jobs_service.enqueue(
        session, "reindex_chapter", {"chapter_id": "d"}, max_attempts=2
    )
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None

    status = await jobs_service.record_failure(session, job.id, RuntimeError("ollama down"))
    assert status == "queued"
    retried = await session.get(Job, job.id)
    await session.refresh(retried)
    assert retried.run_at > datetime.now(UTC)
    assert "ollama down" in (retried.last_error or "")

    # Make it due again and fail the final attempt.
    await session.execute(
        update(Job).where(Job.id == job.id).values(run_at=datetime.now(UTC))
    )
    await session.commit()
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None
    assert job.attempts == 2
    status = await jobs_service.record_failure(session, job.id, RuntimeError("still down"))
    assert status == "dead"
    dead = await session.get(Job, job.id)
    await session.refresh(dead)
    assert dead.status == "dead"
    assert dead.locked_by is None


async def test_superseded_job_is_requeued(session):
    await jobs_service.enqueue(
        session, "reindex_chapter", {"chapter_id": "e"}, max_attempts=2
    )
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None
    assert await jobs_service.requeue_superseded(session, job.id) == "queued"
    requeued = await session.get(Job, job.id)
    await session.refresh(requeued)
    assert requeued.run_at > datetime.now(UTC)


async def test_recover_stuck_resets_an_abandoned_running_job(session):
    await jobs_service.enqueue(session, "reindex_chapter", {"chapter_id": "f"})
    job = await jobs_service.claim_next(session, "worker-1")
    assert job is not None
    # A fresh lock is respected.
    assert await jobs_service.recover_stuck(session) == 0

    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(locked_at=datetime.now(UTC) - timedelta(minutes=20))
    )
    await session.commit()
    assert await jobs_service.recover_stuck(session) == 1
    recovered = await session.get(Job, job.id)
    await session.refresh(recovered)
    assert recovered.status == "queued"
    assert recovered.locked_by is None


async def test_heartbeat_marks_the_worker_alive(session):
    assert await jobs_service.worker_is_alive(session) is False
    await jobs_service.heartbeat(session, "worker-1")
    assert await jobs_service.worker_is_alive(session) is True


async def test_saving_a_chapter_enqueues_one_reindex_job(user_client, session):
    story = (await user_client.post("/stories", json={"title": "Queue me"})).json()
    chapter = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "One", "content": "First draft."},
        )
    ).json()

    for content in ("Second draft.", "Third draft."):
        revision = (
            await user_client.get(f"/stories/chapters/{chapter['id']}")
        ).json()["revision"]
        response = await user_client.put(
            f"/stories/chapters/{chapter['id']}",
            json={"content": content, "expected_revision": revision},
        )
        assert response.status_code == 200

    jobs = list(
        await session.scalars(
            select(Job).where(Job.dedupe_key == f"chapter:{chapter['id']}")
        )
    )
    assert len(jobs) == 1
    assert jobs[0].type == "reindex_chapter"
    assert jobs[0].status == "queued"
    assert jobs[0].payload["chapter_id"] == chapter["id"]


async def test_job_status_is_owned(user_client, make_client, session):
    job = await jobs_service.enqueue(
        session,
        "reindex_chapter",
        {"chapter_id": "x"},
        owner_id=UUID((await user_client.get("/me")).json()["id"]),
    )
    assert job is not None

    response = await user_client.get(f"/jobs/{job}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    intruder = await make_client("mallory", "mallory@example.com")
    assert (await intruder.get(f"/jobs/{job}")).status_code == 404


async def test_worker_once_drains_the_queue(user_client, session, monkeypatch):
    def fake_embed(texts):
        return [[1.0] + [0.0] * 767 for _text in texts]

    monkeypatch.setattr(indexing, "embed_texts", fake_embed)

    story = (await user_client.post("/stories", json={"title": "Worker"})).json()
    chapter = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "One", "content": "A short scene."},
        )
    ).json()

    # Make the queued reindex due immediately instead of after the debounce.
    await session.execute(
        update(Job)
        .where(Job.dedupe_key == f"chapter:{chapter['id']}")
        .values(run_at=datetime.now(UTC))
    )
    await session.commit()

    from app.worker import run_worker

    await run_worker(once=True)

    session.expire_all()
    done = await session.scalar(
        select(Job).where(Job.dedupe_key == f"chapter:{chapter['id']}")
    )
    assert done is not None
    assert done.status == "succeeded"
    assert done.attempts == 1

    status = (await user_client.get(f"/stories/chapters/{chapter['id']}/status")).json()
    assert status["index_status"] == "indexed"


@pytest.mark.parametrize("status", ["succeeded", "dead"])
async def test_counts_by_status_reports_every_bucket(session, status):
    job_id = await jobs_service.enqueue(session, "reindex_chapter", {})
    assert job_id is not None
    claimed = await jobs_service.claim_next(session, "worker-1")
    assert claimed is not None
    await jobs_service.record_success(session, claimed.id)
    counts = await jobs_service.counts_by_status(session)
    assert counts[status] == (1 if status == "succeeded" else 0)
