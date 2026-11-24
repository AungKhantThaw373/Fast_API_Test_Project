from datetime import UTC, datetime, timedelta

from app.services.trash import purge_expired_trash


async def _story_with_chapter(client, content="Recoverable prose."):
    story = (await client.post("/stories", json={"title": "Trash story"})).json()
    chapter = (
        await client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Delete me", "content": content},
        )
    ).json()
    return story, chapter


async def test_deleted_chapter_leaves_the_story_but_stays_in_trash(user_client):
    story, chapter = await _story_with_chapter(user_client)

    response = await user_client.delete(f"/stories/chapters/{chapter['id']}")
    assert response.status_code == 200
    assert response.json()["chapters"] == []

    trash = (await user_client.get("/trash")).json()
    assert [row["id"] for row in trash["chapters"]] == [chapter["id"]]
    assert trash["chapters"][0]["title"] == "Delete me"
    assert trash["retention_days"] == 30

    # Deleted chapters are invisible to the normal API.
    assert (await user_client.get(f"/stories/chapters/{chapter['id']}")).status_code == 404


async def test_restore_brings_the_text_back(user_client):
    _story, chapter = await _story_with_chapter(user_client, content="The exact words.")
    await user_client.delete(f"/stories/chapters/{chapter['id']}")

    restored = await user_client.post(f"/trash/chapters/{chapter['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["chapter"]["chapter_number"] == 1

    reopened = await user_client.get(f"/stories/chapters/{chapter['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["content"] == "The exact words."


async def test_restore_renumbers_when_the_number_is_taken(user_client):
    story, first = await _story_with_chapter(user_client)
    second = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Second", "content": "Second body"},
        )
    ).json()
    assert second["chapter_number"] == 2

    # Trash chapter 2, then add a new chapter that takes number 2.
    await user_client.delete(f"/stories/chapters/{second['id']}")
    third = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Third", "content": "Third body"},
        )
    ).json()
    assert third["chapter_number"] == 2

    restored = (
        await user_client.post(f"/trash/chapters/{second['id']}/restore")
    ).json()
    assert restored["renumbered_from"] == 2
    assert restored["chapter"]["chapter_number"] == 3


async def test_permanent_delete_removes_the_chapter(user_client):
    _story, chapter = await _story_with_chapter(user_client)
    await user_client.delete(f"/stories/chapters/{chapter['id']}")

    assert (await user_client.delete(f"/trash/chapters/{chapter['id']}")).status_code == 204
    assert (await user_client.get("/trash")).json()["chapters"] == []
    assert (await user_client.post(f"/trash/chapters/{chapter['id']}/restore")).status_code == 404


async def test_story_trash_and_restore(user_client):
    story, chapter = await _story_with_chapter(user_client)

    assert (await user_client.delete(f"/stories/{story['id']}")).status_code == 204
    assert (await user_client.get(f"/stories/{story['id']}")).status_code == 404
    assert (await user_client.get("/stories")).json()["stories"] == []

    trash = (await user_client.get("/trash")).json()
    assert [row["id"] for row in trash["stories"]] == [story["id"]]
    assert trash["stories"][0]["chapter_count"] == 1

    restored = await user_client.post(f"/trash/stories/{story['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["restored_chapters"] == 1

    reopened = await user_client.get(f"/stories/{story['id']}")
    assert reopened.status_code == 200
    assert len(reopened.json()["chapters"]) == 1
    assert reopened.json()["chapters"][0]["id"] == chapter["id"]


async def test_chapter_restore_is_refused_while_the_story_is_trashed(user_client):
    story, chapter = await _story_with_chapter(user_client)
    await user_client.delete(f"/stories/{story['id']}")
    response = await user_client.post(f"/trash/chapters/{chapter['id']}/restore")
    assert response.status_code == 409


async def test_purge_respects_the_cutoff(user_client, session):
    _story, chapter = await _story_with_chapter(user_client)
    await user_client.delete(f"/stories/chapters/{chapter['id']}")

    # Not old enough: nothing is purged.
    assert await purge_expired_trash(session) == {"stories": 0, "chapters": 0}
    await session.commit()

    later = datetime.now(UTC) + timedelta(days=31)
    purged = await purge_expired_trash(session, now=later)
    await session.commit()
    assert purged["chapters"] == 1
    assert (await user_client.get("/trash")).json()["chapters"] == []


async def test_another_user_cannot_see_or_restore_your_trash(make_client, user_client):
    _story, chapter = await _story_with_chapter(user_client)
    await user_client.delete(f"/stories/chapters/{chapter['id']}")

    stranger = await make_client("stranger2", "stranger2@example.com")
    assert (await stranger.get("/trash")).json()["chapters"] == []
    assert (
        await stranger.post(f"/trash/chapters/{chapter['id']}/restore")
    ).status_code == 404
