from uuid import UUID

from sqlalchemy import select

from app.models.job_models import Job
from app.models.story_models import Chapter
from app.services.indexing import reconcile_indexing_state


async def test_stuck_indexing_chapter_is_reset_and_queued(user_client, session):
    story = (await user_client.post("/stories", json={"title": "Crashy"})).json()
    chapter = (
        await user_client.post(
            f"/stories/{story['id']}/chapters", json={"title": "One", "content": "Text."}
        )
    ).json()

    # Simulate a crash mid-index: the row is left in the transient state.
    row = await session.get(Chapter, UUID(chapter["id"]))
    assert row is not None
    row.index_status = "indexing"
    row.index_error = "worker died"
    await session.commit()

    summary = await reconcile_indexing_state()
    assert summary["reset"] == 1

    session.expire_all()
    refreshed = await session.scalar(
        select(Chapter).where(Chapter.id == UUID(chapter["id"]))
    )
    assert refreshed is not None
    assert refreshed.index_status == "pending"
    assert refreshed.index_error is None

    job = await session.scalar(
        select(Job).where(
            Job.type == "reindex_chapter",
            Job.dedupe_key == f"chapter:{chapter['id']}",
            Job.status == "queued",
        )
    )
    assert job is not None


async def test_reconciliation_is_quiet_when_nothing_is_stuck(user_client):
    assert await reconcile_indexing_state() == {"reset": 0, "queued": 0}


async def test_system_status_reports_the_environment(user_client):
    status = (await user_client.get("/system/status")).json()
    assert status["database"] == "ok"
    assert status["pgvector"].startswith("ok")
    assert status["schema"] == "ok"
    # No worker runs during tests.
    assert status["worker"] == "offline"
    assert status["pending_chapters"] >= 0
    assert status["failed_chapters"] >= 0
    assert status["running_jobs"] == 0
