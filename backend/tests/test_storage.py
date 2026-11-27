from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update

from app.models.app_models import User
from app.models.job_models import Job
from app.models.story_models import Chapter, Story


async def _story_with_chapter(client, title="Storage story"):
    story = (await client.post("/stories", json={"title": title})).json()
    chapter = (
        await client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Chapter one", "content": "Words that take up storage."},
        )
    ).json()
    return story, chapter


async def _user(session, email="writer@example.com"):
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


async def test_storage_report_reports_counts_tables_and_retention(user_client):
    await _story_with_chapter(user_client)

    response = await user_client.get("/system/storage")
    assert response.status_code == 200
    body = response.json()
    assert body["database_size_bytes"] > 0
    assert {row["name"] for row in body["tables"]} >= {"stories", "story_chapters", "story_chunks"}
    assert body["counts"]["stories"] == 1
    assert body["counts"]["chapters"] == 1
    assert body["counts"]["trashed_chapters"] == 0
    assert body["trash_retention_days"] == 30
    assert body["finished_jobs_retention_days"] == 30
    assert body["expired"]["chapters"] == 0
    assert "api_key" not in str(body).lower()


async def test_cleanup_removes_only_expired_owned_rows(user_client, session):
    _story, chapter = await _story_with_chapter(user_client)
    assert (await user_client.delete(f"/stories/chapters/{chapter['id']}")).status_code == 200

    old = datetime.now(UTC) - timedelta(days=31)
    await session.execute(
        update(Chapter).where(Chapter.id == UUID(chapter["id"])).values(deleted_at=old)
    )
    user = await _user(session)
    old_job = Job(
        owner_id=user.id,
        type="reindex_chapter",
        payload={"chapter_id": chapter["id"]},
        status="succeeded",
        attempts=1,
        max_attempts=3,
        created_at=old,
        updated_at=old,
    )
    session.add(old_job)
    await session.commit()
    old_job_id = old_job.id

    report = (await user_client.get("/system/storage")).json()
    assert report["counts"]["trashed_chapters"] == 1
    assert report["expired"]["chapters"] == 1
    assert report["expired"]["jobs"] == 1

    cleaned = await user_client.post("/system/storage/cleanup")
    assert cleaned.status_code == 200
    assert cleaned.json() == {"stories_deleted": 0, "chapters_deleted": 1, "jobs_deleted": 1}
    assert (await user_client.get("/trash")).json()["chapters"] == []
    assert await session.scalar(select(Job).where(Job.id == old_job_id)) is None

    again = await user_client.post("/system/storage/cleanup")
    assert again.json() == {"stories_deleted": 0, "chapters_deleted": 0, "jobs_deleted": 0}


async def test_cleanup_removes_an_expired_story(user_client, session):
    story, _chapter = await _story_with_chapter(user_client)
    assert (await user_client.delete(f"/stories/{story['id']}")).status_code == 204
    old = datetime.now(UTC) - timedelta(days=31)
    await session.execute(
        update(Story).where(Story.id == UUID(story["id"])).values(deleted_at=old)
    )
    await session.execute(
        update(Chapter).where(Chapter.story_id == UUID(story["id"])).values(deleted_at=old)
    )
    await session.commit()

    cleaned = await user_client.post("/system/storage/cleanup")
    assert cleaned.status_code == 200
    assert cleaned.json()["stories_deleted"] == 1
    assert (await user_client.get("/trash")).json()["stories"] == []
    assert await session.scalar(select(func.count()).select_from(Story)) == 0


async def test_cleanup_does_not_touch_another_account(user_client, make_client, session):
    _story, chapter = await _story_with_chapter(user_client)
    await user_client.delete(f"/stories/chapters/{chapter['id']}")
    old = datetime.now(UTC) - timedelta(days=31)
    await session.execute(
        update(Chapter).where(Chapter.id == UUID(chapter["id"])).values(deleted_at=old)
    )
    await session.commit()

    stranger = await make_client("stranger", "stranger@example.com")
    stranger_story, stranger_chapter = await _story_with_chapter(stranger, "Other story")
    await stranger.delete(f"/stories/chapters/{stranger_chapter['id']}")
    await session.execute(
        update(Chapter)
        .where(Chapter.id == UUID(stranger_chapter["id"]))
        .values(deleted_at=old)
    )
    await session.commit()

    assert (await stranger.get("/system/storage")).json()["counts"]["stories"] == 1
    await user_client.post("/system/storage/cleanup")

    # The other account still sees its chapter in trash and its row still exists.
    assert [row["id"] for row in (await stranger.get("/trash")).json()["chapters"]] == [
        stranger_chapter["id"]
    ]
    assert await session.scalar(
        select(func.count()).select_from(Chapter).where(Chapter.id == UUID(stranger_chapter["id"]))
    ) == 1
    assert stranger_story["id"]


async def test_storage_requires_authentication(client):
    assert (await client.get("/system/storage")).status_code == 401
    assert (await client.post("/system/storage/cleanup")).status_code == 401